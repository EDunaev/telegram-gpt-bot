import logging
from telegram import Update
from config import ADMINS, CHAT_ID, BOT_USERNAME

def format_exc(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_allowed(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    message = getattr(update, "message", None)

    user_id = user.id if user else None
    chat_id = chat.id if chat else None
    chat_type = chat.type if chat else None
    text = ""

    if message:
        text = message.text or message.caption or ""

    # ЛОГИРУЕМ ВСЕГДА, даже если апдейт "битый"
    logging.info(f"[{user_id}] - chat_id: {chat_id} - type: {chat_type} - Text: {text}")

    # 1. Приватный чат с админом
    if chat and chat_type == "private" and user_id in ADMINS:
        return True

    # 2. Группы / супергруппы
    if chat and chat_id == CHAT_ID and chat_type in ("group", "supergroup") and message:
        # Упоминание бота
        if BOT_USERNAME.lower() in text.lower():
            return True
        # Ответ на сообщение бота
        if (message.reply_to_message and 
            message.reply_to_message.from_user and 
            message.reply_to_message.from_user.username == BOT_USERNAME):
            return True

    return False

