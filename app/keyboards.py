from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from app.config import settings

def main_menu_keyboard(user_id: int = None):
    """Главное меню с кнопками, адаптированное под пользователя"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🏠 Баланс")
    builder.button(text="👥 Мои друзья")
    builder.button(text="📜 История")
    builder.button(text="📸 Каталог")
    builder.button(text="❓ Помощь")
    builder.button(text="🎁 Пригласить друга")
    
    if user_id and user_id in settings.ADMIN_IDS:
        builder.button(text="🔗 Управление ссылками")
    
    builder.adjust(2, 2, 2)
    return builder.as_markup(
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False
    )

def referral_menu_keyboard(referral_link: str):
    """Клавиатура для реферальной ссылки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={referral_link}")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def confirm_delete_keyboard():
    """Клавиатура для подтверждения удаления аккаунта"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, я подтверждаю удаление", callback_data="confirm_delete")
    builder.button(text="❌ Отмена", callback_data="cancel_delete")
    builder.adjust(1)
    return builder.as_markup()