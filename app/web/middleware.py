from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import time

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        print(f"🔍 AuthMiddleware: path={path}")
        
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
        
        is_public = False
        for public_path in PUBLIC_PATHS:
            if path == public_path or path.startswith(public_path + "/"):
                is_public = True
                print(f"✅ PUBLIC: {path} matches {public_path}")
                break
        
        if is_public:
            print(f"➡️ Пропускаем публичный путь: {path}")
            return await call_next(request)
        
        print(f"🔒 Требуется авторизация: {path}")
        if "session" not in request.scope:
            print(f"❌ Нет session в scope, редирект на /login")
            return RedirectResponse(url="/login", status_code=303)
        
        if not request.session.get("authenticated"):
            print(f"❌ Не авторизован, редирект на /login")
            return RedirectResponse(url="/login", status_code=303)
        
        expires_at = request.session.get("expires_at")
        if expires_at and time.time() > expires_at:
            print(f"❌ Сессия истекла, редирект на /login")
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)
        
        print(f"✅ Авторизован, пропускаем")
        return await call_next(request)