from sqlalchemy import String, BigInteger, Integer, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from .base import Base

# Для избежания циклических импортов
if TYPE_CHECKING:
    from .rental import Rental
    from .referral import ReferralCode

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    full_name_real: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    registration_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    points_expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Реферальные связи
    invited_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    
    # Админ и черный список
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    blacklisted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Поля для верификации
    verification_level: Mapped[str] = mapped_column(String(20), default="basic")
    instagram: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vkontakte: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verified_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    badge: Mapped[str] = mapped_column(String(10), default="🟢")
    
    # Поля для веб-версии (пароль)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Командный бонус 100k (начислен ли бонус 5000⭐ за суммарные аренды всех друзей на 100000₽)
    team_bonus_100k_awarded: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Связи (будут заполнены после импорта всех моделей)
    invited_by: Mapped[Optional["User"]] = relationship(
        "User", 
        remote_side=[id], 
        foreign_keys=[invited_by_id],
        backref="referrals"
    )
    
    verifier: Mapped[Optional["User"]] = relationship(
        "User", 
        foreign_keys=[verified_by_id],
        remote_side=[id]
    )
    
    # ВНИМАНИЕ: Следующие связи будут добавлены в __init__.py
    # после импорта всех моделей, чтобы избежать циклических зависимостей
    # rentals: Mapped[List["Rental"]] = relationship("Rental", back_populates="user")
    # created_rentals: Mapped[List["Rental"]] = relationship("Rental", back_populates="creator")
    # referral_codes: Mapped[List["ReferralCode"]] = relationship("ReferralCode", back_populates="owner")