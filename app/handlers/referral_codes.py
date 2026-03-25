from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func
from datetime import datetime, timedelta
import random
import string

from ..models import AsyncSessionLocal, User, ReferralCode, Referral, UserLog
from ..config import settings

router = Router()

ADMIN_IDS = settings.ADMIN_IDS

def generate_referral_code(owner_id: int) -> str:
    """Генерирует уникальный реферальный код"""
    chars = string.ascii_letters + string.digits
    code = ''.join(random.choice(chars) for _ in range(8))
    return f"{owner_id}_{code}"

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def show_my_links(telegram_id: int, message: Message):
    """Показывает список ссылок для пользователя"""
    if not is_admin(telegram_id):
        await message.answer("❌ Эта функция доступна только администраторам.")
        return
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Сначала зарегистрируйтесь через /start")
            return
        
        codes = await session.execute(
            select(ReferralCode)
            .where(
                ReferralCode.owner_id == user.id,
                ReferralCode.is_active == True
            )
            .order_by(ReferralCode.created_at.desc())
        )
        codes = codes.scalars().all()
        
        total_uses = sum(code.used_count for code in codes)
        
        stats_text = (
            f"🔗 **Управление ссылками (админ)**\n\n"
            f"📊 **Общая статистика:**\n"
            f"• Всего ссылок: {len(codes)}\n"
            f"• Всего переходов: {total_uses}\n\n"
        )
        
        await message.answer(stats_text, parse_mode="Markdown")
        
        bot_username = (await message.bot.get_me()).username
        
        for code in codes:
            link = f"https://t.me/{bot_username}?start={code.code}"
            
            # Сообщение 1: только ссылка (чистый текст)
            await message.answer(
                link,
                disable_web_page_preview=True
            )
            
            # Сообщение 2: тип ссылки, статистика, кнопки
            if code.is_permanent:
                link_type = "🔵 **Постоянная (основная)**"
            elif code.max_uses == 1:
                link_type = "🟡 **Одноразовая**"
            elif code.expires_at:
                link_type = "🟢 **Временная**"
            else:
                link_type = "⚪ **Дополнительная бессрочная**"
            
            expires = "бессрочно"
            if code.expires_at:
                expires = code.expires_at.strftime("%d.%m.%Y")
            
            limit = "∞" if code.max_uses == 0 else code.max_uses
            
            link_text = (
                f"{link_type}\n"
                f"📊 Использовано: {code.used_count}/{limit}\n"
                f"⏰ Действует до: {expires}\n"
            )
            
            keyboard_buttons = []
            
            if not code.is_permanent:
                keyboard_buttons.append(
                    InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_code_{code.id}")
                )
            
            if code.expires_at or code.max_uses == 1 or not code.is_permanent:
                keyboard_buttons.append(
                    InlineKeyboardButton(text="📊 Статистика", callback_data=f"code_stats_{code.id}")
                )
            
            if keyboard_buttons:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
                await message.answer(link_text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer(link_text, parse_mode="Markdown")
        
        create_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать новую ссылку", callback_data="admin_create_link")],
                [InlineKeyboardButton(text="◀️ Назад в главное меню", callback_data="back_to_main")]
            ]
        )
        await message.answer("🔧 **Действия:**", reply_markup=create_keyboard, parse_mode="Markdown")

@router.message(Command("my_links"))
async def cmd_my_links(message: Message):
    """Показывает все реферальные ссылки (только для админа)"""
    await show_my_links(message.from_user.id, message)

@router.message(F.text == "🔗 Управление ссылками")
async def manage_links_button(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Эта функция доступна только администраторам.")
        return
    await show_my_links(message.from_user.id, message)

@router.callback_query(F.data == "admin_create_link")
async def admin_create_link(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔵 Постоянная (основная)", callback_data="admin_create_permanent")],
            [InlineKeyboardButton(text="🟢 Временная (7 дней)", callback_data="admin_create_temp_7")],
            [InlineKeyboardButton(text="🟢 Временная (14 дней)", callback_data="admin_create_temp_14")],
            [InlineKeyboardButton(text="🟢 Временная (30 дней)", callback_data="admin_create_temp_30")],
            [InlineKeyboardButton(text="🟡 Одноразовая", callback_data="admin_create_single")],
            [InlineKeyboardButton(text="⚪ Дополнительная бессрочная", callback_data="admin_create_extra")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_links")]
        ]
    )
    
    await callback.message.edit_text(
        "🔗 **Создание новой ссылки**\n\n"
        "Выберите тип ссылки:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_create_permanent")
async def admin_create_permanent(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Ошибка: пользователь не найден")
            return
        
        existing = await session.execute(
            select(ReferralCode).where(
                ReferralCode.owner_id == user.id,
                ReferralCode.is_permanent == True,
                ReferralCode.is_active == True
            )
        )
        if existing.scalar_one_or_none():
            await callback.message.edit_text(
                "❌ У вас уже есть постоянная ссылка.\n"
                "Нельзя создать вторую постоянную ссылку."
            )
            return
        
        code = generate_referral_code(user.id)
        new_code = ReferralCode(
            code=code,
            owner_id=user.id,
            max_uses=0,
            expires_at=None,
            is_permanent=True
        )
        session.add(new_code)
        await session.commit()
        
        bot_username = (await callback.message.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"
        
        await callback.message.edit_text(
            f"✅ **Постоянная ссылка создана!**\n\n"
            f"👇 **Ссылка в следующем сообщении:**",
            parse_mode="Markdown"
        )
        
        await callback.message.answer(
            f"{link}",
            disable_web_page_preview=True
        )
    await callback.answer()

@router.callback_query(F.data == "admin_create_extra")
async def admin_create_extra(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Ошибка: пользователь не найден")
            return
        
        code = generate_referral_code(user.id)
        
        new_code = ReferralCode(
            code=code,
            owner_id=user.id,
            max_uses=0,
            expires_at=None,
            is_permanent=False
        )
        session.add(new_code)
        await session.commit()
        
        bot_username = (await callback.message.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"
        
        await callback.message.edit_text(
            f"✅ **Дополнительная ссылка создана!**\n\n"
            f"👇 **Ссылка в следующем сообщении:**",
            parse_mode="Markdown"
        )
        
        await callback.message.answer(
            f"{link}",
            disable_web_page_preview=True
        )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_create_temp_"))
async def admin_create_temp(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    days = int(callback.data.replace("admin_create_temp_", ""))
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Ошибка: пользователь не найден")
            return
        
        code = generate_referral_code(user.id)
        expires_at = datetime.utcnow() + timedelta(days=days)
        
        new_code = ReferralCode(
            code=code,
            owner_id=user.id,
            max_uses=0,
            expires_at=expires_at,
            is_permanent=False
        )
        session.add(new_code)
        await session.commit()
        
        bot_username = (await callback.message.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"
        
        await callback.message.edit_text(
            f"✅ **Временная ссылка создана!**\n"
            f"⏰ Действует до: {expires_at.strftime('%d.%m.%Y')}\n\n"
            f"👇 **Ссылка в следующем сообщении:**",
            parse_mode="Markdown"
        )
        
        await callback.message.answer(
            f"{link}",
            disable_web_page_preview=True
        )
    await callback.answer()

@router.callback_query(F.data == "admin_create_single")
async def admin_create_single(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    async with AsyncSessionLocal() as session:
        user = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Ошибка: пользователь не найден")
            return
        
        code = generate_referral_code(user.id)
        
        new_code = ReferralCode(
            code=code,
            owner_id=user.id,
            max_uses=1,
            expires_at=None,
            is_permanent=False
        )
        session.add(new_code)
        await session.commit()
        
        bot_username = (await callback.message.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code}"
        
        await callback.message.edit_text(
            f"✅ **Одноразовая ссылка создана!**\n"
            f"⚠️ Ссылка сгорит после первого использования.\n\n"
            f"👇 **Ссылка в следующем сообщении:**",
            parse_mode="Markdown"
        )
        
        await callback.message.answer(
            f"{link}",
            disable_web_page_preview=True
        )
    await callback.answer()

@router.callback_query(F.data.startswith("delete_code_"))
async def delete_code(callback: CallbackQuery):
    print(f"🔍 delete_code вызван от пользователя {callback.from_user.id}")
    print(f"🔍 ADMIN_IDS = {settings.ADMIN_IDS}")
    
    if not is_admin(callback.from_user.id):
        print(f"❌ Пользователь {callback.from_user.id} не является администратором")
        await callback.answer("❌ Эта функция доступна только администраторам.", show_alert=True)
        return
    
    code_id = int(callback.data.replace("delete_code_", ""))
    
    async with AsyncSessionLocal() as session:
        code = await session.get(ReferralCode, code_id)
        if code:
            if code.is_permanent:
                await callback.answer("❌ Нельзя удалить постоянную ссылку", show_alert=True)
                return
            
            code.is_active = False
            await session.commit()
            await callback.answer("✅ Ссылка удалена", show_alert=True)
    
    # Показываем обновлённый список ссылок
    await show_my_links(callback.from_user.id, callback.message)

@router.callback_query(F.data.startswith("code_stats_"))
async def code_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    code_id = int(callback.data.replace("code_stats_", ""))
    
    async with AsyncSessionLocal() as session:
        code = await session.get(ReferralCode, code_id)
        if not code:
            await callback.message.edit_text("❌ Ссылка не найдена")
            return
        
        bot_username = (await callback.message.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={code.code}"
        
        total_uses = code.used_count
        
        referrals = await session.execute(
            select(Referral)
            .where(Referral.old_user_id == code.owner_id)
            .order_by(Referral.registration_date.desc())
            .limit(10)
        )
        referrals = referrals.scalars().all()
        
        if code.is_permanent:
            link_type = "🔵 Постоянная (основная)"
        elif code.max_uses == 1:
            link_type = "🟡 Одноразовая"
        elif code.expires_at:
            link_type = "🟢 Временная"
        else:
            link_type = "⚪ Дополнительная бессрочная"
        
        text = (
            f"📊 **Статистика ссылки**\n\n"
            f"Тип: {link_type}\n"
            f"🔗 Ссылка:\n`{link}`\n\n"
            f"📅 Создана: {code.created_at.strftime('%d.%m.%Y')}\n"
            f"📊 Всего переходов: {total_uses}\n"
        )
        
        if code.expires_at:
            text += f"⏰ Истекает: {code.expires_at.strftime('%d.%m.%Y')}\n"
        
        if referrals:
            text += f"\n📋 **Зарегистрировались по ссылке:**\n"
            for ref in referrals[:5]:
                new_user = await session.get(User, ref.new_user_id)
                if new_user:
                    text += f"• {new_user.full_name} ({ref.registration_date.strftime('%d.%m.%Y')})\n"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_links")]
            ]
        )
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "admin_back_to_links")
async def admin_back_to_links(callback: CallbackQuery):
    await show_my_links(callback.from_user.id, callback.message)
    await callback.answer()