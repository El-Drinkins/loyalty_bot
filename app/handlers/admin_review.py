from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select
from datetime import datetime, timedelta

from ..models import AsyncSessionLocal, User, RegistrationRequest, UserLog, Referral
from ..config import settings
from .storm import StormProtection

router = Router()

ADMIN_IDS = settings.ADMIN_IDS

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_admin_id(session, telegram_id: int) -> int:
    admin = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    admin = admin.scalar_one_or_none()
    return admin.id if admin else None

@router.message(Command("review"))
async def cmd_review(message: Message):
    """Показывает список заявок на регистрацию (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Эта команда только для администраторов.")
        return
    
    async with AsyncSessionLocal() as session:
        requests = await session.execute(
            select(RegistrationRequest)
            .where(RegistrationRequest.status == "pending")
            .order_by(RegistrationRequest.created_at)
        )
        requests = requests.scalars().all()
        
        if not requests:
            await message.answer("📭 Нет ожидающих заявок на регистрацию.")
            return
        
        for req in requests[:5]:
            inviter_name = "—"
            if req.invited_by_id:
                inviter = await session.get(User, req.invited_by_id)
                inviter_name = inviter.full_name if inviter else "неизвестно"
            
            risk_color = "🟢" if req.risk_score < 30 else "🟡" if req.risk_score < 70 else "🔴"
            
            text = (
                f"🆕 **Заявка #{req.id}**\n"
                f"👤 {req.full_name or 'Имя не указано'}\n"
                f"📱 {req.phone or 'Телефон не указан'}\n"
                f"🆔 Telegram ID: `{req.telegram_id}`\n"
                f"🎟️ Пригласил: {inviter_name}\n"
                f"📸 Instagram: @{req.instagram or 'не указан'}\n"
                f"📱 VK: {req.vkontakte or 'не указан'}\n"
                f"🌐 IP: {req.ip_address}\n"
                f"🤖 Капча: {'✅' if req.captcha_passed else '❌'}\n"
                f"📊 Риск: {risk_color} {req.risk_score}/100\n"
                f"🕐 Создана: {req.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{req.id}"),
                        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{req.id}")
                    ],
                    [
                        InlineKeyboardButton(text="🚫 В черный список", callback_data=f"ban_{req.id}")
                    ]
                ]
            )
            
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
        
        if len(requests) > 5:
            await message.answer(f"📊 Всего заявок: {len(requests)}. Показаны первые 5.")

@router.callback_query(F.data.startswith("approve_"))
async def approve_request(callback: CallbackQuery):
    """Одобряет заявку на регистрацию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        req = await session.get(RegistrationRequest, request_id)
        if not req:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Создаем пользователя с установленным сроком действия баллов
        user = User(
            telegram_id=req.telegram_id,
            full_name=req.full_name or "Имя не указано",
            phone=req.phone or "",
            balance=200,
            invited_by_id=req.invited_by_id,
            instagram=req.instagram,
            vkontakte=req.vkontakte,
            verification_level="basic",
            badge="🟢",
            verified_at=datetime.utcnow(),
            points_expiry_date=datetime.utcnow() + timedelta(days=90)
        )
        session.add(user)
        await session.flush()
        
        # Создаём реферальную запись, если есть пригласивший
        if req.invited_by_id:
            referral = Referral(
                new_user_id=user.id,
                old_user_id=req.invited_by_id,
                status="pending",
                registration_date=datetime.utcnow()
            )
            session.add(referral)
        
        req.status = "approved"
        req.user_id = user.id
        req.reviewed_by = await get_admin_id(session, callback.from_user.id)
        req.reviewed_at = datetime.utcnow()
        
        log = UserLog(
            user_id=user.id,
            action_type="registration_approved",
            action_details=f"Одобрено администратором {callback.from_user.id}"
        )
        session.add(log)
        
        await session.commit()
        
        try:
            await callback.message.bot.send_message(
                req.telegram_id,
                "✅ **Регистрация подтверждена!**\n\n"
                "Ваша заявка одобрена. Добро пожаловать в программу лояльности!\n\n"
                "🎁 Вам начислено 200 приветственных баллов.\n"
                "⏳ Баллы действительны 3 месяца.\n\n"
                "👥 Ваш друг получит бонус после вашей первой аренды.\n\n"
                "Отправьте /start для начала работы.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
        
        await callback.message.edit_text(
            f"✅ Заявка #{request_id} одобрена. Пользователь создан (ID: {user.id})."
        )
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_request(callback: CallbackQuery):
    """Отклоняет заявку на регистрацию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        req = await session.get(RegistrationRequest, request_id)
        if not req:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        req.status = "rejected"
        req.reviewed_by = await get_admin_id(session, callback.from_user.id)
        req.reviewed_at = datetime.utcnow()
        
        await session.commit()
        
        try:
            await callback.message.bot.send_message(
                req.telegram_id,
                "❌ **Регистрация отклонена**\n\n"
                "К сожалению, ваша заявка была отклонена.\n\n"
                "Если вы считаете, что произошла ошибка, свяжитесь с поддержкой: @admin_support",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
        
        await callback.message.edit_text(f"❌ Заявка #{request_id} отклонена.")
    await callback.answer()

@router.callback_query(F.data.startswith("ban_"))
async def ban_request(callback: CallbackQuery):
    """Блокирует пользователя и отклоняет заявку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        req = await session.get(RegistrationRequest, request_id)
        if not req:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Добавляем IP в черный список через storm protection
        storm = StormProtection(session)
        await storm.add_to_whitelist(
            type='ip',
            value=req.ip_address,
            reason=f"Заблокирован при рассмотрении заявки #{request_id}",
            created_by=await get_admin_id(session, callback.from_user.id),
            expires_at=None
        )
        
        req.status = "rejected"
        req.reviewed_by = await get_admin_id(session, callback.from_user.id)
        req.reviewed_at = datetime.utcnow()
        
        await session.commit()
        
        await callback.message.edit_text(f"🚫 Пользователь заблокирован, заявка #{request_id} отклонена.")
    await callback.answer()