from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import time

class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки аутентификации в админке"""
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Все пути, которые НЕ требуют авторизации
        PUBLIC_PATHS = [
            "/login",
            "/logout", 
            "/static",
            "/public",
            "/client",
            "/client/login",
            "/client/telegram-auth",
            "/client/reset-password"
        ]
        
        # Проверяем, публичный ли путь
        is_public = False
        for public_path in PUBLIC_PATHS:
            if path == public_path or path.startswith(public_path + "/"):
                is_public = True
                break
        
        if is_public:
            return await call_next(request)
        
        # Для всех остальных путей (админка) проверяем авторизацию
        if "session" not in request.scope:
            return RedirectResponse(url="/login", status_code=303)
        
        if not request.session.get("authenticated"):
            return RedirectResponse(url="/login", status_code=303)
        
        expires_at = request.session.get("expires_at")
        if expires_at and time.time() > expires_at:
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)
        
        return await call_next(request)