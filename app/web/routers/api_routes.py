from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..deps import get_db, require_auth
from ...models import User, Referral, RegistrationRequest, Rental

router = APIRouter()

@router.get("/api/search_users")
async def search_users(
    q: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """API для поиска пользователей (для модального окна)"""
    if len(q) < 2:
        return []
    
    conditions = []
    
    if q.isdigit():
        conditions.append(User.id == int(q))
        conditions.append(User.telegram_id == int(q))
    
    conditions.append(User.full_name.ilike(f"%{q}%"))
    conditions.append(User.phone.ilike(f"%{q}%"))
    
    stmt = select(User).where(or_(*conditions)).limit(10)
    
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    response = []
    for user in users:
        invited_count = await db.scalar(
            select(func.count()).where(Referral.old_user_id == user.id)
        )
        response.append({
            "id": user.id,
            "full_name": user.full_name,
            "phone": user.phone,
            "telegram_id": user.telegram_id,
            "invited_count": invited_count or 0
        })
    
    return response

@router.post("/api/admin/approve/{request_id}")
async def api_approve_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """API для одобрения заявки"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    # Создаем пользователя
    user = User(
        telegram_id=req.telegram_id,
        full_name=req.full_name or "Имя не указано",
        phone=req.phone or "",
        balance=200,
        invited_by_id=req.invited_by_id,
        instagram=req.instagram,
        vkontakte=req.vkontakte,
        verification_level="basic",
        badge="🟢",
        verified_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    
    # Обновляем статус заявки
    req.status = "approved"
    req.user_id = user.id
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "ok", "user_id": user.id}

@router.post("/api/admin/reject/{request_id}")
async def api_reject_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """API для отклонения заявки"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "ok"}

@router.post("/api/admin/ban/{request_id}")
async def api_ban_request(
    request_id: int,
    reason: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """API для блокировки пользователя"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.review_comment = reason
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "ok"}

@router.post("/user/{user_id}/update_notes")
async def update_user_notes(
    user_id: int,
    notes: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Обновляет примечания администратора"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    user.admin_notes = notes
    await db.commit()
    
    return RedirectResponse(url=f"/admin/client/{user_id}", status_code=303)


@router.put("/api/rentals/{rental_id}/status")
async def update_rental_status(
    rental_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Обновляет статус аренды"""
    from fastapi import Request
    data = await request.json()
    new_status = data.get("status")
    
    if new_status not in ["active", "completed", "cancelled"]:
        raise HTTPException(400, "Неверный статус")
    
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Аренда не найдена")
    
    rental.status = new_status
    rental.updated_at = datetime.utcnow()
    await db.commit()
    
    return {"success": True}