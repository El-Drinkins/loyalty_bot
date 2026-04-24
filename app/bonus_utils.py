"""
Вспомогательные функции для расчёта бонусов по друзьям
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.models import User, Referral, Rental, Transaction, ReferralBonus
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
    
    # Находим referral запись
    referral = await session.execute(
        select(Referral).where(
            Referral.old_user_id == user_id,
            Referral.new_user_id == friend_id
        )
    )
    referral = referral.scalar_one_or_none()
    
    awarded_bonuses = set()
    if referral:
        # Получаем уже начисленные бонусы
        bonuses_result = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral.id,
                ReferralBonus.status == "awarded"
            )
        )
        for bonus in bonuses_result.scalars().all():
            awarded_bonuses.add(bonus.bonus_type)
    
    return {
        'first_rental': {
            'achieved': rentals_count >= 1,
            'awarded': 'first_rental' in awarded_bonuses,
            'bonus': 300
        },
        'second_rental': {
            'achieved': rentals_count >= 2,
            'awarded': 'second_rental' in awarded_bonuses,
            'bonus': 700
        },
        'threshold_10k': {
            'achieved': total_amount >= 10000,
            'awarded': 'threshold_10k' in awarded_bonuses,
            'bonus': 1000,
            'progress': total_amount,
            'target': 10000
        },
        'threshold_30k': {
            'achieved': total_amount >= 30000,
            'awarded': 'threshold_30k' in awarded_bonuses,
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


# ========== НОВЫЕ ФУНКЦИИ ДЛЯ СИСТЕМЫ РЕФЕРАЛЬНЫХ БОНУСОВ ==========


async def update_referral_total_rentals(session: AsyncSession, referral_id: int) -> int:
    """Обновляет сумму аренд в записи реферала и возвращает новую сумму"""
    # Получаем referral
    referral = await session.get(Referral, referral_id)
    if not referral:
        return 0
    
    # Считаем сумму всех завершённых аренд друга
    result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    total = result.scalar() or 0
    
    # Обновляем поле
    referral.total_rentals_amount = total
    await session.commit()
    
    return total


async def check_and_create_pending_bonuses(session: AsyncSession, referral_id: int) -> list:
    """
    Проверяет, какие бонусы стали доступны, и создаёт записи в referral_bonuses
    Возвращает список созданных бонусов
    """
    referral = await session.get(Referral, referral_id)
    if not referral:
        return []
    
    total = referral.total_rentals_amount
    rentals_count = await get_friend_rentals_count(session, referral.new_user_id)
    
    created_bonuses = []
    
    # Определяем, какие бонусы нужно создать
    bonus_checks = [
        ("first_rental", rentals_count >= 1, 300),
        ("second_rental", rentals_count >= 2, 700),
        ("threshold_10k", total >= 10000, 1000),
        ("threshold_30k", total >= 30000, 1000),
    ]
    
    for bonus_type, condition, amount in bonus_checks:
        if condition:
            # Проверяем, нет ли уже записи об этом бонусе
            existing = await session.execute(
                select(ReferralBonus).where(
                    ReferralBonus.referral_id == referral_id,
                    ReferralBonus.bonus_type == bonus_type
                )
            )
            if not existing.scalar_one_or_none():
                bonus = ReferralBonus(
                    referral_id=referral_id,
                    bonus_type=bonus_type,
                    amount=amount,
                    status="pending"
                )
                session.add(bonus)
                created_bonuses.append(bonus_type)
    
    if created_bonuses:
        await session.commit()
    
    return created_bonuses


async def get_pending_bonuses_for_referral(session: AsyncSession, referral_id: int) -> list:
    """Возвращает список ожидающих подтверждения бонусов для конкретного реферала"""
    result = await session.execute(
        select(ReferralBonus)
        .where(
            ReferralBonus.referral_id == referral_id,
            ReferralBonus.status == "pending"
        )
    )
    return result.scalars().all()


async def get_all_pending_bonuses(session: AsyncSession) -> list:
    """Возвращает все ожидающие подтверждения бонусы с информацией о пользователях"""
    result = await session.execute(
        select(ReferralBonus, Referral, User)
        .join(Referral, ReferralBonus.referral_id == Referral.id)
        .join(User, Referral.old_user_id == User.id)
        .where(ReferralBonus.status == "pending")
        .order_by(ReferralBonus.created_at)
    )
    return result.all()


async def award_referral_bonus(session: AsyncSession, bonus_id: int, admin_id: int) -> bool:
    """
    Начисляет бонус пользователю
    Возвращает True если успешно
    """
    bonus = await session.get(ReferralBonus, bonus_id)
    if not bonus or bonus.status != "pending":
        return False
    
    referral = await session.get(Referral, bonus.referral_id)
    if not referral:
        return False
    
    user = await session.get(User, referral.old_user_id)
    if not user:
        return False
    
    # Начисляем баллы
    user.balance += bonus.amount
    user.points_expiry_date = calculate_expiry_date()
    
    # Создаём транзакцию
    transaction = Transaction(
        user_id=user.id,
        amount=bonus.amount,
        reason=f"Бонус за {get_bonus_type_name(bonus.bonus_type)} друга (ID: {referral.new_user_id})",
        admin_id=admin_id
    )
    session.add(transaction)
    
    # Обновляем статус бонуса
    bonus.status = "awarded"
    bonus.awarded_at = datetime.utcnow()
    bonus.awarded_by = admin_id
    
    # Если это первая аренда, обновляем статус реферала
    if bonus.bonus_type == "first_rental":
        referral.status = "completed"
        referral.completion_date = datetime.utcnow()
    
    await session.commit()
    return True


def get_bonus_type_name(bonus_type: str) -> str:
    """Возвращает читаемое название бонуса"""
    names = {
        "first_rental": "первую аренду",
        "second_rental": "вторую аренду",
        "threshold_10k": "аренды на 10000₽",
        "threshold_30k": "аренды на 30000₽"
    }
    return names.get(bonus_type, bonus_type)


def calculate_expiry_date() -> datetime:
    """Возвращает дату истечения срока баллов (через 90 дней)"""
    from datetime import timedelta
    return datetime.utcnow() + timedelta(days=90)