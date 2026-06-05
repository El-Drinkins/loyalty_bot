# app/web/routers/referral_routes.py

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import random
import string

from ..deps import get_db, templates, require_auth
from ...models import ReferralCode, User

router = APIRouter(tags=["referral_links"])

def generate_code(owner_id: int) -> str:
    chars = string.ascii_letters + string.digits
    code = ''.join(random.choice(chars) for _ in range(8))
    return f"{owner_id}_{code}"

@router.get("/admin/referral-links", response_class=HTMLResponse)
async def referral_links_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    codes = await db.execute(
        select(ReferralCode)
        .where(ReferralCode.is_active == True)
        .order_by(ReferralCode.created_at.desc())
    )
    codes = codes.scalars().all()
    
    bot_username = "Take_a_picBot"

    return templates.TemplateResponse("referral_links.html", {
        "request": request,
        "codes": codes,
        "bot_username": bot_username
    })

@router.post("/admin/referral-links/create")
async def create_referral_link(
    request: Request,
    link_type: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    # Находим админа
    admin = await db.execute(select(User).where(User.is_admin == True))
    admin = admin.scalar_one_or_none()
    
    if not admin:
        admin = await db.execute(select(User).order_by(User.id).limit(1))
        admin = admin.scalar_one_or_none()
    
    code = generate_code(admin.id)
    
    if link_type == "permanent":
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=0, expires_at=None, is_permanent=True, note=note if note else None)
    elif link_type == "single":
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=1, expires_at=None, is_permanent=False, note=note if note else None)
    elif link_type == "temp_7":
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=0, expires_at=datetime.utcnow() + timedelta(days=7), is_permanent=False, note=note if note else None)
    elif link_type == "temp_14":
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=0, expires_at=datetime.utcnow() + timedelta(days=14), is_permanent=False, note=note if note else None)
    elif link_type == "temp_30":
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=0, expires_at=datetime.utcnow() + timedelta(days=30), is_permanent=False, note=note if note else None)
    else:
        new_code = ReferralCode(code=code, owner_id=admin.id, max_uses=0, expires_at=None, is_permanent=False, note=note if note else None)
    
    db.add(new_code)
    await db.commit()
    
    return RedirectResponse(url="/admin/referral-links", status_code=303)

@router.post("/admin/referral-links/{code_id}/delete")
async def delete_referral_link(
    code_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    code = await db.get(ReferralCode, code_id)
    if code and not code.is_permanent:
        code.is_active = False
        await db.commit()
    
    return RedirectResponse(url="/admin/referral-links", status_code=303)

@router.post("/admin/backup")
async def run_backup(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    import subprocess
    try:
        subprocess.run(["bash", "/root/loyalty_bot/backup/backup.sh"], capture_output=True, timeout=30)
        subprocess.run(["bash", "/root/loyalty_bot/backup/upload_to_yandex.sh"], capture_output=True, timeout=30)
        return RedirectResponse(url="/admin/referral-links?backup=ok", status_code=303)
    except Exception:
        return RedirectResponse(url="/admin/referral-links?backup=error", status_code=303)