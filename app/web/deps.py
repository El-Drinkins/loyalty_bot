from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import Request, HTTPException

from ..models import AsyncSessionLocal

templates = Jinja2Templates(directory="app/web/templates")

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text("SHOW TIME ZONE"))
            current_tz = result.scalar()
            print(f"🕐 Текущий часовой пояс ДО: {current_tz}")
            
            await session.execute(text("SET TIME ZONE 'Europe/Moscow'"))
            print("✅ Команда SET TIME ZONE выполнена")
            
            result = await session.execute(text("SHOW TIME ZONE"))
            new_tz = result.scalar()
            print(f"🕐 Текущий часовой пояс ПОСЛЕ: {new_tz}")
            
        except Exception as e:
            print(f"⚠️ Ошибка при установке часового пояса: {e}")
            import traceback
            traceback.print_exc()
        
        yield session

def require_auth(request: Request):
    """Проверяет, авторизован ли пользователь."""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return True