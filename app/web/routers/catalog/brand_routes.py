from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...deps import get_db, templates
from ....models import Brand, Category

router = APIRouter(prefix="/brands", tags=["catalog"])

@router.get("/", response_class=HTMLResponse)
async def brands_list(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    brands = await db.execute(
        select(Brand)
        .options(selectinload(Brand.category))
        .order_by(Brand.sort_order)
    )
    brands = brands.scalars().all()
    
    categories = await db.execute(select(Category))
    categories = categories.scalars().all()
    
    return templates.TemplateResponse("catalog/brands.html", {
        "request": request,
        "brands": brands,
        "categories": categories
    })

@router.post("/add")
async def brand_add(
    request: Request,
    name: str = Form(...),
    category_id: int = Form(...),
    sort_order: int = Form(0),
    db: AsyncSession = Depends(get_db)
):
    brand = Brand(
        name=name,
        category_id=category_id,
        sort_order=sort_order
    )
    db.add(brand)
    await db.commit()
    return RedirectResponse(url="/catalog/brands", status_code=303)

@router.post("/{brand_id}/edit")
async def brand_edit(
    request: Request,
    brand_id: int,
    name: str = Form(...),
    category_id: int = Form(...),
    sort_order: int = Form(...),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, "Бренд не найден")
    
    brand.name = name
    brand.category_id = category_id
    brand.sort_order = sort_order
    brand.is_active = is_active
    
    await db.commit()
    return RedirectResponse(url="/catalog/brands", status_code=303)

@router.post("/{brand_id}/delete")
async def brand_delete(
    request: Request,
    brand_id: int,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if brand:
        await db.delete(brand)
        await db.commit()
    return RedirectResponse(url="/catalog/brands", status_code=303)