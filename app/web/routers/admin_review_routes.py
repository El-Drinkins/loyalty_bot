from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from ..deps import get_db, templates
from ...models import User, RegistrationRequest, SecuritySettings, Whitelist, StormLog, Transaction
from ...config import settings
from ...notifications import send_telegram_notification

router = APIRouter(prefix="/admin/review", tags=["admin"])

@router.get("/", response_class=HTMLResponse)
async def review_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Дашборд для модерации заявок (только ожидающие)"""
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
    db: AsyncSession = Depends(get_db)
):
    """Страница отклонённых заявок"""
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
    db: AsyncSession = Depends(get_db)
):
    """Одобряет заявку и создаёт пользователя"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    if req.status != "pending":
        raise HTTPException(400, "Заявка уже обработана")
    
    # Создаем пользователя
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
        verified_at=datetime.utcnow()
    )
    db.add(user)
    await db.flush()
    
    # Обновляем статус заявки
    req.status = "approved"
    req.user_id = user.id
    req.reviewed_at = datetime.utcnow()
    
    # Добавляем транзакцию на начисление бонусов
    transaction = Transaction(
        user_id=user.id,
        amount=settings.WELCOME_BONUS,
        reason="Бонус за регистрацию"
    )
    db.add(transaction)
    
    await db.commit()
    
    # Отправляем уведомление пользователю
    try:
        await send_telegram_notification(
            req.telegram_id,
            f"✅ **Регистрация подтверждена!**\n\n"
            f"Ваша заявка одобрена. Добро пожаловать в программу лояльности!\n\n"
            f"🎁 Вам начислено {settings.WELCOME_BONUS} приветственных баллов.\n\n"
            f"Отправьте /start для начала работы."
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {req.telegram_id}: {e}")
    
    # Возвращаемся на страницу модерации
    return RedirectResponse(url="/admin/review", status_code=303)

@router.post("/api/reject/{request_id}")
async def api_reject_request(
    request_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Отклоняет заявку и отправляет уведомление пользователю"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    # Отправляем уведомление пользователю
    try:
        await send_telegram_notification(
            req.telegram_id,
            "❌ **Регистрация отклонена**\n\n"
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
    db: AsyncSession = Depends(get_db)
):
    """Блокирует пользователя и отклоняет заявку"""
    req = await db.get(RegistrationRequest, request_id)
    if not req:
        raise HTTPException(404, "Заявка не найдена")
    
    req.status = "rejected"
    req.review_comment = reason
    req.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    # Отправляем уведомление пользователю
    try:
        await send_telegram_notification(
            req.telegram_id,
            f"❌ **Регистрация отклонена**\n\n"
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
    
    return RedirectResponse(url="/admin/review/rejected", status_code=303)

@router.post("/api/delete_request/{request_id}")
async def delete_request(
    request_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаляет заявку навсегда"""
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
    db: AsyncSession = Depends(get_db)
):
    """Удаляет все отклонённые заявки с подтверждением количества"""
    # Получаем количество отклонённых заявок
    rejected_count = await db.scalar(
        select(func.count()).where(RegistrationRequest.status == "rejected")
    ) or 0
    
    # Проверяем, что введённое число совпадает с количеством
    if confirm_count != rejected_count:
        raise HTTPException(400, f"Введите число {rejected_count} для подтверждения")
    
    # Удаляем все отклонённые заявки
    await db.execute(
        RegistrationRequest.__table__.delete().where(RegistrationRequest.status == "rejected")
    )
    await db.commit()
    
    return RedirectResponse(url="/admin/review/rejected?deleted_all=1", status_code=303)

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