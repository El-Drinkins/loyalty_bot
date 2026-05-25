from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class InviteSettings(Base):
    __tablename__ = "invite_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    invitations_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled_text: Mapped[str] = mapped_column(Text, default="Эта функция временно недоступна.\n\nПо вопросам приглашений обращайтесь к администратору: @el_drinkins")