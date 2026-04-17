from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from datetime import datetime
import random
import string

from ..models import AsyncSessionLocal, User, Referral, ReferralCode, UserLog, Transaction
from ..config import settings
from ..keyboards import main_menu_keyboard
from ..bonus_utils import (
    get_friend_rentals_total,
    get_friend_rentals_count,
    get_friend_bonuses_status,
    get_all_friends_total_rentals,
    is_team_bonus_awarded,
    award_team_bonus,
    format_progress_bar,
    format_number
)

router = Router()


def generate_referral_code(owner_id: int) -> str:
    chars = string.ascii_letters + string.digits
    code = ''.join(random.choice(chars) for _ in range(8))
    return f"{owner_id}_{code}"


async def get_or_create_permanent_link(user_id: int, bot_username: str, session):
    code_record = await session.execute(
        select(ReferralCode).where(
            ReferralCode.owner_id == user_id,
            ReferralCode.is_permanent == True,
            ReferralCode.is_active == True
        )
    )
    code_record = code_record.scalar_one_or_none()
    
    if code_record:
        return code_record.code
    
    code = generate_referral_code(user_id)
    new_code = ReferralCode(
        code=code,
        owner_id=user_id,
        max_uses=0,
        expires_at=None,
        is_permanent=True
    )
    session.add(new_code)
    await session.commit()
    return code


async def get_friends_list_with_details(session, user_id: int) -> list:
    """Получает список друзей с суммой аренд и количеством аренд"""
    result = await session.execute(
        select(Referral, User)
        .join(User, User.id == Referral.new_user_id)
        .where(Referral.old_user_id == user_id)
        .order_by(Referral.registration_date.desc())
    )
    referrals = result.all()
    
    friends = []
    for ref, friend in referrals:
        total_rentals = await get_friend_rentals_total(session, friend.id)
        rentals_count = await get_friend_rentals_count(session, friend.id)
        
        friends.append({
            "id": friend.id,
            "full_name": friend.full_name,
            "registration_date": ref.registration_date.strftime("%d.%m.%Y"),
            "status": ref.status,
            "total_rentals": total_rentals,
            "rentals_count": rentals_count,
            "status_emoji": "✅" if ref.status == "completed" else "⏳"
        })
    
    return friends


async def send_friends_list(message: Message, user_id: int):
    """Формирует и отправляет сообщение со списком друзей"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        if user.blacklisted:
            await message.answer("⛔ Вы заблокированы в системе лояльности.")
            return
        
        # Получаем список друзей
        friends = await get_friends_list_with_details(session, user.id)
        
        total_invited = len(friends)
        completed = sum(1 for f in friends if f["status"] == "completed")
        
        # Сумма аренд всех друзей
        total_friends_rentals = await get_all_friends_total_rentals(session, user.id)
        
        # Заработанные баллы (из транзакций пользователя)
        earned_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.user_id == user.id, Transaction.amount > 0)
        )
        earned = earned_result.scalar() or 0
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_friends",
            action_details=f"Просмотр друзей (приглашено: {total_invited})"
        )
        session.add(log)
        await session.commit()
        
        # Формируем сообщение
        lines = []
        
        # Заголовок
        lines.append("👥 **Мои друзья**\n")
        
        # Статистика
        lines.append("📊 **Статистика:**")
        lines.append(f"• Приглашено: {total_invited}")
        lines.append(f"• Подтвердили аренду: {completed}")
        lines.append(f"• Заработано баллов: {format_number(earned)} ⭐")
        lines.append(f"• 💰 Сумма аренд друзей: {format_number(total_friends_rentals)} ₽\n")
        
        # Общий прогресс друзей (командный бонус)
        team_bonus_awarded = await is_team_bonus_awarded(session, user.id)
        
        if total_friends_rentals >= 100000 and team_bonus_awarded:
            lines.append("🏆 **Командный бонус:**")
            lines.append(f"   ✅ Бонус 5 000 ⭐ получен за 100 000 ₽!\n")
        else:
            lines.append("🏆 **Общий прогресс друзей:**")
            progress_bar = format_progress_bar(total_friends_rentals, 100000)
            lines.append(f"   {progress_bar} {format_number(total_friends_rentals)} / 100 000 ₽")
            remaining = 100000 - total_friends_rentals
            lines.append(f"   🎯 Осталось {format_number(remaining)} ₽ до бонуса 5 000 ⭐\n")
        
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        
        # Список друзей
        if friends:
            for friend in friends:
                status_emoji = friend["status_emoji"]
                total = format_number(friend["total_rentals"])
                lines.append(f"{status_emoji} {friend['full_name']} — {friend['registration_date']} — {total} ₽")
                
                # Кнопка деталей будет отдельно, в клавиатуре
                lines.append("")  # отступ перед кнопкой
        else:
            lines.append("📭 У вас пока нет приглашённых друзей.")
        
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        
        # Легенда бонусов
        lines.append("💡 **Бонусы за друзей (суммируются):**")
        lines.append("   📌 Первая аренда друга → 300 ⭐")
        lines.append("   📌 Вторая аренда друга → 700 ⭐")
        lines.append("   📌 Аренды на 10 000 ₽ → +1 000 ⭐")
        lines.append("   📌 Аренды на 30 000 ₽ → +1 000 ⭐")
        lines.append("   🏆 Общие аренды ВСЕХ друзей на 100 000 ₽ → +5 000 ⭐")
        
        # Формируем инлайн-кнопки для каждого друга
        keyboard_buttons = []
        for friend in friends:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📊 {friend['full_name']} — детали",
                    callback_data=f"friend_details_{friend['id']}"
                )
            ])
        
        # Кнопка обновления
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_friends")
        ])
        
        # Кнопка назад
        keyboard_buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


async def send_friend_details(callback: CallbackQuery, friend_id: int):
    """Отправляет детальную информацию о бонусах по другу"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.answer("Ошибка: пользователь не найден")
            return
        
        friend = await session.get(User, friend_id)
        if not friend:
            await callback.answer("Друг не найден")
            return
        
        # Получаем статус бонусов
        bonuses = await get_friend_bonuses_status(session, user.id, friend_id)
        total_amount = await get_friend_rentals_total(session, friend_id)
        
        lines = []
        lines.append(f"📊 **Бонусы по другу: {friend.full_name}**\n")
        lines.append(f"💰 Аренды друга на: {format_number(total_amount)} ₽\n")
        
        # Бонус за первую аренду
        first = bonuses['first_rental']
        if first['achieved'] and first['awarded']:
            lines.append("🏆 **За первую аренду:**")
            lines.append(f"   ✅ Получен: {first['bonus']} ⭐\n")
        elif first['achieved'] and not first['awarded']:
            lines.append("🏆 **За первую аренду:**")
            lines.append(f"   ⏳ Ожидает подтверждения администратора\n")
        else:
            lines.append("🏆 **За первую аренду:**")
            lines.append(f"   ⏳ Ожидается первая аренда\n")
        
        # Бонус за вторую аренду
        second = bonuses['second_rental']
        if second['achieved'] and second['awarded']:
            lines.append("🏆 **За вторую аренду:**")
            lines.append(f"   ✅ Получен: {second['bonus']} ⭐\n")
        elif second['achieved'] and not second['awarded']:
            lines.append("🏆 **За вторую аренду:**")
            lines.append(f"   ⏳ Ожидает подтверждения администратора\n")
        else:
            lines.append("🏆 **За вторую аренду:**")
            lines.append(f"   ⏳ Нужна вторая аренда\n")
        
        # Бонус за 10 000 ₽
        threshold_10k = bonuses['threshold_10k']
        if threshold_10k['achieved'] and threshold_10k['awarded']:
            lines.append(f"🎉 Бонус {threshold_10k['bonus']} ⭐ получен (за 10 000 ₽)\n")
        elif threshold_10k['achieved'] and not threshold_10k['awarded']:
            lines.append(f"🎉 Бонус {threshold_10k['bonus']} ⭐ ожидает начисления (за 10 000 ₽)\n")
        else:
            progress_bar = format_progress_bar(threshold_10k['progress'], threshold_10k['target'])
            lines.append(f"🎯 Бонус {threshold_10k['bonus']} ⭐ за 10 000 ₽:")
            lines.append(f"   {progress_bar} {format_number(threshold_10k['progress'])} / {format_number(threshold_10k['target'])} ₽")
            remaining = threshold_10k['target'] - threshold_10k['progress']
            lines.append(f"   🎯 Осталось {format_number(remaining)} ₽ → +{threshold_10k['bonus']} ⭐\n")
        
        # Бонус за 30 000 ₽
        threshold_30k = bonuses['threshold_30k']
        if threshold_30k['achieved'] and threshold_30k['awarded']:
            lines.append(f"🎉 Бонус {threshold_30k['bonus']} ⭐ получен (за 30 000 ₽)\n")
        elif threshold_30k['achieved'] and not threshold_30k['awarded']:
            lines.append(f"🎉 Бонус {threshold_30k['bonus']} ⭐ ожидает начисления (за 30 000 ₽)\n")
        else:
            progress_bar = format_progress_bar(threshold_30k['progress'], threshold_30k['target'])
            lines.append(f"🎯 Бонус {threshold_30k['bonus']} ⭐ за 30 000 ₽:")
            lines.append(f"   {progress_bar} {format_number(threshold_30k['progress'])} / {format_number(threshold_30k['target'])} ₽")
            remaining = threshold_30k['target'] - threshold_30k['progress']
            lines.append(f"   🎯 Осталось {format_number(remaining)} ₽ → +{threshold_30k['bonus']} ⭐\n")
        
        # Проверяем и начисляем командный бонус (если нужно)
        total_friends_rentals = await get_all_friends_total_rentals(session, user.id)
        await award_team_bonus(session, user.id, total_friends_rentals)
        
        # Кнопка закрытия
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✖️ Закрыть", callback_data="close_details")]
            ]
        )
        
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()


@router.message(F.text == "👥 Мои друзья")
async def my_friends_button(message: Message):
    """Обработчик кнопки 'Мои друзья'"""
    await send_friends_list(message, message.from_user.id)


@router.callback_query(F.data == "refresh_friends")
async def refresh_friends(callback: CallbackQuery):
    """Обновляет список друзей"""
    await callback.message.delete()
    await send_friends_list(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("friend_details_"))
async def friend_details_callback(callback: CallbackQuery):
    """Обработчик кнопки деталей друга"""
    friend_id = int(callback.data.split("_")[2])
    await send_friend_details(callback, friend_id)


@router.callback_query(F.data == "close_details")
async def close_details(callback: CallbackQuery):
    """Закрывает детальное сообщение"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()