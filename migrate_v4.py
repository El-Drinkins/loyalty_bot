import asyncio
from sqlalchemy import text
from app.db import engine

async def migrate():
    print("Начинаем миграцию базы данных...")
    async with engine.begin() as conn:
        try:
            # Создаем таблицу для логов действий пользователей
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    action_type VARCHAR(50) NOT NULL,
                    action_details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица user_logs создана")

            # Создаем таблицу для реферальных кодов
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS referral_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    max_uses INTEGER DEFAULT 1,
                    used_count INTEGER DEFAULT 0,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица referral_codes создана")

            # Создаем индексы для логов
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_user_id ON user_logs(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_created_at ON user_logs(created_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_action ON user_logs(action_type)"))
            print("✅ Индексы для user_logs созданы")

            # Создаем индексы для кодов
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_owner ON referral_codes(owner_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(code)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_expires ON referral_codes(expires_at)"))
            print("✅ Индексы для referral_codes созданы")

            # Настраиваем автоматическое удаление старых логов (через 6 месяцев)
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION delete_old_user_logs() RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    DELETE FROM user_logs WHERE created_at < NOW() - INTERVAL '6 months';
                    RETURN NULL;
                END;
                $$;
            """))
            
            # Создаем триггер
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_delete_old_logs ON user_logs;
                CREATE TRIGGER trigger_delete_old_logs
                AFTER INSERT ON user_logs
                EXECUTE FUNCTION delete_old_user_logs();
            """))
            print("✅ Автоудаление старых логов настроено (6 месяцев)")

            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")