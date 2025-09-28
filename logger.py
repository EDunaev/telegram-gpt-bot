# logger.py
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_FILE = os.path.join(os.path.dirname(__file__), "bot.log")

def setup_logger():
    """
    Создаёт и возвращает объект logger с ротацией логов.
    """
    logger = logging.getLogger("gptbot")
    logger.setLevel(logging.INFO)

    # Ротация логов: 5 файлов по 5 МБ
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    # 🔇 Отключаем лишние логи от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.bot").setLevel(logging.INFO)
    logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.INFO)

    logger.propagate = False  # чтобы не дублировалось в stdout/stderr

    return logger
