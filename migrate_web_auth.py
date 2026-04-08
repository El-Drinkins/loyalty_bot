import asyncio
from sqlalchemy import text
from app.models import engine

async def migrate():
    print("Начинаем миграцию для веб-версии...")
    async with engine.begin() as conn:
        try:
            # Добавляем поле password_hash в таблицу users
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)
            """))
            print("✅ Поле password_hash добавлено")
            
            # Добавляем поле password_set_at (когда был установлен пароль)
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS password_set_at TIMESTAMP
            """))
            print("✅ Поле password_set_at добавлено")
            
            # Создаём таблицу для сессий пользователей
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT,
                    ip_address VARCHAR(50)
                )
            """))
            print("✅ Таблица user_sessions создана")
            
            # Создаём таблицу для кодов восстановления
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS password_reset_codes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code VARCHAR(10) NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица password_reset_codes создана")
            
            # Создаём таблицу для кодов входа через Telegram
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS telegram_auth_codes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code VARCHAR(10) NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица telegram_auth_codes создана")
            
            # Добавляем индексы
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reset_codes_user ON password_reset_codes(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_codes_user ON telegram_auth_codes(user_id)"))
            print("✅ Индексы созданы")
            
            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())