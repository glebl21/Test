import os
import hashlib
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import tempfile
from groq import Groq
from collections import defaultdict

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "ВАШ_GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "ВАШ_GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

transcription_store = {}
user_language = {}
stats = defaultdict(int)

LANGUAGES = {
    "🌐 Авто": "auto",
    "🇷🇺 Русский": "ru",
    "🇬🇧 English": "en",
    "🇩🇪 Deutsch": "de",
    "🇫🇷 Français": "fr",
    "🇪🇸 Español": "es",
    "🇺🇦 Українська": "uk",
}

TRANSLATE_LANGUAGES = {
    "🇷🇺 Русский": "русский",
    "🇬🇧 English": "english",
    "🇩🇪 Deutsch": "немецкий",
    "🇫🇷 Français": "французский",
    "🇪🇸 Español": "испанский",
    "🇺🇦 Українська": "украинский",
    "🇨🇳 中文": "китайский",
}


# ─────────────────────────────────────────────
# Утилиты
# ─────────────────────────────────────────────

def store_text(text):
    key = hashlib.md5(text.encode()).hexdigest()[:16]
    transcription_store[key] = text
    return key


def get_text(key):
    return transcription_store.get(key)


def download_telegram_file(file_id):
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"
    response = requests.get(file_url, timeout=60)
    response.raise_for_status()
    return response.content, file_info.file_size


def gemini_request(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def transcribe_audio(audio_bytes, filename="audio.ogg", language=None):
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model="whisper-large-v3",
                language=language if language != "auto" else None,
                response_format="text",
            )
        return transcription.strip()
    finally:
        os.unlink(tmp_path)


def summarize_text(text):
    return gemini_request(
        "Сделай краткое саммари этого текста. "
        "Выдели ключевые мысли и выводы. "
        "Отвечай на том же языке что и текст. "
        "Используй маркированный список (•).\n\n" + text
    )


def retell_text(text, style):
    styles = {
        "short": "Перескажи текст очень кратко — 2-3 предложения. Отвечай на том же языке.",
        "detailed": "Перескажи текст подробно, сохрани все детали и нюансы. Отвечай на том же языке.",
        "bullets": "Перескажи текст по пунктам, каждый пункт с новой строки через •. Отвечай на том же языке.",
    }
    return gemini_request(styles[style] + "\n\n" + text)


def translate_text(text, target_lang):
    return gemini_request(
        f"Переведи следующий текст на {target_lang}. "
        f"Верни только перевод без пояснений.\n\n{text}"
    )


# ─────────────────────────────────────────────
# Клавиатуры
# ─────────────────────────────────────────────

def make_main_keyboard(text_key):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📝 Саммари", callback_data=f"sum:{text_key}"),
        InlineKeyboardButton("🔁 Пересказ", callback_data=f"retell_menu:{text_key}"),
        InlineKeyboardButton("🌐 Перевести", callback_data=f"translate_menu:{text_key}"),
    )
    return kb


def make_retell_keyboard(text_key):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("Кратко", callback_data=f"retell:short:{text_key}"),
        InlineKeyboardButton("Подробно", callback_data=f"retell:detailed:{text_key}"),
        InlineKeyboardButton("По пунктам", callback_data=f"retell:bullets:{text_key}"),
    )
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"back:{text_key}"))
    return kb


def make_translate_keyboard(text_key):
    kb = InlineKeyboardMarkup(row_width=2)
    for label, lang in TRANSLATE_LANGUAGES.items():
        kb.add(InlineKeyboardButton(label, callback_data=f"translate:{lang}:{text_key}"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"back:{text_key}"))
    return kb


def make_language_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    for label, code in LANGUAGES.items():
        kb.add(InlineKeyboardButton(label, callback_data=f"setlang:{code}"))
    return kb


# ─────────────────────────────────────────────
# Команды
# ─────────────────────────────────────────────

@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    bot.reply_to(
        message,
        "🎙️ *Бот-транскрибатор голосовых сообщений*\n\n"
        "Отправь голосовое, кружок или аудиофайл — переведу в текст!\n\n"
        "🔧 *Команды:*\n"
        "• /lang — выбрать язык транскрибации\n"
        "• /stats — моя статистика\n"
        "• /help — помощь",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["lang"])
def handle_lang(message):
    bot.reply_to(
        message,
        "🌍 Выбери язык транскрибации:",
        reply_markup=make_language_keyboard()
    )


@bot.message_handler(commands=["stats"])
def handle_stats(message):
    user_id = message.from_user.id
    count = stats[user_id]
    lang_code = user_language.get(user_id, "auto")
    lang_name = next((k for k, v in LANGUAGES.items() if v == lang_code), "🌐 Авто")
    bot.reply_to(
        message,
        f"📊 *Твоя статистика:*\n\n"
        f"• Обработано сообщений: *{count}*\n"
        f"• Язык транскрибации: *{lang_name}*",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────
# Обработка аудио
# ─────────────────────────────────────────────

def process_audio(message, file_id, filename="audio.ogg"):
    chat_id = message.chat.id
    user_id = message.from_user.id
    status_msg = bot.reply_to(message, "⏳ Транскрибирую...")
    try:
        file_info = bot.get_file(file_id)
        if file_info.file_size and file_info.file_size > 19 * 1024 * 1024:
            bot.edit_message_text(
                "❌ Файл слишком большой. Максимум 20 МБ.",
                chat_id=chat_id, message_id=status_msg.message_id
            )
            return

        audio_bytes, _ = download_telegram_file(file_id)
        lang = user_language.get(user_id, "auto")
        text = transcribe_audio(audio_bytes, filename, lang)

        if not text:
            bot.edit_message_text(
                "❌ Не удалось распознать речь.",
                chat_id=chat_id, message_id=status_msg.message_id
            )
            return

        stats[user_id] += 1
        text_key = store_text(text)

        bot.edit_message_text(
            f"📄 *Транскрипция:*\n\n{text}",
            chat_id=chat_id,
            message_id=status_msg.message_id,
            parse_mode="Markdown",
            reply_markup=make_main_keyboard(text_key)
        )
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id=chat_id, message_id=status_msg.message_id)
        print(f"[ERROR] {e}")


@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    process_audio(message, message.voice.file_id, "voice.ogg")


@bot.message_handler(content_types=["video_note"])
def handle_video_note(message):
    process_audio(message, message.video_note.file_id, "video_note.mp4")


@bot.message_handler(content_types=["audio"])
def handle_audio(message):
    filename = message.audio.file_name or "audio.mp3"
    process_audio(message, message.audio.file_id, filename)


@bot.message_handler(content_types=["document"])
def handle_document(message):
    mime = message.document.mime_type or ""
    if mime.startswith("audio/") or mime in ["video/mp4", "video/webm"]:
        filename = message.document.file_name or "audio.ogg"
        process_audio(message, message.document.file_id, filename)


# ─────────────────────────────────────────────
# Callback кнопок
# ─────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    data = call.data
    try:
        # Саммари
        if data.startswith("sum:"):
            text_key = data.split(":", 1)[1]
            text = get_text(text_key)
            if not text:
                bot.answer_callback_query(call.id, "❌ Отправь голосовое заново.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "⏳ Генерирую саммари...")
            summary = summarize_text(text)
            bot.send_message(call.message.chat.id, f"📝 *Саммари:*\n\n{summary}",
                             parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        # Меню пересказа
        elif data.startswith("retell_menu:"):
            text_key = data.split(":", 1)[1]
            bot.answer_callback_query(call.id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                          reply_markup=make_retell_keyboard(text_key))

        # Пересказ в стиле
        elif data.startswith("retell:"):
            _, style, text_key = data.split(":", 2)
            text = get_text(text_key)
            if not text:
                bot.answer_callback_query(call.id, "❌ Отправь голосовое заново.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "⏳ Пересказываю...")
            result = retell_text(text, style)
            labels = {"short": "кратко", "detailed": "подробно", "bullets": "по пунктам"}
            bot.send_message(call.message.chat.id,
                             f"🔁 *Пересказ ({labels[style]}):*\n\n{result}",
                             parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        # Меню перевода
        elif data.startswith("translate_menu:"):
            text_key = data.split(":", 1)[1]
            bot.answer_callback_query(call.id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                          reply_markup=make_translate_keyboard(text_key))

        # Перевод
        elif data.startswith("translate:"):
            _, lang, text_key = data.split(":", 2)
            text = get_text(text_key)
            if not text:
                bot.answer_callback_query(call.id, "❌ Отправь голосовое заново.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "⏳ Перевожу...")
            result = translate_text(text, lang)
            bot.send_message(call.message.chat.id,
                             f"🌐 *Перевод ({lang}):*\n\n{result}",
                             parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        # Назад
        elif data.startswith("back:"):
            text_key = data.split(":", 1)[1]
            bot.answer_callback_query(call.id)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                          reply_markup=make_main_keyboard(text_key))

        # Установка языка
        elif data.startswith("setlang:"):
            lang_code = data.split(":", 1)[1]
            user_language[call.from_user.id] = lang_code
            lang_name = next((k for k, v in LANGUAGES.items() if v == lang_code), lang_code)
            bot.answer_callback_query(call.id, f"✅ Язык установлен: {lang_name}", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
        print(f"[ERROR] callback: {e}")


if __name__ == "__main__":
    print("🤖 Бот запущен!")
    bot.infinity_polling(timeout=60, long_polling_timeout=60, allowed_updates=["message", "callback_query"])
