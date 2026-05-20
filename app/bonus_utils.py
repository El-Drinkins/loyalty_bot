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
            'bonus': 200
        },
        'second_rental': {
            'achieved': rentals_count >= 2,
            'awarded': 'second_rental' in awarded_bonuses,
            'bonus': 800
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
    """Проверяет, получен ли уже командный бонус 5000⭐ за 100000₽ (awarded или pending)"""
    # Проверяем, есть ли awarded или pending командный бонус у пользователя
    user = await session.get(User, user_id)
    if user and user.team_bonus_100k_awarded:
        return True
    
    # Также проверяем через referral_bonuses
    result = await session.execute(
        select(ReferralBonus).join(Referral).where(
            Referral.old_user_id == user_id,
            ReferralBonus.bonus_type == "team_100k",
            ReferralBonus.status.in_(["awarded", "pending"])
        )
    )
    return result.scalar_one_or_none() is not None


async def award_team_bonus(session: AsyncSession, user_id: int, total_rentals: int) -> bool:
    """
    Больше не начисляет автоматически.
    Вместо этого создаётся pending-бонус, который админ должен подтвердить.
    """
    # Эта функция больше не используется для автоматического начисления.
    # Бонус создаётся через check_and_create_pending_bonuses.
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
        "threshold_30k": "аренды на 30000₽",
        "team_100k": "командный бонус 100 000 ₽"
    }
    return names.get(bonus_type, bonus_type)


def calculate_expiry_date() -> datetime:
    """Возвращает дату истечения срока баллов (из настроек)"""
    return datetime.utcnow() + timedelta(days=settings.POINTS_VALID_DAYS)


async def check_and_create_pending_bonuses(session, referral_id: int) -> list:
    """
    Проверяет, какие бонусы стали доступны, и создаёт записи в referral_bonuses
    Также удаляет бонусы, если условие больше не выполняется.
    НЕ создаёт новые бонусы, если такой бонус уже был начислен (awarded) или ожидает (pending).
    """
    from .models import Referral, Rental, ReferralBonus
    
    referral = await session.get(Referral, referral_id)
    if not referral:
        print(f"❌ Referral {referral_id} not found")
        return []
    
    total_result = await session.execute(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    total = total_result.scalar() or 0
    
    count_result = await session.execute(
        select(func.count(Rental.id))
        .where(Rental.user_id == referral.new_user_id, Rental.status == "completed")
    )
    rentals_count = count_result.scalar() or 0
    
    print(f"🔍 Referral {referral_id}: user_id={referral.new_user_id}, total={total}, count={rentals_count}")
    
    created_bonuses = []
    
    user = await session.get(User, referral.old_user_id)
    friend = await session.get(User, referral.new_user_id)
    
    # Проверяем, какие бонусы уже были начислены (awarded) или ожидают (pending)
    existing_result = await session.execute(
        select(ReferralBonus.bonus_type, ReferralBonus.status).where(
            ReferralBonus.referral_id == referral_id,
            ReferralBonus.status.in_(["awarded", "pending"])
        )
    )
    existing_types = set(row[0] for row in existing_result.all())
    
    # Бонус за первую аренду
    if rentals_count >= 1 and "first_rental" not in existing_types:
        bonus = ReferralBonus(
            referral_id=referral_id,
            bonus_type="first_rental",
            amount=200,
            status="pending"
        )
        session.add(bonus)
        created_bonuses.append("first_rental")
        print(f"✅ Created bonus: first_rental for referral {referral_id}")
        
        for admin_id in settings.ADMIN_IDS:
            await send_admin_notification(
                settings.BOT_TOKEN,
                [admin_id],
                f"🔔 НОВЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                f"👤 Друг: {friend.full_name if friend else '?'} (ID: {referral.new_user_id})\n"
                f"📞 Телефон: {friend.phone if friend else '?'}\n\n"
                f"🎯 Условие: первая аренда\n"
                f"💰 Бонус: +200 ⭐\n\n"
                f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
            )
    
    # Бонус за вторую аренду
    if rentals_count >= 2 and "second_rental" not in existing_types:
        bonus = ReferralBonus(
            referral_id=referral_id,
            bonus_type="second_rental",
            amount=800,
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
                f"💰 Бонус: +800 ⭐\n\n"
                f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
            )
    
    # Бонус за 10 000 ₽
    if total >= 10000 and "threshold_10k" not in existing_types:
        bonus = ReferralBonus(
            referral_id=referral_id,
            bonus_type="threshold_10k",
            amount=1000,
            status="pending"
        )
        session.add(bonus)
        created_bonuses.append("threshold_10k")
        print(f"✅ Created bonus: threshold_10k for referral {referral_id}")
        
        for admin_id in settings.ADMIN_IDS:
            await send_admin_notification(
                settings.BOT_TOKEN,
                [admin_id],
                f"🔔 НОВЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                f"👤 Друг: {friend.full_name if friend else '?'} (ID: {referral.new_user_id})\n"
                f"📞 Телефон: {friend.phone if friend else '?'}\n\n"
                f"🎯 Условие: сумма аренд достигла 10 000 ₽\n"
                f"💰 Бонус: +1000 ⭐\n\n"
                f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
            )
    
    # Бонус за 30 000 ₽
    if total >= 30000 and "threshold_30k" not in existing_types:
        bonus = ReferralBonus(
            referral_id=referral_id,
            bonus_type="threshold_30k",
            amount=1000,
            status="pending"
        )
        session.add(bonus)
        created_bonuses.append("threshold_30k")
        print(f"✅ Created bonus: threshold_30k for referral {referral_id}")
        
        for admin_id in settings.ADMIN_IDS:
            await send_admin_notification(
                settings.BOT_TOKEN,
                [admin_id],
                f"🔔 НОВЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                f"👤 Друг: {friend.full_name if friend else '?'} (ID: {referral.new_user_id})\n"
                f"📞 Телефон: {friend.phone if friend else '?'}\n\n"
                f"🎯 Условие: сумма аренд достигла 30 000 ₽\n"
                f"💰 Бонус: +1000 ⭐\n\n"
                f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
            )
    
    # Командный бонус за 100 000 ₽ (сумма аренд ВСЕХ друзей)
    all_friends_total = await get_all_friends_total_rentals(session, referral.old_user_id)
    if all_friends_total >= 100000 and "team_100k" not in existing_types:
        # Проверяем, нет ли уже team_100k бонуса у этого пользователя в любом реферале
        team_bonus_exists = await session.execute(
            select(ReferralBonus).join(Referral).where(
                Referral.old_user_id == referral.old_user_id,
                ReferralBonus.bonus_type == "team_100k",
                ReferralBonus.status.in_(["awarded", "pending"])
            )
        )
        if not team_bonus_exists.scalar_one_or_none():
            bonus = ReferralBonus(
                referral_id=referral_id,
                bonus_type="team_100k",
                amount=5000,
                status="pending"
            )
            session.add(bonus)
            created_bonuses.append("team_100k")
            print(f"✅ Created bonus: team_100k for user {referral.old_user_id}")
            
            for admin_id in settings.ADMIN_IDS:
                await send_admin_notification(
                    settings.BOT_TOKEN,
                    [admin_id],
                    f"🔔 НОВЫЙ КОМАНДНЫЙ БОНУС ДЛЯ ПОДТВЕРЖДЕНИЯ!\n\n"
                    f"👥 Пользователь: {user.full_name if user else '?'} (ID: {referral.old_user_id})\n"
                    f"📊 Сумма аренд всех друзей: {all_friends_total} ₽\n\n"
                    f"🎯 Условие: общие аренды всех друзей достигли 100 000 ₽\n"
                    f"💰 Бонус: +5000 ⭐\n\n"
                    f"➡️ Подтвердить в админке: /admin/referral_detail/{referral_id}"
                )
    
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
    
    # Получаем имя друга
    friend = await session.get(User, referral.new_user_id)
    friend_name = friend.full_name if friend else f"ID: {referral.new_user_id}"
    
    user.balance += bonus.amount
    user.points_expiry_date = calculate_expiry_date()
    
    transaction = Transaction(
        user_id=user.id,
        amount=bonus.amount,
        reason=f"Бонус за {get_bonus_type_name(bonus.bonus_type)} друга ({friend_name})" if bonus.bonus_type != "team_100k" else f"Командный бонус за суммарную аренду друзей на 100 000 ₽",
        admin_id=admin_id
    )
    session.add(transaction)
    
    bonus.status = "awarded"
    bonus.awarded_at = datetime.utcnow()
    bonus.awarded_by = admin_id
    
    if bonus.bonus_type == "first_rental":
        referral.status = "completed"
        referral.completion_date = datetime.utcnow()
    
    if bonus.bonus_type == "team_100k":
        user.team_bonus_100k_awarded = True
    
    await session.commit()
    
    # === УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЮ ===
    try:
        from app.notifications import send_telegram_notification
        
        bonus_name = get_bonus_type_name(bonus.bonus_type)
        message = (
            f"🎉 Вам начислен бонус!\n\n"
            f"💰 +{bonus.amount} ⭐\n"
            f"📋 За: {bonus_name} друга ({friend_name})\n" if bonus.bonus_type != "team_100k" else f"📋 Командный бонус за суммарную аренду друзей на 100 000 ₽.\n"
            f"💳 Ваш баланс: {user.balance} ⭐\n\n"
            f"Спасибо, что приглашаете друзей!"
        )
        await send_telegram_notification(user.telegram_id, message)
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {user.telegram_id}: {e}")
    
    return True