from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from .routers import (
    main_router, 
    points_router, 
    stats_router,
    admin_router, 
    user_router, 
    api_router, 
    catalog_router,
    search_router,
    admin_review_router,
    mailing_router,
    auth_router
)
from .middleware import AuthMiddleware

app = FastAPI()

# Добавляем SessionMiddleware ПЕРВЫМ
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here-change-this-in-production",
    session_cookie="loyalty_session",
    max_age=3600 * 24,  # 24 часа
    same_site="lax"
)

# Добавляем AuthMiddleware ВТОРЫМ (после SessionMiddleware)
app.add_middleware(
    AuthMiddleware,
    secret_key="your-secret-key-here-change-this-in-production"
)

# Подключаем шаблоны
templates = Jinja2Templates(directory="app/web/templates")

# Подключаем все роутеры
app.include_router(auth_router)
app.include_router(main_router)
app.include_router(points_router)
app.include_router(stats_router)
app.include_router(admin_router)
app.include_router(user_router)
app.include_router(api_router)
app.include_router(catalog_router, prefix="/catalog")
app.include_router(search_router)
app.include_router(admin_review_router)
app.include_router(mailing_router)

print("=== ЗАРЕГИСТРИРОВАННЫЕ МАРШРУТЫ ===")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"{route.methods} {route.path}")
print("===================================")