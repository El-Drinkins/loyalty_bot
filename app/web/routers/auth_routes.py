from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import time

from ..deps import templates

router = APIRouter(tags=["auth"])

ADMIN_PASSWORD_HASH = hashlib.sha256("4Ue768k3u!".encode()).hexdigest()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if password_hash == ADMIN_PASSWORD_HASH:
        request.session["authenticated"] = True
        request.session["expires_at"] = time.time() + 3600 * 24
        print(f"✅ Сессия установлена: {dict(request.session)}")
        return RedirectResponse(url="/admin/", status_code=303)
    else:
        return RedirectResponse(url="/login?error=invalid_password", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)