import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_IDS: list[int] = []
    WELCOME_BONUS: int = 200
    REFERRAL_BONUS: int = 100
    POINTS_VALID_DAYS: int = 365
    PROXY_URL: str = ""  # <--- ЭТА СТРОКА ДОБАВЛЕНА

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Парсим ADMIN_IDS из строки (если передано строкой)
        if isinstance(self.ADMIN_IDS, str):
            self.ADMIN_IDS = [int(id.strip()) for id in self.ADMIN_IDS.split(",") if id.strip()]

settings = Settings()