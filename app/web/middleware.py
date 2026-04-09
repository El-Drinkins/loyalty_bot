from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
import time

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        # Временно отключаем проверку авторизации для отладки
        print(f"🔍 AuthMiddleware временно отключена, пропускаем: {request.url.path}")
        return await call_next(request)