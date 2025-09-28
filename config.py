import os
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("TELEGRAM_TOKEN или OPENAI_API_KEY не заданы в .env")

client = OpenAI(api_key=OPENAI_API_KEY)
current_model = DEFAULT_MODEL

# Константы
ADMINS = {1091992386, 1687504544}
LIMITED_USERS = {111111111, 222222222, 333333333}
CHAT_ID = -1001785925671
BOT_USERNAME = "DunaevAssistentBot"
