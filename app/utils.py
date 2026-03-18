from datetime import datetime, timedelta
from .config import settings

def generate_referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{user_id}"

def calculate_expiry_date() -> datetime:
    return datetime.utcnow() + timedelta(days=settings.POINTS_VALID_DAYS)