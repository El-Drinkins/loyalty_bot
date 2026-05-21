from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from ..deps import get_db, templates, require_auth
from ...models import Feedback, User

router = APIRouter(tags=["feedback"])
TIMEZONE_OFFSET_HOURS = 3

@router.get("/admin/feedback", response_class=HTMLResponse)
async def feedback_page(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    feedback_type: str = "",
    user_search: str = "",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    query = select(Feedback).options(selectinload(Feedback.user)).order_by(Feedback.created_at.desc())

    if feedback_type:
        query = query.where(Feedback.feedback_type == feedback_type)

    if user_search:
        if user_search.isdigit():
            query = query.where(Feedback.user_id == int(user_search))
        else:
            query = query.join(User).where(User.full_name.ilike(f"%{user_search}%"))

    total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    feedbacks = result.scalars().all()

    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "feedbacks": feedbacks,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "feedback_type": feedback_type,
        "user_search": user_search
    })