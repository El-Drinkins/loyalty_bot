from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..deps import get_db, require_auth
from ...models import User, Transaction, AdminLog, Referral, ReferralStatus
from ...utils import calculate_expiry_date
from ...config import settings
from ...notifications import send_telegram_notification

router = APIRouter()

@router.post("/client/{user_id}/add_points")
async def add_points(
    user_id: int,
    amount: int = Form(...),
    reason: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    old_balance = user.balance
    user.balance += amount
    if amount > 0:
        user.points_expiry_date = calculate_expiry_date()
    
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        reason=reason,
        admin_id=admin_id
    )
    db.add(transaction)
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="add_points",
        user_id=user_id,
        old_value=str(old_balance),
        new_value=str(user.balance),
        reason=reason
    )
    db.add(log)
    
    await db.commit()
    
    await send_telegram_notification(
        user.telegram_id,
        f"💰 Вам начислено {amount} баллов.\nПричина: {reason}"
    )
    
    return RedirectResponse(url=f"/client/{user_id}", status_code=303)

@router.post("/client/{user_id}/subtract_points")
async def subtract_points(
    user_id: int,
    amount: int = Form(...),
    reason: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    if user.balance < amount:
        raise HTTPException(400, "Недостаточно баллов")
    
    old_balance = user.balance
    user.balance -= amount
    transaction = Transaction(
        user_id=user_id,
        amount=-amount,
        reason=reason,
        admin_id=admin_id
    )
    db.add(transaction)
    
    log = AdminLog(
        admin_id=admin_id,
        action_type="subtract_points",
        user_id=user_id,
        old_value=str(old_balance),
        new_value=str(user.balance),
        reason=reason
    )
    db.add(log)
    
    await db.commit()
    
    await send_telegram_notification(
        user.telegram_id,
        f"💸 С вашего счета списано {amount} баллов.\nПричина: {reason}"
    )
    
    return RedirectResponse(url=f"/client/{user_id}", status_code=303)

@router.post("/confirm_referral/{referral_id}")
async def confirm_referral(
    referral_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    referral = await db.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Реферал не найден")
    
    if referral.status == ReferralStatus.completed:
        raise HTTPException(400, "Уже подтверждено")

    referral.status = ReferralStatus.completed
    referral.completion_date = datetime.utcnow()

    inviter = await db.get(User, referral.old_user_id)
    if inviter:
        old_balance = inviter.balance
        inviter.balance += settings.REFERRAL_BONUS
        inviter.points_expiry_date = calculate_expiry_date()

        transaction = Transaction(
            user_id=inviter.id,
            amount=settings.REFERRAL_BONUS,
            reason="Бонус за друга (первая аренда подтверждена)",
            admin_id=admin_id
        )
        db.add(transaction)
        
        log = AdminLog(
            admin_id=admin_id,
            action_type="confirm_referral",
            user_id=inviter.id,
            old_value=str(old_balance),
            new_value=str(inviter.balance),
            reason=f"Подтверждена первая аренда пользователя ID {referral.new_user_id}"
        )
        db.add(log)

        await send_telegram_notification(
            inviter.telegram_id,
            f"🎉 Вам начислено {settings.REFERRAL_BONUS} баллов за друга!"
        )

    await db.commit()
    return RedirectResponse(url="/", status_code=303)