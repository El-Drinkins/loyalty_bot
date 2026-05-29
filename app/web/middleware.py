from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key

    async def dispatch(self, request: Request, call_next):
        # Публичные маршруты
        public_paths = ["/login", "/logout", "/health", "/client", "/admin/2fa", "/admin/setup-totp", "/admin/verify-totp-setup"]
        
        path = request.url.path
        
        for public in public_paths:
            if path.startswith(public):
                return await call_next(request)

        # Проверка авторизации
        if not request.session.get("authenticated"):
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)