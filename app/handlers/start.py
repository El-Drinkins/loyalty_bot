import time
import logging
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from datetime import datetime

from ..models import User, Referral, Transaction, AsyncSessionLocal, ReferralCode, UserLog, RegistrationRequest, SecuritySettings
from ..keyboards import main_menu_keyboard
from ..utils import calculate_expiry_date
from ..config import settings
from .captcha import captcha, CaptchaStates
from .storm import StormProtection

logger = logging.getLogger(__name__)
time_logger = logging.getLogger("time_stats")
time_logger.setLevel(logging.INFO)

router = Router()

class Registration(StatesGroup):
    waiting_for_captcha = State()
    waiting_for_phone = State()
    waiting_for_social = State()
    waiting_for_manual_code = State()

# Приветственное сообщение с кнопкой "Начать регистрацию"
WELCOME_MESSAGE = (
    "📸 Добро пожаловать в программу лояльности!\n\n"
    "Это бот для фотографов и видеографов. Здесь вы можете:\n"
    "• Получать бонусы за регистрацию и аренду техники\n"
    "• Приглашать друзей и получать за это бонусы\n"
    "• Следить за балансом бонусов и историей операций\n\n"
    "🎁 За регистрацию вы получите 200 бонусных баллов!\n\n"
    "Нажмите на кнопку ниже, чтобы начать регистрацию:"
)

def clean_phone_number(phone: str) -> str:
    """Очищает номер телефона от лишних символов"""
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    
    if len(digits) == 11 and digits.startswith('7'):
        return '+' + digits
    
    if len(digits) == 10:
        return '+7' + digits
    
    return None

async def get_security_setting(session, key: str, default: str = "false") -> str:
    result = await session.execute(
        select(SecuritySettings).where(SecuritySettings.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else default

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    start_total = time.time()
    logger.info(f"▶️ Начало обработки /start от пользователя {message.from_user.id}")
    
    # Получаем ref_code из аргументов команды
    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    # Проверяем, есть ли пользователь в базе
    start_db = time.time()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        db_time = time.time() - start_db
        time_logger.info(f"⏱️ Поиск пользователя: {db_time*1000:.2f}мс")

        if user:
            if user.blacklisted:
                await message.answer("⛔ Ваш аккаунт заблокирован.")
                return
            
            await message.answer(
                f"С возвращением, {user.full_name}!\nВаш баланс: {user.balance} ⭐",
                reply_markup=main_menu_keyboard(message.from_user.id)
            )
            return

    # Новый пользователь
    # Сохраняем ref_code в состояние, если он есть
    if ref_code:
        # Проверяем, существует ли такой код
        async with AsyncSessionLocal() as session:
            code_record = await session.execute(
                select(ReferralCode).where(ReferralCode.code == ref_code)
            )
            code_record = code_record.scalar_one_or_none()
            
            if code_record and code_record.is_active:
                if code_record.expires_at and code_record.expires_at < datetime.utcnow():
                    await message.answer("⏰ Срок действия кода истек. Регистрация без кода.")
                    ref_code = None
                elif code_record.max_uses > 0 and code_record.used_count >= code_record.max_uses:
                    await message.answer("⚠️ Лимит ссылки исчерпан. Регистрация без кода.")
                    ref_code = None
                else:
                    await state.update_data(ref_code=ref_code, referrer_id=code_record.owner_id)
                    referrer = await session.get(User, code_record.owner_id)
                    if referrer:
                        await message.answer(f"🎉 Вас пригласил: {referrer.full_name}")
            else:
                await message.answer("❌ Недействительная ссылка. Регистрация без кода.")
                ref_code = None
        
        # Сохраняем ref_code в состояние для использования при нажатии кнопки
        await state.update_data(ref_code=ref_code)
    
    # Показываем приветствие с кнопкой
    start_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать регистрацию", callback_data="start_registration")]
        ]
    )
    
    await message.answer(
        WELCOME_MESSAGE,
        reply_markup=start_keyboard
    )

@router.callback_query(F.data == "start_registration")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Начать регистрацию'"""
    
    # Получаем ref_code из состояния
    data = await state.get_data()
    ref_code = data.get("ref_code")
    
    print(f"🔍 start_registration вызван, ref_code = {ref_code}")
    
    # =========================================================
    # ВКЛЮЧЕНО: регистрация только по реферальному коду
    # =========================================================
    if not ref_code:
        await callback.message.answer(
            "🔒 Регистрация только по приглашениям\n\n"
            "К сожалению, регистрация в боте возможна только по пригласительным ссылкам.\n\n"
            "Если вас пригласил друг, попросите у него ссылку.\n\n"
            "Пример ссылки: https://t.me/your_bot?start=ref123"
        )
        await callback.answer()
        return
    # =========================================================
    
    async with AsyncSessionLocal() as session:
        # Получаем referrer_id из состояния
        referrer_id = data.get("referrer_id")
        
        await state.update_data(ip_address=str(callback.from_user.id))
        
        storm = StormProtection(session)
        
        is_whitelisted = await storm.is_whitelisted(
            ip=str(callback.from_user.id),
            referral_code=ref_code
        )
        
        if is_whitelisted:
            await callback.message.answer(
                "✅ Вы в белом списке! Продолжаем регистрацию.\n\n"
                "📱 Введите ваш номер телефона в формате:\n"
                "• +7 999 123-45-67\n"
                "• 89991234567\n"
                "• 9991234567\n\n"
                "Бот автоматически приведёт его к формату +7XXXXXXXXXX"
            )
            await state.set_state(Registration.waiting_for_phone)
            await callback.answer()
            return
        
        in_storm, storm_stats = await storm.check_storm()
        if in_storm:
            await callback.message.answer(
                "⚠️ Временные технические сложности\n\n"
                "В связи с высокой нагрузкой регистрация временно приостановлена.\n"
                "Пожалуйста, попробуйте через 30 минут.\n\n"
                "Приносим извинения за неудобства."
            )
            await callback.answer()
            return
        
        ip_limit_ok, ip_count = await storm.check_ip_limit(str(callback.from_user.id))
        if not ip_limit_ok:
            await callback.message.answer(
                "⚠️ Превышен лимит регистраций\n\n"
                "С вашего IP-адреса уже зарегистрировано максимальное количество пользователей.\n"
                "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
            )
            await callback.answer()
            return
        
        captcha_enabled = await get_security_setting(session, "captcha_enabled", "false")
        captcha_enabled = captcha_enabled.lower() == "true"
        
        if captcha_enabled:
            question, answer = captcha.generate()
            await state.update_data(captcha_answer=answer)
            keyboard = captcha.create_keyboard(answer)
            
            await callback.message.answer(
                "🤖 Проверка: вы не робот\n\n"
                "Пожалуйста, решите простой пример — это поможет защитить сервис от ботов.\n\n"
                f"{question}\n\n"
                f"Выберите правильный ответ:",
                reply_markup=keyboard
            )
            await state.set_state(Registration.waiting_for_captcha)
        else:
            await callback.message.answer(
                "📱 Введите ваш номер телефона в формате:\n"
                "• +7 999 123-45-67\n"
                "• 89991234567\n"
                "• 9991234567\n\n"
                "Бот автоматически приведёт его к формату +7XXXXXXXXXX"
            )
            await state.set_state(Registration.waiting_for_phone)
    
    await callback.answer()

@router.callback_query(F.data.startswith("captcha_"), Registration.waiting_for_captcha)
async def process_captcha(callback: CallbackQuery, state: FSMContext):
    answer = int(callback.data.split("_")[1])
    data = await state.get_data()
    correct_answer = data.get("captcha_answer")
    
    if answer == correct_answer:
        await state.update_data(captcha_passed=True)
        await callback.message.delete()
        
        await callback.message.answer(
            "✅ Капча пройдена!\n\n"
            "📱 Введите ваш номер телефона в формате:\n"
            "• +7 999 123-45-67\n"
            "• 89991234567\n"
            "• 9991234567\n\n"
            "Бот автоматически приведёт его к формату +7XXXXXXXXXX"
        )
        await state.set_state(Registration.waiting_for_phone)
        await callback.answer()
    else:
        await callback.answer("❌ Неправильный ответ.", show_alert=True)

@router.message(Registration.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обрабатывает введённый номер телефона"""
    raw_phone = message.text.strip()
    phone = clean_phone_number(raw_phone)
    
    if not phone:
        await message.answer(
            "❌ Неверный формат номера.\n\n"
            "Пожалуйста, введите номер в одном из форматов:\n"
            "• +7 999 123-45-67\n"
            "• 89991234567\n"
            "• 9991234567\n\n"
            "Попробуйте еще раз:"
        )
        return
    
    full_name = message.from_user.full_name or "Имя не указано"

    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    ip_address = data.get("ip_address", str(message.from_user.id))
    captcha_passed = data.get("captcha_passed", False)

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.phone == phone))
        if existing.scalar_one_or_none():
            await message.answer(
                "❌ Этот номер уже зарегистрирован.\n\n"
                "Если это ваш номер, свяжитесь с администратором."
            )
            await state.clear()
            return

        request = RegistrationRequest(
            telegram_id=message.from_user.id,
            full_name=full_name,
            phone=phone,
            invited_by_id=referrer_id,
            captcha_passed=captcha_passed,
            ip_address=ip_address,
            risk_score=0
        )
        session.add(request)
        await session.commit()
        await state.update_data(request_id=request.id)

    await message.answer(
        "✅ Номер телефона принят!\n\n"
        "📸 **Добавьте социальные сети**\n\n"
        "Для завершения регистрации укажите ваши социальные сети.\n\n"
        "Это поможет нам убедиться, что вы профессиональный фотограф/видеограф.\n\n"
        "👇 **Нажмите на кнопку ниже** — ничего вводить не нужно.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📷 Добавить Instagram", callback_data="add_instagram")],
                [InlineKeyboardButton(text="📱 Добавить ВКонтакте", callback_data="add_vkontakte")],
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="social_finish")]
            ]
        ),
        parse_mode="Markdown"
    )
    await state.set_state(Registration.waiting_for_social)

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "❓ **Помощь по программе лояльности**\n\n"
        "📌 **Основные команды:**\n"
        "• /start — начать регистрацию / перезапустить бота\n"
        "• /help — показать это сообщение\n\n"
        "📌 **Как начисляются бонусы:**\n"
        "• 200 баллов — за регистрацию\n"
        "• 100 баллов — за каждого друга, который совершит первую аренду\n\n"
        "📌 **Кнопки главного меню:**\n"
        "• 🏠 Баланс — проверить количество баллов\n"
        "• 👥 Мои друзья — список приглашённых\n"
        "• 📜 История — история операций\n"
        "• 🎁 Пригласить друга — получить ссылку для приглашения\n\n"
        "📌 **Требования к Instagram:**\n"
        "• Аккаунт должен быть открытым (публичным)\n"
        "• Приватные аккаунты не принимаются\n\n"
        "По всем вопросам обращайтесь к администратору."
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    await message.answer(
        "👑 **Панель администратора**\n\n"
        "Доступные команды:\n"
        "/admin - показать это меню\n"
        "/review - модерация заявок\n"
        "/stats - статистика\n"
        "/users - список пользователей\n"
        "/blacklist - черный список\n\n"
        "Для управления пользователями используйте веб-интерфейс:\n"
        f"http://194.67.102.115:8000",
        parse_mode="Markdown"
    )

@router.message(Command("enter_code"))
async def cmd_enter_code(message: Message, state: FSMContext):
    await message.answer(
        "🔗 Введите пригласительный код\n\n"
        "Если у вас есть ссылка от друга, введите код из неё:\n\n"
        "Пример ссылки: https://t.me/your_bot?start=ref12345\n"
        "Код для ввода: ref12345\n\n"
        "Просто отправьте код в чат:"
    )
    await state.set_state(Registration.waiting_for_manual_code)

@router.message(Registration.waiting_for_manual_code)
async def process_manual_code(message: Message, state: FSMContext):
    code = message.text.strip()
    
    async with AsyncSessionLocal() as session:
        code_record = await session.execute(
            select(ReferralCode).where(ReferralCode.code == code)
        )
        code_record = code_record.scalar_one_or_none()
        
        if not code_record or not code_record.is_active:
            await message.answer(
                "❌ Недействительный код. Попробуйте еще раз или /start для новой попытки."
            )
            return
        
        if code_record.expires_at and code_record.expires_at < datetime.utcnow():
            await message.answer("⏰ Срок действия кода истек. Попросите новую ссылку.")
            return
        
        if code_record.max_uses > 0 and code_record.used_count >= code_record.max_uses:
            await message.answer("⚠️ Лимит использований кода исчерпан.")
            return
        
        await state.update_data(ref_code=code, referrer_id=code_record.owner_id)
        
        # Показываем приветствие с кнопкой
        start_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Начать регистрацию", callback_data="start_registration")]
            ]
        )
        
        await message.answer(
            WELCOME_MESSAGE,
            reply_markup=start_keyboard
        )

async def log_user_action(user_id: int, action_type: str, details: str = None):
    async with AsyncSessionLocal() as session:
        log = UserLog(
            user_id=user_id,
            action_type=action_type,
            action_details=details
        )
        session.add(log)
        await session.commit()