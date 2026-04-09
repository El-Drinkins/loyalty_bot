from .base_routes import router as base_router
from .category_routes import router as category_router
from .brand_routes import router as brand_router
from .model_routes import router as model_router
from .rental_routes import router as rental_router
from .stats_routes import router as stats_router

from fastapi import APIRouter

router = APIRouter()
router.include_router(base_router)
router.include_router(category_router)
router.include_router(brand_router)
router.include_router(model_router)
router.include_router(rental_router)
router.include_router(stats_router)