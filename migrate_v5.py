import asyncio
from sqlalchemy import text
from app.db import engine

async def migrate():
    print("Начинаем миграцию базы данных...")
    async with engine.begin() as conn:
        try:
            # Добавляем поле is_permanent в таблицу referral_codes
            await conn.execute(text("""
                ALTER TABLE referral_codes 
                ADD COLUMN IF NOT EXISTS is_permanent BOOLEAN DEFAULT FALSE
            """))
            print("✅ Поле is_permanent добавлено в referral_codes")

            # Добавляем индекс для быстрого поиска
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_referral_codes_permanent 
                ON referral_codes(owner_id) WHERE is_permanent = TRUE
            """))
            print("✅ Индекс для постоянных ссылок создан")

            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")