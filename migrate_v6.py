import asyncio
from sqlalchemy import text
from app.db import engine

async def migrate():
    print("Начинаем миграцию базы данных...")
    async with engine.begin() as conn:
        try:
            # Таблица для заявок на регистрацию
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS registration_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    telegram_id BIGINT NOT NULL,
                    full_name VARCHAR(100),
                    phone VARCHAR(20),
                    invited_by_id INTEGER REFERENCES users(id),
                    instagram VARCHAR(100),
                    vkontakte VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'pending',  -- pending, approved, rejected
                    risk_score INTEGER DEFAULT 0,
                    ip_address VARCHAR(50),
                    captcha_passed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_by INTEGER REFERENCES users(id),
                    reviewed_at TIMESTAMP,
                    review_comment TEXT
                )
            """))
            print("✅ Таблица registration_requests создана")

            # Добавляем поля в таблицу users
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS verification_level VARCHAR(20) DEFAULT 'basic',
                ADD COLUMN IF NOT EXISTS instagram VARCHAR(100),
                ADD COLUMN IF NOT EXISTS vkontakte VARCHAR(100),
                ADD COLUMN IF NOT EXISTS admin_notes TEXT,
                ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS verified_by INTEGER REFERENCES users(id),
                ADD COLUMN IF NOT EXISTS badge VARCHAR(10) DEFAULT '🟢'
            """))
            print("✅ Поля добавлены в таблицу users")

            # Таблица для настроек защиты
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS security_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица security_settings создана")

            # Таблица для белого списка IP/ссылок
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,  -- ip, referral_code, user
                    value VARCHAR(255) NOT NULL,
                    reason TEXT,
                    created_by INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица whitelist создана")

            # Таблица для шторм-логов
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS storm_logs (
                    id SERIAL PRIMARY KEY,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    requests_count INTEGER,
                    ip_addresses TEXT,
                    action_taken VARCHAR(100),
                    resolved_at TIMESTAMP
                )
            """))
            print("✅ Таблица storm_logs создана")

            # Добавляем начальные настройки
            await conn.execute(text("""
                INSERT INTO security_settings (key, value) VALUES 
                ('storm_threshold', '100'),
                ('storm_cooldown', '60'),
                ('ip_limit', '5'),
                ('captcha_enabled', 'true'),
                ('manual_review_enabled', 'true'),
                ('whitelist_enabled', 'true')
                ON CONFLICT (key) DO NOTHING
            """))
            print("✅ Начальные настройки добавлены")

            print("\n🎉 Миграция успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")