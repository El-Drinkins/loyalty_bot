from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..deps import get_db, require_auth, templates
from ...models import User, Transaction, AdminLog, Referral, ReferralStatus, ReferralBonus
from ...utils import calculate_expiry_date
from ...config import settings
from ...notifications import send_telegram_notification
from ...bonus_utils import award_referral_bonus, get_pending_bonuses_for_referral

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
    return RedirectResponse(url="/admin/", status_code=303)


# ========== НОВЫЕ ЭНДПОИНТЫ ДЛЯ РЕФЕРАЛЬНЫХ БОНУСОВ ==========

@router.get("/referrals/{user_id}")
async def referrals_page(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_auth)
):
    """Страница со списком рефералов пользователя"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    
    # Получаем всех друзей пользователя
    result = await db.execute(
        select(Referral, User)
        .join(User, User.id == Referral.new_user_id)
        .where(Referral.old_user_id == user_id)
        .order_by(Referral.registration_date.desc())
    )
    referrals = result.all()
    
    friends_data = []
    for ref, friend in referrals:
        # Получаем сумму аренд
        total_rentals = ref.total_rentals_amount
        
        # Получаем сумму полученных бонусов
        bonuses_result = await db.execute(
            select(func.sum(ReferralBonus.amount))
            .where(
                ReferralBonus.referral_id == ref.id,
                ReferralBonus.status == "awarded"
            )
        )
        total_bonus = bonuses_result.scalar() or 0
        
        # Получаем ожидающие бонусы
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
    """Детальная страница реферала"""
    referral = await db.get(Referral, referral_id)
    if not referral:
        raise HTTPException(404, "Реферал не найден")
    
    friend = await db.get(User, referral.new_user_id)
    user = await db.get(User, referral.old_user_id)
    
    # Получаем все бонусы
    bonuses_result = await db.execute(
        select(ReferralBonus).where(ReferralBonus.referral_id == referral_id)
    )
    bonuses = bonuses_result.scalars().all()
    
    awarded_bonuses = [b for b in bonuses if b.status == "awarded"]
    pending_bonuses = [b for b in bonuses if b.status == "pending"]
    
    # Сумма аренд
    total_rentals = referral.total_rentals_amount
    
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
    """API для подтверждения бонуса"""
    success = await award_referral_bonus(db, bonus_id, admin_id)
    if not success:
        raise HTTPException(400, "Не удалось подтвердить бонус")
    
    # Получаем информацию для редиректа
    bonus = await db.get(ReferralBonus, bonus_id)
    if bonus:
        referral = await db.get(Referral, bonus.referral_id)
        if referral:
            return RedirectResponse(url=f"/admin/referral_detail/{referral.id}", status_code=303)
    
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/api/confirm_all_pending/{referral_id}")
async def confirm_all_pending_bonuses(
    request: Request,
    referral_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Form(0),
    _=Depends(require_auth)
):
    """Подтверждает все ожидающие бонусы для реферала"""
    pending = await get_pending_bonuses_for_referral(db, referral_id)
    
    awarded = 0
    for bonus in pending:
        if await award_referral_bonus(db, bonus.id, admin_id):
            awarded += 1
    
    return RedirectResponse(url=f"/admin/referral_detail/{referral_id}", status_code=303)