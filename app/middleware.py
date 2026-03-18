from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from sqlalchemy import select

from .models import AsyncSessionLocal, User, UserLog  # изменен импорт

# Список кнопок, которые не логируем через middleware
BUTTONS_TO_SKIP = ["🏠 Баланс", "👥 Мои друзья", "📜 История", "❓ Помощь", "🔗 Мои ссылки", "🎁 Пригласить друга в бот", "🔗 Управление ссылками"]

class BlacklistMiddleware(BaseMiddleware):
    """
    Middleware для проверки, не находится ли пользователь в черном списке.
    Если пользователь в черном списке, бот игнорирует его сообщения.
    """
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Определяем ID пользователя из события
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        if not user_id:
            return await handler(event, data)
        
        # Проверяем, есть ли пользователь в черном списке
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            # Если пользователь в черном списке - игнорируем
            if user and user.blacklisted:
                # Для callback запросов нужно ответить, чтобы убрать "часики"
                if isinstance(event, CallbackQuery):
                    await event.answer("⛔ Вы заблокированы в системе лояльности", show_alert=True)
                return None  # Прерываем обработку
        
        # Пользователь не в черном списке - передаем дальше
        return await handler(event, data)


class UserLoggingMiddleware(BaseMiddleware):
    """
    Middleware для логирования действий пользователей
    """
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Определяем тип действия и пользователя
        user_id = None
        action_type = None
        action_details = None
        should_log = True
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            if event.text:
                if event.text.startswith('/'):
                    # Команды - логируем
                    action_type = "command"
                    action_details = event.text
                elif event.text in BUTTONS_TO_SKIP:
                    # Это кнопки меню - не логируем здесь, они будут обработаны в хендлерах
                    should_log = False
                else:
                    # Другие сообщения
                    action_type = "message"
                    action_details = event.text[:100]
            elif event.contact:
                action_type = "contact_sent"
                action_details = "Отправил номер телефона"
        
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            action_type = "callback"
            action_details = event.data
        
        # Если есть что логировать и это не кнопка меню
        if user_id and action_type and should_log:
            async with AsyncSessionLocal() as session:
                user = await session.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                user = user.scalar_one_or_none()
                
                if user:
                    log = UserLog(
                        user_id=user.id,
                        action_type=action_type,
                        action_details=action_details
                    )
                    session.add(log)
                    await session.commit()
        
        return await handler(event, data)