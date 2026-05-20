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
    - Базовая ставка: 5% (посуточно), 10% (на месяц)
    - +1% за каждый календарный месяц, в котором была хотя бы одна завершённая аренда
    - Текущий месяц не учитывается
    - Максимум: 10% (посуточно), 15% (на месяц)
    - Пропуск месяца — сброс до базовой
    """
    base_rate = 5
    max_rate = 10
    
    result = await session.execute(
        select(Rental)
        .where(Rental.user_id == user.id, Rental.status == "completed")
        .order_by(Rental.end_date.desc())
    )
    rentals = result.scalars().all()
    
    if not rentals:
        return base_rate
    
    months_with_rentals = set()
    for rental in rentals:
        months_with_rentals.add((rental.end_date.year, rental.end_date.month))
    
    if not months_with_rentals:
        return base_rate
    
    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month
    
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
            if (user.cashback_frozen and 
                user.cashback_frozen_year == check_year and 
                user.cashback_frozen_month == check_month):
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


async def calculate_monthly_rate(session: AsyncSession, user) -> int:
    """
    Рассчитывает ставку для аренды на месяц.
    Базовая: 10%. +1% если есть активная месячная аренда (продление).
    Максимум: 15%.
    """
    base_monthly = 10
    max_monthly = 15
    
    result = await session.execute(
        select(Rental)
        .where(
            Rental.user_id == user.id,
            Rental.status == "active",
            Rental.is_monthly == True
        )
        .limit(1)
    )
    active_monthly = result.scalar_one_or_none()
    
    if active_monthly:
        return min(base_monthly + 1, max_monthly)
    
    return base_monthly


async def has_rental_in_current_month(session: AsyncSession, user) -> bool:
    """Проверяет, была ли у пользователя хотя бы одна аренда от 1000 руб. в текущем месяце."""
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    result = await session.execute(
        select(Rental)
        .where(
            Rental.user_id == user.id,
            Rental.status == "completed",
            Rental.end_date >= month_start,
            Rental.total_price >= 1000
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def has_active_monthly_rental(session: AsyncSession, user) -> bool:
    """Проверяет, есть ли у пользователя активная аренда на месяц."""
    result = await session.execute(
        select(Rental)
        .where(
            Rental.user_id == user.id,
            Rental.status == "active",
            Rental.is_monthly == True
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_cashback_info(session: AsyncSession, user) -> dict:
    """Возвращает полную информацию о кэшбэке для отображения."""
    rate = await calculate_cashback_rate(session, user)
    monthly_rate = await calculate_monthly_rate(session, user)
    has_rental_this_month = await has_rental_in_current_month(session, user)
    has_active_monthly = await has_active_monthly_rental(session, user)
    
    # Ставка на следующий месяц, если будет аренда: текущая + 1%
    next_rate_if_rental = min(rate + 1, 10)
    # Ставка на следующий месяц, если не будет аренды: сброс до базовой
    next_rate_if_no_rental = 5
    
    # Для месячной аренды
    if has_active_monthly:
        next_monthly = min(monthly_rate + 1, 15)
    else:
        next_monthly = 10
    
    # Статус
    if rate == 10:
        status = "максимальная"
    elif rate >= 7:
        status = "повышена"
    else:
        status = "базовая"
    
    return {
        "rate": rate,
        "monthly_rate": monthly_rate,
        "status": status,
        "months": rate - 5,
        "has_rental_this_month": has_rental_this_month,
        "has_active_monthly": has_active_monthly,
        "next_rate_if_rental": next_rate_if_rental,
        "next_rate_if_no_rental": next_rate_if_no_rental,
        "next_monthly": next_monthly,
        "is_max_daily": rate >= 10,
        "is_max_monthly": monthly_rate >= 15,
        "frozen": user.cashback_frozen,
        "frozen_month": user.cashback_frozen_month,
        "frozen_year": user.cashback_frozen_year
    }