#!/usr/bin/env python3
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext.filters import Document
import logging

from config import init_env, TELEGRAM_TOKEN, current_model
from handlers import (
    start, help_cmd, set_model, quota, reset,
    handle_text, handle_voice, handle_unsupported, search_cmd,
    error_handler
)
import logger  # чтобы настроить логирование

def main():
    init_env()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(CommandHandler("quota", quota))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | Document.ALL | filters.VIDEO, handle_unsupported))

    app.add_error_handler(error_handler)

    logging.info(f"GPT-бот запущен! Текущая модель: {current_model}")
    app.run_polling()

if __name__ == "__main__":
    main()
