import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from handlers.commands import start, help_cmd, set_model, quota
from handlers.text import handle_text
from handlers.voice import handle_voice
from handlers.unsupported import handle_unsupported
from config import TELEGRAM_TOKEN, current_model

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(CommandHandler("quota", quota))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VIDEO, handle_unsupported))

    logging.info(f"GPT-бот запущен! Текущая модель: {current_model}")
    app.run_polling()

if __name__ == "__main__":
    main()
