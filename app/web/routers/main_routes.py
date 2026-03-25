from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from itertools import groupby

from ..deps import get_db, templates, require_auth
from ...models import User, Referral, Transaction, ReferralStatus

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def admin_index(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_users = await db.execute(select(func.count(User.id)))
    total_users = total_users.scalar()
    
    total_balance = await db.execute(select(func.sum(User.balance)))
    total_balance = total_balance.scalar() or 0

    stmt = (
        select(Referral)
        .options(
            selectinload(Referral.new_user).selectinload(User.invited_by)
        )
        .where(Referral.status == ReferralStatus.pending)
    )
    result = await db.execute(stmt)
    pending_refs = result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_users": total_users,
        "total_balance": total_balance,
        "pending_refs": pending_refs
    })

@router.get("/client/{user_id}", response_class=HTMLResponse)
async def client_card(
    request: Request, 
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Клиент не найден")

    inviter = None
    if user.invited_by_id:
        inviter = await db.get(User, user.invited_by_id)

    total_invited = await db.execute(
        select(func.count()).where(Referral.old_user_id == user_id)
    )
    total_invited = total_invited.scalar()
    
    completed_invited = await db.execute(
        select(func.count()).where(Referral.old_user_id == user_id, Referral.status == ReferralStatus.completed)
    )
    completed_invited = completed_invited.scalar()

    transactions = await db.execute(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.timestamp.desc())
    )
    transactions = transactions.scalars().all()
    
    grouped = []
    for date, group in groupby(transactions, key=lambda x: x.timestamp.strftime('%d.%m.%Y')):
        grouped.append((date, list(group)))

    return templates.TemplateResponse("client/base_client.html", {
        "request": request,
        "user": user,
        "inviter": inviter,
        "total_invited": total_invited,
        "completed_invited": completed_invited,
        "transactions": transactions,
        "grouped_transactions": grouped
    })