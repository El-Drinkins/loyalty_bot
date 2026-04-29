"""
Модуль проверки истекающих баллов
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AsyncSessionLocal, User
from app.notifications import send_telegram_notification
from app.config import settings


async def get_users_with_expiry_date(session: AsyncSession, days_from_now: int):
    """
    Возвращает пользователей, у которых дата сгорания баллов ровно через указанное количество дней
    """
    target_date = (datetime.utcnow() + timedelta(days=days_from_now)).date()
    
    result = await session.execute(
        select(User).where(
            User.points_expiry_date.is_not(None),
            func.date(User.points_expiry_date) == target_date
        )
    )
    return result.scalars().all()


def format_expiry_message(balance: int, expiry_date: datetime, days: int) -> str:
    """
    Форматирует сообщение в зависимости от количества дней до сгорания
    """
    date_str = expiry_date.strftime("%d.%m.%Y")
    balance_str = f"{balance:,}".replace(",", " ")
    
    if days == 30:
        return (
            f"⏳ Ваши баллы скоро сгорят\n\n"
            f"Через месяц, {date_str}, ваши баллы будут аннулированы.\n\n"
            f"💰 Осталось: {balance_str} ⭐\n\n"
            f"💡 Баллами можно оплатить до 50% стоимости любой аренды.\n\n"
            f"🔄 Сделайте новую аренду, чтобы продлить срок действия всех баллов ещё на 3 месяца!"
        )
    elif days == 7:
        return (
            f"⚠️ Осталось 7 дней!\n\n"
            f"Ваши баллы ({balance_str} ⭐) сгорят {date_str}.\n\n"
            f"💡 Баллами можно оплатить до 50% стоимости любой аренды.\n\n"
            f"🔄 Сделайте новую аренду, чтобы продлить срок действия всех баллов ещё на 3 месяца!"
        )
    elif days == 1:
        return (
            f"🔴 ПОСЛЕДНИЙ ДЕНЬ!\n\n"
            f"Завтра ваши баллы ({balance_str} ⭐) будут аннулированы.\n\n"
            f"💡 Баллами можно оплатить до 50% стоимости любой аренды.\n\n"
            f"🔄 Сделайте новую аренду сегодня, чтобы продлить срок действия всех баллов ещё на 3 месяца!"
        )
    else:
        return (
            f"⏳ Ваши баллы сгорают {date_str}\n\n"
            f"💰 Баланс: {balance_str} ⭐\n\n"
            f"💡 Баллами можно оплатить до 50% стоимости любой аренды.\n\n"
            f"🔄 Сделайте новую аренду, чтобы продлить срок действия всех баллов ещё на 3 месяца!"
        )


async def check_expiring_points():
    """
    Проверяет пользователей с истекающими баллами и отправляет напоминания
    Возвращает количество отправленных уведомлений
    """
    # Периоды напоминания: 30 дней, 7 дней, 1 день
    reminder_days = [30, 7, 1]
    total_sent = 0
    
    async with AsyncSessionLocal() as session:
        for days in reminder_days:
            users = await get_users_with_expiry_date(session, days)
            
            for user in users:
                message = format_expiry_message(user.balance, user.points_expiry_date, days)
                
                try:
                    await send_telegram_notification(user.telegram_id, message)
                    total_sent += 1
                    print(f"✅ Напоминание отправлено пользователю {user.telegram_id} (за {days} дней)")
                except Exception as e:
                    print(f"❌ Ошибка отправки пользователю {user.telegram_id}: {e}")
    
    return total_sent


async def test_expiry_for_user(user_id: int, days: int):
    """
    Тестовая функция: отправляет напоминание конкретному пользователю
    """
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            print(f"❌ Пользователь с ID {user_id} не найден")
            return False
        
        # Устанавливаем тестовую дату сгорания
        test_expiry = datetime.utcnow() + timedelta(days=days)
        user.points_expiry_date = test_expiry
        await session.commit()
        
        message = format_expiry_message(user.balance, user.points_expiry_date, days)
        
        try:
            await send_telegram_notification(user.telegram_id, message)
            print(f"✅ Тестовое напоминание отправлено пользователю {user.telegram_id}")
            return True
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False


if __name__ == "__main__":
    # Для ручного запуска
    asyncio.run(check_expiring_points())