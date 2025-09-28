import logging
from telegram import Update
from config import ADMINS, CHAT_ID, BOT_USERNAME

def format_exc(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_allowed(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    chat = update.effective_chat
    message = update.message

    text = ""
    if message:
        text = message.text or message.caption or ""

    logging.info(f"[{user_id}] - chat_id: {chat.id} - type: {chat.type} - Text: {text}")

    # 1. Приватный чат с админом — всегда можно
    if chat.type == "private" and user_id in ADMINS:
        return True

    # 2. Группы / супергруппы
    if chat.id == CHAT_ID and chat.type in ("group", "supergroup") and message:
        # Упоминание бота
        if BOT_USERNAME.lower() in text.lower():
            return True
        # Ответ на сообщение бота
        if message.reply_to_message and message.reply_to_message.from_user and \
           message.reply_to_message.from_user.username == BOT_USERNAME:
            return True

    return False
