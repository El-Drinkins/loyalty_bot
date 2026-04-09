from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from collections import defaultdict
import secrets
import string
import hashlib

from ..deps import get_db, templates, require_auth
from ...models import User, Referral, Transaction, AdminLog, UserLog, Rental, Model, Brand

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request, 
    page: int = 1, 
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_users = await db.scalar(select(func.count(User.id)))
    
    offset = (page - 1) * per_page
    
    stmt = (
        select(User)
        .options(selectinload(User.invited_by))
        .order_by(User.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    total_pages = (total_users + per_page - 1) // per_page
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "total_users": total_users,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    })


@router.post("/user/{user_id}/update_real_name")
async def update_real_name(
    user_id: int,
    real_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    old_value = user.full_name_real
    user.full_name_real = real_name.strip() if real_name.strip() else None
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="update_real_name",
        user_id=user_id,
        old_value=old_value or "",
        new_value=user.full_name_real or "",
        reason="Обновление ФИО вручную"
    )
    db.add(log)
    
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/client/{user_id}/delete")
async def delete_user(
    user_id: int,
    confirm_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    if confirm_name.strip() != user.full_name:
        raise HTTPException(400, "Имя для подтверждения не совпадает")
    
    try:
        log = AdminLog(
            admin_id=admin_id,
            action_type="delete_user",
            user_id=user_id,
            old_value="",
            new_value="",
            reason=f"Удален пользователь {user.full_name}"
        )
        db.add(log)
        
        await db.execute(Transaction.__table__.delete().where(Transaction.user_id == user_id))
        await db.execute(Referral.__table__.delete().where(Referral.old_user_id == user_id))
        await db.execute(Referral.__table__.delete().where(Referral.new_user_id == user_id))
        await db.execute(AdminLog.__table__.delete().where(AdminLog.user_id == user_id))
        await db.execute(UserLog.__table__.delete().where(UserLog.user_id == user_id))
        await db.execute(User.__table__.delete().where(User.id == user_id))
        
        await db.commit()
        
        return RedirectResponse(url="/admin/users?deleted=1", status_code=303)
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка при удалении: {str(e)}")


@router.post("/client/{user_id}/reset_password")
async def reset_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    """Сброс пароля пользователя администратором"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))
    
    user.password_hash = hashlib.sha256(temp_password.encode()).hexdigest()
    user.password_set_at = datetime.utcnow()
    await db.commit()
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="reset_password",
        user_id=user_id,
        old_value="",
        new_value="",
        reason=f"Сброс пароля администратором"
    )
    db.add(log)
    await db.commit()
    
    return JSONResponse({
        "success": True,
        "temp_password": temp_password
    })


@router.get("/client/{user_id}/finance", response_class=HTMLResponse)
async def client_finance_page(
    request: Request,
    user_id: int,
    year_filter: int = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    rentals_query = (
        select(Rental)
        .where(Rental.user_id == user_id)
        .options(
            selectinload(Rental.model).selectinload(Model.brand)
        )
    )
    result = await db.execute(rentals_query)
    rentals = result.scalars().all()
    
    total_spent = sum(r.total_price for r in rentals)
    total_rentals = len(rentals)
    avg_check = total_spent // total_rentals if total_rentals > 0 else 0
    
    current_year = datetime.utcnow().year
    start_of_year = date(current_year, 1, 1)
    spent_current_year = sum(r.total_price for r in rentals if r.start_date.date() >= start_of_year)
    
    years_data = defaultdict(lambda: {"total": 0, "count": 0})
    for rental in rentals:
        year = rental.start_date.year
        years_data[year]["total"] += rental.total_price
        years_data[year]["count"] += 1
    
    years_list = []
    for year in sorted(years_data.keys(), reverse=True):
        years_list.append({
            "year": year,
            "total": years_data[year]["total"],
            "count": years_data[year]["count"],
            "avg": years_data[year]["total"] // years_data[year]["count"] if years_data[year]["count"] > 0 else 0
        })
    
    models_data = defaultdict(lambda: {"total": 0, "count": 0, "model": None, "brand_name": ""})
    for rental in rentals:
        model_id = rental.model_id
        if year_filter and rental.start_date.year != year_filter:
            continue
        models_data[model_id]["total"] += rental.total_price
        models_data[model_id]["count"] += 1
        if not models_data[model_id]["model"]:
            models_data[model_id]["model"] = rental.model
            if rental.model and rental.model.brand:
                models_data[model_id]["brand_name"] = rental.model.brand.name
    
    models_list = []
    for model_id, data in models_data.items():
        model = data["model"]
        if model:
            model_name = f"{data['brand_name']} {model.name}" if data['brand_name'] else model.name
        else:
            model_name = f"Модель #{model_id} (удалена)"
        models_list.append({
            "id": model_id,
            "name": model_name,
            "total": data["total"],
            "count": data["count"],
            "avg": data["total"] // data["count"] if data["count"] > 0 else 0
        })
    
    models_list.sort(key=lambda x: x["total"], reverse=True)
    
    available_years = sorted(set(r.start_date.year for r in rentals), reverse=True)
    
    return templates.TemplateResponse("client/finance.html", {
        "request": request,
        "user": user,
        "total_spent": total_spent,
        "total_rentals": total_rentals,
        "avg_check": avg_check,
        "spent_current_year": spent_current_year,
        "years_list": years_list,
        "models_list": models_list,
        "current_year": current_year,
        "year_filter": year_filter,
        "available_years": available_years
    })


@router.get("/client/{user_id}/finance/export")
async def export_finance_csv(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    from fastapi.responses import Response
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    rentals = await db.execute(
        select(Rental, Model, Brand)
        .join(Model, Rental.model_id == Model.id)
        .join(Brand, Model.brand_id == Brand.id)
        .where(Rental.user_id == user_id)
        .order_by(Rental.start_date.desc())
    )
    rentals = rentals.all()
    
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow(['Номер аренды', 'Модель', 'Бренд', 'Дата начала', 'Дата окончания', 'Сумма', 'Статус'])
    
    for rental, model, brand in rentals:
        writer.writerow([
            rental.rental_number,
            model.name,
            brand.name,
            rental.start_date.strftime('%d.%m.%Y'),
            rental.end_date.strftime('%d.%m.%Y'),
            rental.total_price,
            rental.status
        ])
    
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=finance_{user.full_name}_{user.id}.csv"}
    )