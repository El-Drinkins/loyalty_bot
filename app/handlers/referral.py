from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from ..models import User, Referral, AsyncSessionLocal, UserLog, ReferralCode
from ..keyboards import referral_menu_keyboard, main_menu_keyboard
from ..utils import generate_referral_link
from ..config import settings

router = Router()

@router.message(F.text == "👥 Мои друзья")
async def my_friends(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return

        # Проверка на блокировку
        if user.blacklisted:
            await message.answer(
                "⛔ Вы заблокированы в системе лояльности.\n"
                "Для получения информации обратитесь к администратору."
            )
            return

        # Статистика приглашенных
        total_invited = await session.execute(
            select(func.count()).where(Referral.old_user_id == user.id)
        )
        total_invited = total_invited.scalar() or 0

        completed = await session.execute(
            select(func.count()).where(Referral.old_user_id == user.id, Referral.status == "completed")
        )
        completed = completed.scalar() or 0

        # Получаем список приглашенных друзей
        referrals_query = await session.execute(
            select(Referral)
            .where(Referral.old_user_id == user.id)
            .order_by(Referral.registration_date.desc())
            .limit(10)
        )
        referrals = referrals_query.scalars().all()

        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_friends",
            action_details=f"Просмотр друзей (приглашено: {total_invited})"
        )
        session.add(log)
        await session.commit()

        # Получаем username бота и ссылку
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username
        
        # Получаем постоянную ссылку пользователя
        code_record = await session.execute(
            select(ReferralCode).where(
                ReferralCode.owner_id == user.id,
                ReferralCode.is_permanent == True,
                ReferralCode.is_active == True
            )
        )
        code_record = code_record.scalar_one_or_none()
        
        if code_record:
            link = f"https://t.me/{bot_username}?start={code_record.code}"
        else:
            # Если нет постоянной ссылки, создаем
            from .referral_codes import generate_referral_code
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
            link = f"https://t.me/{bot_username}?start={code}"

        text = (
            f"👥 **Мои друзья**\n\n"
            f"📊 **Статистика:**\n"
            f"• Приглашено: **{total_invited}** друзей\n"
            f"• Подтвердили аренду: **{completed}**\n"
            f"• Заработано баллов: **{completed * settings.REFERRAL_BONUS}** ⭐\n\n"
        )

        if referrals:
            text += "📋 **Последние приглашенные:**\n"
            for ref in referrals:
                status_emoji = "✅" if ref.status == "completed" else "⏳"
                new_user = await session.get(User, ref.new_user_id)
                if new_user:
                    date_str = ref.registration_date.strftime("%d.%m.%Y")
                    text += f"{status_emoji} {new_user.full_name} — {date_str}\n"
            text += "\n"

        text += (
            f"🔗 **Ваша реферальная ссылка:**\n"
            f"[Нажмите, чтобы скопировать]({link})\n\n"
            f"Или отправьте другу эту ссылку:\n"
            f"`{link}`\n\n"
            f"Поделитесь этой ссылкой с друзьями!\n"
            f"За каждого друга, который совершит первую аренду, "
            f"вы получите **{settings.REFERRAL_BONUS}** баллов."
        )

        await message.answer(
            text,
            reply_markup=referral_menu_keyboard(link),
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard(callback.from_user.id))
    await callback.answer()