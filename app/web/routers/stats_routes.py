from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from ..deps import get_db, templates, require_auth
from ...models import User, Referral, Transaction, ReferralStatus

router = APIRouter()

@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_users = await db.scalar(select(func.count(User.id)))
    total_balance = await db.scalar(select(func.sum(User.balance))) or 0
    avg_balance = total_balance // total_users if total_users else 0
    
    referral_users = await db.scalar(
        select(func.count()).where(User.invited_by_id.is_not(None))
    )
    
    completed_referrals = await db.scalar(
        select(func.count()).where(Referral.status == ReferralStatus.completed)
    )
    
    total_transactions = await db.scalar(select(func.count(Transaction.id)))
    
    top_users = await db.execute(
        select(User)
        .order_by(User.balance.desc())
        .limit(10)
        .options(selectinload(User.invited_by))
    )
    top_users = top_users.scalars().all()
    
    daily_stats = []
    for i in range(7):
        date = (datetime.utcnow() - timedelta(days=i)).date()
        
        new_users = await db.scalar(
            select(func.count(User.id))
            .where(func.date(User.registration_date) == date)
        )
        
        points_earned = await db.scalar(
            select(func.sum(Transaction.amount))
            .where(
                func.date(Transaction.timestamp) == date,
                Transaction.amount > 0
            )
        ) or 0
        
        points_spent = await db.scalar(
            select(func.sum(Transaction.amount))
            .where(
                func.date(Transaction.timestamp) == date,
                Transaction.amount < 0
            )
        ) or 0
        
        daily_stats.append({
            "date": date.strftime("%d.%m.%Y"),
            "new_users": new_users or 0,
            "points_earned": points_earned,
            "points_spent": abs(points_spent)
        })
    
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "total_users": total_users,
        "total_balance": total_balance,
        "avg_balance": avg_balance,
        "referral_users": referral_users or 0,
        "completed_referrals": completed_referrals or 0,
        "total_transactions": total_transactions or 0,
        "top_users": top_users,
        "daily_stats": daily_stats
    })

@router.get("/spent_stats", response_class=HTMLResponse)
async def spent_stats_page(
    request: Request, 
    page: int = 1, 
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_spent = await db.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.amount < 0)
    ) or 0
    total_spent = abs(total_spent)
    
    total_count = await db.scalar(
        select(func.count(Transaction.id)).where(Transaction.amount < 0)
    ) or 0
    
    avg_spent = total_spent // total_count if total_count else 0
    
    max_spent = await db.scalar(
        select(func.max(Transaction.amount)).where(Transaction.amount < 0)
    ) or 0
    max_spent = abs(max_spent)
    
    monthly_stats = []
    for i in range(6):
        month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_total = await db.scalar(
            select(func.sum(Transaction.amount))
            .where(
                Transaction.amount < 0,
                Transaction.timestamp >= month_start,
                Transaction.timestamp <= month_end
            )
        ) or 0
        
        month_count = await db.scalar(
            select(func.count(Transaction.id))
            .where(
                Transaction.amount < 0,
                Transaction.timestamp >= month_start,
                Transaction.timestamp <= month_end
            )
        ) or 0
        
        if month_count > 0:
            monthly_stats.append({
                "month": month_start.strftime("%B %Y"),
                "total": abs(month_total),
                "count": month_count,
                "avg": abs(month_total) // month_count
            })
    
    reasons_query = await db.execute(
        select(Transaction.reason, func.count(Transaction.id), func.sum(Transaction.amount))
        .where(Transaction.amount < 0)
        .group_by(Transaction.reason)
        .order_by(func.count(Transaction.id).desc())
        .limit(10)
    )
    top_reasons = []
    for reason, count, total in reasons_query:
        top_reasons.append({
            "reason": reason,
            "count": count,
            "total": abs(total),
            "percent": round(count / total_count * 100, 1) if total_count else 0
        })
    
    top_clients_query = await db.execute(
        select(
            Transaction.user_id,
            func.count(Transaction.id).label('count'),
            func.sum(Transaction.amount).label('total')
        )
        .where(Transaction.amount < 0)
        .group_by(Transaction.user_id)
        .order_by(func.sum(Transaction.amount).asc())
        .limit(10)
    )
    
    top_clients = []
    for user_id, count, total in top_clients_query:
        user = await db.get(User, user_id)
        if user:
            top_clients.append({
                "id": user_id,
                "full_name": user.full_name,
                "phone": user.phone,
                "total_spent": abs(total),
                "count": count,
                "avg": abs(total) // count
            })
    
    offset = (page - 1) * per_page
    
    history_query = await db.execute(
        select(Transaction)
        .where(Transaction.amount < 0)
        .order_by(Transaction.timestamp.desc())
        .offset(offset)
        .limit(per_page)
    )
    spent_history = []
    for t in history_query.scalars().all():
        user = await db.get(User, t.user_id)
        spent_history.append({
            "id": t.id,
            "user_id": t.user_id,
            "user_name": user.full_name if user else "Неизвестно",
            "amount": abs(t.amount),
            "reason": t.reason,
            "timestamp": t.timestamp,
            "admin_id": t.admin_id
        })
    
    total_pages = (total_count + per_page - 1) // per_page
    
    return templates.TemplateResponse("spent_stats.html", {
        "request": request,
        "total_spent": total_spent,
        "total_count": total_count,
        "avg_spent": avg_spent,
        "max_spent": max_spent,
        "monthly_stats": monthly_stats,
        "top_reasons": top_reasons,
        "top_clients": top_clients,
        "spent_history": spent_history,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })

@router.get("/earned_stats", response_class=HTMLResponse)
async def earned_stats_page(
    request: Request, 
    page: int = 1, 
    per_page: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    total_earned = await db.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.amount > 0)
    ) or 0
    
    total_count = await db.scalar(
        select(func.count(Transaction.id)).where(Transaction.amount > 0)
    ) or 0
    
    avg_earned = total_earned // total_count if total_count else 0
    
    max_earned = await db.scalar(
        select(func.max(Transaction.amount)).where(Transaction.amount > 0)
    ) or 0
    
    monthly_stats = []
    for i in range(6):
        month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_total = await db.scalar(
            select(func.sum(Transaction.amount))
            .where(
                Transaction.amount > 0,
                Transaction.timestamp >= month_start,
                Transaction.timestamp <= month_end
            )
        ) or 0
        
        month_count = await db.scalar(
            select(func.count(Transaction.id))
            .where(
                Transaction.amount > 0,
                Transaction.timestamp >= month_start,
                Transaction.timestamp <= month_end
            )
        ) or 0
        
        if month_count > 0:
            monthly_stats.append({
                "month": month_start.strftime("%B %Y"),
                "total": month_total,
                "count": month_count,
                "avg": month_total // month_count
            })
    
    reasons_query = await db.execute(
        select(Transaction.reason, func.count(Transaction.id), func.sum(Transaction.amount))
        .where(Transaction.amount > 0)
        .group_by(Transaction.reason)
        .order_by(func.count(Transaction.id).desc())
        .limit(10)
    )
    top_reasons = []
    for reason, count, total in reasons_query:
        top_reasons.append({
            "reason": reason,
            "count": count,
            "total": total,
            "percent": round(count / total_count * 100, 1) if total_count else 0
        })
    
    top_clients_query = await db.execute(
        select(
            Transaction.user_id,
            func.count(Transaction.id).label('count'),
            func.sum(Transaction.amount).label('total')
        )
        .where(Transaction.amount > 0)
        .group_by(Transaction.user_id)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
    )
    
    top_clients = []
    for user_id, count, total in top_clients_query:
        user = await db.get(User, user_id)
        if user:
            top_clients.append({
                "id": user_id,
                "full_name": user.full_name,
                "phone": user.phone,
                "total_earned": total,
                "count": count,
                "avg": total // count
            })
    
    offset = (page - 1) * per_page
    
    history_query = await db.execute(
        select(Transaction)
        .where(Transaction.amount > 0)
        .order_by(Transaction.timestamp.desc())
        .offset(offset)
        .limit(per_page)
    )
    earned_history = []
    for t in history_query.scalars().all():
        user = await db.get(User, t.user_id)
        earned_history.append({
            "id": t.id,
            "user_id": t.user_id,
            "user_name": user.full_name if user else "Неизвестно",
            "amount": t.amount,
            "reason": t.reason,
            "timestamp": t.timestamp,
            "admin_id": t.admin_id
        })
    
    total_pages = (total_count + per_page - 1) // per_page
    
    return templates.TemplateResponse("earned_stats.html", {
        "request": request,
        "total_earned": total_earned,
        "total_count": total_count,
        "avg_earned": avg_earned,
        "max_earned": max_earned,
        "monthly_stats": monthly_stats,
        "top_reasons": top_reasons,
        "top_clients": top_clients,
        "earned_history": earned_history,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })