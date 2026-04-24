import asyncio
from sqlalchemy import text
from app.models import engine

async def migrate():
    print("Начинаем миграцию для системы реферальных бонусов...")
    async with engine.begin() as conn:
        try:
            # Добавляем поле total_rentals_amount в таблицу referrals
            await conn.execute(text("""
                ALTER TABLE referrals 
                ADD COLUMN IF NOT EXISTS total_rentals_amount INTEGER DEFAULT 0
            """))
            print("✅ Поле total_rentals_amount добавлено в referrals")
            
            # Создаём таблицу referral_bonuses
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS referral_bonuses (
                    id SERIAL PRIMARY KEY,
                    referral_id INTEGER NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
                    bonus_type VARCHAR(50) NOT NULL,
                    amount INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    awarded_at TIMESTAMP,
                    awarded_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица referral_bonuses создана")
            
            # Создаём индексы
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referral 
                ON referral_bonuses(referral_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_referral_bonuses_status 
                ON referral_bonuses(status)
            """))
            print("✅ Индексы созданы")
            
            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")