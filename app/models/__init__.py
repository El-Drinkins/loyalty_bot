from sqlalchemy.orm import relationship

from .base import Base, engine, AsyncSessionLocal, init_db
from .user import User
from .referral import Referral, ReferralStatus, ReferralCode
from .transaction import Transaction, AdminLog, UserLog
from .catalog import Category, Brand, Model
from .rental import Rental
from .security import RegistrationRequest, SecuritySettings, Whitelist, StormLog

# После импорта всех моделей добавляем связи, которые требуют двусторонней ссылки
from .user import User
from .rental import Rental
from .referral import ReferralCode
from .catalog import Model

# Добавляем связи в класс User
User.rentals = relationship(
    "Rental", 
    foreign_keys="[Rental.user_id]", 
    back_populates="user",
    overlaps="referrals"
)
User.created_rentals = relationship(
    "Rental", 
    foreign_keys="[Rental.created_by]", 
    back_populates="creator",
    overlaps="referrals"
)
User.referral_codes = relationship(
    "ReferralCode", 
    foreign_keys="[ReferralCode.owner_id]", 
    back_populates="owner",
    overlaps="referrals"
)

# Добавляем связь в класс Model
Model.rentals = relationship(
    "Rental", 
    foreign_keys="[Rental.model_id]", 
    back_populates="model"
)

# Экспортируем все модели для удобства
__all__ = [
    "Base", "engine", "AsyncSessionLocal", "init_db",
    "User",
    "Referral", "ReferralStatus", "ReferralCode",
    "Transaction", "AdminLog", "UserLog",
    "Category", "Brand", "Model",
    "Rental",
    "RegistrationRequest", "SecuritySettings", "Whitelist", "StormLog"
]