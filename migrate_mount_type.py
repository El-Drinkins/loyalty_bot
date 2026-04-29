import asyncio
from sqlalchemy import text
from app.models import engine

async def migrate():
    print("Начинаем миграцию для добавления поля mount_type...")
    async with engine.begin() as conn:
        try:
            # Добавляем поле mount_type в таблицу models
            await conn.execute(text("""
                ALTER TABLE models 
                ADD COLUMN IF NOT EXISTS mount_type VARCHAR(50)
            """))
            print("✅ Поле mount_type добавлено в таблицу models")
            
            # Создаём индекс для быстрого поиска по mount_type
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_models_mount_type 
                ON models(mount_type)
            """))
            print("✅ Индекс для mount_type создан")
            
            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")