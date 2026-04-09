from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
import hashlib
import time
import os

from ..deps import templates

router = APIRouter(tags=["auth"])

# Пароль администратора (хранится в хэшированном виде)
# По умолчанию пароль: admin123
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode()).hexdigest()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    """
    Страница входа в админку
    """
    # Если уже авторизован — перенаправляем в админку
    if request.session.get("authenticated"):
        return RedirectResponse(url="/admin/", status_code=303)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })


@router.post("/login")
async def login(
    request: Request,
    password: str = Form(...)
):
    """
    Обработка отправки формы логина
    """
    # Проверяем пароль
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if password_hash == ADMIN_PASSWORD_HASH:
        # Пароль верный — создаём сессию
        request.session["authenticated"] = True
        request.session["expires_at"] = time.time() + 3600 * 24  # 24 часа
        return RedirectResponse(url="/admin/", status_code=303)
    else:
        # Неверный пароль
        return RedirectResponse(
            url="/login?error=invalid_password", 
            status_code=303
        )


@router.get("/logout")
async def logout(request: Request):
    """
    Выход из админки (очистка сессии)
    """
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)