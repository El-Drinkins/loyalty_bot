"""
Единый файл миграций для бота лояльности.
Объединяет все миграции (migrate_v2..v7, catalog, web_auth, mount_type, referral_bonuses, team_bonus, add_column).
Можно безопасно запускать на существующей базе — все операции идут через IF NOT EXISTS / IF EXISTS.
"""
import asyncio
from sqlalchemy import text
from app.models import engine


async def migrate():
    print("=" * 60)
    print("ЗАПУСК ЕДИНОЙ МИГРАЦИИ")
    print("=" * 60)

    async with engine.begin() as conn:
        # ============================================================
        # 1. ТАБЛИЦЫ, НЕ ЗАВИСЯЩИЕ ОТ USERS
        # ============================================================

        # 1.1. Каталог: категории, бренды, модели
        print("\n📦 1. Таблицы каталога...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                icon VARCHAR(10) DEFAULT '📦',
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ categories")

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS brands (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ brands")

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS models (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                brand_id INTEGER REFERENCES brands(id) ON DELETE CASCADE,
                price_per_day INTEGER NOT NULL,
                deposit INTEGER,
                specs TEXT,
                image_url TEXT,
                review_url TEXT,
                default_equipment TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                mount_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ models")

        # Индексы каталога
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_models_brand ON models(brand_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_models_mount_type ON models(mount_type)"))
        print("   ✅ индексы каталога")

        # 1.2. Защита: security_settings, whitelist, storm_logs (не зависят от users)
        print("\n🛡️ 2. Таблицы защиты...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS security_settings (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ security_settings")

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
        print("   ✅ storm_logs")

        # ============================================================
        # 2. ДОБАВЛЕНИЕ КОЛОНОК В USERS (все изменения users — в одном месте)
        # ============================================================
        print("\n👤 3. Дополнительные колонки в users...")
        await conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS verification_level VARCHAR(20) DEFAULT 'basic',
            ADD COLUMN IF NOT EXISTS instagram VARCHAR(100),
            ADD COLUMN IF NOT EXISTS vkontakte VARCHAR(100),
            ADD COLUMN IF NOT EXISTS admin_notes TEXT,
            ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS verified_by_id INTEGER REFERENCES users(id),
            ADD COLUMN IF NOT EXISTS badge VARCHAR(10) DEFAULT '🟢',
            ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
            ADD COLUMN IF NOT EXISTS password_set_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS team_bonus_100k_awarded BOOLEAN DEFAULT FALSE
        """))
        print("   ✅ колонки users")

        # ============================================================
        # 3. ТАБЛИЦЫ, ЗАВИСЯЩИЕ ОТ USERS
        # ============================================================

        # 3.1. Аренды
        print("\n📋 4. Таблица rentals...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rentals (
                id SERIAL PRIMARY KEY,
                rental_number VARCHAR(50) UNIQUE NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
                price_per_day INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                deposit INTEGER,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                notes TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ rentals")

        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rentals_user ON rentals(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rentals_status ON rentals(status)"))
        print("   ✅ индексы rentals")

        # 3.2. Реферальные коды
        print("\n🔗 5. Таблица referral_codes...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                is_permanent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ referral_codes")

        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_owner ON referral_codes(owner_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(code)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_referral_codes_expires ON referral_codes(expires_at)"))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_referral_codes_permanent 
            ON referral_codes(owner_id) WHERE is_permanent = TRUE
        """))
        print("   ✅ индексы referral_codes")

        # 3.3. Реферальные бонусы (зависит от referrals, но referrals уже создан ранее)
        print("\n🎁 6. Таблица referral_bonuses...")
        # Сначала добавляем колонку в referrals
        await conn.execute(text("""
            ALTER TABLE referrals 
            ADD COLUMN IF NOT EXISTS total_rentals_amount INTEGER DEFAULT 0
        """))
        print("   ✅ total_rentals_amount в referrals")

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
        print("   ✅ referral_bonuses")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referral ON referral_bonuses(referral_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_referral_bonuses_status ON referral_bonuses(status)
        """))
        print("   ✅ индексы referral_bonuses")

        # 3.4. Регистрационные заявки
        print("\n📝 7. Таблица registration_requests...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS registration_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                telegram_id BIGINT NOT NULL,
                full_name VARCHAR(100),
                phone VARCHAR(20),
                invited_by_id INTEGER REFERENCES users(id),
                instagram VARCHAR(100),
                instagram_status VARCHAR(20),
                vkontakte VARCHAR(100),
                status VARCHAR(50) DEFAULT 'pending',
                risk_score INTEGER DEFAULT 0,
                ip_address VARCHAR(50),
                captcha_passed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP,
                review_comment TEXT
            )
        """))
        print("   ✅ registration_requests")

        # 3.5. Белый список (whitelist — зависит от users, создаём после users)
        print("\n⭐ 8. Таблица whitelist...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS whitelist (
                id SERIAL PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                value VARCHAR(255) NOT NULL,
                reason TEXT,
                created_by INTEGER REFERENCES users(id),
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ whitelist")

        # 3.6. Админ-логи и пользовательские логи
        print("\n📊 9. Таблицы логов...")
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
        print("   ✅ admin_logs")

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                action_type VARCHAR(50) NOT NULL,
                action_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("   ✅ user_logs")

        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_user_id ON admin_logs(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON admin_logs(admin_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_user_id ON user_logs(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_created_at ON user_logs(created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_logs_action ON user_logs(action_type)"))
        print("   ✅ индексы логов")

        # 3.7. Веб-сессии
        print("\n🌐 10. Таблицы веб-авторизации...")
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
        print("   ✅ user_sessions")

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
        print("   ✅ password_reset_codes")

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
        print("   ✅ telegram_auth_codes")

        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reset_codes_user ON password_reset_codes(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_codes_user ON telegram_auth_codes(user_id)"))
        print("   ✅ индексы веб-авторизации")

        # ============================================================
        # 4. УНИКАЛЬНЫЕ ОГРАНИЧЕНИЯ
        # ============================================================
        print("\n🔐 11. Уникальные ограничения...")
        await conn.execute(text("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_invited_by') THEN
                    ALTER TABLE users ADD CONSTRAINT unique_invited_by UNIQUE (invited_by_id, id);
                END IF;
            END $$;
        """))
        print("   ✅ unique_invited_by")

        await conn.execute(text("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_referral_pair') THEN
                    ALTER TABLE referrals ADD CONSTRAINT unique_referral_pair UNIQUE (old_user_id, new_user_id);
                END IF;
            END $$;
        """))
        print("   ✅ unique_referral_pair")

        # ============================================================
        # 5. АВТОУДАЛЕНИЕ СТАРЫХ ЛОГОВ
        # ============================================================
        print("\n🧹 12. Автоудаление старых логов (6 месяцев)...")
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
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS trigger_delete_old_logs ON user_logs;
            CREATE TRIGGER trigger_delete_old_logs
            AFTER INSERT ON user_logs
            EXECUTE FUNCTION delete_old_user_logs();
        """))
        print("   ✅ триггер автоудаления")

        # ============================================================
        # 6. НАЧАЛЬНЫЕ ДАННЫЕ
        # ============================================================
        print("\n📥 13. Начальные данные...")
        await conn.execute(text("""
            INSERT INTO categories (name, icon, sort_order) VALUES 
            ('Фотоаппараты', '📷', 1),
            ('Объективы', '🎞️', 2),
            ('Освещение', '💡', 3),
            ('Звук', '🎤', 4),
            ('Аксессуары', '🔋', 5)
            ON CONFLICT DO NOTHING
        """))
        print("   ✅ категории")

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
        print("   ✅ security_settings")

    print("\n" + "=" * 60)
    print("✅ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(migrate())