import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message

from .config import settings
from .handlers import start, menu, referral, admin_commands, referral_codes, invite, captcha, social_verification, admin_review
from .models import init_db

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    logging.info("✅ База данных инициализирована")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(referral.router)
    dp.include_router(referral_codes.router)
    dp.include_router(invite.router)
    dp.include_router(captcha.router)
    dp.include_router(social_verification.router)
    dp.include_router(admin_review.router)
    dp.include_router(admin_commands.router)

    # ОБРАБОТЧИК ТОЛЬКО ДЛЯ /friend_ И /friend (НЕ ТРОГАЕТ КНОПКИ)
    @dp.message(lambda message: message.text and (message.text.startswith('/friend_') or message.text.startswith('/friend')))
    async def friend_handler(message: Message):
        text = message.text
        logging.info(f"📩 Обработка друга: {text}")
        from app.handlers.invite import send_friend_details
        try:
            # Извлекаем ID: /friend_6 -> 6, /friend6 -> 6
            parts = text.replace('/friend_', '/friend').split('/friend')
            if len(parts) > 1 and parts[1].isdigit():
                friend_id = int(parts[1])
                await send_friend_details(message, friend_id, message.from_user.id)
            else:
                await message.answer("❌ Неверный формат. Используйте: /friend_6")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")

    logging.info("🚀 Бот запущен и готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())