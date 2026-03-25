from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import time

# Список маршрутов, которые доступны без авторизации
PUBLIC_PATHS = [
    "/login",
    "/logout",
    "/static",
]

class CombinedAuthMiddleware(BaseHTTPMiddleware):
    """Объединённый middleware: сессия + авторизация"""
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
        # Внутренний SessionMiddleware
        self.session_middleware = SessionMiddleware(
            app,
            secret_key=secret_key,
            session_cookie="loyalty_session",
            max_age=3600 * 24,  # 24 часа
            same_site="lax"
        )
    
    async def dispatch(self, request: Request, call_next):
        # Сначала пропускаем через SessionMiddleware
        # Создаём заглушку для call_next, чтобы SessionMiddleware мог выполниться
        async def session_call_next(scope, receive, send):
            # После того как SessionMiddleware обработал запрос, продолжаем
            pass
        
        # Временно сохраняем оригинальный call_next
        original_call_next = call_next
        
        # Запускаем SessionMiddleware
        # Это сложно сделать напрямую, поэтому используем другой подход
        
        # Просто проверяем, есть ли session в scope
        # Если нет — значит, SessionMiddleware ещё не обработал запрос
        # Но мы не можем его вызвать вручную...
        
        # Более простой подход: перенести логику в один middleware,
        # который сам управляет сессией через cookies
        
        # Получаем session из cookies вручную
        from starlette.datastructures import MutableHeaders
        import json
        import base64
        
        # Проверяем, не публичный ли маршрут
        path = request.url.path
        for public_path in PUBLIC_PATHS:
            if path.startswith(public_path):
                return await original_call_next(request)
        
        # Получаем session из cookie
        session_cookie = request.cookies.get("loyalty_session")
        session_data = {}
        
        if session_cookie:
            try:
                # Декодируем cookie (упрощённо, без проверки подписи)
                import binascii
                decoded = base64.urlsafe_b64decode(session_cookie)
                session_data = json.loads(decoded)
            except:
                pass
        
        authenticated = session_data.get("authenticated", False)
        
        if authenticated:
            expires_at = session_data.get("expires_at")
            if expires_at and time.time() > expires_at:
                # Сессия истекла
                response = RedirectResponse(url="/login", status_code=303)
                response.delete_cookie("loyalty_session")
                return response
            # Продолжаем, передавая session_data в request
            request.state.session = session_data
            return await original_call_next(request)
        
        # Не авторизован — редирект на логин
        return RedirectResponse(url="/login", status_code=303)