"""
Настройка логирования для бота.
Заменяет все print() на структурированные логи с записью в файлы.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Создаём папку для логов, если её нет
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Общий формат для всех логов
LOG_FORMAT = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """
    Создаёт настроенный логгер.
    
    Параметры:
    - name: имя логгера (обычно __name__ модуля)
    - log_file: имя файла (например, 'bot.log', 'web.log')
    - level: уровень логирования
    
    Возвращает: объект Logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Чтобы не дублировались обработчики при перезагрузке
    if logger.handlers:
        return logger
    
    # Вывод в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(LOG_FORMAT)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)
    
    # Запись в файл с ротацией (макс 10 МБ на файл, храним 30 файлов)
    file_path = os.path.join(LOGS_DIR, log_file)
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=10 * 1024 * 1024,  # 10 МБ
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setFormatter(LOG_FORMAT)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)
    
    return logger


# Готовые логгеры для разных частей проекта
bot_logger = setup_logger("bot", "bot.log")
web_logger = setup_logger("web", "web.log")
db_logger = setup_logger("database", "database.log")