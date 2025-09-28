import logging
from telegram import Update
from telegram.ext import ContextTypes
from helpers import is_allowed

async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user = update.effective_user
    kind = type(update.message.effective_attachment)
    caption = update.message.caption or "(без подписи)"

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - UNSUPPORTED: {kind} - Caption: {caption}")
    await update.message.reply_text("❌ Извините, я пока не умею обрабатывать файлы, изображения или вложения.")
