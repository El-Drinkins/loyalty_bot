from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime
import os
import shutil
from ...deps import get_db, templates, require_auth
from ....models import Model, Brand, Category, Rental

router = APIRouter(prefix="/models", tags=["catalog"])

@router.get("/", response_class=HTMLResponse)
async def models_list(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    category_id: int = None,
    brand_id: int = None,
    search: str = "",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    query = select(Model).options(
        selectinload(Model.brand).selectinload(Brand.category)
    )
    if category_id:
        query = query.join(Brand).where(Brand.category_id == category_id)
    if brand_id:
        query = query.where(Model.brand_id == brand_id)
    if search:
        query = query.where(Model.name.ilike(f"%{search}%"))
    query = query.order_by(Model.id.desc())

    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    models = await db.execute(query)
    models = models.scalars().all()

    categories = await db.execute(select(Category))
    categories = categories.scalars().all()
    brands = await db.execute(select(Brand))
    brands = brands.scalars().all()

    total_pages = (total_count + per_page - 1) // per_page

    return templates.TemplateResponse("catalog/models.html", {
        "request": request,
        "models": models,
        "categories": categories,
        "brands": brands,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "category_filter": category_id,
        "brand_filter": brand_id,
        "search_query": search
    })

@router.get("/add", response_class=HTMLResponse)
async def model_add_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    result = await db.execute(
        select(Brand)
        .where(Brand.is_active == True)
        .options(selectinload(Brand.category))
        .order_by(Brand.name)
    )
    brands = result.scalars().all()
    return templates.TemplateResponse("catalog/model_form.html", {
        "request": request,
        "brands": brands,
        "model": None
    })

@router.post("/add")
async def model_add(
    request: Request,
    name: str = Form(...),
    brand_id: int = Form(...),
    price_per_day: int = Form(...),
    deposit: int = Form(0),
    specs: str = Form(""),
    image_url: str = Form(""),
    review_url: str = Form(""),
    default_equipment: str = Form(""),
    mount_type: str = Form(""),
    is_active: bool = Form(True),
    photo: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    photo_url = image_url

    if photo and photo.filename:
        upload_dir = "app/web/public/photos"
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{photo.filename}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_url = f"http://85.137.251.207:8000/public/photos/{filename}"

    model = Model(
        name=name,
        brand_id=brand_id,
        price_per_day=price_per_day,
        deposit=deposit if deposit else None,
        specs=specs,
        image_url=photo_url,
        review_url=review_url,
        default_equipment=default_equipment,
        mount_type=mount_type if mount_type else None,
        is_active=is_active
    )
    db.add(model)
    await db.commit()
    return RedirectResponse(url="/admin/catalog/models", status_code=303)

@router.get("/{model_id}/edit", response_class=HTMLResponse)
async def model_edit_form(
    request: Request,
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(404, "Модель не найдена")
    result = await db.execute(
        select(Brand)
        .where(Brand.is_active == True)
        .options(selectinload(Brand.category))
        .order_by(Brand.name)
    )
    brands = result.scalars().all()
    return templates.TemplateResponse("catalog/model_form.html", {
        "request": request,
        "brands": brands,
        "model": model
    })

@router.post("/{model_id}/edit")
async def model_edit(
    request: Request,
    model_id: int,
    name: str = Form(...),
    brand_id: int = Form(...),
    price_per_day: int = Form(...),
    deposit: int = Form(0),
    specs: str = Form(""),
    image_url: str = Form(""),
    review_url: str = Form(""),
    default_equipment: str = Form(""),
    mount_type: str = Form(""),
    is_active: bool = Form(False),
    photo: UploadFile = File(None),
    page: int = Form(1),
    search: str = Form(""),
    filter_brand_id: int = Form(0),
    filter_category_id: int = Form(0),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(404, "Модель не найдена")

    if photo and photo.filename:
        upload_dir = "app/web/public/photos"
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{photo.filename}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        model.image_url = f"http://85.137.251.207:8000/public/photos/{filename}"
    else:
        model.image_url = image_url

    model.name = name
    model.brand_id = brand_id
    model.price_per_day = price_per_day
    model.deposit = deposit if deposit else None
    model.specs = specs
    model.review_url = review_url
    model.default_equipment = default_equipment
    model.mount_type = mount_type if mount_type else None
    model.is_active = is_active
    model.updated_at = datetime.utcnow()
    await db.commit()

    params = f"?page={page}"
    if search:
        params += f"&search={search}"
    if filter_brand_id:
        params += f"&brand_id={filter_brand_id}"
    if filter_category_id:
        params += f"&category_id={filter_category_id}"

    return RedirectResponse(url=f"/admin/catalog/models{params}", status_code=303)

@router.post("/{model_id}/delete")
async def model_delete(
    request: Request,
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    model = await db.get(Model, model_id)
    if model:
        await db.delete(model)
        await db.commit()
    return RedirectResponse(url="/admin/catalog/models", status_code=303)

@router.get("/{model_id}/stats", response_class=HTMLResponse)
async def model_stats(
    request: Request,
    model_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(404, "Модель не найдена")
    total_rentals = await db.scalar(
        select(func.count()).where(Rental.model_id == model_id)
    )
    active_rentals = await db.scalar(
        select(func.count()).where(Rental.model_id == model_id, Rental.status == "active")
    )
    total_revenue = await db.scalar(
        select(func.sum(Rental.total_price)).where(Rental.model_id == model_id)
    ) or 0
    avg_duration = await db.scalar(
        select(func.avg(Rental.end_date - Rental.start_date)).where(Rental.model_id == model_id)
    )
    recent_rentals = await db.execute(
        select(Rental)
        .where(Rental.model_id == model_id)
        .order_by(Rental.created_at.desc())
        .limit(10)
        .options(selectinload(Rental.user))
    )
    recent_rentals = recent_rentals.scalars().all()
    return templates.TemplateResponse("catalog/model_stats.html", {
        "request": request,
        "model": model,
        "total_rentals": total_rentals,
        "active_rentals": active_rentals,
        "total_revenue": total_revenue,
        "avg_duration": avg_duration,
        "recent_rentals": recent_rentals
    })