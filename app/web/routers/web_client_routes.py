from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import hashlib
import secrets
import random
import string

from ..deps import get_db, templates
from ...models import User, Referral, Transaction, TelegramAuthCode, PasswordResetCode, UserSession
from ...config import settings
from ...notifications import send_telegram_notification

router = APIRouter(prefix="/client", tags=["web_client"])

# Вспомогательные функции
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

def generate_code(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def generate_session_token() -> str:
    return secrets.token_urlsafe(32)

async def get_current_user(request: Request, db: AsyncSession) -> User | None:
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    
    result = await db.execute(
        select(UserSession).where(
            UserSession.session_token == session_token,
            UserSession.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return None
    
    user = await db.get(User, session.user_id)
    return user

def create_session_response(user_id: int, remember_me: bool, request: Request) -> RedirectResponse:
    session_token = generate_session_token()
    expires_at = datetime.utcnow() + timedelta(days=30 if remember_me else 1)
    
    # Сохраняем сессию в БД (асинхронно, но здесь синхронный контекст)
    # В реальном коде нужно делать через await, но для роутера это отдельная функция
    
    response = RedirectResponse(url="/client/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        expires= expires_at,
        httponly=True,
        samesite="lax"
    )
    return response, session_token, expires_at


# ==========================================
# СТРАНИЦЫ
# ==========================================

@router.get("/", response_class=HTMLResponse)
async def client_index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    
    if not user:
        return templates.TemplateResponse("web_client/auth/login.html", {"request": request})
    
    # Получаем статистику друзей
    total_invited = await db.scalar(
        select(func.count()).where(Referral.old_user_id == user.id)
    ) or 0
    
    completed = await db.scalar(
        select(func.count()).where(
            Referral.old_user_id == user.id,
            Referral.status == "completed"
        )
    ) or 0
    
    # Получаем последние 5 транзакций
    transactions = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.timestamp.desc())
        .limit(5)
    )
    transactions = transactions.scalars().all()
    
    # Получаем реферальную ссылку
    bot_username = "Take_a_picBot"
    from app.handlers.invite import get_or_create_permanent_link
    code = await get_or_create_permanent_link(user.id, bot_username, db)
    referral_link = f"https://t.me/{bot_username}?start={code}"
    
    expiry_date = user.points_expiry_date.strftime("%d.%m.%Y") if user.points_expiry_date else "не ограничен"
    
    return templates.TemplateResponse("web_client/index.html", {
        "request": request,
        "user": user,
        "total_invited": total_invited,
        "completed_invited": completed,
        "transactions": transactions,
        "referral_link": referral_link,
        "expiry_date": expiry_date
    })


@router.get("/friends", response_class=HTMLResponse)
async def client_friends(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    
    if not user:
        return templates.TemplateResponse("web_client/auth/login.html", {"request": request})
    
    total_invited = await db.scalar(
        select(func.count()).where(Referral.old_user_id == user.id)
    ) or 0
    
    completed = await db.scalar(
        select(func.count()).where(
            Referral.old_user_id == user.id,
            Referral.status == "completed"
        )
    ) or 0
    
    referrals = await db.execute(
        select(Referral, User)
        .join(User, User.id == Referral.new_user_id)
        .where(Referral.old_user_id == user.id)
        .order_by(Referral.registration_date.desc())
    )
    referrals = referrals.all()
    
    friends_list = []
    for ref, friend in referrals:
        friends_list.append({
            "id": friend.id,
            "full_name": friend.full_name,
            "registration_date": ref.registration_date.strftime("%d.%m.%Y"),
            "status": ref.status,
            "status_emoji": "✅" if ref.status == "completed" else "⏳"
        })
    
    return templates.TemplateResponse("web_client/friends.html", {
        "request": request,
        "user": user,
        "total_invited": total_invited,
        "completed_invited": completed,
        "earned": completed * settings.REFERRAL_BONUS,
        "friends": friends_list
    })


@router.get("/history", response_class=HTMLResponse)
async def client_history(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    
    if not user:
        return templates.TemplateResponse("web_client/auth/login.html", {"request": request})
    
    transactions = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.timestamp.desc())
    )
    transactions = transactions.scalars().all()
    
    # Группируем по датам
    grouped = {}
    for t in transactions:
        date_str = t.timestamp.strftime("%d.%m.%Y")
        if date_str not in grouped:
            grouped[date_str] = []
        grouped[date_str].append(t)
    
    return templates.TemplateResponse("web_client/history.html", {
        "request": request,
        "user": user,
        "grouped_transactions": grouped
    })


@router.get("/regulations", response_class=HTMLResponse)
async def client_regulations(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    
    regulations_text = (
        "📋 Программа лояльности\n\n"
        "Что такое баллы?\n"
        "Баллы — это ваши бонусы за аренду.\n"
        "1 балл = 1 рубль.\n\n"
        "Баллами можно оплатить до 50% стоимости любой будущей аренды.\n"
        "Вы сами решаете, сколько баллов использовать (хоть 100, хоть 2000), "
        "главное — не больше половины суммы аренды.\n\n"
        "Как получить баллы?\n\n"
        "1. Кэшбэк за аренду\n"
        "За каждую аренду, которую вы оплатили деньгами (без использования баллов), "
        "мы начисляем:\n"
        "• 5% от суммы — за посуточную аренду.\n"
        "• 10% от суммы — за аренду от месяца.\n\n"
        "Баллы начисляются после завершения аренды.\n\n"
        "2. Повышенный кэшбэк за регулярность\n\n"
        "Для посуточной аренды:\n"
        "• Базовая ставка — 5%.\n"
        "• Если вы совершили хотя бы одну аренду от 500 руб. за календарный месяц, "
        "ставка повышается на 1%. В следующем месяце кэшбэк будет начисляться по ставке 6%.\n"
        "• Каждый новый месяц с арендой повышает ставку ещё на 1%. Максимум — 10%.\n"
        "• Если вы не брали технику целый месяц, ставка возвращается к 5%.\n"
        "• Один раз в год по вашему запросу можно заморозить ставку на один месяц без аренд.\n\n"
        "Для аренды от месяца:\n"
        "• Базовая ставка — 10%.\n"
        "• При продлении аренды на второй месяц подряд ставка повышается на 1%.\n"
        "• Максимум — 15%.\n"
        "• После возврата техники ставка сбрасывается до базовой (10%).\n\n"
        "3. Приглашение друзей\n"
        "У каждого клиента есть персональная реферальная ссылка. Перешлите её другу — "
        "и вы оба получите бонусы.\n\n"
        "Что получит друг:\n"
        "Регистрация по вашей ссылке → 300 баллов.\n\n"
        "Баллы нужно потратить в течение 3 месяцев, иначе они сгорят.\n\n"
        "Что получите вы (приглашающий):\n"
        "Бонусы начисляются после того, как друг вернул технику в целости.\n"
        "• Первая аренда друга от 1000 руб. → 300 баллов\n"
        "• Вторая аренда друга от 1000 руб. → 700 баллов\n"
        "• Первая аренда друга на месяц (любая техника) → 500 баллов\n"
        "• Суммарные аренды друга достигли 10 000 руб. → 1000 баллов\n"
        "• Суммарные аренды друга достигли 30 000 руб. → 1000 баллов\n\n"
        "Таким образом за приглашение одного друга можно заработать 3500 баллов.\n\n"
        "Как потратить баллы?\n"
        "• Баллами можно оплатить до 50% стоимости любой аренды.\n"
        "• Вы сами решаете, сколько баллов использовать. Хоть 100, хоть 2000 — "
        "главное, не больше половины суммы аренды.\n"
        "• Если вы использовали баллы при оплате аренды то, за эту аренду баллы не начисляются.\n\n"
        "Срок действия баллов\n"
        "• Баллы действуют 3 месяца с даты последней аренды.\n"
        "• Совершили новую аренду (даже с оплатой баллами) — срок всех баллов "
        "снова становится 3 месяца.\n"
        "• Если вы не арендовали технику 3 месяца и больше — баллы сгорают.\n\n"
        "Как узнать свой баланс?\n"
        "Вы всегда можете проверить количество баллов и историю начислений в этом боте.\n"
        "Нажмите кнопку «Баланс» или отправьте команду /balance.\n\n"
        "Важно\n"
        "• Баллы не обмениваются на деньги.\n"
        "• Баллы за приглашение друзей начисляются только после того, как друг "
        "вернул технику в целости.\n"
        "• Программа может быть изменена, но мы всегда уведомим вас заранее.\n\n"
        "Арендуйте чаще, приглашайте друзей и копите баллы!"
    )
    
    return templates.TemplateResponse("web_client/regulations.html", {
        "request": request,
        "user": user,
        "regulations_text": regulations_text
    })


@router.get("/profile", response_class=HTMLResponse)
async def client_profile(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    
    if not user:
        return templates.TemplateResponse("web_client/auth/login.html", {"request": request})
    
    return templates.TemplateResponse("web_client/profile.html", {
        "request": request,
        "user": user
    })


@router.post("/profile/change_password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    user = await get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    
    if new_password != confirm_password:
        return JSONResponse({"error": "Пароли не совпадают"}, status_code=400)
    
    if len(new_password) < 6:
        return JSONResponse({"error": "Пароль должен быть не менее 6 символов"}, status_code=400)
    
    # Проверяем текущий пароль
    if user.password_hash and not verify_password(current_password, user.password_hash):
        return JSONResponse({"error": "Неверный текущий пароль"}, status_code=400)
    
    user.password_hash = hash_password(new_password)
    user.password_set_at = datetime.utcnow()
    await db.commit()
    
    return JSONResponse({"success": True})


@router.post("/logout")
async def client_logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.execute(
            UserSession.__table__.delete().where(UserSession.session_token == session_token)
        )
        await db.commit()
    
    response = RedirectResponse(url="/client/", status_code=303)
    response.delete_cookie("session_token")
    return response


# ==========================================
# АВТОРИЗАЦИЯ
# ==========================================

@router.get("/login", response_class=HTMLResponse)
async def client_login_page(request: Request, error: str = None):
    return templates.TemplateResponse("web_client/auth/login.html", {
        "request": request,
        "error": error
    })


@router.post("/login")
async def client_login(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    # Нормализуем номер телефона
    import re
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    if len(digits) == 10:
        digits = '7' + digits
    normalized_phone = '+' + digits if digits.startswith('7') else phone
    
    # Ищем пользователя
    result = await db.execute(
        select(User).where(User.phone == normalized_phone)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return templates.TemplateResponse("web_client/auth/login.html", {
            "request": request,
            "error": "Пользователь с таким номером не найден"
        })
    
    if not user.password_hash:
        return templates.TemplateResponse("web_client/auth/login.html", {
            "request": request,
            "error": "У вас ещё не установлен пароль. Восстановите пароль через Telegram"
        })
    
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse("web_client/auth/login.html", {
            "request": request,
            "error": "Неверный пароль"
        })
    
    # Создаём сессию
    session_token = generate_session_token()
    expires_at = datetime.utcnow() + timedelta(days=30 if remember_me else 1)
    
    user_session = UserSession(
        user_id=user.id,
        session_token=session_token,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host
    )
    db.add(user_session)
    await db.commit()
    
    response = RedirectResponse(url="/client/", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        expires=expires_at,
        httponly=True,
        samesite="lax"
    )
    return response


@router.get("/telegram-auth")
async def telegram_auth_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/client/", status_code=303)
    
    return templates.TemplateResponse("web_client/auth/telegram_auth.html", {"request": request})


@router.post("/telegram-auth/request-code")
async def request_telegram_auth_code(
    request: Request,
    phone: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Нормализуем номер
    import re
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    if len(digits) == 10:
        digits = '7' + digits
    normalized_phone = '+' + digits if digits.startswith('7') else phone
    
    result = await db.execute(
        select(User).where(User.phone == normalized_phone)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return JSONResponse({"error": "Пользователь не найден"}, status_code=404)
    
    # Генерируем код
    code = generate_code(6)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    # Сохраняем код в БД
    auth_code = TelegramAuthCode(
        user_id=user.id,
        code=code,
        expires_at=expires_at
    )
    db.add(auth_code)
    await db.commit()
    
    # Отправляем код в Telegram
    try:
        await send_telegram_notification(
            user.telegram_id,
            f"🔐 Код для входа на сайт: `{code}`\n\nКод действителен 10 минут."
        )
    except Exception as e:
        print(f"Не удалось отправить код: {e}")
        return JSONResponse({"error": "Не удалось отправить код. Убедитесь, что бот не заблокирован"}, status_code=500)
    
    return JSONResponse({"success": True, "user_id": user.id})


@router.post("/telegram-auth/verify")
async def verify_telegram_auth_code(
    request: Request,
    user_id: int = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Ищем код
    result = await db.execute(
        select(TelegramAuthCode).where(
            TelegramAuthCode.user_id == user_id,
            TelegramAuthCode.code == code,
            TelegramAuthCode.expires_at > datetime.utcnow()
        )
    )
    auth_code = result.scalar_one_or_none()
    
    if not auth_code:
        return JSONResponse({"error": "Неверный или истёкший код"}, status_code=400)
    
    # Удаляем использованный код
    await db.delete(auth_code)
    
    # Получаем пользователя
    user = await db.get(User, user_id)
    if not user:
        return JSONResponse({"error": "Пользователь не найден"}, status_code=404)
    
    # Создаём сессию
    session_token = generate_session_token()
    expires_at = datetime.utcnow() + timedelta(days=30)
    
    user_session = UserSession(
        user_id=user.id,
        session_token=session_token,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host
    )
    db.add(user_session)
    await db.commit()
    
    response = JSONResponse({"success": True})
    response.set_cookie(
        key="session_token",
        value=session_token,
        expires=expires_at,
        httponly=True,
        samesite="lax"
    )
    return response


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, error: str = None, step: str = "phone"):
    return templates.TemplateResponse("web_client/auth/reset_password.html", {
        "request": request,
        "error": error,
        "step": step
    })


@router.post("/reset-password/request-code")
async def request_reset_code(
    request: Request,
    phone: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Нормализуем номер
    import re
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    if len(digits) == 10:
        digits = '7' + digits
    normalized_phone = '+' + digits if digits.startswith('7') else phone
    
    result = await db.execute(
        select(User).where(User.phone == normalized_phone)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return JSONResponse({"error": "Пользователь не найден"}, status_code=404)
    
    # Проверяем количество попыток
    recent_attempts = await db.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.created_at > datetime.utcnow() - timedelta(minutes=15)
        )
    )
    attempts = recent_attempts.scalars().all()
    if len(attempts) >= 3:
        return JSONResponse({"error": "Слишком много попыток. Попробуйте через 15 минут"}, status_code=429)
    
    # Генерируем код
    code = generate_code(6)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    reset_code = PasswordResetCode(
        user_id=user.id,
        code=code,
        expires_at=expires_at
    )
    db.add(reset_code)
    await db.commit()
    
    # Отправляем код в Telegram
    try:
        await send_telegram_notification(
            user.telegram_id,
            f"🔐 Код для восстановления пароля: `{code}`\n\nКод действителен 10 минут.\nЕсли вы не запрашивали восстановление пароля, проигнорируйте это сообщение."
        )
    except Exception as e:
        print(f"Не удалось отправить код: {e}")
        return JSONResponse({"error": "Не удалось отправить код. Убедитесь, что бот не заблокирован"}, status_code=500)
    
    return JSONResponse({"success": True, "user_id": user.id})


@router.post("/reset-password/verify")
async def verify_reset_code(
    request: Request,
    user_id: int = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if new_password != confirm_password:
        return JSONResponse({"error": "Пароли не совпадают"}, status_code=400)
    
    if len(new_password) < 6:
        return JSONResponse({"error": "Пароль должен быть не менее 6 символов"}, status_code=400)
    
    # Ищем код
    result = await db.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user_id,
            PasswordResetCode.code == code,
            PasswordResetCode.expires_at > datetime.utcnow()
        )
    )
    reset_code = result.scalar_one_or_none()
    
    if not reset_code:
        return JSONResponse({"error": "Неверный или истёкший код"}, status_code=400)
    
    # Увеличиваем счётчик попыток
    reset_code.attempts += 1
    if reset_code.attempts >= 3:
        await db.delete(reset_code)
        await db.commit()
        return JSONResponse({"error": "Исчерпано количество попыток"}, status_code=400)
    
    # Обновляем пароль
    user = await db.get(User, user_id)
    if user:
        user.password_hash = hash_password(new_password)
        user.password_set_at = datetime.utcnow()
    
    await db.delete(reset_code)
    await db.commit()
    
    return JSONResponse({"success": True})