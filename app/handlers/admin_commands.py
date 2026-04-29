from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select, func

from ..models import User, AsyncSessionLocal
from ..config import settings

router = Router()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда для администраторов"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    await message.answer(
        "👑 **Панель администратора**\n\n"
        "Доступные команды:\n"
        "/admin - показать это меню\n"
        "/review - модерация заявок\n"
        "/stats - статистика\n"
        "/users - список пользователей\n"
        "/blacklist - черный список\n"
        "/test_expiry - проверить истекающие баллы\n"
        "/test_expiry_for_user ID ДНИ - отправить тестовое напоминание\n\n"
        "Для управления пользователями используйте веб-интерфейс:\n"
        f"http://85.137.251.207:8000/admin",
        parse_mode="Markdown"
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Быстрая статистика"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    async with AsyncSessionLocal() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        blacklisted = await session.scalar(
            select(func.count(User.id)).where(User.blacklisted == True)
        )
        total_balance = await session.scalar(select(func.sum(User.balance))) or 0
        
        await message.answer(
            f"📊 **Статистика**\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"⛔ Заблокировано: {blacklisted}\n"
            f"💰 Суммарный баланс: {total_balance} ⭐",
            parse_mode="Markdown"
        )

@router.message(Command("users"))
async def cmd_users(message: Message):
    """Список пользователей (первые 10)"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    async with AsyncSessionLocal() as session:
        users = await session.execute(
            select(User).order_by(User.id.desc()).limit(10)
        )
        users = users.scalars().all()
        
        if not users:
            await message.answer("📭 Нет зарегистрированных пользователей.")
            return
        
        text = "📋 **Последние пользователи:**\n\n"
        for user in users:
            status = "⛔" if user.blacklisted else "✅"
            text += f"{status} {user.id}: {user.full_name} - {user.balance}⭐\n"
        
        await message.answer(text, parse_mode="Markdown")

@router.message(Command("blacklist"))
async def cmd_blacklist(message: Message):
    """Список заблокированных пользователей"""
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    
    async with AsyncSessionLocal() as session:
        users = await session.execute(
            select(User)
            .where(User.blacklisted == True)
            .order_by(User.blacklisted_at.desc())
        )
        users = users.scalars().all()
        
        if not users:
            await message.answer("✅ Черный список пуст.")
            return
        
        text = "⛔ **Черный список:**\n\n"
        for user in users:
            date = user.blacklisted_at.strftime("%d.%m.%Y") if user.blacklisted_at else "?"
            text += f"• {user.full_name} (ID: {user.id})\n  Причина: {user.blacklist_reason}\n  Дата: {date}\n\n"
        
        await message.answer(text, parse_mode="Markdown")


@router.message(Command("test_expiry"))
async def cmd_test_expiry(message: Message):
    """Тестовая команда для проверки напоминаний о сгорании баллов (только для админа)"""
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    from app.expiry_checker import check_expiring_points
    
    await message.answer("🔄 Проверяю истекающие баллы...")
    
    try:
        count = await check_expiring_points()
        await message.answer(f"✅ Проверка завершена. Отправлено уведомлений: {count}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("test_expiry_for_user"))
async def cmd_test_expiry_for_user(message: Message):
    """Тестовая команда для отправки напоминания конкретному пользователю (только для админа)
    Использование: /test_expiry_for_user ID_ПОЛЬЗОВАТЕЛЯ ДНИ
    Пример: /test_expiry_for_user 123456789 7
    """
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Использование: /test_expiry_for_user ID_ПОЛЬЗОВАТЕЛЯ ДНИ\n"
                            "Пример: /test_expiry_for_user 123456789 7\n\n"
                            "Дни могут быть: 1, 7 или 30")
        return
    
    try:
        user_id = int(args[1])
        days = int(args[2])
        
        if days not in [1, 7, 30]:
            await message.answer("❌ Дни должны быть 1, 7 или 30")
            return
        
        from app.expiry_checker import test_expiry_for_user
        
        await message.answer(f"🔄 Отправляю тестовое напоминание пользователю {user_id} за {days} дней...")
        
        result = await test_expiry_for_user(user_id, days)
        
        if result:
            await message.answer(f"✅ Тестовое напоминание отправлено пользователю {user_id}")
        else:
            await message.answer(f"❌ Не удалось отправить. Проверьте ID пользователя.")
            
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /test_expiry_for_user ID ДНИ")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")