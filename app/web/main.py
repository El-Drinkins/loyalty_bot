from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os

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
    auth_router,
    web_client_router
)
from .middleware import AuthMiddleware

app = FastAPI()

# SessionMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here-change-this-in-production",
    session_cookie="loyalty_session",
    max_age=3600 * 24,
    same_site="lax"
)

# AuthMiddleware для админки
app.add_middleware(
    AuthMiddleware,
    secret_key="your-secret-key-here-change-this-in-production"
)

# Подключаем статические файлы веб-версии из папки public
public_dir = os.path.join(os.path.dirname(__file__), "public")
if os.path.exists(public_dir):
    app.mount("/public", StaticFiles(directory=public_dir), name="public")
    print(f"✅ Статические файлы веб-версии подключены из {public_dir}")
else:
    print(f"⚠️ Папка public не найдена: {public_dir}")

# Подключаем шаблоны
templates = Jinja2Templates(directory="app/web/templates")

# Подключаем все роутеры (ВАЖНО: web_client_router ДО main_router)
app.include_router(auth_router)
app.include_router(web_client_router)      # <--- ДОЛЖЕН БЫТЬ ПЕРВЫМ
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
    if hasattr(route, "methods"):
        print(f"{route.methods} {route.path}")
    else:
        print(f"Mount: {route.path}")
print("===================================")