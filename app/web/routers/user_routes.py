from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from collections import defaultdict
import csv
import io

from ..deps import get_db, templates, require_auth
from ...models import User, Referral, Transaction, AdminLog, UserLog, Rental, Model, Brand, Category

router = APIRouter()

# ... существующие функции ...

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
    
    # Получаем все аренды пользователя
    rentals_query = select(Rental).where(Rental.user_id == user_id)
    result = await db.execute(rentals_query)
    rentals = result.scalars().all()
    
    # 1. Общая статистика
    total_spent = sum(r.total_price for r in rentals)
    total_rentals = len(rentals)
    avg_check = total_spent // total_rentals if total_rentals > 0 else 0
    
    # 2. Потрачено с начала текущего года
    current_year = datetime.utcnow().year
    start_of_year = date(current_year, 1, 1)
    spent_current_year = sum(r.total_price for r in rentals if r.start_date >= start_of_year)
    
    # 3. Динамика по годам
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
    
    # 4. Статистика по моделям техники
    models_data = defaultdict(lambda: {"total": 0, "count": 0, "model": None})
    for rental in rentals:
        model_id = rental.model_id
        if year_filter and rental.start_date.year != year_filter:
            continue
        models_data[model_id]["total"] += rental.total_price
        models_data[model_id]["count"] += 1
        if not models_data[model_id]["model"]:
            models_data[model_id]["model"] = rental.model
    
    models_list = []
    for model_id, data in models_data.items():
        model = data["model"]
        models_list.append({
            "id": model.id,
            "name": f"{model.brand.name} {model.name}",
            "total": data["total"],
            "count": data["count"],
            "avg": data["total"] // data["count"] if data["count"] > 0 else 0
        })
    
    # Сортируем по убыванию потраченной суммы
    models_list.sort(key=lambda x: x["total"], reverse=True)
    
    # Годы для фильтра
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
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    # Получаем все аренды пользователя
    rentals = await db.execute(
        select(Rental, Model, Brand)
        .join(Model, Rental.model_id == Model.id)
        .join(Brand, Model.brand_id == Brand.id)
        .where(Rental.user_id == user_id)
        .order_by(Rental.start_date.desc())
    )
    rentals = rentals.all()
    
    # Создаём CSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Заголовки
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
    
    # Отправляем файл
    from fastapi.responses import Response
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=finance_{user.full_name}_{user.id}.csv"}
    )