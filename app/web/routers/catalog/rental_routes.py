from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from ...deps import get_db, templates, require_auth
from ....models import User, Model, Brand, Category, Rental, Referral
from .base_routes import generate_rental_number
from ....bonus_utils import update_referral_total_rentals, check_and_create_pending_bonuses

router = APIRouter(prefix="/rentals", tags=["catalog"])

async def update_referral_for_user(db: AsyncSession, user_id: int):
    """Обновляет сумму аренд и создаёт ожидающие бонусы для реферала"""
    referral = await db.execute(
        select(Referral).where(Referral.new_user_id == user_id)
    )
    referral = referral.scalar_one_or_none()
    if referral:
        print(f"🔄 Updating referral {referral.id} for user {user_id}")
        await update_referral_total_rentals(db, referral.id)
        await check_and_create_pending_bonuses(db, referral.id)
    else:
        print(f"⚠️ No referral found for user {user_id}")

@router.get("/", response_class=HTMLResponse)
async def rentals_list(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    status: str = "",
    user_id: int = None,
    model_id: int = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    query = select(Rental).options(
        selectinload(Rental.user),
        selectinload(Rental.model).selectinload(Model.brand)
    ).order_by(Rental.created_at.desc())
    
    if status:
        query = query.where(Rental.status == status)
    if user_id:
        query = query.where(Rental.user_id == user_id)
    if model_id:
        query = query.where(Rental.model_id == model_id)
    
    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    rentals = await db.execute(query)
    rentals = rentals.scalars().all()
    
    total_pages = (total_count + per_page - 1) // per_page
    
    active_count = await db.scalar(select(func.count()).where(Rental.status == "active"))
    completed_count = await db.scalar(select(func.count()).where(Rental.status == "completed"))
    
    return templates.TemplateResponse("catalog/rentals.html", {
        "request": request,
        "rentals": rentals,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "status_filter": status,
        "user_filter": user_id,
        "model_filter": model_id,
        "active_count": active_count,
        "completed_count": completed_count
    })

@router.get("/add", response_class=HTMLResponse)
async def rental_add_form(
    request: Request,
    admin_id: int = 1,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    models = await db.execute(
        select(Model)
        .where(Model.is_active == True)
        .options(selectinload(Model.brand))
    )
    models = models.scalars().all()
    
    users = await db.execute(select(User).order_by(User.full_name))
    users = users.scalars().all()
    
    rental_number = generate_rental_number()
    
    return templates.TemplateResponse("catalog/rental_form.html", {
        "request": request,
        "models": models,
        "users": users,
        "rental_number": rental_number,
        "rental": None,
        "admin_id": admin_id
    })

@router.post("/add")
async def rental_add(
    request: Request,
    rental_number: str = Form(...),
    user_id: int = Form(...),
    model_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    price_per_day: int = Form(...),
    total_price: int = Form(...),
    deposit: int = Form(0),
    notes: str = Form(""),
    status: str = Form("active"),
    admin_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    admin = await db.get(User, admin_id)
    
    rental = Rental(
        rental_number=rental_number,
        user_id=user_id,
        model_id=model_id,
        price_per_day=price_per_day,
        total_price=total_price,
        deposit=deposit if deposit else None,
        start_date=datetime.strptime(start_date, "%Y-%m-%d"),
        end_date=datetime.strptime(end_date, "%Y-%m-%d"),
        status=status,
        notes=notes,
        created_by=admin_id if admin else None
    )
    
    db.add(rental)
    
    user = await db.get(User, user_id)
    if user:
        user.points_expiry_date = datetime.utcnow() + timedelta(days=90)
    
    await db.commit()
    
    if status == "completed":
        await update_referral_for_user(db, user_id)
    
    return RedirectResponse(url="/admin/catalog/rentals", status_code=303)

@router.get("/{rental_id}/edit", response_class=HTMLResponse)
async def rental_edit_form(
    request: Request,
    rental_id: int,
    admin_id: int = 1,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    models = await db.execute(
        select(Model)
        .where(Model.is_active == True)
        .options(selectinload(Model.brand))
    )
    models = models.scalars().all()
    
    users = await db.execute(select(User).order_by(User.full_name))
    users = users.scalars().all()
    
    return templates.TemplateResponse("catalog/rental_form.html", {
        "request": request,
        "models": models,
        "users": users,
        "rental": rental,
        "admin_id": admin_id
    })

@router.post("/{rental_id}/edit")
async def rental_edit(
    request: Request,
    rental_id: int,
    user_id: int = Form(...),
    model_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    price_per_day: int = Form(...),
    total_price: int = Form(...),
    deposit: int = Form(0),
    notes: str = Form(""),
    status: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    old_status = rental.status
    new_status = status
    
    rental.user_id = user_id
    rental.model_id = model_id
    rental.start_date = datetime.strptime(start_date, "%Y-%m-%d")
    rental.end_date = datetime.strptime(end_date, "%Y-%m-%d")
    rental.price_per_day = price_per_day
    rental.total_price = total_price
    rental.deposit = deposit if deposit else None
    rental.notes = notes
    rental.status = new_status
    rental.updated_at = datetime.utcnow()
    
    user = await db.get(User, user_id)
    if user:
        user.points_expiry_date = datetime.utcnow() + timedelta(days=90)
    
    await db.commit()
    
    if old_status != "completed" and new_status == "completed":
        await update_referral_for_user(db, user_id)
    
    return RedirectResponse(url="/admin/catalog/rentals", status_code=303)

@router.post("/{rental_id}/delete")
async def rental_delete(
    request: Request,
    rental_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    rental = await db.get(Rental, rental_id)
    if rental:
        user_id = rental.user_id
        await db.delete(rental)
        await db.commit()
        await update_referral_for_user(db, user_id)
    return RedirectResponse(url="/admin/catalog/rentals", status_code=303)

@router.get("/{rental_id}", response_class=HTMLResponse)
async def rental_detail(
    request: Request,
    rental_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    rental = await db.get(
        Rental, 
        rental_id,
        options=[
            selectinload(Rental.user),
            selectinload(Rental.model)
            .selectinload(Model.brand)
            .selectinload(Brand.category)
        ]
    )
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    return templates.TemplateResponse("catalog/rental_detail.html", {
        "request": request,
        "rental": rental
    })


@router.put("/{rental_id}/status")
async def update_rental_status(
    request: Request,
    rental_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    data = await request.json()
    new_status = data.get("status")
    
    if new_status not in ["active", "completed", "cancelled"]:
        raise HTTPException(400, "Неверный статус")
    
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    old_status = rental.status
    rental.status = new_status
    rental.updated_at = datetime.utcnow()
    await db.commit()
    
    if old_status != "completed" and new_status == "completed":
        await update_referral_for_user(db, rental.user_id)
    
    return {"success": True}


@router.post("/{rental_id}/confirm_status")
async def confirm_rental_status(
    request: Request,
    rental_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Подтверждает статус аренды и обновляет бонусы"""
    data = await request.json()
    new_status = data.get("status")
    
    if new_status not in ["active", "completed", "cancelled"]:
        raise HTTPException(400, "Неверный статус")
    
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    old_status = rental.status
    
    # Меняем статус
    rental.status = new_status
    rental.updated_at = datetime.utcnow()
    await db.commit()
    
    # Если статус изменился на "completed", обновляем реферала
    if old_status != "completed" and new_status == "completed":
        await update_referral_for_user(db, rental.user_id)
        print(f"✅ Аренда {rental_id} завершена, бонусы обновлены")
    
    return {"success": True, "old_status": old_status, "new_status": new_status}