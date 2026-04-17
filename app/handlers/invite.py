from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from datetime import datetime
import random
import string

from ..models import AsyncSessionLocal, User, Referral, ReferralCode, UserLog
from ..config import settings
from ..keyboards import main_menu_keyboard

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
    
    # Сообщение 1: Заголовок
    await message.answer(
        "🎁 Пригласить друга в бот\n\n"
        "🔗 Ваша ссылка:"
    )
    
    # Сообщение 2: Только ссылка (отдельным сообщением для удобного копирования)
    await message.answer(
        link,
        disable_web_page_preview=True
    )
    
    # Сообщение 3: Инструкция и кнопки
    share_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="👥 Отправить другу в Telegram", 
                url=f"https://t.me/share/url?url={link}&text=🎁 Присоединяйся к программе лояльности! Переходи по ссылке и получи бонусы!"
            )],
            [InlineKeyboardButton(text="👥 Мои друзья", callback_data="my_friends_list")],
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


@router.message(F.text == "👥 Мои друзья")
async def show_friends_directly(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        if user.blacklisted:
            await message.answer("⛔ Вы заблокированы в системе лояльности.")
            return
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_friends",
            action_details="Просмотр списка друзей"
        )
        session.add(log)
        await session.commit()
        
        total_invited = await session.scalar(
            select(func.count()).where(Referral.old_user_id == user.id)
        ) or 0
        
        completed = await session.scalar(
            select(func.count()).where(
                Referral.old_user_id == user.id,
                Referral.status == "completed"
            )
        ) or 0
        
        referrals = await session.execute(
            select(Referral)
            .where(Referral.old_user_id == user.id)
            .order_by(Referral.registration_date.desc())
        )
        referrals = referrals.scalars().all()
        
        text = (
            f"👥 **Мои друзья**\n\n"
            f"📊 **Статистика:**\n"
            f"• Приглашено: **{total_invited}** друзей\n"
            f"• Подтвердили аренду: **{completed}**\n"
            f"• Заработано баллов: **{completed * settings.REFERRAL_BONUS}** ⭐\n\n"
        )
        
        if referrals:
            text += "📋 **Список приглашенных:**\n"
            for ref in referrals:
                status_emoji = "✅" if ref.status == "completed" else "⏳"
                new_user = await session.get(User, ref.new_user_id)
                if new_user:
                    date_str = ref.registration_date.strftime("%d.%m.%Y")
                    text += f"{status_emoji} {new_user.full_name} — {date_str}\n"
        else:
            text += "У вас пока нет приглашенных друзей."
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="back_to_invite")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ]
        )
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "my_friends_list")
async def show_friends_list(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.answer("Ошибка: пользователь не найден")
            return
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_friends",
            action_details="Просмотр списка друзей (callback)"
        )
        session.add(log)
        await session.commit()
        
        total_invited = await session.scalar(
            select(func.count()).where(Referral.old_user_id == user.id)
        ) or 0
        
        completed = await session.scalar(
            select(func.count()).where(
                Referral.old_user_id == user.id,
                Referral.status == "completed"
            )
        ) or 0
        
        referrals = await session.execute(
            select(Referral)
            .where(Referral.old_user_id == user.id)
            .order_by(Referral.registration_date.desc())
        )
        referrals = referrals.scalars().all()
        
        text = (
            f"👥 **Мои друзья**\n\n"
            f"📊 **Статистика:**\n"
            f"• Приглашено: **{total_invited}** друзей\n"
            f"• Подтвердили аренду: **{completed}**\n"
            f"• Заработано баллов: **{completed * settings.REFERRAL_BONUS}** ⭐\n\n"
        )
        
        if referrals:
            text += "📋 **Список приглашенных:**\n"
            for ref in referrals:
                status_emoji = "✅" if ref.status == "completed" else "⏳"
                new_user = await session.get(User, ref.new_user_id)
                if new_user:
                    date_str = ref.registration_date.strftime("%d.%m.%Y")
                    text += f"{status_emoji} {new_user.full_name} — {date_str}\n"
        else:
            text += "У вас пока нет приглашенных друзей."
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="back_to_invite")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ]
        )
        
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("copy_link_"))
async def copy_link_callback(callback: CallbackQuery):
    code = callback.data.replace("copy_link_", "")
    bot_username = (await callback.message.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    
    await callback.answer(
        "✅ Ссылка скопирована! Теперь вы можете отправить её другу.",
        show_alert=True
    )


@router.callback_query(F.data == "back_to_invite")
async def back_to_invite(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.answer("Ошибка: пользователь не найден")
            return
        
        bot_username = (await callback.message.bot.get_me()).username
        code = await get_or_create_permanent_link(user.id, bot_username, session)
        link = f"https://t.me/{bot_username}?start={code}"
        
        share_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="👥 Отправить другу в Telegram", 
                    url=f"https://t.me/share/url?url={link}&text=🎁 Присоединяйся к программе лояльности! Переходи по ссылке и получи бонусы!"
                )],
                [InlineKeyboardButton(text="👥 Мои друзья", callback_data="my_friends_list")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ]
        )
        
        # Сообщение 1: Заголовок
        await callback.message.answer(
            "🎁 Пригласить друга в бот\n\n"
            "🔗 Ваша ссылка:"
        )
        
        # Сообщение 2: Только ссылка
        await callback.message.answer(
            link,
            disable_web_page_preview=True
        )
        
        # Сообщение 3: Инструкция и кнопки
        await callback.message.answer(
            "📱 Как поделиться:\n"
            "1️⃣ Нажмите на ссылку выше, чтобы выделить её\n"
            "2️⃣ Скопируйте ссылку\n"
            "3️⃣ Отправьте другу\n\n"
            "Или нажмите кнопку ниже, чтобы отправить через Telegram:\n\n"
            f"За каждого друга, который совершит первую аренду, вы получите **{settings.REFERRAL_BONUS}** баллов.",
            reply_markup=share_keyboard,
            parse_mode="Markdown"
        )
        await callback.message.delete()
    await callback.answer()