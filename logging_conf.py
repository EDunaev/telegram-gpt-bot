import logging
from logging.handlers import RotatingFileHandler

# Конфигурация логирования (с ротацией файлов)
log_file = "bot.log"
handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)

logging.basicConfig(
    handlers=[handler],
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# отключаем лишние логи
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.INFO)
logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)
logging.getLogger("telegram.request").setLevel(logging.INFO)
