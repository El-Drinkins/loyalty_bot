import time
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from datetime import datetime

from ..models import User, Referral, Transaction, AsyncSessionLocal, ReferralCode, UserLog, RegistrationRequest
from ..keyboards import contact_keyboard, main_menu_keyboard
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

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    start_total = time.time()
    logger.info(f"▶️ Начало обработки /start от пользователя {message.from_user.id}")
    
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

    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    # Приветственное сообщение для нового пользователя
    welcome_text = (
        "📸 Добро пожаловать в программу лояльности!\n\n"
        "Это бот для фотографов и видеографов. Здесь вы можете:\n"
        "• Получать бонусы за регистрацию и аренду техники\n"
        "• Приглашать друзей и получать за это бонусы\n"
        "• Следить за балансом бонусов и историей операций\n\n"
        "🎁 За регистрацию вы получите 200 бонусных баллов!\n\n"
        "Для продолжения регистрации введите /start"
    )
    
    await message.answer(welcome_text)

@router.message(CommandStart())
async def cmd_start_after_welcome(message: Message, state: FSMContext):
    """Обработчик повторного /start после приветствия"""
    start_total = time.time()
    logger.info(f"▶️ Начало обработки /start от пользователя {message.from_user.id}")
    
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

    args = message.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    async with AsyncSessionLocal() as session:
        question, answer = captcha.generate()
        await state.update_data(captcha_answer=answer)
        keyboard = captcha.create_keyboard(answer)
        
        await message.answer(
            f"🔐 Проверка: решите пример\n\n{question}\n\nВыберите правильный ответ:",
            reply_markup=keyboard
        )
        await state.set_state(Registration.waiting_for_captcha)

@router.callback_query(F.data.startswith("captcha_"), Registration.waiting_for_captcha)
async def process_captcha(callback: CallbackQuery, state: FSMContext):
    answer = int(callback.data.split("_")[1])
    data = await state.get_data()
    correct_answer = data.get("captcha_answer")
    
    if answer == correct_answer:
        await state.update_data(captcha_passed=True)
        await callback.message.delete()
        
        # Inline-кнопка для отправки номера телефона
        phone_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📱 Отправить номер телефона", callback_data="send_phone")]
            ]
        )
        
        await callback.message.answer(
            "✅ Капча пройдена!\n\n"
            "📱 Отправьте ваш номер телефона, нажав на кнопку ниже.\n"
            "(⚠️ Не вводите номер в поле для текста — бот его не примет)",
            reply_markup=phone_keyboard
        )
        await state.set_state(Registration.waiting_for_phone)
        await callback.answer()
    else:
        await callback.answer("❌ Неправильный ответ.", show_alert=True)

@router.callback_query(F.data == "send_phone", Registration.waiting_for_phone)
async def request_phone(callback: CallbackQuery, state: FSMContext):
    """Обработчик inline-кнопки для отправки номера телефона"""
    # Запрашиваем контакт через обычную кнопку (только так можно получить номер)
    from ..keyboards import contact_keyboard
    
    # Удаляем сообщение с inline-кнопкой
    await callback.message.delete()
    
    await callback.message.answer(
        "📱 Нажмите на кнопку ниже, чтобы отправить номер телефона:",
        reply_markup=contact_keyboard()
    )
    await callback.answer()

@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Отправьте свой номер.")
        return

    phone = contact.phone_number
    full_name = message.from_user.full_name or "Имя не указано"

    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    captcha_passed = data.get("captcha_passed", False)

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.phone == phone))
        if existing.scalar_one_or_none():
            await message.answer("❌ Этот номер уже зарегистрирован.")
            await state.clear()
            return

        request = RegistrationRequest(
            telegram_id=message.from_user.id,
            full_name=full_name,
            phone=phone,
            invited_by_id=referrer_id,
            captcha_passed=captcha_passed,
            ip_address=str(message.from_user.id),
            risk_score=0
        )
        session.add(request)
        await session.commit()
        await state.update_data(request_id=request.id)

    await message.answer(
        "📸 **Добавьте социальные сети**\n\n"
        "Для завершения регистрации укажите ваши социальные сети.\n\n"
        "Это поможет нам убедиться, что вы профессиональный фотограф/видеограф.",
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

# Обработчик текстового ввода номера телефона (если пользователь всё же ввел текст)
@router.message(Registration.waiting_for_phone)
async def handle_wrong_phone_input(message: Message, state: FSMContext):
    """Если пользователь ввел текст вместо нажатия кнопки"""
    from ..keyboards import contact_keyboard
    
    await message.answer(
        "❌ Вы отправили текст, а бот ожидает номер телефона.\n\n"
        "Пожалуйста, нажмите на кнопку ниже, чтобы отправить номер:",
        reply_markup=contact_keyboard()
    )

# Остальные функции (cmd_enter_code, process_manual_code, log_user_action) оставь как есть
@router.message(Command("enter_code"))
async def cmd_enter_code(message: Message, state: FSMContext):
    """Команда для ручного ввода кода"""
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
    """Обработка ручного ввода кода"""
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
        
        await cmd_start(message, state)

async def log_user_action(user_id: int, action_type: str, details: str = None):
    """Вспомогательная функция для логирования"""
    async with AsyncSessionLocal() as session:
        log = UserLog(
            user_id=user_id,
            action_type=action_type,
            action_details=details
        )
        session.add(log)
        await session.commit()