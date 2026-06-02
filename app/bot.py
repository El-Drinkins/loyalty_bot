import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .handlers import start, menu, referral, admin_commands, referral_codes, invite, captcha, social_verification, admin_review, catalog, feedback
from .middleware import BlacklistMiddleware, UserLoggingMiddleware
from .models import init_db
from .expiry_checker import check_expiring_points
from .logger import bot_logger as logger

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
                    logger.warning(f"Отправлено тревожное уведомление админу {admin_id}")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")
        
        _bot_initial_name = current_name
        _bot_initial_photo_id = current_photo_id
        
    except Exception as e:
        logger.error(f"Ошибка при проверке идентичности бота: {e}")


async def main():
    await init_db()
    logger.info("База данных инициализирована")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    global _bot_initial_name, _bot_initial_photo_id
    try:
        me = await bot.get_me()
        _bot_initial_name = me.first_name
        photos = await bot.get_user_profile_photos(me.id, limit=1)
        _bot_initial_photo_id = photos.photos[0][0].file_id if photos.photos else None
        logger.info(f"Эталонные данные бота сохранены: название='{_bot_initial_name}'")
    except Exception as e:
        logger.error(f"Не удалось получить данные бота при запуске: {e}")

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
    dp.include_router(catalog.router)
    dp.include_router(feedback.router)


    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_expiring_points, 'cron', hour=15, minute=0)
    scheduler.add_job(check_bot_identity, 'interval', hours=1, args=[bot])
    scheduler.start()
    logger.info("Планировщик запущен (проверка баллов: 9:00, проверка бота: каждый час)")

    logger.info("Бот запущен и готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())