from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import os

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
        
        # Проверяем, есть ли сессия и ключ authenticated
        if request.session.get("authenticated") is True:
            # Проверяем, не истекла ли сессия
            if request.session.get("expires_at"):
                import time
                if time.time() > request.session["expires_at"]:
                    # Сессия истекла
                    request.session.clear()
                    return RedirectResponse(url="/login", status_code=303)
            return await call_next(request)
        
        # Не авторизован — редирект на логин
        return RedirectResponse(url="/login", status_code=303)