import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .handlers import start, menu, referral, admin_commands, referral_codes, invite, captcha, social_verification, admin_review
from .middleware import BlacklistMiddleware, UserLoggingMiddleware
from .models import init_db
from .expiry_checker import check_expiring_points

logging.basicConfig(level=logging.INFO)

# Глобальные переменные для хранения эталонных данных бота
_bot_initial_name = None
_bot_initial_photo_id = None


async def check_bot_identity(bot: Bot):
    """
    Проверяет, не изменились ли название и аватарка бота.
    Если изменились — отправляет тревожное уведомление админу.
    """
    global _bot_initial_name, _bot_initial_photo_id
    
    try:
        me = await bot.get_me()
        current_name = me.first_name
        
        # Получаем ID текущей аватарки
        photos = await bot.get_user_profile_photos(me.id, limit=1)
        current_photo_id = photos.photos[0][0].file_id if photos.photos else None
        
        changes = []
        
        if _bot_initial_name and current_name != _bot_initial_name:
            changes.append(f"Название: «{_bot_initial_name}» → «{current_name}»")
        
        if _bot_initial_photo_id and current_photo_id != _bot_initial_photo_id:
            changes.append("Аватарка изменена")
        
        if changes:
            alert_text = (
                "🚨 ТРЕВОГА! БОТА МОГЛИ УГНАТЬ!\n\n"
                + "\n".join(changes)
                + f"\n\nТекущее название: {current_name}\n"
                + f"Username: @{me.username}\n"
                + f"ID бота: {me.id}\n\n"
                + "Кто-то получил доступ к BotFather и изменил настройки бота.\n"
                + "Срочно проверьте доступы!"
            )
            
            for admin_id in settings.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, alert_text)
                    logging.warning(f"Отправлено тревожное уведомление админу {admin_id}")
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
        
        # Обновляем эталонные значения
        _bot_initial_name = current_name
        _bot_initial_photo_id = current_photo_id
        
    except Exception as e:
        logging.error(f"Ошибка при проверке идентичности бота: {e}")


async def main():
    await init_db()
    logging.info("✅ База данных инициализирована")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Запоминаем эталонные данные бота при запуске
    global _bot_initial_name, _bot_initial_photo_id
    try:
        me = await bot.get_me()
        _bot_initial_name = me.first_name
        photos = await bot.get_user_profile_photos(me.id, limit=1)
        _bot_initial_photo_id = photos.photos[0][0].file_id if photos.photos else None
        logging.info(f"🔍 Эталонные данные бота сохранены: название='{_bot_initial_name}', фото={_bot_initial_photo_id}")
    except Exception as e:
        logging.error(f"Не удалось получить данные бота при запуске: {e}")

    dp.message.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(BlacklistMiddleware())
    dp.message.middleware(UserLoggingMiddleware())
    dp.callback_query.middleware(UserLoggingMiddleware())

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(referral.router)
    dp.include_router(referral_codes.router)
    dp.include_router(invite.router)
    dp.include_router(captcha.router)
    dp.include_router(social_verification.router)
    dp.include_router(admin_review.router)
    dp.include_router(admin_commands.router)

    # Планировщик
    scheduler = AsyncIOScheduler()
    
    # Проверка истекающих баллов — каждый день в 9:00
    scheduler.add_job(check_expiring_points, 'cron', hour=9, minute=0)
    
    # Проверка целостности бота — каждый час
    scheduler.add_job(check_bot_identity, 'interval', hours=1, args=[bot])
    
    scheduler.start()
    logging.info("⏰ Планировщик запущен:")
    logging.info("   - Проверка сгорающих баллов: каждый день в 9:00")
    logging.info("   - Проверка целостности бота: каждый час")

    logging.info("🚀 Бот запущен и готов к работе!")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())