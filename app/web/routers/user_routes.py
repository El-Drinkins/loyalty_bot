from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from ..deps import get_db, templates
from ...models import User, Referral, Transaction, AdminLog, UserLog  # изменен импорт

router = APIRouter()

@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request, 
    page: int = 1, 
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
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
    admin_id: int = Form(0)
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
    
    return RedirectResponse(url="/users", status_code=303)

@router.post("/client/{user_id}/delete")
async def delete_user(
    user_id: int,
    confirm_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0)
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
        
        return RedirectResponse(url="/users?deleted=1", status_code=303)
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка при удалении: {str(e)}")