from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from itertools import groupby

from ..deps import get_db, templates, require_auth
from ...models import User, Referral, Transaction, ReferralStatus
from ...cashback import get_cashback_info

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def admin_index(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_users = await db.scalar(select(func.count(User.id)))
    total_balance = await db.scalar(select(func.sum(User.balance))) or 0

    from ...bonus_utils import get_all_pending_bonuses
    pending_bonuses = await get_all_pending_bonuses(db)

    # Последние сообщения обратной связи
    from ...models import Feedback
    feedback_result = await db.execute(
        select(Feedback)
        .options(selectinload(Feedback.user))
        .order_by(Feedback.created_at.desc())
        .limit(5)
    )
    latest_feedback = feedback_result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_users": total_users,
        "total_balance": total_balance,
        "pending_bonuses": pending_bonuses,
        "latest_feedback": latest_feedback
    })

@router.get("/client/{user_id}", response_class=HTMLResponse)
async def client_card(
    request: Request, 
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    user = await db.get(
        User, 
        user_id,
        options=[
            selectinload(User.invited_by),
            selectinload(User.referred_users).selectinload(Referral.new_user),
            selectinload(User.rentals)
        ]
    )
    if not user:
        raise HTTPException(404, "Клиент не найден")

    inviter = user.invited_by

    total_invited = len(user.referred_users) if user.referred_users else 0
    completed_invited = 0
    if user.referred_users:
        completed_invited = sum(1 for ref in user.referred_users if ref.status == ReferralStatus.completed)

    transactions = await db.execute(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.timestamp.desc())
    )
    transactions = transactions.scalars().all()
    
    grouped = []
    for date, group in groupby(transactions, key=lambda x: x.timestamp.strftime('%d.%m.%Y')):
        grouped.append((date, list(group)))

    # Загружаем информацию о кэшбэке
    cashback_info = await get_cashback_info(db, user)
        # Сообщения обратной связи пользователя
    from ...models import Feedback
    feedback_result = await db.execute(
        select(Feedback)
        .where(Feedback.user_id == user_id)
        .order_by(Feedback.created_at.desc())
    )
    user_feedback = feedback_result.scalars().all()

    return templates.TemplateResponse("client/base_client.html", {
        "request": request,
        "user": user,
        "inviter": inviter,
        "total_invited": total_invited,
        "completed_invited": completed_invited,
        "transactions": transactions,
        "grouped_transactions": grouped,
        "cashback_info": cashback_info
        "user_feedback": user_feedback
    })