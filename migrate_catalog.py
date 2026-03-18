import asyncio
from sqlalchemy import text
from app.db import engine

async def migrate():
    print("Начинаем миграцию базы данных для каталога...")
    async with engine.begin() as conn:
        try:
            # Таблица категорий
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
            print("✅ Таблица categories создана")

            # Таблица брендов
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
            print("✅ Таблица brands создана")

            # Таблица моделей
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Таблица models создана")

            # Таблица аренд
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
            print("✅ Таблица rentals создана")

            # Индексы
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_models_brand ON models(brand_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rentals_user ON rentals(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rentals_status ON rentals(status)"))
            print("✅ Индексы созданы")

            # Добавляем начальные данные
            await conn.execute(text("""
                INSERT INTO categories (name, icon, sort_order) VALUES 
                ('Фотоаппараты', '📷', 1),
                ('Объективы', '🎞️', 2),
                ('Освещение', '💡', 3),
                ('Звук', '🎚️', 4),
                ('Аксессуары', '🔋', 5)
                ON CONFLICT DO NOTHING
            """))
            print("✅ Начальные категории добавлены")

            print("\n🎉 Миграция каталога успешно завершена!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(migrate())
    input("\nНажмите Enter для выхода...")