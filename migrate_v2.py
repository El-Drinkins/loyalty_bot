import asyncio
from sqlalchemy import text
from app.db import engine

async def migrate():
    print("Начинаем миграцию базы данных...")
    async with engine.begin() as conn:
        try:
            # Создаем таблицу для логов администратора
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id SERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    user_id INTEGER NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица admin_logs создана")

            # Добавляем уникальные ограничения для защиты от дублирования
            # Убеждаемся, что у пользователя может быть только один пригласивший
            await conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_invited_by') THEN
                        ALTER TABLE users ADD CONSTRAINT unique_invited_by UNIQUE (invited_by_id, id);
                    END IF;
                END $$;
            """))
            print("✅ Ограничение unique_invited_by добавлено")

            # Убеждаемся, что пара (пригласивший, приглашенный) уникальна в таблице referrals
            await conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_referral_pair') THEN
                        ALTER TABLE referrals ADD CONSTRAINT unique_referral_pair UNIQUE (old_user_id, new_user_id);
                    END IF;
                END $$;
            """))
            print("✅ Ограничение unique_referral_pair добавлено")

            # Создаем индексы по отдельности (исправлено)
            try:
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_user_id ON admin_logs(user_id)"))
                print("✅ Индекс idx_admin_logs_user_id создан")
            except Exception as e:
                print(f"⚠️ Индекс idx_admin_logs_user_id: {e}")

            try:
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON admin_logs(admin_id)"))
                print("✅ Индекс idx_admin_logs_admin_id создан")
            except Exception as e:
                print(f"⚠️ Индекс idx_admin_logs_admin_id: {e}")

            try:
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at)"))
                print("✅ Индекс idx_admin_logs_created_at создан")
            except Exception as e:
                print(f"⚠️ Индекс idx_admin_logs_created_at: {e}")

            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")