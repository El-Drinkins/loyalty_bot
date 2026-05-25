from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..deps import get_db, templates, require_auth
from ...models import InviteSettings

router = APIRouter(tags=["invite_settings"])

@router.get("/admin/invite-settings", response_class=HTMLResponse)
async def invite_settings_page(
    request: Request,
    saved: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    result = await db.execute(select(InviteSettings).where(InviteSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = InviteSettings(id=1)
        db.add(settings)
        await db.commit()

    return templates.TemplateResponse("invite_settings.html", {
        "request": request,
        "settings": settings,
        "saved": saved
    })

@router.post("/admin/invite-settings")
async def save_invite_settings(
    request: Request,
    invitations_enabled: bool = Form(False),
    disabled_text: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    result = await db.execute(select(InviteSettings).where(InviteSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = InviteSettings(id=1)
        db.add(settings)

    settings.invitations_enabled = invitations_enabled
    settings.disabled_text = disabled_text
    await db.commit()

    return RedirectResponse(url="/admin/invite-settings?saved=1", status_code=303)