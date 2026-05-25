from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import pyotp
import qrcode
import io
import base64
from ..deps import get_db, templates
from ...models import User
from ...config import settings

router = APIRouter(tags=["totp"])

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name="LoyaltyBot"
    )

def generate_qr_code(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode()

@router.get("/setup-totp", response_class=HTMLResponse)
async def setup_totp_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("authenticated"):
        return RedirectResponse(url="/login", status_code=303)
    
    admin_id = request.session.get("admin_id")
    admin = await db.get(User, admin_id)
    
    if not admin or not admin.is_admin:
        return RedirectResponse(url="/login", status_code=303)
    
    secret = admin.totp_secret
    if not secret:
        secret = generate_totp_secret()
        admin.totp_secret = secret
        await db.commit()
    
    uri = get_totp_uri(secret, admin.phone or f"admin{admin.id}")
    qr_code = generate_qr_code(uri)
    
    return templates.TemplateResponse("totp_setup.html", {
        "request": request,
        "secret": secret,
        "qr_code": qr_code,
        "uri": uri
    })

@router.post("/verify-totp-setup")
async def verify_totp_setup(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("authenticated"):
        return RedirectResponse(url="/login", status_code=303)
    
    admin_id = request.session.get("admin_id")
    admin = await db.get(User, admin_id)
    
    if not admin or not admin.totp_secret:
        return RedirectResponse(url="/login", status_code=303)
    
    totp = pyotp.TOTP(admin.totp_secret)
    if totp.verify(code):
        admin.totp_enabled = True
        await db.commit()
        return RedirectResponse(url="/admin/", status_code=303)
    
    return RedirectResponse(url="/admin/setup-totp?error=invalid_code", status_code=303)