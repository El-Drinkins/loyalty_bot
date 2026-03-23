from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from ..deps import get_db, templates
from ...models import User, RegistrationRequest, SecuritySettings, Whitelist, StormLog
from ...config import settings

router = APIRouter(prefix="/admin/review", tags=["admin"])

@router.get("/", response_class=HTMLResponse)
async def review_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Дашборд для модерации заявок (только ожидающие)"""
    pending_count = await db.scalar(
        select(func.count()).where(RegistrationRequest.status == "pending")
    )
    approved_today = await db.scalar(
        select(func.count())
        .where(
            RegistrationRequest.status == "approved",
            func.date(RegistrationRequest.reviewed_at) == datetime.utcnow().date()
        )
    )
    rejected_today = await db.scalar(
        select(func.count())
        .where(
            RegistrationRequest.status == "rejected",
            func.date(RegistrationRequest.reviewed_at) == datetime.utcnow().date()
        )
    )
    
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
        "approved_today": approved_today,
        "rejected_today": rejected_today,
        "requests": requests
    })

@router.get("/all", response_class=HTMLResponse)
async def review_all(
    request: Request,
    status: str = "pending",
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Показывает заявки с фильтром по статусу"""
    # Статистика по статусам
    stats = {}
    for s in ['pending', 'approved', 'rejected']:
        stats[s] = await db.scalar(
            select(func.count()).where(RegistrationRequest.status == s)
        ) or 0
    
    # Запрос с фильтром
    query = select(RegistrationRequest).where(RegistrationRequest.status == status)
    total_count = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    
    offset = (page - 1) * per_page
    query = query.order_by(RegistrationRequest.created_at.desc()).offset(offset).limit(per_page)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    
    return templates.TemplateResponse("admin/review_all.html", {
        "request": request,
        "requests": requests,
        "stats": stats,
        "current_status": status,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "per_page": per_page
    })

@router.post("/restore/{request_id}")
async def restore_request(
    request_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Восстанавливает отклонённую заявку (меняет статус на pending)"""
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
    
    return RedirectResponse(url="/admin/review/all?status=pending", status_code=303)

@router.get("/settings", response_class=HTMLResponse)
async def review_settings(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Настройки защиты"""
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
    db: AsyncSession = Depends(get_db)
):
    """Обновляет настройки защиты"""
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
    db: AsyncSession = Depends(get_db)
):
    """Добавляет запись в белый список"""
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
    db: AsyncSession = Depends(get_db)
):
    """Удаляет запись из белого списка"""
    entry = await db.get(Whitelist, entry_id)
    if entry:
        await db.delete(entry)
        await db.commit()
    
    return RedirectResponse(url="/admin/review/settings?deleted=1", status_code=303)