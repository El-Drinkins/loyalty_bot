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

# Настраиваем логгер для замеров времени
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
    
    # Проверяем, есть ли пользователь в БД
    start_db = time.time()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        db_time = time.time() - start_db
        time_logger.info(f"⏱️ Поиск пользователя: {db_time*1000:.2f}мс")

        if user:
            # Проверяем, не заблокирован ли пользователь
            if user.blacklisted:
                await message.answer(
                    "⛔ Ваш аккаунт заблокирован.\n\n"
                    "Для получения информации обратитесь к администратору."
                )
                total_time = time.time() - start_total
                time_logger.info(f"⏱️ ВСЕГО (блокировка): {total_time*1000:.2f}мс")
                return
            
            # Уже зарегистрирован – показываем меню
            start_menu = time.time()
            await message.answer(
                f"С возвращением, {user.full_name}!\nВаш баланс: {user.balance} ⭐",
                reply_markup=main_menu_keyboard(message.from_user.id)
            )
            menu_time = time.time() - start_menu
            
            # Логируем действие
            start_log = time.time()
            log = UserLog(
                user_id=user.id,
                action_type="command",
                action_details="/start (returning)"
            )
            session.add(log)
            await session.commit()
            log_time = time.time() - start_log
            
            total_time = time.time() - start_total
            time_logger.info(
                f"⏱️ ВОЗВРАЩЕНИЕ | "
                f"БД: {db_time*1000:.1f}мс | "
                f"Меню: {menu_time*1000:.1f}мс | "
                f"Лог: {log_time*1000:.1f}мс | "
                f"ВСЕГО: {total_time*1000:.1f}мс"
            )
            return

    # Новый пользователь – проверяем реферальный код
    args = message.text.split()
    ref_code = None
    
    if len(args) > 1:
        ref_code = args[1]
    
    # =========================================================
    # ВРЕМЕННО ОТКЛЮЧЕНО: регистрация без реферального кода
    # =========================================================
    # if not ref_code:
    #     total_time = time.time() - start_total
    #     time_logger.info(f"⏱️ Обработка без кода: {total_time*1000:.2f}мс")
    #     await message.answer(
    #         "🔒 Регистрация только по приглашениям\n\n"
    #         "К сожалению, регистрация в боте возможна только по пригласительным ссылкам.\n\n"
    #         "Если вас пригласил друг, попросите у него ссылку.\n\n"
    #         "Пример ссылки: https://t.me/your_bot?start=ref123"
    #     )
    #     return
    # =========================================================

    # Проверяем код
    start_code = time.time()
    async with AsyncSessionLocal() as session:
        code_record = await session.execute(
            select(ReferralCode).where(ReferralCode.code == ref_code)
        )
        code_record = code_record.scalar_one_or_none()
        code_time = time.time() - start_code
        time_logger.info(f"⏱️ Проверка кода: {code_time*1000:.2f}мс")
        
        # Если код не передан или недействителен, всё равно продолжаем (так как мы отключили проверку)
        # Но если код передан, проверяем его валидность
        if ref_code and (not code_record or not code_record.is_active):
            await message.answer(
                "❌ Недействительный код. Продолжаем регистрацию без реферальной ссылки."
            )
            # Не возвращаемся, продолжаем регистрацию
            
        if ref_code and code_record:
            if code_record.expires_at and code_record.expires_at < datetime.utcnow():
                await message.answer(
                    "⏰ Срок действия кода истек. Продолжаем регистрацию без реферальной ссылки."
                )
            elif code_record.max_uses > 0 and code_record.used_count >= code_record.max_uses:
                await message.answer(
                    "⚠️ Лимит ссылки исчерпан. Продолжаем регистрацию без реферальной ссылки."
                )
            else:
                # Сохраняем данные о пригласившем
                await state.update_data(
                    ref_code=ref_code,
                    referrer_id=code_record.owner_id,
                    ip_address=str(message.from_user.id)
                )
                referrer = await session.get(User, code_record.owner_id)
                referrer_name = referrer.full_name if referrer else "пользователь"
                await message.answer(
                    f"🎉 Вас пригласил: {referrer_name}\n\n"
                    "Продолжаем регистрацию..."
                )
        
        # Показываем капчу (всегда)
        start_captcha_gen = time.time()
        question, answer = captcha.generate()
        await state.update_data(captcha_answer=answer)
        keyboard = captcha.create_keyboard(answer)
        captcha_gen_time = time.time() - start_captcha_gen
        time_logger.info(f"⏱️ Генерация капчи: {captcha_gen_time*1000:.2f}мс")
        
        start_send = time.time()
        await message.answer(
            f"🔐 Проверка: решите пример\n\n"
            f"{question}\n\n"
            f"Выберите правильный ответ:",
            reply_markup=keyboard
        )
        send_time = time.time() - start_send
        time_logger.info(f"⏱️ Отправка сообщения: {send_time*1000:.2f}мс")
        
        await state.set_state(Registration.waiting_for_captcha)
        
        total_time = time.time() - start_total
        time_logger.info(
            f"⏱️ ВСЕГО регистрация: {total_time*1000:.1f}мс"
        )

# ==================================================
# ОБРАБОТЧИК КАПЧИ (вызывает функцию из captcha.py)
# ==================================================
@router.callback_query(F.data.startswith("captcha_"), Registration.waiting_for_captcha)
async def process_captcha(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает ответ на капчу"""
    from .captcha import check_captcha
    await check_captcha(callback, state)

# ==================================================
# ОБРАБОТЧИК ПОЛУЧЕНИЯ ТЕЛЕФОНА (ЧЕРЕЗ КНОПКУ)
# ==================================================
@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    """Обрабатывает полученный контакт (номер телефона)"""
    start_total = time.time()
    
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Пожалуйста, отправьте свой собственный номер телефона.")
        return

    phone = contact.phone_number
    full_name = message.from_user.full_name or "Имя не указано"

    data = await state.get_data()
    ref_code = data.get("ref_code")
    referrer_id = data.get("referrer_id")
    captcha_passed = data.get("captcha_passed", False)
    ip_address = data.get("ip_address", str(message.from_user.id))

    start_db = time.time()
    async with AsyncSessionLocal() as session:
        # Проверяем, не занят ли номер
        existing = await session.execute(select(User).where(User.phone == phone))
        if existing.scalar_one_or_none():
            await message.answer(
                "❌ Этот номер уже зарегистрирован.\n\n"
                "Если это ваш номер, попробуйте восстановить доступ или свяжитесь с администратором."
            )
            await state.clear()
            return

        # Создаем заявку на регистрацию
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
        
        db_time = time.time() - start_db
        time_logger.info(f"⏱️ Создание заявки: {db_time*1000:.2f}мс")
        
        await state.update_data(request_id=request.id)

    start_send = time.time()
    await message.answer(
        "📸 **Добавьте социальные сети**\n\n"
        "Для завершения регистрации укажите ваши социальные сети.\n\n"
        "Это поможет нам убедиться, что вы профессиональный фотограф.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📷 Добавить Instagram", callback_data="add_instagram")],
                [InlineKeyboardButton(text="📱 Добавить ВКонтакте", callback_data="add_vkontakte")],
                [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="social_finish")]
            ]
        ),
        parse_mode="Markdown"
    )
    send_time = time.time() - start_send
    time_logger.info(f"⏱️ Отправка сообщения о соцсетях: {send_time*1000:.2f}мс")
    
    total_time = time.time() - start_total
    time_logger.info(f"⏱️ ВСЕГО process_phone: {total_time*1000:.2f}мс")
    
    await state.set_state(Registration.waiting_for_social)

# ==================================================
# КОМАНДА ДЛЯ РУЧНОГО ВВОДА КОДА
# ==================================================
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

# ==================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ЛОГИРОВАНИЯ
# ==================================================
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