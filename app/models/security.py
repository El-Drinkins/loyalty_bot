from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional

from .base import Base

class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    invited_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    instagram: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    instagram_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    vkontakte: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    captcha_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    inviter: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_by_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])

class SecuritySettings(Base):
    __tablename__ = "security_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Whitelist(Base):
    __tablename__ = "whitelist"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(255))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    creator: Mapped[Optional["User"]] = relationship("User")

class StormLog(Base):
    __tablename__ = "storm_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    requests_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_addresses: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)