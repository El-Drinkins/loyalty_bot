"""
Вспомогательные функции для расчёта бонусов по друзьям
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
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
    """
    total_amount = await get_friend_rentals_total(session, friend_id)
    rentals_count = await get_friend_rentals_count(session, friend_id)
    
    referral = await session.execute(
        select(Referral).where(
            Referral.old_user_id == user_id,
            Referral.new_user_id == friend_id
        )
    )
    referral = referral.scalar_one_or_none()
    
    awarded_bonuses = set()
    if referral:
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
    result = await session.execute(
        select(Referral.new_user_id).where(Referral.old_user_id == user_id)
    )
    friend_ids = [row[0] for row in result.all()]
    
    if not friend_ids:
        return 0
    
    result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id.in_(friend_ids), Rental.status == "completed")
    )
    return result.scalar() or 0


async def is_team_bonus_awarded(session: AsyncSession, user_id: int) -> bool:
    """Проверяет, получен ли уже командный бонус 5000⭐ за 100000₽"""
    user = await session.get(User, user_id)
    return user.team_bonus_100k_awarded if user else False


async def award_team_bonus(session: AsyncSession, user_id: int, total_rentals: int) -> bool:
    """Начисляет командный бонус 5000⭐"""
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


async def update_referral_total_rentals(session: AsyncSession, referral_id: int) -> int:
    """Обновляет сумму аренд в записи реферала"""
    referral = await session.get(Referral, referral_id)
    if not referral:
        return 0
    
    result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    total = result.scalar() or 0
    
    referral.total_rentals_amount = total
    await session.commit()
    
    return total


async def send_admin_notification(bot_token: str, admin_ids: list, text: str):
    """Отправляет уведомление администраторам в Telegram"""
    import httpx
    for admin_id in admin_ids:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": admin_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload)
        except Exception as e:
            print(f"Failed to send notification to {admin_id}: {e}")


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
    return datetime.utcnow() + timedelta(days=90)


async def check_and_create_pending_bonuses(session, referral_id: int) -> list:
    """
    Проверяет, какие бонусы стали доступны, и создаёт записи в referral_bonuses
    Также удаляет бонусы, если условие больше не выполняется (например, после удаления аренды)
    """
    from .models import Referral, Rental, ReferralBonus
    
    referral = await session.get(Referral, referral_id)
    if not referral:
        print(f"❌ Referral {referral_id} not found")
        return []
    
    # Получаем сумму всех завершённых аренд
    total_result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    total = total_result.scalar() or 0
    
    # Получаем количество завершённых аренд
    count_result = await session.execute(
        select(func.count(Rental.id))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    rentals_count = count_result.scalar() or 0
    
    print(f"🔍 Referral {referral_id}: user_id={referral.new_user_id}, total={total}, count={rentals_count}")
    
    created_bonuses = []
    
    # Получаем информацию для уведомлений
    user = await session.get(User, referral.old_user_id)
    friend = await session.get(User, referral.new_user_id)
    
    # ----- Бонус за первую аренду -----
    if rentals_count >= 1:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "first_rental",
                ReferralBonus.status == "pending"
            )
        )
        if not existing.scalar_one_or_none():
            bonus = ReferralBonus(
                referral_id=referral_id,
                bonus_type="first_rental",
                amount=300,
                status="pending"
            )
            session.add(bonus)
            created_bonuses.append("first_rental")
            print(f"✅ Created bonus: first_rental for referral {referral_id}")
            
            # Уведомление администратору
            for admin_id in settings.ADMIN_IDS:
                await send_admin_notification(
                    settings.BOT_TOKEN,
                    [admin_id],
                    f"🔔 НОВЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                    f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                    f"👤 Друг: {friend.full_name if friend else '?'} (ID: {referral.new_user_id})\n"
                    f"📞 Телефон: {friend.phone if friend else '?'}\n\n"
                    f"🎯 Условие: первая аренда\n"
                    f"💰 Бонус: +300 ⭐\n\n"
                    f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
                )
    else:
        # Если нет аренд, удаляем бонус за первую аренду (если он есть)
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "first_rental",
                ReferralBonus.status == "pending"
            )
        )
        bonus = existing.scalar_one_or_none()
        if bonus:
            await session.delete(bonus)
            print(f"🗑️ Deleted bonus: first_rental for referral {referral_id} (no rentals)")
    
    # ----- Бонус за вторую аренду -----
    if rentals_count >= 2:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "second_rental",
                ReferralBonus.status == "pending"
            )
        )
        if not existing.scalar_one_or_none():
            bonus = ReferralBonus(
                referral_id=referral_id,
                bonus_type="second_rental",
                amount=700,
                status="pending"
            )
            session.add(bonus)
            created_bonuses.append("second_rental")
            print(f"✅ Created bonus: second_rental for referral {referral_id}")
            
            for admin_id in settings.ADMIN_IDS:
                await send_admin_notification(
                    settings.BOT_TOKEN,
                    [admin_id],
                    f"🔔 НОВЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                    f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                    f"👤 Друг: {friend.full_name if friend else '?'} (ID: {referral.new_user_id})\n"
                    f"📞 Телефон: {friend.phone if friend else '?'}\n\n"
                    f"🎯 Условие: вторая аренда\n"
                    f"💰 Бонус: +700 ⭐\n\n"
                    f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
                )
    else:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "second_rental",
                ReferralBonus.status == "pending"
            )
        )
        bonus = existing.scalar_one_or_none()
        if bonus:
            await session.delete(bonus)
            print(f"🗑️ Deleted bonus: second_rental for referral {referral_id}")
    
    # ----- Бонус за 10 000 ₽ -----
    if total >= 10000:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "threshold_10k",
                ReferralBonus.status == "pending"
            )
        )
        if not existing.scalar_one_or_none():
            bonus = ReferralBonus(
                referral_id=referral_id,
                bonus_type="threshold_10k",
                amount=1000,
                status="pending"
            )
            session.add(bonus)
            created_bonuses.append("threshold_10k")
            print(f"✅ Created bonus: threshold_10k for referral {referral_id}")
    else:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "threshold_10k",
                ReferralBonus.status == "pending"
            )
        )
        bonus = existing.scalar_one_or_none()
        if bonus:
            await session.delete(bonus)
            print(f"🗑️ Deleted bonus: threshold_10k for referral {referral_id}")
    
    # ----- Бонус за 30 000 ₽ -----
    if total >= 30000:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "threshold_30k",
                ReferralBonus.status == "pending"
            )
        )
        if not existing.scalar_one_or_none():
            bonus = ReferralBonus(
                referral_id=referral_id,
                bonus_type="threshold_30k",
                amount=1000,
                status="pending"
            )
            session.add(bonus)
            created_bonuses.append("threshold_30k")
            print(f"✅ Created bonus: threshold_30k for referral {referral_id}")
    else:
        existing = await session.execute(
            select(ReferralBonus).where(
                ReferralBonus.referral_id == referral_id,
                ReferralBonus.bonus_type == "threshold_30k",
                ReferralBonus.status == "pending"
            )
        )
        bonus = existing.scalar_one_or_none()
        if bonus:
            await session.delete(bonus)
            print(f"🗑️ Deleted bonus: threshold_30k for referral {referral_id}")
    
    if created_bonuses:
        await session.commit()
        print(f"🎉 Committed {len(created_bonuses)} bonuses for referral {referral_id}")
    else:
        await session.commit()
        print(f"⚠️ No new bonuses for referral {referral_id}")
    
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
    """Начисляет бонус пользователю"""
    bonus = await session.get(ReferralBonus, bonus_id)
    if not bonus or bonus.status != "pending":
        return False
    
    referral = await session.get(Referral, bonus.referral_id)
    if not referral:
        return False
    
    user = await session.get(User, referral.old_user_id)
    if not user:
        return False
    
    user.balance += bonus.amount
    user.points_expiry_date = calculate_expiry_date()
    
    transaction = Transaction(
        user_id=user.id,
        amount=bonus.amount,
        reason=f"Бонус за {get_bonus_type_name(bonus.bonus_type)} друга (ID: {referral.new_user_id})",
        admin_id=admin_id
    )
    session.add(transaction)
    
    bonus.status = "awarded"
    bonus.awarded_at = datetime.utcnow()
    bonus.awarded_by = admin_id
    
    if bonus.bonus_type == "first_rental":
        referral.status = "completed"
        referral.completion_date = datetime.utcnow()
    
    await session.commit()
    return True