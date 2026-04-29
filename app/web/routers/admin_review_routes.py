from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from itertools import groupby
import httpx

from ..deps import get_db, templates, require_auth
from ...models import User, RegistrationRequest, SecuritySettings, Whitelist, StormLog, Transaction, Referral, ReferralStatus, ReferralBonus
from ...config import settings
from ...notifications import send_telegram_notification

router = APIRouter()

TIMEZONE_OFFSET_HOURS = 3

@router.get("/", response_class=HTMLResponse)
async def review_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    pending_count = await db.scalar(
        select(func.count()).where(RegistrationRequest.status == "pending")
    ) or 0
    
    rejected_count = await db.scalar(
        select(func.count()).where(RegistrationRequest.status == "rejected")
    ) or 0
    
    requests = await db.execute(
        select(RegistrationRequest)
        .where(RegistrationRequest.status == "pending")
        .order_by(RegistrationRequest.created_at.desc())
        .limit(20)
        .options(
            selectinload(RegistrationRequest.inviter),
            selectinload(RegistrationRequest.reviewer)
        )
    )
    requests = requests.scalars().all()
    
    return templates.TemplateResponse("admin/review_dashboard.html", {
        "request": request,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "requests": requests
    })


@router.get("/rejected", response_class=HTMLResponse)
async def review_rejected(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    query = select(RegistrationRequest).where(RegistrationRequest.status == "rejected")
    total_count = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    
    offset = (page - 1) * per_page
    query = query.order_by(RegistrationRequest.created_at.desc()).offset(offset).limit(per_page)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return templates.TemplateResponse("admin/review_rejected.html", {
        "request": request,
        "requests": requests,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })


@router.post("/api/approve/{request_id}")
async def api_approve_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    if req.status != "pending":
        raise HTTPException(400, "Заявка уже обработана")
    
    user = User(
        telegram_id=req.telegram_id,
        full_name=req.full_name or "Имя не указано",
        phone=req.phone or "",
        balance=settings.WELCOME_BONUS,
        invited_by_id=req.invited_by_id,
        instagram=req.instagram,
        vkontakte=req.vkontakte,
        verification_level="basic",
        badge="🟢",
        verified_at=datetime.utcnow(),
        points_expiry_date=datetime.utcnow() + timedelta(days=90)
    )
    db.add(user)
    await db.flush()
    
    if req.invited_by_id:
        existing = await db.execute(
            select(Referral).where(
                Referral.new_user_id == user.id,
                Referral.old_user_id == req.invited_by_id
            )
        )
        if not existing.scalar_one_or_none():
            referral = Referral(
                new_user_id=user.id,
                old_user_id=req.invited_by_id,
                status=ReferralStatus.pending,
                registration_date=datetime.utcnow()
            )
            db.add(referral)
    
    req.status = "approved"
    req.user_id = user.id
    req.reviewed_at = datetime.utcnow()
    
    transaction = Transaction(
        user_id=user.id,
        amount=settings.WELCOME_BONUS,
        reason="Бонус за регистрацию"
    )
    db.add(transaction)
    
    await db.commit()
    
    try:
        await send_telegram_notification(
            req.telegram_id,
            f"✅ Регистрация подтверждена!\n\n"
            f"Ваша заявка одобрена. Добро пожаловать в программу лояльности!\n\n"
            f"🎁 Вам начислено {settings.WELCOME_BONUS} приветственных баллов.\n\n"
            f"Отправьте /start для начала работы."
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
    
    return RedirectResponse(url="/admin/review", status_code=303)


@router.post("/api/reject/{request_id}")
async def api_reject_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    try:
        await send_telegram_notification(
            req.telegram_id,
            "❌ Регистрация отклонена\n\n"
            "К сожалению, ваша заявка была отклонена.\n\n"
            "Если вы считаете, что произошла ошибка, свяжитесь с поддержкой: @admin_support"
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
    
    return RedirectResponse(url="/admin/review", status_code=303)


@router.post("/api/ban/{request_id}")
async def api_ban_request(
    request_id: int,
    reason: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.review_comment = reason
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    try:
        await send_telegram_notification(
            req.telegram_id,
            f"❌ Регистрация отклонена\n\n"
            f"К сожалению, ваша заявка была отклонена.\n\n"
            f"Причина: {reason}\n\n"
            f"Если вы считаете, что произошла ошибка, свяжитесь с поддержкой: @admin_support"
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
    
    return RedirectResponse(url="/admin/review", status_code=303)


@router.post("/restore/{request_id}")
async def restore_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    if req.status != 'rejected':
        raise HTTPException(400, "Восстановить можно только отклонённые заявки")
    
    req.status = 'pending'
    req.review_comment = None
    req.reviewed_by = None
    req.reviewed_at = None
    await db.commit()
    
    return RedirectResponse(url="/admin/review/rejected", status_code=303)


@router.post("/api/delete_request/{request_id}")
async def delete_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    await db.delete(req)
    await db.commit()
    
    return RedirectResponse(url="/admin/review/rejected", status_code=303)


@router.post("/api/delete_all_rejected")
async def delete_all_rejected(
    request: Request,
    confirm_count: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    rejected_count = await db.scalar(
        select(func.count()).where(RegistrationRequest.status == "rejected")
    ) or 0
    
    if confirm_count != rejected_count:
        raise HTTPException(400, f"Введите число {rejected_count} для подтверждения")
    
    await db.execute(
        RegistrationRequest.__table__.delete().where(RegistrationRequest.status == "rejected")
    )
    await db.commit()
    
    return RedirectResponse(url="/admin/review/rejected?deleted_all=1", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def review_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    settings_dict = {}
    keys = ['storm_threshold', 'storm_cooldown', 'ip_limit', 
            'captcha_enabled', 'manual_review_enabled', 'whitelist_enabled']
    
    for key in keys:
        result = await db.execute(
            select(SecuritySettings).where(SecuritySettings.key == key)
        )
        setting = result.scalar_one_or_none()
        settings_dict[key] = setting.value if setting else ''
    
    whitelist = await db.execute(
        select(Whitelist).order_by(Whitelist.created_at.desc()).limit(50)
    )
    whitelist = whitelist.scalars().all()
    
    return templates.TemplateResponse("admin/review_settings.html", {
        "request": request,
        "settings": settings_dict,
        "whitelist": whitelist
    })


@router.post("/settings/update")
async def update_settings(
    request: Request,
    storm_threshold: int = Form(...),
    storm_cooldown: int = Form(...),
    ip_limit: int = Form(...),
    captcha_enabled: bool = Form(False),
    manual_review_enabled: bool = Form(False),
    whitelist_enabled: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    updates = {
        'storm_threshold': str(storm_threshold),
        'storm_cooldown': str(storm_cooldown),
        'ip_limit': str(ip_limit),
        'captcha_enabled': str(captcha_enabled).lower(),
        'manual_review_enabled': str(manual_review_enabled).lower(),
        'whitelist_enabled': str(whitelist_enabled).lower()
    }
    
    for key, value in updates.items():
        await db.execute(
            SecuritySettings.__table__.update()
            .where(SecuritySettings.key == key)
            .values(value=value, updated_at=datetime.utcnow())
        )
    
    await db.commit()
    return RedirectResponse(url="/admin/review/settings?updated=1", status_code=303)


@router.post("/whitelist/add")
async def add_to_whitelist(
    request: Request,
    type: str = Form(...),
    value: str = Form(...),
    reason: str = Form(...),
    expires_at: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    expires = None
    if expires_at:
        try:
            expires = datetime.strptime(expires_at, "%Y-%m-%d")
        except:
            pass
    
    entry = Whitelist(
        type=type,
        value=value,
        reason=reason,
        expires_at=expires
    )
    db.add(entry)
    await db.commit()
    
    return RedirectResponse(url="/admin/review/settings?added=1", status_code=303)


@router.post("/whitelist/{entry_id}/delete")
async def delete_from_whitelist(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    entry = await db.get(Whitelist, entry_id)
    if entry:
        await db.delete(entry)
        await db.commit()
    
    return RedirectResponse(url="/admin/review/settings?deleted=1", status_code=303)


@router.get("/admin_logs", response_class=HTMLResponse)
async def admin_logs_page(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    action: str = "",
    user_id: str = "",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
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
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
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