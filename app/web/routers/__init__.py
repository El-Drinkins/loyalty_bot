from .main_routes import router as main_router
from .points_routes import router as points_router
from .stats_routes import router as stats_router
from .admin_routes import router as admin_router
from .user_routes import router as user_router
from .api_routes import router as api_router
from .search_routes import router as search_router
from .catalog import router as catalog_router
from .admin_review_routes import router as admin_review_router

__all__ = [
    "main_router",
    "points_router",
    "stats_router",
    "admin_router",
    "user_router",
    "api_router",
    "search_router",
    "catalog_router",
    "admin_review_router"
]