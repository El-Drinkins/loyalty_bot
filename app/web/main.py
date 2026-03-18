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
    admin_review_router
)

app = FastAPI()

# Добавляем middleware для сессий
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here-change-this-in-production",
    session_cookie="loyalty_session",
    max_age=3600,
    same_site="lax"
)

# Подключаем шаблоны
templates = Jinja2Templates(directory="app/web/templates")

# Подключаем все роутеры
app.include_router(main_router)                    # Главная страница
app.include_router(points_router)                  # Начисление/списание баллов
app.include_router(stats_router)                    # Статистика
app.include_router(admin_router)                    # Админские логи
app.include_router(user_router)                     # Управление пользователями
app.include_router(api_router)                      # API для поиска
app.include_router(catalog_router, prefix="/catalog")  # Каталог техники
app.include_router(search_router)                   # Поиск клиентов
app.include_router(admin_review_router, prefix="/admin")  # Модерация

print("=== ЗАРЕГИСТРИРОВАННЫЕ МАРШРУТЫ ===")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"{route.methods} {route.path}")
print("===================================")