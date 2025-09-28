import requests
from telegram import Update
from telegram.ext import ContextTypes
from config import OPENAI_API_KEY, current_model
from helpers import is_allowed, is_admin, format_exc

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
    from config import current_model
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 У вас нет прав на смену модели.")
        return

    if not context.args:
        await update.message.reply_text(
            f"Текущая модель: {current_model}\n"
            "Использование: /model gpt-4o или /model gpt-3.5-turbo"
        )
        return

    new_model = context.args[0].strip()
    from config import current_model as cm
    cm = new_model
    await update.message.reply_text(f"✅ Модель установлена: {new_model}")

async def quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 У вас нет прав на просмотр квоты.")
        return

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
