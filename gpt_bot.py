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

def should_web_search(user_input: str) -> bool:
    """
    Быстрый и дешёвый детектор намерения идти в веб:
    1) Жёсткие триггеры по ключевым словам (надёжно, 0$)
    2) (опц.) LLM-детектор — раскомментируй блок ниже
    """
    kw = [
        "новост", "актуаль", "что произошло", "что сейчас",
        "свеж", "google", "погугли", "поиск", "найди",
        "сколько стоит", "цена", "курс", "сегодня", "сейчас",
        "расписание", "когда выйдет", "релиз", "обновлен"
    ]
    low = user_input.lower()
    if any(k in low for k in kw):
        return True

    # --- Опционально: уточняем у LLM (удорожает запрос) ---
    # decision_prompt = (
    #     "Определи, нужен ли интернет-поиск. Ответь ровно 'YES' или 'NO'.\n"
    #     f"Запрос: {user_input}"
    # )
    # try:
    #     decision = client.chat.completions.create(
    #         model=current_model,
    #         messages=[{"role": "user", "content": decision_prompt}],
    #         max_tokens=3
    #     ).choices[0].message.content.strip().upper()
    #     return decision == "YES"
    # except Exception:
    #     return False

    return False

def google_search(query: str, num_results: int = 5) -> List[dict]:
    """
    Возвращает структурированный список: [{title, link, snippet}]
    Требуются GOOGLE_CSE_API_KEY и GOOGLE_CSE_CX в .env
    """
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GOOGLE_CSE_API_KEY")
    cx = os.getenv("GOOGLE_CSE_CX")
    if not api_key or not cx:
        raise RuntimeError("Google CSE ключи не заданы (GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX).")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": num_results}

    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    items = []
    for it in data.get("items", []):
        items.append({
            "title": it.get("title", "Без названия"),
            "link": it.get("link", ""),
            "snippet": it.get("snippet", "")
        })
    return items

def summarize_search_results(query: str, results: List[dict]) -> str:
    """
    Кормим результаты в GPT и просим чистое краткое резюме без воды + ссылки.
    """
    # Соберём компактный текст для анализа
    lines = []
    for i, it in enumerate(results, 1):
        lines.append(f"{i}. {it['title']}\n{it['snippet']}\n{it['link']}")
    corpus = "\n\n".join(lines)

    system_prompt = (
        "Ты новостной и веб-аналитик. У тебя НЕТ доступа в интернет; "
        "анализируй только предоставленные сниппеты и ссылки. "
        "Сделай краткое, структурированное резюме (3–6 пунктов), "
        "убери рекламу, дубликаты и воду, не выдумывай факты. "
        "В конце дай список 2–4 релевантных ссылок для углубления."
    )
    user_prompt = (
        f"Запрос пользователя: {query}\n\n"
        f"Результаты поиска (заголовок / сниппет / ссылка):\n\n{corpus}"
    )

    resp = client.chat.completions.create(
        model=current_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3
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
        history = user_histories[user_id]
        # history уже deque(maxlen=10); копию отдаём в GPT
        messages.extend(list(history))
        # добавляем текущий юзерский запрос (один раз!)
        messages.append({"role": "user", "content": user_input})
    else:
        # без истории
        messages.append({"role": "user", "content": user_input})

    try:
        # 3) Умное решение: нужен ли веб-поиск
        if should_web_search(user_input):
            results = google_search(user_input, num_results=5)
            if results:
                summary = summarize_search_results(user_input, results)
                answer_text = summary
            else:
                answer_text = "Ничего релевантного не нашёл по запросу."
        else:
            # обычный ответ GPT (без интернета)
            resp = client.chat_completions.create(  # <= если у тебя openai>=1.x, корректно: client.chat.completions.create
                model=current_model,
                messages=messages
            )
            answer_text = resp.choices[0].message.content

        # 4) Отправляем ответ
        await message.reply_text(answer_text)

        # 5) Если приватка с админом — дописываем И ответ ассистента в историю
        if chat.type == "private" and user_id in ADMINS:
            history = user_histories[user_id]
            # добавляем последние две реплики в историю: user + assistant
            # (user уже добавили выше, добавим assistant)
            history.append({"role": "assistant", "content": answer_text})

    except Exception as e:
        logging.exception("handle_text error")
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
