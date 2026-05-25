from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from .base import Base

if TYPE_CHECKING:
    from .user import User

class BackupCode(Base):
    __tablename__ = "backup_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(20))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")