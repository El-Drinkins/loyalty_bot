"""
Вспомогательные функции для расчёта бонусов по друзьям
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models import User, Referral, Rental, Transaction
from app.config import settings


async def get_friend_rentals_total(session: AsyncSession, friend_id: int) -> int:
    """
    Возвращает сумму всех аренд друга (завершённые аренды)
    """
    result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == friend_id, Rental.status == "completed")
    )
    return result.scalar() or 0


async def get_friend_rentals_count(session: AsyncSession, friend_id: int) -> int:
    """
    Возвращает количество завершённых аренд друга
    """
    result = await session.execute(
        select(func.count(Rental.id))
        .where(Rental.user_id == friend_id, Rental.status == "completed")
    )
    return result.scalar() or 0


async def get_friend_bonuses_status(session: AsyncSession, user_id: int, friend_id: int) -> dict:
    """
    Возвращает статус всех бонусов по конкретному другу
    
    Возвращает словарь:
    {
        'first_rental': {'achieved': bool, 'awarded': bool, 'bonus': 300},
        'second_rental': {'achieved': bool, 'awarded': bool, 'bonus': 700},
        'threshold_10k': {'achieved': bool, 'awarded': bool, 'bonus': 1000, 'progress': int, 'target': 10000},
        'threshold_30k': {'achieved': bool, 'awarded': bool, 'bonus': 1000, 'progress': int, 'target': 30000}
    }
    """
    # Получаем сумму аренд и количество аренд друга
    total_amount = await get_friend_rentals_total(session, friend_id)
    rentals_count = await get_friend_rentals_count(session, friend_id)
    
    # Проверяем, какие бонусы уже начислены пользователю за этого друга
    awarded_bonuses = set()
    
    # Ищем транзакции с бонусами за этого друга
    # Формат reason: "Бонус за первую аренду друга (ID: {friend_id})"
    bonus_reasons = [
        f"Бонус за первую аренду друга (ID: {friend_id})",
        f"Бонус за вторую аренду друга (ID: {friend_id})",
        f"Бонус за аренды друга на 10000₽ (ID: {friend_id})",
        f"Бонус за аренды друга на 30000₽ (ID: {friend_id})",
    ]
    
    for reason in bonus_reasons:
        result = await session.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.reason == reason,
                Transaction.amount > 0
            )
        )
        if result.scalar_one_or_none():
            awarded_bonuses.add(reason)
    
    return {
        'first_rental': {
            'achieved': rentals_count >= 1,
            'awarded': f"Бонус за первую аренду друга (ID: {friend_id})" in awarded_bonuses,
            'bonus': 300
        },
        'second_rental': {
            'achieved': rentals_count >= 2,
            'awarded': f"Бонус за вторую аренду друга (ID: {friend_id})" in awarded_bonuses,
            'bonus': 700
        },
        'threshold_10k': {
            'achieved': total_amount >= 10000,
            'awarded': f"Бонус за аренды друга на 10000₽ (ID: {friend_id})" in awarded_bonuses,
            'bonus': 1000,
            'progress': total_amount,
            'target': 10000
        },
        'threshold_30k': {
            'achieved': total_amount >= 30000,
            'awarded': f"Бонус за аренды друга на 30000₽ (ID: {friend_id})" in awarded_bonuses,
            'bonus': 1000,
            'progress': total_amount,
            'target': 30000
        }
    }


async def get_all_friends_total_rentals(session: AsyncSession, user_id: int) -> int:
    """
    Возвращает сумму аренд ВСЕХ друзей пользователя
    """
    # Получаем всех друзей пользователя
    result = await session.execute(
        select(Referral.new_user_id).where(Referral.old_user_id == user_id)
    )
    friend_ids = [row[0] for row in result.all()]
    
    if not friend_ids:
        return 0
    
    # Суммируем все завершённые аренды всех друзей
    result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id.in_(friend_ids), Rental.status == "completed")
    )
    return result.scalar() or 0


async def is_team_bonus_awarded(session: AsyncSession, user_id: int) -> bool:
    """
    Проверяет, получен ли уже командный бонус 5000⭐ за 100000₽
    """
    user = await session.get(User, user_id)
    return user.team_bonus_100k_awarded if user else False


async def award_team_bonus(session: AsyncSession, user_id: int, total_rentals: int) -> bool:
    """
    Начисляет командный бонус 5000⭐ если сумма аренд друзей >= 100000₽ и бонус ещё не выдан
    Возвращает True если бонус был начислен
    """
    if total_rentals >= 100000:
        already_awarded = await is_team_bonus_awarded(session, user_id)
        if not already_awarded:
            user = await session.get(User, user_id)
            if user:
                user.balance += 5000
                user.team_bonus_100k_awarded = True
                
                transaction = Transaction(
                    user_id=user_id,
                    amount=5000,
                    reason="🏆 Командный бонус: аренды всех друзей на 100 000 ₽"
                )
                session.add(transaction)
                await session.commit()
                return True
    return False


def format_progress_bar(current: int, target: int, length: int = 10) -> str:
    """Форматирует прогресс-бар: ▰▰▰▰░░░░░░"""
    if target <= 0:
        return "░" * length
    
    percent = min(current / target, 1.0)
    filled = int(percent * length)
    empty = length - filled
    return "▰" * filled + "░" * empty


def format_number(num: int) -> str:
    """Форматирует число с пробелами: 10000 -> 10 000"""
    return f"{num:,}".replace(",", " ")