from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...deps import get_db, templates
from ....models import Model, Brand, Category, Rental

router = APIRouter(prefix="/stats", tags=["catalog"])

@router.get("/", response_class=HTMLResponse)
async def catalog_stats(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Общая статистика
    total_models = await db.scalar(select(func.count(Model.id)))
    active_models = await db.scalar(select(func.count(Model.id)).where(Model.is_active == True))
    
    total_rentals = await db.scalar(select(func.count(Rental.id)))
    active_rentals = await db.scalar(select(func.count(Rental.id)).where(Rental.status == "active"))
    completed_rentals = await db.scalar(select(func.count(Rental.id)).where(Rental.status == "completed"))
    
    total_revenue = await db.scalar(select(func.sum(Rental.total_price))) or 0
    
    # Топ моделей с загрузкой бренда и его категории
    top_models = await db.execute(
        select(Model, func.count(Rental.id).label('rental_count'))
        .join(Rental, Rental.model_id == Model.id)
        .group_by(Model.id)
        .order_by(func.count(Rental.id).desc())
        .limit(10)
        .options(
            selectinload(Model.brand).selectinload(Brand.category)
        )
    )
    top_models = top_models.all()
    
    # Статистика по категориям
    category_stats = await db.execute(
        select(
            Category.name,
            func.count(Model.id).label('model_count'),
            func.count(Rental.id).label('rental_count')
        )
        .join(Brand, Brand.category_id == Category.id)
        .join(Model, Model.brand_id == Brand.id)
        .outerjoin(Rental, Rental.model_id == Model.id)
        .group_by(Category.id)
    )
    category_stats = category_stats.all()
    
    return templates.TemplateResponse("catalog/stats.html", {
        "request": request,
        "total_models": total_models,
        "active_models": active_models,
        "total_rentals": total_rentals,
        "active_rentals": active_rentals,
        "completed_rentals": completed_rentals,
        "total_revenue": total_revenue,
        "top_models": top_models,
        "category_stats": category_stats
    })