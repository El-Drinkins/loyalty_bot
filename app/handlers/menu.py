from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from collections import defaultdict

from ..models import User, Transaction, AsyncSessionLocal, UserLog
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
        
        transactions = await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.timestamp.desc())
        )
        transactions = transactions.scalars().all()
        
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
        
        grouped = defaultdict(list)
        for t in transactions:
            date_str = t.timestamp.strftime("%d.%m.%Y")
            grouped[date_str].append(t)
        
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
    
    help_text = (
        "❓ **Помощь**\n\n"
        "**Часто задаваемые вопросы:**\n\n"
        "❓ **Сколько стоит 1 балл?**\n"
        "1 балл = 1 рубль.\n\n"
        "❓ **Сколько баллов можно потратить за аренду?**\n"
        "До 50% стоимости аренды.\n\n"
        "❓ **Как получить баллы за аренду?**\n"
        "Автоматически после завершения аренды. 5% — посуточно, 10% — от месяца.\n\n"
        "❓ **Что такое повышенный кэшбэк?**\n"
        "Если арендуете каждый месяц — ставка растёт: 5% → 6% → ... → 10% (максимум).\n\n"
        "❓ **Как получить бонус за друга?**\n"
        "Перешлите свою ссылку другу. Бонусы начисляются после его первой аренды.\n\n"
        "❓ **Сколько действуют баллы?**\n"
        "3 месяца с последней аренды. Новая аренда продлевает срок.\n\n"
        "❓ **Где посмотреть баланс?**\n"
        "Нажмите кнопку «🏠 Баланс» или отправьте команду /balance.\n\n"
        "📋 **Полные правила программы**\n"
        "/regulations\n\n"
        "📞 **Связаться с поддержкой**\n"
        "@admin_support"
    )
    
    await message.answer(help_text, parse_mode="Markdown")

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


# ==========================================
# НОВЫЙ ОБРАБОТЧИК ДЛЯ /regulations
# ==========================================

@router.message(F.text == "/regulations")
async def regulations_command(message: Message):
    """Отправляет полные правила программы лояльности"""
    
    regulations_text = (
        "📋 **Программа лояльности**\n\n"
        "**Что такое баллы?**\n"
        "Баллы — это ваши бонусы за аренду.\n"
        "1 балл = 1 рубль.\n\n"
        "Баллами можно оплатить до 50% стоимости любой будущей аренды.\n"
        "Вы сами решаете, сколько баллов использовать (хоть 100, хоть 2000), "
        "главное — не больше половины суммы аренды.\n\n"
        "**Как получить баллы?**\n\n"
        "**1. Кэшбэк за аренду**\n"
        "За каждую аренду, которую вы оплатили деньгами (без использования баллов), "
        "мы начисляем:\n"
        "• 5% от суммы — за посуточную аренду.\n"
        "• 10% от суммы — за аренду от месяца.\n\n"
        "Баллы начисляются после завершения аренды.\n\n"
        "**2. Повышенный кэшбэк за регулярность**\n\n"
        "*Для посуточной аренды:*\n"
        "• Базовая ставка — 5%.\n"
        "• Если вы совершили хотя бы одну аренду от 500 руб. за календарный месяц, "
        "ставка повышается на 1%. В следующем месяце кэшбэк будет начисляться по ставке 6%.\n"
        "• Каждый новый месяц с арендой повышает ставку ещё на 1%. Максимум — 10%.\n"
        "• Если вы не брали технику целый месяц, ставка возвращается к 5%.\n"
        "• Один раз в год по вашему запросу мы можем заморозить ставку на один месяц без аренд.\n\n"
        "*Для аренды от месяца:*\n"
        "• Базовая ставка — 10%.\n"
        "• При продлении аренды на второй месяц подряд ставка повышается на 1%.\n"
        "• Максимум — 15%.\n"
        "• После возврата техники ставка сбрасывается до базовой (10%).\n\n"
        "**3. Приглашение друзей**\n"
        "У каждого клиента есть персональная реферальная ссылка. Перешлите её другу — "
        "и вы оба получите бонусы.\n\n"
        "*Что получит друг:*\n"
        "Регистрация по вашей ссылке → 300 баллов\n\n"
        "Баллы нужно потратить в течение 3 месяцев, иначе сгорят.\n\n"
        "*Что получите вы (приглашающий):*\n"
        "Бонусы начисляются после того, как друг вернул технику в целости.\n"
        "• Первая аренда друга от 1000 руб. → 300 баллов\n"
        "• Вторая аренда друга от 1000 руб. → 700 баллов\n"
        "• Первая аренда друга на месяц (любая техника) → 500 баллов\n"
        "• Суммарные аренды друга достигли 10 000 руб. → 1000 баллов\n"
        "• Суммарные аренды друга достигли 30 000 руб. → 1000 баллов\n\n"
        "Максимальный бонус с одного друга — 3500 баллов.\n\n"
        "**Как потратить баллы?**\n"
        "• Баллами можно оплатить до 50% стоимости любой аренды.\n"
        "• Вы сами решаете, сколько баллов использовать. Хоть 100, хоть 2000 — "
        "главное, не больше половины суммы аренды.\n"
        "• Если вы использовали баллы при оплате, за эту аренду баллы не начисляются.\n\n"
        "**Срок действия баллов**\n"
        "• Баллы действуют 3 месяца с даты последней аренды.\n"
        "• Совершили новую аренду (даже с оплатой баллами) — срок всех баллов "
        "снова становится 3 месяца.\n"
        "• Если вы не арендовали технику 3 месяца и больше — баллы сгорают.\n\n"
        "**Как узнать свой баланс?**\n"
        "Вы всегда можете проверить количество баллов и историю начислений в этом боте.\n"
        "Нажмите кнопку «🏠 Баланс» или отправьте команду /balance.\n\n"
        "**Важно**\n"
        "• Баллы не обмениваются на деньги и не возвращаются при отмене аренды.\n"
        "• Бонусы за приглашение друзей начисляются только после того, как друг "
        "вернул технику в целости.\n"
        "• Программа может быть изменена, но мы всегда уведомим вас заранее.\n\n"
        "Арендуйте чаще, приглашайте друзей и копите баллы!"
    )
    
    # Разбиваем длинное сообщение на части (если нужно)
    if len(regulations_text) <= 4096:
        await message.answer(regulations_text, parse_mode="Markdown")
    else:
        # Если текст слишком длинный, разбиваем на части
        parts = []
        current_part = []
        current_length = 0
        
        for line in regulations_text.split('\n'):
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
                await message.answer(f"📋 *Программа лояльности (часть {i}/{len(parts)})*\n\n{part}", parse_mode="Markdown")
            else:
                await message.answer(part, parse_mode="Markdown")