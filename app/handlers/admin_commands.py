from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select, func

from ..models import User, AsyncSessionLocal  # изменен импорт
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
        "/blacklist - черный список\n\n"
        "Для управления пользователями используйте веб-интерфейс:\n"
        f"http://localhost:8000",
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