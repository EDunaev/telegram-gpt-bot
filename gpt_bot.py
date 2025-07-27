#!/usr/bin/env python3
import os
import tempfile
import requests
import logging
from datetime import datetime
from pydub import AudioSegment
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.ext.filters import Document

# --------------------
# Env & clients
# --------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # можно переопределить через .env

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("TELEGRAM_TOKEN или OPENAI_API_KEY не заданы в .env")

client = OpenAI(api_key=OPENAI_API_KEY)
current_model = DEFAULT_MODEL  # будет изменяться командой /model
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# --------------------
# Helpers
# --------------------
def format_exc(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"

# --------------------
# Handlers
# --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я Telegram-ассистент с поддержкой текста и голосовых сообщений.\n\n"
        "Команды:\n"
        "/model <name> — сменить модель (gpt-4o, gpt-3.5-turbo, ...)\n"
        "/quota — показать остаток бюджета OpenAI API\n"
        "/help — помощь"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — приветствие\n"
        "/model <name> — сменить модель (например: /model gpt-3.5-turbo)\n"
        "/quota — показать остаток бюджета OpenAI API\n\n"
        "Просто пришлите текст или голосовое сообщение — я отвечу 🙂"
    )

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_input = update.message.text
    user = update.effective_user

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - TEXT: {user_input}")
    try:
        resp = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": user_input}],
        )
        await update.message.reply_text(resp.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {format_exc(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user = update.effective_user
    kind = type(update.message.effective_attachment)

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - UNSUPPORTED: {kind}")
    await update.message.reply_text("❌ Извините, я пока не умею обрабатывать файлы, изображения или вложения.")


# --------------------
# Main
# --------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(CommandHandler("quota", quota))

    # Сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | Document.ALL | filters.VIDEO | filters.VOICE, handle_unsupported))

    print(f"GPT-бот запущен! Текущая модель: {current_model}")
    app.run_polling()

if __name__ == "__main__":
    main()
