"""
Расчёт ставки кэшбэка для пользователя.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.models import Rental


async def calculate_cashback_rate(session: AsyncSession, user) -> int:
    """
    Рассчитывает текущую ставку кэшбэка для пользователя.
    
    Правила:
    - Базовая ставка: 5%
    - +1% за каждый ЗАВЕРШЁННЫЙ календарный месяц, в котором была хотя бы одна аренда
    - Текущий месяц не учитывается (ставка повышается со следующего месяца)
    - Максимум: 10%
    - Если пропущен месяц — сброс до базовой ставки
    """
    base_rate = 5
    max_rate = 10
    
    # Получаем все завершённые аренды пользователя
    result = await session.execute(
        select(Rental)
        .where(Rental.user_id == user.id, Rental.status == "completed")
        .order_by(Rental.end_date.desc())
    )
    rentals = result.scalars().all()
    
    if not rentals:
        return base_rate
    
    # Собираем уникальные месяцы с завершёнными арендами
    months_with_rentals = set()
    for rental in rentals:
        months_with_rentals.add((rental.end_date.year, rental.end_date.month))
    
    if not months_with_rentals:
        return base_rate
    
    # Текущий месяц
    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month
    
    # Считаем последовательные ЗАВЕРШЁННЫЕ месяцы от предыдущего назад
    # Предыдущий месяц — первый, который может дать повышение
    consecutive = 0
    check_year = current_year
    check_month = current_month - 1
    if check_month == 0:
        check_month = 12
        check_year -= 1
    
    while True:
        if (check_year, check_month) in months_with_rentals:
            consecutive += 1
        else:
            # Проверяем, не заморожен ли этот месяц
            if (user.cashback_frozen and 
                user.cashback_frozen_year == check_year and 
                user.cashback_frozen_month == check_month):
                # Замороженный месяц — не сбрасываем, но и не засчитываем
                pass
            else:
                break
        
        check_month -= 1
        if check_month == 0:
            check_month = 12
            check_year -= 1
    
    rate = base_rate + consecutive
    if rate > max_rate:
        rate = max_rate
    
    return rate


async def update_cashback_info(session: AsyncSession, user) -> None:
    """Обновляет информацию о ставке кэшбэка для пользователя."""
    rate = await calculate_cashback_rate(session, user)
    user.cashback_rate = rate
    await session.commit()


async def get_cashback_info(session: AsyncSession, user) -> dict:
    """Возвращает полную информацию о кэшбэке для отображения."""
    rate = await calculate_cashback_rate(session, user)
    
    # Определяем статус
    if rate == 5:
        status = "базовая"
    elif rate < 7:
        status = "повышена"
    elif rate < 10:
        status = "высокая"
    else:
        status = "максимальная"
    
    months = rate - 5  # количество месяцев повышения
    
    return {
        "rate": rate,
        "status": status,
        "months": months,
        "frozen": user.cashback_frozen,
        "frozen_month": user.cashback_frozen_month,
        "frozen_year": user.cashback_frozen_year,
        "can_freeze": not user.cashback_frozen
    }