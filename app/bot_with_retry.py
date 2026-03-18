import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
import time

from .config import settings
from .handlers import start, menu, referral, admin_commands, referral_codes, invite, captcha, social_verification, admin_review
from .middleware import BlacklistMiddleware, UserLoggingMiddleware
from .models import init_db

logging.basicConfig(level=logging.INFO)

async def wait_for_connection(bot: Bot, max_retries=5, delay=5):
    """Пытается подключиться к Telegram API с повторными попытками"""
    for attempt in range(max_retries):
        try:
            logging.info(f"🔄 Попытка подключения {attempt + 1}/{max_retries}...")
            me = await bot.get_me()
            logging.info(f"✅ Подключено! Бот: @{me.username}")
            return True
        except Exception as e:
            logging.warning(f"❌ Попытка {attempt + 1} не удалась: {e}")
            if attempt < max_retries - 1:
                logging.info(f"⏳ Ожидание {delay} секунд перед следующей попыткой...")
                await asyncio.sleep(delay)
    return False

async def main():
    # Инициализация базы данных
    await init_db()
    logging.info("✅ База данных инициализирована")

    # Создаем бота
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Пытаемся подключиться с повторными попытками
    connected = await wait_for_connection(bot)
    if not connected:
        logging.error("❌ Не удалось подключиться к Telegram API после нескольких попыток")
        return

    # Регистрируем middleware
    dp.message.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(BlacklistMiddleware())
    dp.message.middleware(UserLoggingMiddleware())
    dp.callback_query.middleware(UserLoggingMiddleware())

    # Регистрируем все роутеры
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(referral.router)
    dp.include_router(referral_codes.router)
    dp.include_router(invite.router)
    dp.include_router(captcha.router)
    dp.include_router(social_verification.router)
    dp.include_router(admin_review.router)
    dp.include_router(admin_commands.router)

    logging.info("🚀 Бот запущен и готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())