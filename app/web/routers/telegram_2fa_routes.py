from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..deps import get_db, templates
from ...models import User, BackupCode
from ...notifications import send_telegram_notification
import hashlib
import secrets
import string
from datetime import datetime

router = APIRouter(tags=["telegram_2fa"])

def generate_2fa_code() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(6))

def generate_backup_codes() -> list:
    codes = []
    for _ in range(10):
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        codes.append(code)
    return codes

@router.get("/admin/2fa", response_class=HTMLResponse)
async def telegram_2fa_page(
    request: Request,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("2fa_pending"):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("telegram_2fa.html", {
        "request": request,
        "error": error
    })

@router.post("/admin/2fa/verify")
async def verify_telegram_2fa(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("2fa_pending"):
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session.get("2fa_user_id")
    stored_code = request.session.get("2fa_code")

    if code == stored_code:
        request.session["authenticated"] = True
        # Уведомление о входе
        admin = await db.get(User, user_id)
        if admin and admin.telegram_id:
            await send_telegram_notification(
                admin.telegram_id,
                f"🔔 Вход в админку\n\n"
                f"🕐 {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
                f"🌐 IP: {request.client.host}"
            )
        request.session.pop("2fa_pending", None)
        request.session.pop("2fa_user_id", None)
        request.session.pop("2fa_code", None)

        if admin and not admin.telegram_2fa_enabled:
            admin.telegram_2fa_enabled = True
            await db.commit()

        return RedirectResponse(url="/admin/", status_code=303)

    return RedirectResponse(url="/admin/2fa?error=invalid_code", status_code=303)

@router.post("/admin/2fa/verify-backup")
async def verify_backup_code(
    request: Request,
    backup_code: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("2fa_pending"):
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session.get("2fa_user_id")

    result = await db.execute(
        select(BackupCode).where(
            BackupCode.user_id == user_id,
            BackupCode.code == backup_code,
            BackupCode.used == False
        )
    )
    code = result.scalar_one_or_none()

    if code:
        code.used = True
        code.used_at = datetime.utcnow()
        await db.commit()

        request.session["authenticated"] = True
        # Уведомление о входе
        admin = await db.get(User, user_id)
        if admin and admin.telegram_id:
            await send_telegram_notification(
                admin.telegram_id,
                f"🔔 Вход в админку (по резервному коду)\n\n"
                f"🕐 {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
                f"🌐 IP: {request.client.host}"
            )
        request.session.pop("2fa_pending", None)
        request.session.pop("2fa_user_id", None)
        request.session.pop("2fa_code", None)

        return RedirectResponse(url="/admin/", status_code=303)

    return RedirectResponse(url="/admin/2fa?error=invalid_backup", status_code=303)

@router.get("/admin/2fa/generate-backup", response_class=HTMLResponse)
async def generate_backup_codes_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("authenticated"):
        return RedirectResponse(url="/login", status_code=303)

    admin = await db.get(User, 1)
    if not admin or not admin.telegram_2fa_enabled:
        return RedirectResponse(url="/admin/", status_code=303)

    # Удаляем старые неиспользованные коды
    await db.execute(
        delete(BackupCode).where(
            BackupCode.user_id == admin.id,
            BackupCode.used == False
        )
    )

    codes = generate_backup_codes()
    for code_str in codes:
        backup = BackupCode(
            user_id=admin.id,
            code=code_str
        )
        db.add(backup)

    await db.commit()

    return templates.TemplateResponse("backup_codes.html", {
        "request": request,
        "codes": codes
    })