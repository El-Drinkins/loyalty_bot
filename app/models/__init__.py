from sqlalchemy.orm import relationship

from .base import Base, engine, AsyncSessionLocal, init_db
from .user import User
from .referral import Referral, ReferralStatus, ReferralCode, ReferralBonus
from .transaction import Transaction, AdminLog, UserLog
from .catalog import Category, Brand, Model
from .rental import Rental
from .security import RegistrationRequest, SecuritySettings, Whitelist, StormLog
from .web_auth import TelegramAuthCode, PasswordResetCode, UserSession

# После импорта всех моделей добавляем связи, которые требуют двусторонней ссылки
from .user import User
from .rental import Rental
from .referral import ReferralCode, Referral
from .catalog import Model

# Добавляем связи в класс User (если их нет)
if not hasattr(User, 'rentals'):
    User.rentals = relationship(
        "Rental", 
        foreign_keys="[Rental.user_id]", 
        back_populates="user",
        overlaps="referrals"
    )
if not hasattr(User, 'created_rentals'):
    User.created_rentals = relationship(
        "Rental", 
        foreign_keys="[Rental.created_by]", 
        back_populates="creator",
        overlaps="referrals"
    )
if not hasattr(User, 'referral_codes'):
    User.referral_codes = relationship(
        "ReferralCode", 
        foreign_keys="[ReferralCode.owner_id]", 
        back_populates="owner",
        overlaps="referrals"
    )
if not hasattr(User, 'referred_users'):
    User.referred_users = relationship(
        "Referral",
        foreign_keys="[Referral.old_user_id]",
        back_populates="old_user",
        overlaps="referrals"
    )
if not hasattr(User, 'referred_by'):
    User.referred_by = relationship(
        "Referral",
        foreign_keys="[Referral.new_user_id]",
        back_populates="new_user",
        overlaps="referrals"
    )

# Добавляем связь в класс Model
if not hasattr(Model, 'rentals'):
    Model.rentals = relationship(
        "Rental", 
        foreign_keys="[Rental.model_id]", 
        back_populates="model"
    )

# Экспортируем все модели для удобства
__all__ = [
    "Base", "engine", "AsyncSessionLocal", "init_db",
    "User",
    "Referral", "ReferralStatus", "ReferralCode", "ReferralBonus",
    "Transaction", "AdminLog", "UserLog",
    "Category", "Brand", "Model",
    "Rental",
    "RegistrationRequest", "SecuritySettings", "Whitelist", "StormLog",
    "TelegramAuthCode", "PasswordResetCode", "UserSession"
]