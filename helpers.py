import logging
from telegram import Update
from config import ADMINS, CHAT_ID, BOT_USERNAME

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

    # Админ в приватке — всегда разрешено
    if chat.type == "private" and user_id in ADMINS:
        return True

    # Группа: если упоминание или reply на бота
    if chat.id == CHAT_ID and chat.type in ("group", "supergroup"):
        if BOT_USERNAME.lower() in text.lower():
            return True
        if message.reply_to_message and message.reply_to_message.from_user.username == BOT_USERNAME:
            return True

    return False
