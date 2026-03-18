from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from collections import defaultdict

from ..models import User, Transaction, AsyncSessionLocal, UserLog  # изменен импорт
from ..keyboards import main_menu_keyboard
from ..config import settings

router = Router()

@router.message(F.text == "🏠 Баланс")
async def show_balance(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_balance",
            action_details=f"Баланс: {user.balance}"
        )
        session.add(log)
        await session.commit()
        
        expiry = user.points_expiry_date.strftime("%d.%m.%Y") if user.points_expiry_date else "не ограничен"
        await message.answer(
            f"💰 Ваш баланс: *{user.balance}* баллов\n"
            f"⏳ Сгорают: *{expiry}*",
            parse_mode="Markdown"
        )

@router.message(F.text == "📜 История")
async def show_history(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        # Получаем все транзакции пользователя
        transactions = await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.timestamp.desc())
        )
        transactions = transactions.scalars().all()
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_history",
            action_details=f"Просмотр истории (всего операций: {len(transactions)})"
        )
        session.add(log)
        await session.commit()
        
        if not transactions:
            await message.answer("📭 У вас пока нет операций.")
            return
        
        # Группируем транзакции по датам
        grouped = defaultdict(list)
        for t in transactions:
            date_str = t.timestamp.strftime("%d.%m.%Y")
            grouped[date_str].append(t)
        
        # Формируем сообщение
        lines = ["📊 *История ваших операций*\n"]
        
        for date_str in sorted(grouped.keys(), reverse=True):
            lines.append(f"\n📅 *{date_str}*")
            
            day_transactions = grouped[date_str]
            day_transactions.sort(key=lambda x: x.timestamp, reverse=True)
            
            running_balance = user.balance
            for i, t in enumerate(day_transactions):
                if i > 0:
                    for j in range(i):
                        running_balance -= day_transactions[j].amount
                
                amount_str = f"+{t.amount}" if t.amount > 0 else str(t.amount)
                emoji = "🟢" if t.amount > 0 else "🔴"
                time_str = t.timestamp.strftime("%H:%M")
                
                lines.append(f"{emoji} {amount_str} баллов {t.reason}")
                lines.append(f"{time_str}")
                
                if t.amount > 0:
                    lines.append(f"💰 *Баланс после начисления: {running_balance}* ⭐")
                else:
                    lines.append(f"💰 *Баланс после списания: {running_balance}* ⭐")
                
                if i < len(day_transactions) - 1:
                    lines.append("---------------------------------")
        
        full_text = "\n".join(lines)
        
        if len(full_text) <= 4096:
            await message.answer(full_text, parse_mode="Markdown")
        else:
            parts = []
            current_part = []
            current_length = 0
            
            for line in lines:
                line_length = len(line) + 1
                if current_length + line_length > 4000:
                    parts.append("\n".join(current_part))
                    current_part = [line]
                    current_length = line_length
                else:
                    current_part.append(line)
                    current_length += line_length
            
            if current_part:
                parts.append("\n".join(current_part))
            
            for i, part in enumerate(parts, 1):
                if len(parts) > 1:
                    await message.answer(f"📜 *История (часть {i}/{len(parts)})*\n\n{part}", parse_mode="Markdown")
                else:
                    await message.answer(part, parse_mode="Markdown")

@router.message(F.text == "❓ Помощь")
async def help_message(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user.scalar_one_or_none()
        
        if user:
            log = UserLog(
                user_id=user.id,
                action_type="help",
                action_details="Просмотр справки"
            )
            session.add(log)
            await session.commit()
    
    await message.answer(
        "❓ *Помощь по программе лояльности*\n\n"
        "📌 *Основные команды:*\n"
        "🏠 Баланс - просмотр текущего баланса\n"
        "👥 Мои друзья - список приглашенных друзей\n"
        "📜 История - история операций\n"
        "🎁 Пригласить друга - получить ссылку для приглашения\n\n"
        "📌 *Как начисляются баллы:*\n"
        "• 200 баллов за регистрацию\n"
        "• 100 баллов за каждого приглашенного друга\n\n"
        "📌 *Если пропало меню:*\n"
        "• Отправьте команду */start* - меню появится снова",
        parse_mode="Markdown"
    )

@router.message(F.text == "👥 Мои друзья")
async def my_friends_button(message: Message):
    from .invite import show_friends_directly
    await show_friends_directly(message)

@router.message(F.text == "🎁 Пригласить друга в бот")
async def invite_button(message: Message):
    from .invite import invite_friend
    await invite_friend(message)

@router.message(F.text == "🔗 Управление ссылками")
async def manage_links_button(message: Message):
    if message.from_user.id in settings.ADMIN_IDS:
        from .referral_codes import cmd_my_links
        await cmd_my_links(message)
    else:
        await message.answer("❌ Эта функция доступна только администраторам.")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню", 
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()