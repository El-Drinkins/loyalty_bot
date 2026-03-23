from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..deps import get_db, templates
from ...models import User
from ...notifications import send_telegram_notification

router = APIRouter(prefix="/mailing", tags=["mailing"])

@router.get("/", response_class=HTMLResponse)
async def mailing_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Страница рассылки"""
    total_users = await db.scalar(select(func.count(User.id))) or 0
    users_with_telegram = await db.scalar(
        select(func.count()).where(User.telegram_id.is_not(None))
    ) or 0
    
    return templates.TemplateResponse("mailing.html", {
        "request": request,
        "total_users": total_users,
        "users_with_telegram": users_with_telegram,
        "last_mailing": None  # можно добавить логирование рассылок
    })

@router.post("/")
async def send_mailing(
    request: Request,
    recipient_type: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    preview: bool = Form(True),
    db: AsyncSession = Depends(get_db)
):
    """Отправляет рассылку"""
    # Получаем список пользователей
    if recipient_type == "all":
        result = await db.execute(select(User))
    elif recipient_type == "with_telegram":
        result = await db.execute(
            select(User).where(User.telegram_id.is_not(None))
        )
    elif recipient_type == "with_referrals":
        result = await db.execute(
            select(User).where(User.invited_by_id.is_not(None))
        )
    elif recipient_type == "active_last_month":
        # Активные за последний месяц (есть транзакции)
        from ...models import Transaction
        month_ago = datetime.utcnow().replace(day=1)
        result = await db.execute(
            select(User).where(
                User.id.in_(
                    select(Transaction.user_id).where(Transaction.timestamp >= month_ago)
                )
            )
        )
    else:
        result = await db.execute(select(User))
    
    users = result.scalars().all()
    
    # Формируем текст сообщения
    full_message = f"📢 **{subject}**\n\n{message}"
    
    # Если предпросмотр — отправляем только себе
    if preview:
        admin_id = 271186601  # твой Telegram ID
        await send_telegram_notification(admin_id, full_message)
        return RedirectResponse(url="/mailing?preview_sent=1", status_code=303)
    
    # Отправляем всем
    sent_count = 0
    for user in users:
        if user.telegram_id:
            try:
                await send_telegram_notification(user.telegram_id, full_message)
                sent_count += 1
            except Exception as e:
                print(f"Failed to send to {user.telegram_id}: {e}")
    
    return RedirectResponse(url=f"/mailing?sent={sent_count}&total={len(users)}", status_code=303)