from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import hashlib
import time
import secrets
import string
from ..deps import templates, get_db
from ...models import User
from ...notifications import send_telegram_notification

router = APIRouter(tags=["auth"])

ADMIN_PASSWORD_HASH = hashlib.sha256(settings.ADMIN_PASSWORD.encode()).hexdigest()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@router.post("/login")
async def login(request: Request, password: str = Form(...), db=Depends(get_db)):
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if password_hash == ADMIN_PASSWORD_HASH:
        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        request.session["2fa_pending"] = True
        request.session["2fa_user_id"] = 1
        request.session["2fa_code"] = code

        admin = await db.get(User, 1)
        if admin and admin.telegram_id:
            await send_telegram_notification(
                admin.telegram_id,
                f"🔐 Код для входа в админку: {code}\n\nКод действителен 5 минут."
            )

        return RedirectResponse(url="/admin/2fa", status_code=303)
    else:
        return RedirectResponse(url="/login?error=invalid_password", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)