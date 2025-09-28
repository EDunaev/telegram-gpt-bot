import logging
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import ContextTypes
from config import client, current_model, ADMINS, BOT_USERNAME
from helpers import is_allowed, format_exc
from search.google import google_search
from search.summarize import summarize_search_results
from .utils import should_web_search

user_histories = defaultdict(lambda: deque(maxlen=5))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    message = update.message
    chat = update.effective_chat
    user = update.effective_user
    user_id = user.id

    raw_text = message.text or ""
    user_input = raw_text.replace(f"@{BOT_USERNAME}", "").strip()

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - TEXT: {user_input}")

    messages = []

    if chat.type in ("group", "supergroup") and message.reply_to_message:
        reply_msg = message.reply_to_message
        if reply_msg.from_user and reply_msg.from_user.username == BOT_USERNAME:
            prev_text = reply_msg.text or ""
            if prev_text:
                messages.append({"role": "user", "content": prev_text})

    if chat.type == "private" and user_id in ADMINS:
        history = user_histories[user_id]
        messages.extend(list(history))
        messages.append({"role": "user", "content": user_input})
    else:
        messages.append({"role": "user", "content": user_input})

    try:
        if should_web_search(user_input):
            logging.info("Запрос в интернете")
            raw_results = google_search(user_input, num_results=8, date_restrict="m6")
            answer_text = summarize_search_results(user_input, raw_results) if raw_results else "Ничего не нашёл по запросу."
        else:
            resp = client.chat.completions.create(
                model=current_model,
                messages=messages
            )
            answer_text = resp.choices[0].message.content

        logging.info(f"[BOT -> {user.id}] Ответ: {answer_text}")
        await message.reply_text(answer_text)

        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            history.append({"role": "assistant", "content": answer_text})

    except Exception as e:
        logging.exception("handle_text error")
        await message.reply_text(f"❌ Ошибка: {format_exc(e)}")
