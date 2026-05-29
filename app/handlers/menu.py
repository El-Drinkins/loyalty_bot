from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func
from collections import defaultdict, OrderedDict
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
    """Форматирует сообщение с транзакциями для страницы"""
    if not transactions:
        return "📭 У вас пока нет операций."

    lines = ["📊 **История ваших операций**\n"]
    lines.append(f"Страница {current_page} из {total_pages}\n")

    running_balance = user_balance
    for i, t in enumerate(transactions):
        date_str = t.timestamp.strftime("%d.%m.%Y")
        amount_str = f"+{t.amount}" if t.amount > 0 else str(t.amount)
        emoji = "🟢" if t.amount > 0 else "🔴"
        time_str = t.timestamp.strftime("%H:%M")

        if i == 0:
            balance_after = running_balance
        else:
            balance_after = balance_before
        balance_before = balance_after - t.amount

        lines.append(f"📅 <b>{date_str}</b>")
        lines.append(f"{emoji} <b>{amount_str}</b> баллов {t.reason}")
        lines.append(time_str)
        if t.amount > 0:
            lines.append(f"💰 Баланс после начисления: <b>{balance_after}</b> ⭐")
        else:
            lines.append(f"💰 Баланс после списания: <b>{balance_after}</b> ⭐")

        if i < len(transactions) - 1:
            lines.append("➖➖➖➖➖➖➖➖➖➖")
            lines.append("")

    return "\n".join(lines)


def get_navigation_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру для навигации по страницам"""
    buttons = []
    
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
    
    if total_pages > 5:
        page_buttons = []
        
        for i in range(1, min(4, total_pages + 1)):
            if i == current_page:
                page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
            else:
                page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        if current_page > 4:
            page_buttons.append(InlineKeyboardButton(text="...", callback_data="noop"))
        
        start = max(4, current_page - 1)
        end = min(total_pages - 1, current_page + 1)
        for i in range(start, end + 1):
            if i > 3 and i < total_pages:
                if i == current_page:
                    page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
                else:
                    page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        if current_page < total_pages - 2:
            page_buttons.append(InlineKeyboardButton(text="...", callback_data="noop"))
        
        for i in range(max(total_pages - 2, 4), total_pages + 1):
            if i > 3:
                if i == current_page:
                    page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
                else:
                    page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        
        if page_buttons:
            buttons.append(page_buttons)
    else:
        page_buttons = []
        for i in range(1, total_pages + 1):
            if i == current_page:
                page_buttons.append(InlineKeyboardButton(text=f"•{i}•", callback_data="noop"))
            else:
                page_buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"history_page_{i}"))
        buttons.append(page_buttons)
    
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
        
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        transactions = await get_transactions_page(user.id, page)
        
        log = UserLog(
            user_id=user.id,
            action_type="view_history",
            action_details=f"Просмотр истории (страница {page} из {total_pages}, всего операций: {total_count})"
        )
        session.add(log)
        await session.commit()
        
        text = format_transaction_message(transactions, page, total_pages, user.balance)
        keyboard = get_navigation_keyboard(page, total_pages)
        
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(F.text == "💰 Мои баллы")
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
        
        from app.cashback import get_cashback_info
        cashback_info = await get_cashback_info(session, user)
        
        # Названия месяцев
        months_ru_nom = {
            1: "январь", 2: "февраль", 3: "март", 4: "апрель",
            5: "май", 6: "июнь", 7: "июль", 8: "август",
            9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
        }
        months_ru_loc = {
            1: "январе", 2: "феврале", 3: "марте", 4: "апреле",
            5: "мае", 6: "июне", 7: "июле", 8: "августе",
            9: "сентябре", 10: "октябре", 11: "ноябре", 12: "декабре"
        }
        months_ru_gen = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }
        
        now = datetime.utcnow()
        current_month = now.month
        next_month = current_month + 1
        if next_month > 12:
            next_month = 1
        
        text = (
            f"💰 Ваш баланс: <b>{format_number(user.balance)} баллов</b> (лимит: 20 000 ⭐)\n"
            f"⏳ Сгорают: <b>{expiry}</b>\n\n"
            f"📊 <b>Ваши ставки кэшбэка в {months_ru_loc[current_month]}:</b>\n"
            f"• Посуточная аренда: <b>{cashback_info['rate']}%</b>\n"
            f"• Аренда на месяц: <b>{cashback_info['monthly_rate']}%</b>\n\n"
            f"📊 <b>Прогноз ставки вашего кэшбэка на {months_ru_nom[next_month]}:</b>\n"
        )
        
        if cashback_info['has_rental_this_month']:
            if cashback_info['is_max_daily']:
                text += "🎉 Вы достигли максимальной ставки 10% за посуточную аренду!\n"
                text += "   Поддерживайте её регулярными арендами каждый месяц.\n\n"
            else:
                text += f"• Посуточная аренда: <b>{cashback_info['next_rate_if_rental']}%</b> (повышена за аренду в {months_ru_loc[current_month]})\n\n"
        else:
            if cashback_info['is_max_daily']:
                text += "🎉 Вы достигли максимальной ставки 10% за посуточную аренду!\n"
                text += "   Поддерживайте её регулярными арендами каждый месяц.\n\n"
            else:
                text += f"• Посуточная аренда: <b>{cashback_info['next_rate_if_rental']}%</b> (если совершите хотя бы одну аренду в {months_ru_loc[current_month]} от 1000 ₽)\n"
                text += f"  или <b>{cashback_info['next_rate_if_no_rental']}%</b> (если {months_ru_nom[current_month]} без аренд)\n\n"
        
        if cashback_info['has_active_monthly']:
            if cashback_info['is_max_monthly']:
                text += "🎉 Вы достигли максимальной ставки 15% за аренду на месяц!\n"
                text += "   Поддерживайте её регулярными продлениями.\n"
            else:
                text += f"📌 У вас действует аренда на месяц.\n"
                text += f"   При продлении ставка повысится до <b>{cashback_info['next_monthly']}%</b>.\n"
        else:
            if cashback_info['is_max_monthly']:
                text += "🎉 Вы достигли максимальной ставки 15% за аренду на месяц!\n"
                text += "   Поддерживайте её регулярными продлениями.\n"
            else:
                text += f"• Аренда на месяц: базовая ставка <b>10%</b>.\n"
                text += f"   При продлении каждый месяц +1% (максимум 15%).\n"

        text += "\n📞 Для заказа техники напишите в Telegram: @el_drinkins"
        text += "\n📋 Полные правила: /regulations"
        await message.answer(text, parse_mode="HTML")

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    await show_balance(message)

@router.message(F.text == "📜 История")
async def show_history(message: Message):
    await send_history_page(message, message.from_user.id, 1)


@router.callback_query(F.data.startswith("history_page_"))
async def history_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await callback.message.delete()
    await send_history_page(callback.message, callback.from_user.id, page)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


@router.message(F.text == "❓ Помощь")
async def help_message(message: Message):
    """Показывает страницу помощи (для кнопки и команды /help)"""
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
        "❓ <b>Помощь по боту и бонусной программе</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "• /faq — часто задаваемые вопросы\n"
        "• /regulations — полные правила программы\n"
        "• /start — начать регистрацию / перезапустить бота\n"
        "• /help — показать это сообщение\n"
        "• /catalog — открыть каталог техники\n\n"
        "📌 <b>Кнопки главного меню:</b>\n"
        "• 💰 Мои баллы — проверить количество баллов\n"
        "• 👥 Мои друзья — список приглашённых\n"
        "• 📜 История — история операций\n"
        "• 📸 Каталог — посмотреть технику\n"
        "• 🎁 Пригласить друга — получить ссылку для приглашения\n\n"
        "📌 <b>Для заказа техники напишите:</b>\n"
        "- телеграм @el_Drinkins\n"
        "- инста @fototehnika_arenda_ufa\n\n"
        "📌 <b>Требования к соцсетям:</b>\n"
        "• Аккаунт должен быть открытым (публичным)\n"
        "• Приватные аккаунты не принимаются\n\n"
        "📞 <b>Связаться с поддержкой</b>\n"
        " @el_Drinkins"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Сообщить об ошибке в боте", callback_data="feedback_bug")],
            [InlineKeyboardButton(text="💡 Предложить улучшение", callback_data="feedback_improvement")],
            [InlineKeyboardButton(text="📷 Какую технику добавить в прокат?", callback_data="feedback_equipment")],
        ]
    )
    
    await message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await help_message(message)


@router.message(Command("faq"))
async def cmd_faq(message: Message):
    """Показывает часто задаваемые вопросы"""
    faq_text = (
        "❓ <b>ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ</b>\n\n"
        "❓ <b>Сколько стоит 1 балл?</b>\n"
        " 1 балл = 1 рубль.\n\n"
        "❓ <b>Сколько баллов можно потратить за аренду?</b>\n"
        " До 50% стоимости аренды.\n\n"
        "❓ <b>Как получить баллы за аренду?</b>\n"
        " Баллы начисляются после завершения аренды. 5% — за посуточную аренду, 10% — за аренду от месяца.\n\n"
        "❓ <b>Что такое повышенный кэшбэк?</b>\n"
        " Если арендуете каждый месяц — ставка растёт: 5% → 6% → ... → 10% (максимум за суточную аренду). 10% → 11% → ... → 15% (максимум за аренду от месяца).\n\n"
        "❓ <b>Какой максимальный баланс баллов?</b>\n"
        " Максимальный баланс — 20 000 ⭐. При достижении лимита новые баллы не начисляются. Потратьте накопленные — и лимит освободится.\n\n"
        "❓ <b>Как получить бонус за друга?</b>\n"
        " Перешлите свою ссылку другу. Бонусы начисляются после его первой аренды. Найти свою реферальную ссылку можно нажав на кнопку \"Пригласить друга\" в главном меню.\n\n"
        "❓ <b>Кого можно приглашать?</b>\n"
        " Только фотографов, видеографов. Заявки от людей вне профессии рассматриваться не будут.\n\n"
        "❓ <b>Сколько действуют баллы?</b>\n"
        " 3 месяца с последней аренды. Новая аренда продлевает срок всех баллов еще на 3 месяца.\n\n"
        "❓ <b>Где посмотреть баланс?</b>\n"
        " Нажмите кнопку «💰 Мои баллы» в главном меню или отправьте боту команду /balance.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Полные правила программы лояльности тут /regulations\n\n"
        "🔙 /help — вернуться к помощи"
    )
    await message.answer(faq_text, parse_mode="HTML")


@router.message(F.text == "👥 Мои друзья")
async def my_friends_button(message: Message):
    from .invite import send_friends_list
    await send_friends_list(message, message.from_user.id)


@router.message(F.text == "🎁 Пригласить друга")
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


@router.message(F.text == "📸 Каталог")
async def catalog_button(message: Message):
    from .catalog import cmd_catalog
    await cmd_catalog(message)


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню", 
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@router.message(Command("regulations"))
async def regulations_command(message: Message):
    regulations_text = (
        "📋 <b>Бонусная программа</b>\n\n"
        "<b>Что такое баллы?</b>\n"
        "Баллы — это ваш кэшбэк за аренду.\n"
        "1 балл = 1 рубль.\n\n"
        "Баллами можно оплатить до 50% стоимости любой будущей аренды.\n"
        "Вы сами решаете, сколько баллов использовать (хоть 100, хоть 2000), главное — не больше половины стоимости аренды. При оплате аренды баллами их сумма должна быть кратна 100 (100, 200, 500, 1000...)\n\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Как получить баллы?</b>\n\n"
        "<b>1. Кэшбэк за аренду</b>\n"
        "За каждую аренду, которую вы оплатили деньгами (без использования баллов), мы начисляем:\n"
        "• 5% от суммы — за посуточную аренду.\n"
        "• 10% от суммы — за аренду от месяца.\n\n"
        "• Максимальный баланс — 20 000 ⭐. При достижении лимита новые баллы не начисляются. Потратьте накопленные — и лимит освободится.\n\n"
        "Баллы начисляются после возврата техники и завершения аренды.\n\n"
        "<b>2. Повышенный кэшбэк за регулярные аренды</b>\n\n"
        "<b>Для посуточной аренды:</b>\n"
        "• Базовая ставка — 5%.\n"
        "• Если вы совершили хотя бы одну аренду от 1000 руб. за календарный месяц, ставка повышается на 1%. В следующем месяце кэшбэк будет начисляться по ставке 6%.\n"
        "• Каждый новый месяц с арендой повышает ставку ещё на 1%. Максимум — 10%.\n"
        "• Если вы не брали технику целый календарный месяц, ставка возвращается к 5%.\n"
        "• Один раз в год по вашему запросу можно заморозить ставку на один месяц без аренд.\n\n"
        "<b>Для аренды от месяца:</b>\n"
        "• Базовая ставка — 10%. Расчет идет не по календарному месяцу, а от даты до такой же даты в следующем месяце.\n"
        "Например, вы взяли в аренду объектив 11 мая до 11 июня. За эту аренду будет начислен кэшбэк по базовой ставке - 10%.\n"
        "• При продлении аренды на второй месяц подряд ставка повышается на 1%.\n"
        "• Максимум — 15%.\n"
        "• После возврата техники ставка сбрасывается до базовой (10%).\n\n"
        "Точную ставку вашего кэшбэка на текущий месяц и прогноз ставки на будущий месяц можно посмотреть нажав на кнопку \"Мои баллы\"\n\n"
        "<b>3. Приглашение друзей</b>\n"
        "У каждого пользователя этого бота есть персональная реферальная ссылка. Перешлите её другу — и вы оба получите бонусы.\n\n"
        "⚠️ Приглашайте только фотографов, видеографов. Заявки от людей вне профессии рассматриваться не будут.\n\n"
        "<b>Что получит друг:</b>\n"
        "Регистрация по вашей ссылке → 200 баллов.\n\n"
        "<b>Что получите вы (приглашающий):</b>\n"
        "• Первая аренда друга → 200 баллов\n"
        "• Вторая аренда друга → 800 баллов\n"
        "• Суммарные аренды друга достигли 10 000 руб. → 1 000 баллов\n"
        "• Суммарные аренды друга достигли 30 000 руб. → 1 000 баллов\n"
        "Бонусы начисляются после того, как друг вернул технику в целости.\n\n"
        "Таким образом за приглашение одного друга можно заработать 3 000 баллов.\n\n"
        "Кроме этого, существует командный бонус: когда общая сумма аренд всех ваших друзей достигнет 100 000 ₽, вы получите 5 000 ⭐.\n\n"
        "Нажав на кнопку \"Мои друзья\" вы можете посмотреть статистику по заработанным баллам за приглашение друзей, а также статистику по каждому другу индивидуально.\n\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Как потратить баллы?</b>\n"
        "• Баллами можно оплатить до 50% стоимости любой аренды.\n"
        "• Вы сами решаете, сколько баллов использовать. Хоть 100, хоть 2000 — главное, не больше половины суммы аренды. При оплате аренды баллами их сумма должна быть кратна 100 (100, 200, 500, 1000...)\n"
        "• Если вы использовали баллы при оплате аренды, то за эту аренду баллы не начисляются.\n\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Срок действия баллов</b>\n"
        "• Баллы действуют 3 месяца с даты последней аренды.\n"
        "• Совершили новую аренду от 1000 руб — срок действия всех баллов снова становится 3 месяца.\n"
        "• Если вы не арендовали технику 3 месяца и больше — баллы сгорают.\n"
        "• Вы получите уведомления о сгорании баллов заранее: за 30 дней, за 7 дней и за 1 день до сгорания.\n"
        "• Дату сгорания баллов можно посмотреть нажав в главном меню на кнопку \"Мои баллы\".\n\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Как узнать свой баланс?</b>\n"
        "Вы всегда можете проверить количество баллов, историю их начислений и списаний в этом боте.\n"
        "Нажмите кнопку «💰 Мои баллы» или отправьте команду /balance.\n\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Важно</b>\n"
        "• Баллы не обмениваются на деньги.\n"
        "• Баллы за приглашение друзей начисляются только после того, как друг вернул технику в целости.\n"
        "• Бонусная программа может быть изменена или закрыта, но мы всегда уведомим вас заранее.\n\n"
        "Арендуйте чаще, приглашайте друзей, копите и тратьте баллы!"
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
                await message.answer(f"📋 Бонусная программа (часть {i}/{len(parts)})\n\n{part}", parse_mode="HTML")
            else:
                await message.answer(part, parse_mode="HTML")

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    await show_balance(message)