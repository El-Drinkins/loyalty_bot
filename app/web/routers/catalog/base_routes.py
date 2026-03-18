from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime
import random
import string

from ...deps import get_db, templates
from ....models import Category, Brand, Model

router = APIRouter(tags=["catalog"])

# Функция для генерации номера аренды (общая для всех)
def generate_rental_number():
    return f"R-{datetime.now().strftime('%Y%m')}-{random.randint(1000, 9999)}"

@router.get("/", response_class=HTMLResponse)
async def catalog_index(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Получаем все категории с брендами и моделями
    categories = await db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.sort_order)
        .options(
            selectinload(Category.brands).selectinload(Brand.models)
        )
    )
    categories = categories.scalars().all()
    
    # Статистика
    total_models = await db.scalar(select(func.count(Model.id)))
    active_models = await db.scalar(select(func.count(Model.id)).where(Model.is_active == True))
    total_brands = await db.scalar(select(func.count(Brand.id)))
    
    return templates.TemplateResponse("catalog/index.html", {
        "request": request,
        "categories": categories,
        "total_models": total_models,
        "active_models": active_models,
        "total_brands": total_brands
    })