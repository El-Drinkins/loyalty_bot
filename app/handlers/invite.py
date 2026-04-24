from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
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

# Разделитель (10 символов, не переносится на мобильных)
SEPARATOR = "➖➖➖➖➖➖➖➖➖➖"

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
    """Получает список друзей с суммой аренд"""
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
        
        friends.append({
            "id": friend.id,
            "full_name": friend.full_name,
            "registration_date": ref.registration_date.strftime("%d.%m.%Y"),
            "status": ref.status,
            "total_rentals": total_rentals,
            "status_emoji": "✅" if ref.status == "completed" else "⏳"
        })
    
    return friends

async def send_friends_list(message: Message, user_id: int):
    """Отправляет основное сообщение со списком друзей и статистикой"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        if user.blacklisted:
            await message.answer("⛔ Вы заблокированы в системе лояльности.")
            return
        
        friends = await get_friends_list_with_details(session, user.id)
        
        total_invited = len(friends)
        completed = sum(1 for f in friends if f["status"] == "completed")
        total_friends_rentals = await get_all_friends_total_rentals(session, user.id)
        
        earned_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.user_id == user.id, Transaction.amount > 0)
        )
        earned = earned_result.scalar() or 0
        
        log = UserLog(
            user_id=user.id,
            action_type="view_friends",
            action_details=f"Просмотр друзей (приглашено: {total_invited})"
        )
        session.add(log)
        await session.commit()
        
        lines = []
        
        # Заголовок и статистика
        lines.append("👥 **Мои друзья**\n")
        lines.append("📊 **Статистика:**")
        lines.append(f"• Приглашено: {total_invited}")
        lines.append(f"• Подтвердили аренду: {completed}")
        lines.append(f"• Заработано баллов: {format_number(earned)} ⭐")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        
        # Бонусы за друзей (легенда)
        lines.append("💡 **Бонусы за друзей (суммируются):**")
        lines.append("   📌 Первая аренда друга → 300 ⭐")
        lines.append("   📌 Вторая аренда друга → 700 ⭐")
        lines.append("   📌 Аренды друга на 10 000 ₽ → +1 000 ⭐")
        lines.append("   📌 Аренды друга на 30 000 ₽ → +1 000 ⭐")
        lines.append("   🏆 Общие аренды ВСЕХ друзей на 100 000 ₽ → +5 000 ⭐")
        lines.append("")
        lines.append(SEPARATOR)
        lines.append("")
        
        # Общий прогресс друзей
        lines.append("🏆 **Общий прогресс друзей**\n")
        lines.append(f"• Сумма аренд всех ваших друзей: {format_number(total_friends_rentals)} ₽")
        lines.append(f"• Цель: 100 000 ₽")
        lines.append("")
        lines.append("🎁 Когда друзья суммарно арендуют на 100 000 ₽,")
        lines.append("   вы получите +5 000 ⭐")
        lines.append("")
        lines.append(SEPARATOR)
        
        # Кнопка статистики по друзьям
        keyboard_buttons = []
        
        if total_invited > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📊 Статистика по друзьям ({total_invited})",
                    callback_data="show_friends_list"
                )
            ])
        else:
            keyboard_buttons.append([
                InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="back_to_invite")
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await message.answer(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

async def send_friends_choice(message: Message, user_id: int):
    """Отправляет сообщение с выбором друга"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        friends = await get_friends_list_with_details(session, user.id)
        
        if not friends:
            await message.answer("👥 У вас пока нет приглашённых друзей.")
            return
        
        # Сортируем: новые пользователи сверху (уже отсортировано в get_friends_list_with_details)
        buttons = []
        for friend in friends:
            total = format_number(friend["total_rentals"])
            buttons.append([
                InlineKeyboardButton(
                    text=f"👤 {friend['full_name']} — {total} ₽",
                    callback_data=f"friend_detail_{friend['id']}"
                )
            ])
        
        buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_friends_main")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            "🔍 **Выберите друга**\n\nЧтобы посмотреть подробную статистику по бонусам:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

async def send_friend_detail(message: Message, friend_id: int, user_telegram_id: int):
    """Отправляет детальную статистику по конкретному другу"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_telegram_id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        friend = await session.get(User, friend_id)
        if not friend:
            await message.answer("❌ Друг не найден")
            return
        
        # Проверяем, что этот друг действительно приглашён пользователем
        referral = await session.execute(
            select(Referral).where(
                Referral.old_user_id == user.id,
                Referral.new_user_id == friend_id
            )
        )
        if not referral.scalar_one_or_none():
            await message.answer("❌ Этот пользователь не является вашим другом")
            return
        
        bonuses = await get_friend_bonuses_status(session, user.id, friend_id)
        total_amount = await get_friend_rentals_total(session, friend_id)
        
        lines = []
        lines.append(f"📊 **Бонусы по другу: {friend.full_name}**\n")
        lines.append(f"💰 Аренды друга на: {format_number(total_amount)} ₽\n")
        
        # Бонус за первую аренду
        first = bonuses['first_rental']
        lines.append("🏆 **За первую аренду:**")
        if first['achieved'] and first['awarded']:
            lines.append(f"   ✅ Получен: {first['bonus']} ⭐")
        elif first['achieved'] and not first['awarded']:
            lines.append(f"   ⏳ Ожидает подтверждения администратора")
        else:
            lines.append(f"   ⏳ Ожидается первая аренда")
        lines.append("")
        
        # Бонус за вторую аренду
        second = bonuses['second_rental']
        lines.append("🏆 **За вторую аренду:**")
        if second['achieved'] and second['awarded']:
            lines.append(f"   ✅ Получен: {second['bonus']} ⭐")
        elif second['achieved'] and not second['awarded']:
            lines.append(f"   ⏳ Ожидает подтверждения администратора")
        else:
            lines.append(f"   ⏳ Нужна вторая аренда")
        lines.append("")
        
        # Бонус за 10 000 ₽
        threshold_10k = bonuses['threshold_10k']
        lines.append("🏆 **За аренды на 10 000 ₽**")
        lines.append("   (когда друг арендует на 10 000 ₽, вы получите +1 000 ⭐)")
        lines.append("")
        lines.append(f"   Цель: {format_number(threshold_10k['target'])} ₽")
        lines.append(f"   Заработано: {format_number(threshold_10k['progress'])} ₽")
        
        if threshold_10k['achieved'] and threshold_10k['awarded']:
            lines.append(f"   ✅ Бонус {threshold_10k['bonus']} ⭐ получен")
        elif threshold_10k['achieved'] and not threshold_10k['awarded']:
            lines.append(f"   ⏳ Бонус {threshold_10k['bonus']} ⭐ ожидает подтверждения администратора")
        else:
            remaining = threshold_10k['target'] - threshold_10k['progress']
            lines.append(f"   Осталось: {format_number(remaining)} ₽")
            lines.append("")
            lines.append(f"   🎯 Когда друг арендует ещё на {format_number(remaining)} ₽,")
            lines.append(f"      вы получите +{threshold_10k['bonus']} ⭐")
        lines.append("")
        
        # Бонус за 30 000 ₽
        threshold_30k = bonuses['threshold_30k']
        lines.append("🏆 **За аренды на 30 000 ₽**")
        lines.append("   (когда друг арендует на 30 000 ₽, вы получите +1 000 ⭐)")
        lines.append("")
        lines.append(f"   Цель: {format_number(threshold_30k['target'])} ₽")
        lines.append(f"   Заработано: {format_number(threshold_30k['progress'])} ₽")
        
        if threshold_30k['achieved'] and threshold_30k['awarded']:
            lines.append(f"   ✅ Бонус {threshold_30k['bonus']} ⭐ получен")
        elif threshold_30k['achieved'] and not threshold_30k['awarded']:
            lines.append(f"   ⏳ Бонус {threshold_30k['bonus']} ⭐ ожидает подтверждения администратора")
        else:
            remaining = threshold_30k['target'] - threshold_30k['progress']
            lines.append(f"   Осталось: {format_number(remaining)} ₽")
            lines.append("")
            lines.append(f"   🎯 Когда друг арендует ещё на {format_number(remaining)} ₽,")
            lines.append(f"      вы получите +{threshold_30k['bonus']} ⭐")
        
        # Проверяем командный бонус
        total_friends_rentals = await get_all_friends_total_rentals(session, user.id)
        await award_team_bonus(session, user.id, total_friends_rentals)
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к списку друзей", callback_data="back_to_friends_choice")]
            ]
        )
        
        await message.answer(
            "\n".join(lines),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@router.message(F.text == "👥 Мои друзья")
async def my_friends_button(message: Message):
    await send_friends_list(message, message.from_user.id)

@router.message(Command("friends"))
async def cmd_friends(message: Message):
    await send_friends_list(message, message.from_user.id)

@router.callback_query(F.data == "show_friends_list")
async def show_friends_list_callback(callback: CallbackQuery):
    """Показывает список друзей для выбора"""
    await callback.message.delete()
    await send_friends_choice(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "back_to_friends_main")
async def back_to_friends_main_callback(callback: CallbackQuery):
    """Возврат к основному сообщению со списком друзей"""
    await callback.message.delete()
    await send_friends_list(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "back_to_friends_choice")
async def back_to_friends_choice_callback(callback: CallbackQuery):
    """Возврат к выбору друга"""
    await callback.message.delete()
    await send_friends_choice(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data.startswith("friend_detail_"))
async def friend_detail_callback(callback: CallbackQuery):
    """Показывает детальную статистику друга"""
    friend_id = int(callback.data.split("_")[2])
    await callback.message.delete()
    await send_friend_detail(callback.message, friend_id, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_invite")
async def back_to_invite_callback(callback: CallbackQuery):
    await callback.message.delete()
    from .invite import invite_friend
    await invite_friend(callback.message)
    await callback.answer()

@router.message(F.text == "🎁 Пригласить друга в бот")
async def invite_friend(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        if user.blacklisted:
            await message.answer("⛔ Вы заблокированы в системе лояльности.")
            return
        
        bot_username = (await message.bot.get_me()).username
        code = await get_or_create_permanent_link(user.id, bot_username, session)
        link = f"https://t.me/{bot_username}?start={code}"
        
        log = UserLog(
            user_id=user.id,
            action_type="invite_friend",
            action_details="Открыл страницу приглашения"
        )
        session.add(log)
        await session.commit()
    
    await message.answer(
        "🎁 Пригласить друга в бот\n\n"
        "🔗 Ваша ссылка:"
    )
    
    await message.answer(
        link,
        disable_web_page_preview=True
    )
    
    share_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="👥 Отправить другу в Telegram", 
                url=f"https://t.me/share/url?url={link}&text=🎁 Присоединяйся к программе лояльности! Переходи по ссылке и получи бонусы!"
            )],
            [InlineKeyboardButton(text="👥 Мои друзья", callback_data="show_friends_list")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
        ]
    )
    
    await message.answer(
        "📱 Как поделиться:\n"
        "1️⃣ Нажмите на ссылку выше, чтобы выделить её\n"
        "2️⃣ Скопируйте ссылку\n"
        "3️⃣ Отправьте другу\n\n"
        "Или нажмите кнопку ниже, чтобы отправить через Telegram:\n\n"
        f"За каждого друга, который совершит первую аренду, вы получите **{settings.REFERRAL_BONUS}** баллов.",
        reply_markup=share_keyboard,
        parse_mode="Markdown"
    )

async def show_friends_directly(message: Message):
    """Для обратной совместимости с menu.py"""
    await send_friends_list(message, message.from_user.id)