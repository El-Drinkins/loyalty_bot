import asyncio
from sqlalchemy import text
from app.models import engine

async def migrate():
    print("Начинаем миграцию для командного бонуса...")
    async with engine.begin() as conn:
        try:
            # Добавляем поле team_bonus_100k_awarded в таблицу users
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS team_bonus_100k_awarded BOOLEAN DEFAULT FALSE
            """))
            print("✅ Поле team_bonus_100k_awarded добавлено в таблицу users")
            
            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")