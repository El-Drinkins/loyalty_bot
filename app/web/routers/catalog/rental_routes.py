from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
import os
import shutil
from ...deps import get_db, templates, require_auth
from ....models import User, Model, Brand, Category, Rental, Referral, Transaction, AdminLog
from .base_routes import generate_rental_number
from ....bonus_utils import update_referral_total_rentals, check_and_create_pending_bonuses
from ....cashback import get_cashback_info, calculate_cashback_rate
from ....notifications import send_telegram_notification
from ....config import settings

router = APIRouter(prefix="/rentals", tags=["catalog"])

async def update_referral_for_user(db: AsyncSession, user_id: int):
    """Обновляет сумму аренд и создаёт ожидающие бонусы для реферала"""
    referral = await db.execute(
        select(Referral).where(Referral.new_user_id == user_id)
    )
    referral = referral.scalar_one_or_none()
    if referral:
        # Не начисляем бонусы, если пригласивший — админ
        old_user = await db.get(User, referral.old_user_id)
        if old_user and old_user.telegram_id in settings.ADMIN_IDS:
            print(f"⚠️ Пропуск бонусов для админа {referral.old_user_id}")
            return
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
    user_id: int = 0,
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
    if user_id and user_id > 0:
        query = query.where(Rental.user_id == user_id)
    if model_id:
        query = query.where(Rental.model_id == model_id)

    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    rentals = await db.execute(query)
    rentals = rentals.scalars().all()

    # Проверяем начисление кэшбэка для каждой завершённой аренды
    rentals_with_cashback = []
    for rental in rentals:
        cashback_paid = False
        if rental.status == "completed" and rental.model:
            model_name = rental.model.name
            tx_result = await db.execute(
                select(Transaction).where(
                    Transaction.user_id == rental.user_id,
                    Transaction.reason.ilike(f"%Кэшбэк за аренду {model_name}%")
                ).limit(1)
            )
            cashback_paid = tx_result.scalar_one_or_none() is not None
        rentals_with_cashback.append({
            "rental": rental,
            "cashback_paid": cashback_paid
        })

    total_pages = (total_count + per_page - 1) // per_page

    active_count = await db.scalar(select(func.count()).where(Rental.status == "active"))
    completed_count = await db.scalar(select(func.count()).where(Rental.status == "completed"))

    return templates.TemplateResponse("catalog/rentals.html", {
        "request": request,
        "rentals": rentals_with_cashback,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "status_filter": status,
        "user_filter": user_id if user_id else "",
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
    is_monthly: bool = Form(False),
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
        is_monthly=is_monthly,
        created_by=admin_id if admin else None
    )
    db.add(rental)

    user = await db.get(User, user_id)
    if user and total_price >= 1000:
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
    is_monthly: bool = Form(False),
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
    rental.is_monthly = is_monthly
    rental.updated_at = datetime.utcnow()

    user = await db.get(User, user_id)
    if user and total_price >= 1000:
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

    cashback_info = await get_cashback_info(db, rental.user)

    # Проверяем, начислен ли уже кэшбэк
    cashback_paid = False
    if rental.status == "completed" and rental.model:
        model_name = rental.model.name
        tx_result = await db.execute(
            select(Transaction).where(
                Transaction.user_id == rental.user_id,
                Transaction.reason.ilike(f"%Кэшбэк за аренду {model_name}%")
            ).limit(1)
        )
        cashback_paid = tx_result.scalar_one_or_none() is not None

    return templates.TemplateResponse("catalog/rental_detail.html", {
        "request": request,
        "rental": rental,
        "cashback_info": cashback_info,
        "cashback_paid": cashback_paid
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
    rental.status = new_status
    rental.updated_at = datetime.utcnow()

    await db.commit()

    if old_status != "completed" and new_status == "completed":
        await update_referral_for_user(db, rental.user_id)
        print(f"✅ Аренда {rental_id} завершена, бонусы обновлены")

    return {"success": True, "old_status": old_status, "new_status": new_status}

@router.post("/{rental_id}/add_cashback")
async def add_cashback_from_rental(
    request: Request,
    rental_id: int,
    custom_amount: int = Form(0),
    admin_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Начисляет кэшбэк за завершённую аренду."""
    rental = await db.get(
        Rental, 
        rental_id,
        options=[
            selectinload(Rental.user),
            selectinload(Rental.model).selectinload(Model.brand)
        ]
    )
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    if rental.status != "completed":
        raise HTTPException(400, "Кэшбэк начисляется только за завершённые аренды")

    user = rental.user
    rate = await calculate_cashback_rate(db, user)

    if custom_amount > 0:
        cashback_amount = custom_amount
    else:
        cashback_amount = int(rental.total_price * rate / 100)

    if cashback_amount <= 0:
        raise HTTPException(400, "Сумма кэшбэка равна нулю")

    model_name = rental.model.name

    if user.balance + cashback_amount > settings.MAX_BALANCE:
        return templates.TemplateResponse("client/confirm_overlimit.html", {
            "request": request,
            "user": user,
            "action": "cashback",
            "action_url": f"/admin/catalog/rentals/{rental_id}/add_cashback_force",
            "amount": cashback_amount,
            "reason": f"Кэшбэк за аренду {model_name}",
            "current_balance": user.balance,
            "new_balance": user.balance + cashback_amount,
            "max_balance": settings.MAX_BALANCE,
            "message": f"После начисления кэшбэка (+{cashback_amount} ⭐) баланс составит {user.balance + cashback_amount} ⭐, что превышает лимит {settings.MAX_BALANCE} ⭐.",
            "custom_amount": cashback_amount
        })

    old_balance = user.balance
    user.balance += cashback_amount
    user.points_expiry_date = datetime.utcnow() + timedelta(days=settings.POINTS_VALID_DAYS)

    transaction = Transaction(
        user_id=user.id,
        amount=cashback_amount,
        reason=f"Кэшбэк за аренду {model_name}",
        admin_id=admin_id
    )
    db.add(transaction)

    log = AdminLog(
        admin_id=admin_id,
        action_type="add_points",
        user_id=user.id,
        old_value=str(old_balance),
        new_value=str(user.balance),
        reason=f"Кэшбэк {rate}% за аренду {model_name}"
    )
    db.add(log)

    await db.commit()

    try:
        await send_telegram_notification(
            user.telegram_id,
            f"💰 Вам начислен кэшбэк {cashback_amount} баллов за аренду {model_name}.\n"
            f"💳 Ваш баланс: {user.balance} ⭐"
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление: {e}")

    return RedirectResponse(url=f"/admin/catalog/rentals/{rental_id}", status_code=303)

@router.post("/{rental_id}/add_cashback_force")
async def add_cashback_force(
    request: Request,
    rental_id: int,
    custom_amount: int = Form(0),
    admin_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Принудительное начисление кэшбэка с превышением лимита."""
    rental = await db.get(
        Rental, 
        rental_id,
        options=[
            selectinload(Rental.user),
            selectinload(Rental.model).selectinload(Model.brand)
        ]
    )
    if not rental:
        raise HTTPException(404, "Аренда не найдена")

    user = rental.user
    rate = await calculate_cashback_rate(db, user)

    if custom_amount > 0:
        cashback_amount = custom_amount
    else:
        cashback_amount = int(rental.total_price * rate / 100)

    model_name = rental.model.name

    old_balance = user.balance
    user.balance += cashback_amount
    user.points_expiry_date = datetime.utcnow() + timedelta(days=settings.POINTS_VALID_DAYS)

    transaction = Transaction(
        user_id=user.id,
        amount=cashback_amount,
        reason=f"Кэшбэк за аренду {model_name} (превышен лимит)",
        admin_id=admin_id
    )
    db.add(transaction)

    log = AdminLog(
        admin_id=admin_id,
        action_type="add_points_force",
        user_id=user.id,
        old_value=str(old_balance),
        new_value=str(user.balance),
        reason=f"Кэшбэк {rate}% за аренду {model_name} (превышен лимит)"
    )
    db.add(log)

    await db.commit()

    try:
        await send_telegram_notification(
            user.telegram_id,
            f"💰 Вам начислен кэшбэк {cashback_amount} баллов за аренду {model_name}.\n"
            f"💳 Ваш баланс: {user.balance} ⭐"
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление: {e}")

    return RedirectResponse(url=f"/admin/catalog/rentals/{rental_id}", status_code=303)