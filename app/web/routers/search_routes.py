from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..deps import get_db, templates, require_auth
from ...models import User

router = APIRouter(tags=["search"])

@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Страница поиска клиентов"""
    results = []
    if q:
        # Ищем по ID, имени или телефону
        conditions = []
        if q.isdigit():
            conditions.append(User.id == int(q))
        conditions.append(User.full_name.ilike(f"%{q}%"))
        conditions.append(User.phone.ilike(f"%{q}%"))
        
        stmt = select(User).where(or_(*conditions)).limit(50)
        result = await db.execute(stmt)
        results = result.scalars().all()
    
    return templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "results": results
    })