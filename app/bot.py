import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message

from .config import settings
from .handlers import start, menu, referral, admin_commands, referral_codes, invite, captcha, social_verification, admin_review
# from .middleware import BlacklistMiddleware, UserLoggingMiddleware  # ВРЕМЕННО ОТКЛЮЧАЕМ
from .models import init_db

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    logging.info("✅ База данных инициализирована")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # ВРЕМЕННО ОТКЛЮЧАЕМ MIDDLEWARE ДЛЯ ТЕСТА
    # dp.message.middleware(BlacklistMiddleware())
    # dp.callback_query.middleware(BlacklistMiddleware())
    # dp.message.middleware(UserLoggingMiddleware())
    # dp.callback_query.middleware(UserLoggingMiddleware())

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(referral.router)
    dp.include_router(referral_codes.router)
    dp.include_router(invite.router)
    dp.include_router(captcha.router)
    dp.include_router(social_verification.router)
    dp.include_router(admin_review.router)
    dp.include_router(admin_commands.router)

    # ОБРАБОТЧИК ДЛЯ /friend_ (ДОБАВЛЯЕМ ПРЯМО СЮДА)
    @dp.message()
    async def catch_all(message: Message):
        logging.info(f"📩 Получено сообщение: {message.text}")
        if message.text and message.text.startswith('/friend_'):
            from app.handlers.invite import send_friend_details
            try:
                friend_id = int(message.text.split("_")[1])
                await send_friend_details(message, friend_id, message.from_user.id)
            except Exception as e:
                await message.answer(f"❌ Ошибка: {e}")
        else:
            await message.answer(f"✅ Бот получил: {message.text}")

    logging.info("🚀 Бот запущен и готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())