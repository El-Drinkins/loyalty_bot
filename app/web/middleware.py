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
        
        # Временно пропускаем все запросы для проверки админки
        print(f"🔍 Временно пропускаем: {path}")
        return await call_next(request)