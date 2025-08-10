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
from typing import List

# переменные инициализируются позже
TELEGRAM_TOKEN = None
OPENAI_API_KEY = None
DEFAULT_MODEL = None
GOOGLE_CSE_API_KEY = None
GOOGLE_CSE_CX = None
client = None
current_model = None
user_histories = defaultdict(lambda: deque(maxlen=100))

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

def should_web_search(user_input: str) -> bool:
   
    # --- Опционально: уточняем у LLM (удорожает запрос) ---
    decision_prompt = (
         "Определи, нужен ли интернет-поиск. Ответь ровно 'YES' или 'NO'.\n"
         f"Запрос: {user_input}"
    )
    try:
       decision = client.chat.completions.create(
             model=current_model,
             messages=[{"role": "user", "content": decision_prompt}],
             max_tokens=3
         ).choices[0].message.content.strip().upper()
       return decision == "YES"
    except Exception:
         return False

    return False

def google_search(query, num_results=5, date_restrict=None):
    import requests
    from urllib.parse import urlencode

    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise RuntimeError("GOOGLE_API_KEY или GOOGLE_CSE_ID не заданы в .env")

    params = {
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": num_results
    }

    if date_restrict:
        params["dateRestrict"] = date_restrict  # например, m6 — за последние 6 месяцев

    url = f"https://www.googleapis.com/customsearch/v1?{urlencode(params)}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "link": item.get("link")
        })

    return results

def summarize_search_results(user_query: str, results: list) -> str:
    """
    GPT сам решает: что показать, как структурировать и какие источники использовать.
    Мы лишь передаём сырые результаты (title/snippet/link), без предварительной фильтрации.
    """
    if not results:
        return "Ничего не нашёл по запросу."

    # Сжато передаём сниппеты в модель
    blocks = []
    for i, it in enumerate(results, 1):
        title = it.get("title", "Без названия")
        snippet = it.get("snippet", "")
        link = it.get("link", "")
        blocks.append(f"{i}. {title}\n{snippet}\n{link}")
    corpus = "\n\n".join(blocks)

    system_prompt = (
        "Ты ассистент‑аналитик результатов веб‑поиска. У тебя НЕТ прямого доступа в интернет; "
        "используй ТОЛЬКО предоставленные сниппеты и ссылки как факты. "
        "Задача: на основе вопроса пользователя САМ выбери, что важно показать и в каком формате.\n\n"
        "Правила принятия решения:\n"
        "• Пойми тип вопроса: новости/сводка, сравнение/«какой актуальный», определение, how‑to и т.п.\n"
        "• Структуру и объём ответа подбери под задачу: краткий прямой ответ; либо 3–6 пунктов; либо краткий обзор.\n"
        "• Убирай нерелевантные и рекламные результаты; не повторяй одно и то же.\n"
        "• Ничего не придумывай сверх сниппетов. Если данных недостаточно — задай 1 уточняющий вопрос.\n"
        "• В конце добавь раздел «Источники» с 2–4 ССЫЛКАМИ, которые ты действительно использовал."
    )

    user_prompt = (
        f"Вопрос пользователя: «{user_query}».\n\n"
        f"Ниже результаты поиска (заголовок / сниппет / ссылка). "
        f"САМ выбери, что показать и в каком формате, чтобы лучше ответить на вопрос.\n\n"
        f"{corpus}"
    )

    resp = client.chat.completions.create(
        model=current_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content


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
    user = update.effective_user
    user_id = user.id

    raw_text = message.text or ""
    user_input = raw_text.replace(f"@{BOT_USERNAME}", "").strip()

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - TEXT: {user_input}")

    # База для сообщений в OpenAI
    messages = []

    # 1) ГРУППЫ: если это reply на сообщение бота — добавим предыдущий ответ как контекст
    if chat.type in ("group", "supergroup") and message.reply_to_message:
        reply_msg = message.reply_to_message
        if reply_msg.from_user and reply_msg.from_user.username == BOT_USERNAME:
            prev_text = reply_msg.text or ""
            if prev_text:
                messages.append({"role": "user", "content": prev_text})

    # 2) ПРИВАТНЫЕ ЧАТЫ: индивидуальный контекст ТОЛЬКО для админов
    if chat.type == "private" and user_id in ADMINS:
        history = user_histories[user_id]          # defaultdict — KeyError не будет
        messages.extend(list(history))             # отдаём историю в GPT
        messages.append({"role": "user", "content": user_input})
    else:
        messages.append({"role": "user", "content": user_input})

    try:
        # 3) Умное решение: нужен ли веб‑поиск
        if should_web_search(user_input):
            raw_results = google_search(user_input, num_results=8, date_restrict="m6")
            answer_text = summarize_search_results(user_input, raw_results)
        else:
            # обычный ответ GPT (без интернета)
            resp = client.chat.completions.create(   # <-- исправленный вызов
                model=current_model,
                messages=messages
            )
            answer_text = resp.choices[0].message.content

        logging.info(f"[BOT -> {user.id}] Ответ: {answer_text}")
        # 4) Отправляем ответ
        await message.reply_text(answer_text)

        # 5) Если приватка с админом — сохраним и ответ ассистента
        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            history.append({"role": "assistant", "content": answer_text})

    except Exception as e:
        logging.exception("handle_text error")
        await message.reply_text(f"❌ Ошибка: {format_exc(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id

    logging.info(f"[{user.id}] @{user.username or 'no_username'} - VOICE: получено голосовое сообщение")
    try:
        # 1. Скачиваем голосовое
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            await voice_file.download_to_drive(f.name)
            ogg_path = f.name

        # 2. Конвертируем в wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")

        # 3. Распознаём речь (Whisper)
        with open(wav_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )

        text = transcript.text.strip()
        logging.info(f"{user} - VOICE TEXT: {text}")

        # 4. Формируем сообщения для GPT
        messages = []
        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            messages.extend(list(history))
            messages.append({"role": "user", "content": text})
        else:
            messages.append({"role": "user", "content": text})

        # 5. Отвечаем GPT
        resp = client.chat.completions.create(
            model=current_model,
            messages=messages,
        )
        answer_text = resp.choices[0].message.content

        logging.info(f"[BOT -> {user.id}] Ответ: {answer_text}")

        # 6. Отправляем ответ
        await update.message.reply_text(
            f"🗣️ Ты сказал: {text}\n\n🤖 {answer_text}"
        )

        # 7. Сохраняем историю для админов в приватке
        if chat.type == "private" and user_id in ADMINS:
            history.append({"role": "assistant", "content": answer_text})

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
async def error_handler(update, context):
    logging.exception("Unhandled error: %s", context.error)

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

    app.add_error_handler(error_handler)

    logging.info(f"GPT-бот запущен! Текущая модель: {current_model}")
    app.run_polling()
    me = app.bot.get_me()
    logging.info("Bot username:", me.username)

if __name__ == "__main__":
    main()
