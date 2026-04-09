from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...deps import get_db, templates, require_auth
from ....models import Category

router = APIRouter(prefix="/categories", tags=["catalog"])

@router.get("/", response_class=HTMLResponse)
async def categories_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    categories = await db.execute(
        select(Category).order_by(Category.sort_order)
    )
    categories = categories.scalars().all()
    return templates.TemplateResponse("catalog/categories.html", {
        "request": request,
        "categories": categories
    })

@router.post("/add")
async def category_add(
    request: Request,
    name: str = Form(...),
    icon: str = Form("📦"),
    sort_order: int = Form(0),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    category = Category(
        name=name,
        icon=icon,
        sort_order=sort_order
    )
    db.add(category)
    await db.commit()
    return RedirectResponse(url="/admin/catalog/categories", status_code=303)

@router.post("/{category_id}/edit")
async def category_edit(
    request: Request,
    category_id: int,
    name: str = Form(...),
    icon: str = Form(...),
    sort_order: int = Form(...),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(404, "Категория не найдена")
    
    category.name = name
    category.icon = icon
    category.sort_order = sort_order
    category.is_active = is_active
    
    await db.commit()
    return RedirectResponse(url="/admin/catalog/categories", status_code=303)

@router.post("/{category_id}/delete")
async def category_delete(
    request: Request,
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    category = await db.get(Category, category_id)
    if category:
        await db.delete(category)
        await db.commit()
    return RedirectResponse(url="/admin/catalog/categories", status_code=303)