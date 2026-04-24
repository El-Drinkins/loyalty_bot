from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import enum

from .base import Base

if TYPE_CHECKING:
    from .user import User

class ReferralStatus(enum.Enum):
    pending = "pending"
    completed = "completed"

class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    new_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    old_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ReferralStatus] = mapped_column(Enum(ReferralStatus), default=ReferralStatus.pending)
    registration_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completion_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # НОВОЕ ПОЛЕ: сумма всех аренд друга
    total_rentals_amount: Mapped[int] = mapped_column(Integer, default=0)

    # Связи
    new_user: Mapped["User"] = relationship("User", foreign_keys=[new_user_id])
    old_user: Mapped["User"] = relationship("User", foreign_keys=[old_user_id])

class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_permanent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    owner: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[owner_id],
        back_populates="referral_codes"
    )


class ReferralBonus(Base):
    """Новая таблица для отслеживания бонусов за рефералов"""
    __tablename__ = "referral_bonuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    referral_id: Mapped[int] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"))
    bonus_type: Mapped[str] = mapped_column(String(50))  # first_rental, second_rental, threshold_10k, threshold_30k
    amount: Mapped[int] = mapped_column(Integer)  # 300, 700, 1000, 1000
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, awarded
    awarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    awarded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    referral: Mapped["Referral"] = relationship("Referral")
    awarder: Mapped[Optional["User"]] = relationship("User", foreign_keys=[awarded_by])