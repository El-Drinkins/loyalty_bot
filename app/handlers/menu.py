from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from collections import defaultdict
import math

from ..models import User, Transaction, AsyncSessionLocal, UserLog
from ..keyboards import main_menu_keyboard
from ..config import settings

router = Router()

# Количество операций на одной странице
OPERATIONS_PER_PAGE = 10


def format_number(num: int) -> str:
    """Форматирует число с пробелами: 10000 -> 10 000"""
    return f"{num:,}".replace(",", " ")


async def get_transactions_count(user_id: int) -> int:
    """Возвращает общее количество транзакций пользователя"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
        )
        return result.scalar() or 0


async def get_transactions_page(user_id: int, page: int) -> list:
    """Возвращает транзакции для указанной страницы"""
    offset = (page - 1) * OPERATIONS_PER_PAGE
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.timestamp.desc())
            .offset(offset)
            .limit(OPERATIONS_PER_PAGE)
        )
        return result.scalars().all()


def format_transaction_message(transactions: list, current_page: int, total_pages: int, user_balance: int) -> str:
    """Форматирует сообщение с транзакциями для страницы (старый стиль)"""
    if not transactions:
        return "📭 У вас пока нет операций."
    
    # Группируем транзакции по дате
    grouped = defaultdict(list)
    for t in transactions:
        date_str = t.timestamp.strftime("%d.%m.%Y")
        grouped[date_str].append(t)
    
    lines = ["📊 **История ваших операций**\n"]
    lines.append(f"Страница {current_page} из {total_pages}\n")
    
    for date_str in sorted(grouped.keys(), reverse=True):
        lines.append(f"📅 {date_str}")
        
        day_transactions = grouped[date_str]
        day_transactions.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Рассчитываем баланс после каждой операции (от конца к началу)
        running_balance = user_balance
        for i, t in enumerate(day_transactions):
            if i > 0:
                for j in range(i):
                    running_balance -= day_transactions[j].amount
        
        for i, t in enumerate(day_transactions):
            if i > 0:
                running_balance -= day_transactions[i-1].amount
            
            amount_str = f"+{t.amount}" if t.amount > 0 else str(t.amount)
            emoji = "🟢" if t.amount > 0 else "🔴"
            time_str = t.timestamp.strftime("%H:%M")
            
            lines.append(f"{emoji} {amount_str} баллов {t.reason}")
            lines.append(time_str)
            
            if t.amount > 0:
                lines.append(f"💰 Баланс после начисления: {format_number(running_balance)} ⭐")
            else:
                lines.append(f"💰 Баланс после списания: {format_number(running_balance)} ⭐")
            
            # Разделитель после КАЖДОЙ операции, кроме последней в дне
            if i < len(day_transactions) - 1:
                lines.append("---------------------------------")
        
        lines.append("")  # Пустая строка между датами
    
    return "\n".join(lines)


def get_navigation_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для навигации по страницам"""
    buttons = []
    
    # Кнопки навигации (предыдущая/следующая)
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Предыдущая", callback_data=f"history_page_{current_page - 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="◀️ Предыдущая", callback_data="noop"))
    
    nav_row.append(InlineKeyboardButton(text=f"{current_page} / {total_pages}", callback_data="noop"))
    
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Следующая ▶️", callback_data=f"history_page_{current_page + 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="Следующая ▶️", callback_data="noop"))
    
    buttons.append(nav_row)
    
    # Кнопки быстрого перехода по страницам (если страниц > 5)
    if total_pages > 5:
        page_buttons = []
        
        # Показываем первые 3 страницы
        for i in range(1, min(4, total_pages + 1)):
            if i == current_page:
                page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
            else:
                page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        # Если есть пропуск, добавляем "..."
        if current_page > 4:
            page_buttons.append(InlineKeyboardButton(text="...", callback_data="noop"))
        
        # Показываем страницу вокруг текущей
        start = max(4, current_page - 1)
        end = min(total_pages - 1, current_page + 1)
        for i in range(start, end + 1):
            if i > 3 and i < total_pages:
                if i == current_page:
                    page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
                else:
                    page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        # Если есть пропуск в конце
        if current_page < total_pages - 2:
            page_buttons.append(InlineKeyboardButton(text="...", callback_data="noop"))
        
        # Показываем последние 3 страницы
        for i in range(max(total_pages - 2, 4), total_pages + 1):
            if i > 3:
                if i == current_page:
                    page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
                else:
                    page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        if page_buttons:
            buttons.append(page_buttons)
    else:
        # Если страниц мало, показываем все
        page_buttons = []
        for i in range(1, total_pages + 1):
            if i == current_page:
                page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
            else:
                page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        buttons.append(page_buttons)
    
    # Кнопка "В начало" и "Назад в меню"
    buttons.append([
        InlineKeyboardButton(text="🔝 В начало", callback_data="history_page_1"),
        InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_history_page(message: Message, user_id: int, page: int = 1):
    """Отправляет страницу истории операций"""
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == user_id))
        user = user.scalar_one_or_none()
        
        if not user:
            await message.answer("Пожалуйста, зарегистрируйтесь через /start")
            return
        
        total_count = await get_transactions_count(user.id)
        
        if total_count == 0:
            await message.answer("📭 У вас пока нет операций.")
            return
        
        total_pages = math.ceil(total_count / OPERATIONS_PER_PAGE)
        
        # Корректируем номер страницы
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        transactions = await get_transactions_page(user.id, page)
        
        # Логируем действие
        log = UserLog(
            user_id=user.id,
            action_type="view_history",
            action_details=f"Просмотр истории (страница {page} из {total_pages}, всего операций: {total_count})"
        )
        session.add(log)
        await session.commit()
        
        # Формируем сообщение
        text = format_transaction_message(transactions, page, total_pages, user.balance)
        keyboard = get_navigation_keyboard(page, total_pages)
        
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


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
            f"💰 Ваш баланс: {format_number(user.balance)} баллов\n"
            f"⏳ Сгорают: {expiry}"
        )


@router.message(F.text == "📜 История")
async def show_history(message: Message):
    """Показывает первую страницу истории операций"""
    await send_history_page(message, message.from_user.id, 1)


@router.callback_query(F.data.startswith("history_page_"))
async def history_page_callback(callback: CallbackQuery):
    """Обработчик навигации по страницам истории"""
    page = int(callback.data.split("_")[2])
    await callback.message.delete()
    await send_history_page(callback.message, callback.from_user.id, page)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """Заглушка для неактивных кнопок"""
    await callback.answer()


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
        "❓ <b>Помощь</b>\n\n"
        "<b>Часто задаваемые вопросы:</b>\n\n"
        "❓ <b>Сколько стоит 1 балл?</b>\n"
        "1 балл = 1 рубль.\n\n"
        "❓ <b>Сколько баллов можно потратить за аренду?</b>\n"
        "До 50% стоимости аренды.\n\n"
        "❓ <b>Как получить баллы за аренду?</b>\n"
        "Баллы начисляются после завершения аренды. 5% — посуточно, 10% — от месяца.\n\n"
        "❓ <b>Что такое повышенный кэшбэк?</b>\n"
        "Если арендуете каждый месяц — ставка растёт: 5% → 6% → ... → 10% (максимум).\n\n"
        "❓ <b>Как получить бонус за друга?</b>\n"
        "Перешлите свою ссылку другу. Бонусы начисляются после его первой аренды.\n\n"
        "❓ <b>Сколько действуют баллы?</b>\n"
        "3 месяца с последней аренды. Новая аренда продлевает срок.\n\n"
        "❓ <b>Где посмотреть баланс?</b>\n"
        "Нажмите кнопку «🏠 Баланс» или отправьте команду /balance.\n\n"
        "📋 <b>Полные правила программы</b>\n"
        "/regulations\n\n"
        "📞 <b>Связаться с поддержкой</b>\n"
        "@el_drinkins"
    )
    
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "👥 Мои друзья")
async def my_friends_button(message: Message):
    from .invite import send_friends_list
    await send_friends_list(message, message.from_user.id)


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


@router.message(F.text == "/regulations")
async def regulations_command(message: Message):
    regulations_text = (
        "📋 <b>Программа лояльности</b>\n\n"
        "<b>Что такое баллы?</b>\n"
        "Баллы — это ваши бонусы за аренду.\n"
        "1 балл = 1 рубль.\n\n"
        "Баллами можно оплатить до 50% стоимости любой будущей аренды.\n"
        "Вы сами решаете, сколько баллов использовать (хоть 100, хоть 2000), "
        "главное — не больше половины суммы аренды.\n\n"
        "<b>Как получить баллы?</b>\n\n"
        "<b>1. Кэшбэк за аренду</b>\n"
        "За каждую аренду, которую вы оплатили деньгами (без использования баллов), "
        "мы начисляем:\n"
        "• 5% от суммы — за посуточную аренду.\n"
        "• 10% от суммы — за аренду от месяца.\n\n"
        "Баллы начисляются после завершения аренды.\n\n"
        "<b>2. Повышенный кэшбэк за регулярность</b>\n\n"
        "<b>Для посуточной аренды:</b>\n"
        "• Базовая ставка — 5%.\n"
        "• Если вы совершили хотя бы одну аренду от 500 руб. за календарный месяц, "
        "ставка повышается на 1%. В следующем месяце кэшбэк будет начисляться по ставке 6%.\n"
        "• Каждый новый месяц с арендой повышает ставку ещё на 1%. Максимум — 10%.\n"
        "• Если вы не брали технику целый месяц, ставка возвращается к 5%.\n"
        "• Один раз в год по вашему запросу можно заморозить ставку на один месяц без аренд.\n\n"
        "<b>Для аренды от месяца:</b>\n"
        "• Базовая ставка — 10%.\n"
        "• При продлении аренды на второй месяц подряд ставка повышается на 1%.\n"
        "• Максимум — 15%.\n"
        "• После возврата техники ставка сбрасывается до базовой (10%).\n\n"
        "<b>3. Приглашение друзей</b>\n"
        "У каждого клиента есть персональная реферальная ссылка. Перешлите её другу — "
        "и вы оба получите бонусы.\n\n"
        "<b>Что получит друг:</b>\n"
        "Регистрация по вашей ссылке → 300 баллов.\n\n"
        "Баллы нужно потратить в течение 3 месяцев, иначе они сгорят.\n\n"
        "<b>Что получите вы (приглашающий):</b>\n"
        "Бонусы начисляются после того, как друг вернул технику в целости.\n"
        "• Первая аренда друга от 1000 руб. → 300 баллов\n"
        "• Вторая аренда друга от 1000 руб. → 700 баллов\n"
        "• Первая аренда друга на месяц (любая техника) → 500 баллов\n"
        "• Суммарные аренды друга достигли 10 000 руб. → 1000 баллов\n"
        "• Суммарные аренды друга достигли 30 000 руб. → 1000 баллов\n\n"
        "Таким образом за приглашение одного друга можно заработать 3500 баллов.\n\n"
        "<b>Как потратить баллы?</b>\n"
        "• Баллами можно оплатить до 50% стоимости любой аренды.\n"
        "• Вы сами решаете, сколько баллов использовать. Хоть 100, хоть 2000 — "
        "главное, не больше половины суммы аренды.\n"
        "• Если вы использовали баллы при оплате аренды то, за эту аренду баллы не начисляются.\n\n"
        "<b>Срок действия баллов</b>\n"
        "• Баллы действуют 3 месяца с даты последней аренды.\n"
        "• Совершили новую аренду (даже с оплатой баллами) — срок всех баллов "
        "снова становится 3 месяца.\n"
        "• Если вы не арендовали технику 3 месяца и больше — баллы сгорают.\n\n"
        "<b>Как узнать свой баланс?</b>\n"
        "Вы всегда можете проверить количество баллов и историю начислений в этом боте.\n"
        "Нажмите кнопку «🏠 Баланс» или отправьте команду /balance.\n\n"
        "<b>Важно</b>\n"
        "• Баллы не обмениваются на деньги.\n"
        "• Баллы за приглашение друзей начисляются только после того, как друг "
        "вернул технику в целости.\n"
        "• Программа может быть изменена, но мы всегда уведомим вас заранее.\n\n"
        "<b>Арендуйте чаще, приглашайте друзей и копите баллы!</b>"
    )
    
    if len(regulations_text) <= 4096:
        await message.answer(regulations_text, parse_mode="HTML")
    else:
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
                await message.answer(f"📋 Программа лояльности (часть {i}/{len(parts)})\n\n{part}", parse_mode="HTML")
            else:
                await message.answer(part, parse_mode="HTML")