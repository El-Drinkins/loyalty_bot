import asyncio
from sqlalchemy import text
from app.models import engine

async def migrate():
    print("Начинаем миграцию для добавления новых полей пользователя...")
    async with engine.begin() as conn:
        try:
            # Добавляем новые колонки в таблицу users (если их нет)
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS verification_level VARCHAR(20) DEFAULT 'basic',
                ADD COLUMN IF NOT EXISTS instagram VARCHAR(100),
                ADD COLUMN IF NOT EXISTS vkontakte VARCHAR(100),
                ADD COLUMN IF NOT EXISTS admin_notes TEXT,
                ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS verified_by_id INTEGER REFERENCES users(id),
                ADD COLUMN IF NOT EXISTS badge VARCHAR(10) DEFAULT '🟢'
            """))
            print("✅ Колонки успешно добавлены (или уже существовали).")

            print("\n🎉 Миграция успешно завершена!")

        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")