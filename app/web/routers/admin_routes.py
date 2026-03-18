from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from itertools import groupby

from ..deps import get_db, templates
from ...models import User, AdminLog, UserLog, Referral, Transaction, ReferralStatus  # изменен импорт
from ...notifications import send_telegram_notification

router = APIRouter()

TIMEZONE_OFFSET_HOURS = 3

@router.get("/admin_logs", response_class=HTMLResponse)
async def admin_logs_page(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    action: str = "",
    user_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    query = select(AdminLog).order_by(AdminLog.created_at.desc())
    
    if action:
        query = query.where(AdminLog.action_type == action)
    
    if user_id and user_id.isdigit():
        query = query.where(AdminLog.user_id == int(user_id))
    
    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    logs_with_names = []
    for log in logs:
        user = await db.get(User, log.user_id) if log.user_id else None
        local_time = log.created_at + timedelta(hours=TIMEZONE_OFFSET_HOURS)
        
        logs_with_names.append({
            "id": log.id,
            "admin_id": log.admin_id,
            "action_type": log.action_type,
            "user_id": log.user_id,
            "user_name": user.full_name if user else f"ID: {log.user_id}",
            "old_value": log.old_value,
            "new_value": log.new_value,
            "reason": log.reason,
            "created_at": local_time
        })
    
    grouped = []
    for date, group in groupby(logs_with_names, key=lambda x: x["created_at"].strftime('%d.%m.%Y')):
        grouped.append((date, list(group)))
    
    total_pages = (total_count + per_page - 1) // per_page
    
    return templates.TemplateResponse("admin_logs.html", {
        "request": request,
        "grouped_logs": grouped,
        "page": page,
        "total_pages": total_pages,
        "action_filter": action,
        "user_filter": user_id
    })

@router.get("/user_logs", response_class=HTMLResponse)
async def user_logs_page(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    action: str = "",
    user_id: str = "",
    db: AsyncSession = Depends(get_db)
):
    query = select(UserLog).order_by(UserLog.created_at.desc())
    
    if action:
        query = query.where(UserLog.action_type == action)
    
    if user_id and user_id.isdigit():
        query = query.where(UserLog.user_id == int(user_id))
        current_user = await db.get(User, int(user_id))
        user_name = current_user.full_name if current_user else f"ID {user_id}"
    else:
        user_name = None
    
    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    result = await db.execute(query.options(selectinload(UserLog.user)))
    logs = result.scalars().all()
    
    logs_with_names = []
    for log in logs:
        local_time = log.created_at + timedelta(hours=TIMEZONE_OFFSET_HOURS)
        
        logs_with_names.append({
            "id": log.id,
            "user_id": log.user_id,
            "user_name": log.user.full_name if log.user else f"ID: {log.user_id}",
            "action_type": log.action_type,
            "action_details": log.action_details,
            "created_at": local_time
        })
    
    grouped = []
    for date, group in groupby(logs_with_names, key=lambda x: x["created_at"].strftime('%d.%m.%Y')):
        grouped.append((date, list(group)))
    
    total_pages = (total_count + per_page - 1) // per_page
    
    return templates.TemplateResponse("user_logs.html", {
        "request": request,
        "grouped_logs": grouped,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "action_filter": action,
        "user_filter": user_id,
        "user_name": user_name
    })

@router.post("/client/{user_id}/add_to_blacklist")
async def add_to_blacklist(
    user_id: int,
    reason: str = Form(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    if user.blacklisted:
        raise HTTPException(400, "Пользователь уже в черном списке")
    
    full_reason = reason
    if comment:
        full_reason += f" ({comment})"
    
    user.blacklisted = True
    user.blacklist_reason = full_reason
    user.blacklisted_at = datetime.utcnow()
    
    transaction = Transaction(
        user_id=user_id,
        amount=0,
        reason=f"⛔ Блокировка: {full_reason}",
        admin_id=admin_id,
        timestamp=datetime.utcnow()
    )
    db.add(transaction)
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="blacklist",
        user_id=user_id,
        old_value="False",
        new_value="True",
        reason=full_reason
    )
    db.add(log)
    
    await db.commit()
    
    try:
        await send_telegram_notification(
            user.telegram_id,
            f"⛔ Ваш аккаунт был заблокирован.\n\n"
            f"Причина: {full_reason}\n\n"
            f"Для получения дополнительной информации свяжитесь с администратором."
        )
    except Exception as e:
        print(f"Failed to send blacklist notification: {e}")
    
    return RedirectResponse(url=f"/client/{user_id}", status_code=303)

@router.post("/client/{user_id}/remove_from_blacklist")
async def remove_from_blacklist(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    if not user.blacklisted:
        raise HTTPException(400, "Пользователь не в черном списке")
    
    old_reason = user.blacklist_reason
    
    user.blacklisted = False
    user.blacklist_reason = None
    user.blacklisted_at = None
    
    transaction = Transaction(
        user_id=user_id,
        amount=0,
        reason="✅ Разблокировка аккаунта",
        admin_id=admin_id,
        timestamp=datetime.utcnow()
    )
    db.add(transaction)
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="unblacklist",
        user_id=user_id,
        old_value="True",
        new_value="False",
        reason=f"Снята блокировка: {old_reason}"
    )
    db.add(log)
    
    await db.commit()
    
    try:
        await send_telegram_notification(
            user.telegram_id,
            f"✅ Ваш аккаунт был разблокирован.\n\n"
            f"Вы снова можете пользоваться программой лояльности."
        )
    except Exception as e:
        print(f"Failed to send unblock notification: {e}")
    
    return RedirectResponse(url=f"/client/{user_id}", status_code=303)

@router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .where(User.blacklisted == True)
        .order_by(User.blacklisted_at.desc())
    )
    blacklisted_users = result.scalars().all()
    
    return templates.TemplateResponse("blacklist.html", {
        "request": request,
        "users": blacklisted_users
    })