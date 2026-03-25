from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import time

# Список маршрутов, которые доступны без авторизации
PUBLIC_PATHS = [
    "/login",
    "/logout",
    "/static",
]

class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки аутентификации"""
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        # Проверяем, не публичный ли маршрут
        path = request.url.path
        
        # Пропускаем публичные маршруты
        for public_path in PUBLIC_PATHS:
            if path.startswith(public_path):
                return await call_next(request)
        
        # Проверяем, авторизован ли пользователь
        # Сессия уже должна быть доступна благодаря SessionMiddleware
        authenticated = request.session.get("authenticated", False)
        
        if authenticated:
            # Проверяем, не истекла ли сессия
            expires_at = request.session.get("expires_at")
            if expires_at and time.time() > expires_at:
                # Сессия истекла
                request.session.clear()
                return RedirectResponse(url="/login", status_code=303)
            return await call_next(request)
        
        # Не авторизован — редирект на логин
        return RedirectResponse(url="/login", status_code=303)