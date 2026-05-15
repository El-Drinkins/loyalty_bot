from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..deps import get_db, require_auth, templates
from ...models import User, Transaction, AdminLog, Referral, ReferralStatus, ReferralBonus, Rental
from ...utils import calculate_expiry_date
from ...config import settings
from ...notifications import send_telegram_notification
from ...bonus_utils import award_referral_bonus, get_pending_bonuses_for_referral, get_bonus_type_name

router = APIRouter()


def check_balance_limit(user: User, amount: int) -> bool:
    """Проверяет, не превысит ли баланс лимит после начисления. True = превышен."""
    return amount > 0 and (user.balance + amount) > settings.MAX_BALANCE


async def add_points_to_user(db: AsyncSession, user_id: int, amount: int, reason: str, admin_id: int):
    """Начисляет баллы пользователю. Возвращает пользователя после начисления."""
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
    
    try:
        await send_telegram_notification(
            user.telegram_id,
            f"💰 Вам начислено {amount} баллов.\nПричина: {reason}"
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление пользователю {user.telegram_id}: {e}")
    
    return user


@router.post("/client/{user_id}/add_points")
async def add_points(
    request: Request,
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
    
    if check_balance_limit(user, amount):
        return templates.TemplateResponse("client/confirm_overlimit.html", {
            "request": request,
            "user": user,
            "action": "add_points",
            "action_url": f"/admin/client/{user_id}/add_points",
            "amount": amount,
            "reason": reason,
            "current_balance": user.balance,
            "new_balance": user.balance + amount,
            "max_balance": settings.MAX_BALANCE,
            "message": f"После начисления баланс составит {user.balance + amount} ⭐, что превышает лимит {settings.MAX_BALANCE} ⭐."
        })
    
    await add_points_to_user(db, user_id, amount, reason, admin_id)
    return RedirectResponse(url=f"/admin/client/{user_id}", status_code=303)


@router.post("/client/{user_id}/add_points_force")
async def add_points_force(
    request: Request,
    user_id: int,
    amount: int = Form(...),
    reason: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    await add_points_to_user(db, user_id, amount, f"{reason} (превышен лимит)", admin_id)
    return RedirectResponse(url=f"/admin/client/{user_id}", status_code=303)


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
    
    await add_points_to_user(db, user_id, -amount, reason, admin_id)
    return RedirectResponse(url=f"/admin/client/{user_id}", status_code=303)


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

    await add_points_to_user(
        db, referral.old_user_id, settings.REFERRAL_BONUS,
        f"Бонус за друга (первая аренда подтверждена, ID: {referral.new_user_id})",
        admin_id
    )

    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/referrals/{user_id}")
async def referrals_page(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    result = await db.execute(
        select(Referral, User)
        .join(User, User.id == Referral.new_user_id)
        .where(Referral.old_user_id == user_id)
        .order_by(Referral.registration_date.desc())
    )
    referrals = result.all()
    
    friends_data = []
    for ref, friend in referrals:
        total_rentals = await db.scalar(
            select(func.coalesce(func.sum(Rental.total_price), 0))
            .where(Rental.user_id == friend.id, Rental.status == "completed")
        ) or 0
        
        bonuses_result = await db.execute(
            select(func.sum(ReferralBonus.amount))
            .where(ReferralBonus.referral_id == ref.id, ReferralBonus.status == "awarded")
        )
        total_bonus = bonuses_result.scalar() or 0
        
        pending_bonuses = await get_pending_bonuses_for_referral(db, ref.id)
        
        friends_data.append({
            "referral_id": ref.id,
            "friend": friend,
            "total_rentals": total_rentals,
            "total_bonus": total_bonus,
            "pending_bonuses": pending_bonuses,
            "status_emoji": "✅" if ref.status == ReferralStatus.completed else "⏳"
        })
    
    return templates.TemplateResponse("client/referrals.html", {
        "request": request,
        "user": user,
        "friends": friends_data
    })


@router.get("/referral_detail/{referral_id}")
async def referral_detail_page(
    request: Request,
    referral_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    referral = await db.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Реферал не найден")
    
    friend = await db.get(User, referral.new_user_id)
    user = await db.get(User, referral.old_user_id)
    
    total_rentals = await db.scalar(
        select(func.coalesce(func.sum(Rental.total_price), 0))
        .where(Rental.user_id == friend.id, Rental.status == "completed")
    ) or 0
    
    bonuses_result = await db.execute(
        select(ReferralBonus).where(ReferralBonus.referral_id == referral_id)
    )
    bonuses = bonuses_result.scalars().all()
    
    awarded_bonuses = [b for b in bonuses if b.status == "awarded"]
    pending_bonuses = [b for b in bonuses if b.status == "pending"]
    
    return templates.TemplateResponse("client/referral_detail.html", {
        "request": request,
        "user": user,
        "friend": friend,
        "referral": referral,
        "total_rentals": total_rentals,
        "awarded_bonuses": awarded_bonuses,
        "pending_bonuses": pending_bonuses
    })


@router.post("/api/confirm_bonus/{bonus_id}")
async def confirm_bonus_api(
    request: Request,
    bonus_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    bonus = await db.get(ReferralBonus, bonus_id)
    if not bonus or bonus.status != "pending":
        raise HTTPException(400, "Бонус не найден или уже обработан")
    
    referral = await db.get(Referral, bonus.referral_id)
    if not referral:
        raise HTTPException(404, "Реферал не найден")
    
    user = await db.get(User, referral.old_user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    if check_balance_limit(user, bonus.amount):
        bonus_name = get_bonus_type_name(bonus.bonus_type)
        return templates.TemplateResponse("client/confirm_overlimit.html", {
            "request": request,
            "user": user,
            "action": "confirm_bonus",
            "action_url": f"/admin/api/confirm_bonus/{bonus_id}",
            "amount": bonus.amount,
            "reason": f"Бонус за {bonus_name}",
            "current_balance": user.balance,
            "new_balance": user.balance + bonus.amount,
            "max_balance": settings.MAX_BALANCE,
            "message": f"После начисления бонуса (+{bonus.amount} ⭐) баланс составит {user.balance + bonus.amount} ⭐, что превышает лимит {settings.MAX_BALANCE} ⭐."
        })
    
    success = await award_referral_bonus(db, bonus_id, admin_id)
    if not success:
        raise HTTPException(400, "Не удалось подтвердить бонус")
    
    return RedirectResponse(url=f"/admin/referral_detail/{referral.id}", status_code=303)


@router.post("/api/confirm_all_pending/{referral_id}")
async def confirm_all_pending_bonuses(
    request: Request,
    referral_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    pending = await get_pending_bonuses_for_referral(db, referral_id)
    
    for bonus in pending:
        await award_referral_bonus(db, bonus.id, admin_id)
    
    return RedirectResponse(url=f"/admin/referral_detail/{referral_id}", status_code=303)