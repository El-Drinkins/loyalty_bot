from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
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
from .routers.feedback_routes import router as feedback_router
from .routers.totp_routes import router as totp_router
from .middleware import AuthMiddleware
from ..models import AsyncSessionLocal
from ..logger import web_logger as logger

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here-change-this-in-production",
    session_cookie="loyalty_session",
    max_age=3600 * 24,
    same_site="lax"
)

app.add_middleware(
    AuthMiddleware,
    secret_key="your-secret-key-here-change-this-in-production"
)

public_dir = os.path.join(os.path.dirname(__file__), "public")
if os.path.exists(public_dir):
    app.mount("/public", StaticFiles(directory=public_dir), name="public")
    logger.info(f"Статические файлы веб-версии подключены из {public_dir}")
else:
    logger.warning(f"Папка public не найдена: {public_dir}")

templates = Jinja2Templates(directory="app/web/templates")

# Подключаем все роутеры
app.include_router(auth_router)
app.include_router(web_client_router)
app.include_router(main_router, prefix="/admin")
app.include_router(points_router, prefix="/admin")
app.include_router(stats_router, prefix="/admin")
app.include_router(admin_router)
app.include_router(user_router, prefix="/admin")
app.include_router(api_router, prefix="/admin")
app.include_router(search_router, prefix="/admin")
app.include_router(mailing_router, prefix="/admin")
app.include_router(catalog_router, prefix="/admin/catalog")
app.include_router(admin_review_router, prefix="/admin/review")
app.include_router(feedback_router)
app.include_router(totp_router)

# ========== HEALTH CHECK ==========
@app.get("/health")
async def health_check():
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar()
            return {
                "status": "ok",
                "server": "running",
                "database": "connected"
            }
    except Exception as e:
        logger.error(f"Health check: база данных недоступна — {e}")
        return {
            "status": "error",
            "server": "running",
            "database": "disconnected",
            "error": str(e)
        }

logger.info("Маршруты зарегистрированы:")
for route in app.routes:
    if hasattr(route, "methods"):
        logger.debug(f" {route.methods} {route.path}")