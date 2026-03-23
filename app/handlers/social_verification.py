import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..models import AsyncSessionLocal, RegistrationRequest

router = Router()

class SocialStates(StatesGroup):
    waiting_for_instagram = State()
    waiting_for_vkontakte = State()

def validate_instagram(username: str) -> bool:
    pattern = r'^[a-zA-Z0-9._]{1,30}$'
    return bool(re.match(pattern, username))

def validate_vkontakte(url_or_id: str) -> tuple[bool, str]:
    url_or_id = url_or_id.strip()
    
    if url_or_id.isdigit():
        return True, f"id{url_or_id}"
    
    if url_or_id.startswith('@'):
        url_or_id = url_or_id[1:]
    
    vk_patterns = [
        r'vk\.com/([a-zA-Z0-9_.]+)',
        r'vkontakte\.ru/([a-zA-Z0-9_.]+)',
        r'^([a-zA-Z0-9_.]+)$'
    ]
    
    for pattern in vk_patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return True, match.group(1)
    
    return False, ""

@router.callback_query(F.data == "add_instagram")
async def add_instagram(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 Добавьте Instagram\n\n"
        "Введите ваш Instagram username (без @):\n\n"
        "Пример: petrov_photo\n\n"
        "⚠️ Важно: аккаунт должен быть открытым (публичным).\n"
        "Приватные аккаунты не будут приняты."
    )
    await state.set_state(SocialStates.waiting_for_instagram)
    await callback.answer()

@router.message(SocialStates.waiting_for_instagram)
async def process_instagram(message: Message, state: FSMContext):
    username = message.text.strip().replace('@', '')
    
    if not validate_instagram(username):
        await message.answer(
            "❌ Некорректный username\n\n"
            "Instagram username может содержать только:\n"
            "• латинские буквы\n"
            "• цифры\n"
            "• точки (.)\n"
            "• подчеркивания (_)\n"
            "Длина: от 1 до 30 символов\n\n"
            "Попробуйте еще раз:"
        )
        return
    
    await state.update_data(instagram=username)
    await state.update_data(instagram_status='pending')
    
    data = await state.get_data()
    request_id = data.get('request_id')
    
    if request_id:
        async with AsyncSessionLocal() as session:
            req = await session.get(RegistrationRequest, request_id)
            if req:
                req.instagram = username
                await session.commit()
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, добавить", callback_data="social_confirm_instagram")],
            [InlineKeyboardButton(text="❌ Изменить", callback_data="add_instagram")],
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="social_skip_instagram")]
        ]
    )
    
    await message.answer(
        f"📸 Подтвердите Instagram\n\n"
        f"Вы ввели: @{username}\n\n"
        f"⚠️ Напоминаем: аккаунт должен быть открытым (публичным).\n"
        f"Приватные аккаунты не будут приняты.\n\n"
        f"Всё верно?",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "social_confirm_instagram")
async def confirm_instagram(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    instagram = data.get('instagram')
    
    await callback.message.edit_text(
        f"✅ Instagram @{instagram} добавлен!"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Добавить ВКонтакте", callback_data="add_vkontakte")],
            [InlineKeyboardButton(text="⏭️ Завершить регистрацию", callback_data="social_finish")]
        ]
    )
    await callback.message.answer(
        "Хотите добавить ВКонтакте?",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "add_vkontakte")
async def add_vkontakte(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📱 Добавьте ВКонтакте\n\n"
        "Введите ссылку на профиль или ID:\n\n"
        "Примеры:\n"
        "• vk.com/durov\n"
        "• @durov\n"
        "• durov\n"
        "• id123456"
    )
    await state.set_state(SocialStates.waiting_for_vkontakte)
    await callback.answer()

@router.message(SocialStates.waiting_for_vkontakte)
async def process_vkontakte(message: Message, state: FSMContext):
    valid, value = validate_vkontakte(message.text)
    
    if not valid:
        await message.answer(
            "❌ Некорректная ссылка\n\n"
            "Пожалуйста, введите корректную ссылку на профиль ВКонтакте.\n\n"
            "Примеры:\n"
            "• vk.com/durov\n"
            "• @durov\n"
            "• durov\n"
            "• id123456"
        )
        return
    
    await state.update_data(vkontakte=value)
    
    data = await state.get_data()
    request_id = data.get('request_id')
    
    if request_id:
        async with AsyncSessionLocal() as session:
            req = await session.get(RegistrationRequest, request_id)
            if req:
                req.vkontakte = value
                await session.commit()
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, добавить", callback_data="social_confirm_vkontakte")],
            [InlineKeyboardButton(text="❌ Изменить", callback_data="add_vkontakte")],
            [InlineKeyboardButton(text="⏭️ Завершить регистрацию", callback_data="social_finish")]
        ]
    )
    
    display_value = f"vk.com/{value}" if not value.startswith('id') else value
    await message.answer(
        f"📱 Подтвердите ВКонтакте\n\n"
        f"Вы ввели: {display_value}\n\n"
        f"Всё верно?",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "social_confirm_vkontakte")
async def confirm_vkontakte(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    vkontakte = data.get('vkontakte')
    
    display_value = f"vk.com/{vkontakte}" if not vkontakte.startswith('id') else vkontakte
    await callback.message.edit_text(
        f"✅ ВКонтакте {display_value} добавлен!"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить регистрацию", callback_data="social_finish")]
        ]
    )
    await callback.message.answer(
        "Все данные собраны! Завершите регистрацию.",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "social_skip_instagram")
async def skip_instagram(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Добавить ВКонтакте", callback_data="add_vkontakte")],
            [InlineKeyboardButton(text="⏭️ Завершить регистрацию", callback_data="social_finish")]
        ]
    )
    await callback.message.edit_text(
        "Instagram пропущен. Хотите добавить ВКонтакте?"
    )
    await callback.answer()

@router.callback_query(F.data == "social_finish")
async def social_finish(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✅ Ваша заявка отправлена на модерацию. Ожидайте подтверждения администратора."
    )
    await callback.answer()
    await state.clear()