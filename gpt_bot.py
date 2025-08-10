#!/usr/bin/env python3
import os
import tempfile
import requests
import logging
import os
import requests
from dotenv import load_dotenv
from pydub import AudioSegment
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.ext.filters import Document
from collections import defaultdict, deque
from telegram.ext import CommandHandler

# переменные инициализируются позже
TELEGRAM_TOKEN = None
OPENAI_API_KEY = None
DEFAULT_MODEL = None
GOOGLE_CSE_API_KEY = None
GOOGLE_CSE_CX = None
client = None
current_model = None
user_histories = {}

ADMINS = {1091992386, 1687504544} 
LIMITED_USERS = {111111111, 222222222, 333333333} 
CHAT_ID = -1001785925671
BOT_USERNAME = "DunaevAssistentBot"
chat_history = defaultdict(lambda: deque(maxlen=100))

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 🔇 Отключаем лишние логи от сторонних библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.INFO)
logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)
logging.getLogger("telegram.request").setLevel(logging.INFO)

# --------------------
# Helpers
# --------------------
def init_env():
    global TELEGRAM_TOKEN, OPENAI_API_KEY, DEFAULT_MODEL, GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX, client, current_model
    
    # --------------------
    # Env & clients
    # --------------------
    load_dotenv()
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo") 
    GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
    GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX")

    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        raise RuntimeError("TELEGRAM_TOKEN или OPENAI_API_KEY не заданы в .env")

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    current_model = DEFAULT_MODEL

def format_exc(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_allowed(update: Update) -> bool:
    user_id = update.effective_user.id
    chat = update.effective_chat
    message = update.message

    text = message.text or message.caption or ""
    logging.info(f"[{user_id}] - chat_id: {chat.id} - type: {chat.type} - Text: {text}")
 # Если пользователь — админ, всегда разрешаем
    if chat.type == "private" and user_id in ADMINS:
        return True

    if chat.id == CHAT_ID and chat.type in ("group", "supergroup"):
        # 1. Упоминание
        if BOT_USERNAME.lower() in text.lower():
            return True
        # 2. Ответ на сообщение бота
        if message.reply_to_message and message.reply_to_message.from_user.username == BOT_USERNAME:
            return True
    
    return False

def google_search(query: str, num_results: int = 5):
    """
    Выполняет поиск в Google с помощью Custom Search API.
    
    :param query: строка поиска
    :param num_results: сколько результатов вернуть (1-10)
    :return: список строк "Заголовок - Ссылка"
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        raise RuntimeError("Google API ключ или CX не заданы в .env")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "num": num_results
    }

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("items", []):
        title = item.get("title", "Без названия")
        link = item.get("link", "")
        snippet = item.get("snippet", "")
        results.append(f"{title}\n{snippet}\n{link}")

    return results
# --------------------
# Handlers
# --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    base = "Привет! Я Telegram-ассистент с поддержкой текста и голосовых сообщений.\n\n"
    common_cmds = "Команды:\n/start — приветствие\n/help — помощь"
    if is_admin(user_id):
        extra = "\n/model <name> — сменить модель\n/quota — показать остаток бюджета OpenAI API"
        await update.message.reply_text(base + common_cmds + extra)
    else:
        await update.message.reply_text(base + common_cmds)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
         return
    user_id = update.effective_user.id
    base = "Доступные команды:\n/start — приветствие\n/help — помощь"
    if is_admin(user_id):
        extra = "\n/model <name> — сменить модель\n/quota — показать остаток бюджета OpenAI API"
        await update.message.reply_text(base + extra)
    else:
        await update.message.reply_text(base)

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 У вас нет прав на смену модели.")
        return
    
    global current_model
    if not context.args:
        await update.message.reply_text(
            f"Текущая модель: {current_model}\n"
            "Использование: /model gpt-4o или /model gpt-3.5-turbo"
        )
        return
    new_model = context.args[0].strip()
    current_model = new_model
    await update.message.reply_text(f"✅ Модель установлена: {current_model}")

async def quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 У вас нет прав на смену модели.")
        return
    """Показывает остаток средств по API. Может не работать для некоторых аккаунтов."""
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        r = requests.get(
            "https://api.openai.com/dashboard/billing/credit_grants",
            headers=headers,
            timeout=10,
        )
        if r.status_code != 200:
            await update.message.reply_text(
                f"Не удалось получить квоту (HTTP {r.status_code}): {r.text}"
            )
            return
        data = r.json()
        total = data.get("total_granted", 0.0)
        used = data.get("total_used", 0.0)
        remaining = data.get("total_available", 0.0)
        await update.message.reply_text(
            f"💰 Баланс OpenAI API:\n"
            f"— Выдано: ${total:.2f}\n"
            f"— Использовано: ${used:.2f}\n"
            f"— Остаток: ${remaining:.2f}"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении квоты: {format_exc(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    message = update.message
    chat = update.effective_chat
    user_input = message.text or ""
    user_input = user_input.replace(f"@{BOT_USERNAME}", "").strip()
    user = update.effective_user
    user_id = user.id

    messages = []

    # 💬 Если это reply на сообщение бота с текстом — добавим как контекст
    if chat.type in ("group", "supergroup") and message.reply_to_message:
        reply_msg = message.reply_to_message
        if reply_msg.from_user and reply_msg.from_user.username == BOT_USERNAME:
            prev_text = reply_msg.text or ""
            if prev_text:
                messages.append({"role": "user", "content": prev_text})
    
    if chat.type == "private":
        if user_id not in user_histories:
            user_histories[user_id] = []
        messages = user_histories[user_id]
        messages.append({"role": "user", "content": user_input})
        
    messages.append({"role": "user", "content": user_input})

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - TEXT: {user_input}")
    try:
        resp = client.chat.completions.create(
            model=current_model,
            messages=messages,
        )
        await message.reply_text(resp.choices[0].message.content)
    except Exception as e:
        await message.reply_text(f"❌ Ошибка: {format_exc(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user = update.effective_user
    logging.info(f"[{user.id}] @{user.username or 'no_username'} - VOICE: получено голосовое сообщение")
    try:
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            await voice_file.download_to_drive(f.name)
            ogg_path = f.name

        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")

        # Распознаём речь (Whisper)
        with open(wav_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = transcript.text
        logging.info(f"{user} - VOICE TEXT: {text}")

        # Отвечаем LLM-ом
        resp = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": text}],
        )
        await update.message.reply_text(
            f"🗣️ Ты сказал: {text}\n\n🤖 {resp.choices[0].message.content}"
        )
    except Exception as e:
        logging.error(f"{user} - VOICE ERROR: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка при обработке голосового: {format_exc(e)}")

async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user = update.effective_user
    kind = type(update.message.effective_attachment)
    caption = update.message.caption or "(без подписи)"

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - UNSUPPORTED: {kind} - Caption: {caption}")
    await update.message.reply_text("❌ Извините, я пока не умею обрабатывать файлы, изображения или вложения.")

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Укажи запрос: /search <текст>")
        return
    
    query = " ".join(context.args)
    try:
        results = google_search(query)
        if not results:
            await update.message.reply_text("Ничего не найдено.")
            return
        
        reply_text = "\n\n".join(results)
        await update.message.reply_text(reply_text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка поиска: {e}")

async def debug_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logging.info("RAW UPDATE: %s", update.to_dict())
    except Exception as e:
        logging.exception("Failed to log raw update: %s", e)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.type == "private":
        user_histories.pop(user_id, None)
        await update.message.reply_text("🧹 Контекст очищен.")

# --------------------
# Main
# --------------------
def main():
    init_env()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(CommandHandler("quota", quota))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search_cmd))

    # Сообщения
    #app.add_handler(MessageHandler(filters.ALL, debug_log), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | Document.ALL | filters.VIDEO, handle_unsupported))

 

    logging.info(f"GPT-бот запущен! Текущая модель: {current_model}")
    app.run_polling()
    me = app.bot.get_me()
    logging.info("Bot username:", me.username)

if __name__ == "__main__":
    main()
