import asyncio
import time
from sqlalchemy import select
from app.models import AsyncSessionLocal, User

async def test_db():
    print("="*50)
    print("ТЕСТ СКОРОСТИ БАЗЫ ДАННЫХ")
    print("="*50)
    
    # Тест 1: Простое подключение
    print("\n📡 Тест 1: Подключение к БД...")
    start = time.time()
    async with AsyncSessionLocal() as session:
        connect_time = time.time() - start
        print(f"   Подключение: {connect_time*1000:.2f} мс")
        
        # Тест 2: Простой SELECT запрос
        print("\n📊 Тест 2: Простой SELECT (первый пользователь)...")
        start = time.time()
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        select_time = time.time() - start
        print(f"   SELECT запрос: {select_time*1000:.2f} мс")
        
        if user:
            print(f"   Найден пользователь: {user.full_name}")
        else:
            print("   Пользователей нет")
        
        # Тест 3: COUNT запрос
        print("\n🔢 Тест 3: COUNT запрос...")
        start = time.time()
        from sqlalchemy import func
        result = await session.execute(select(func.count(User.id)))
        count = result.scalar()
        count_time = time.time() - start
        print(f"   COUNT запрос: {count_time*1000:.2f} мс")
        print(f"   Всего пользователей: {count}")
    
    print("\n" + "="*50)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("="*50)
    print("\n📊 НОРМАЛЬНЫЕ ПОКАЗАТЕЛИ:")
    print("   • Подключение: < 50 мс")
    print("   • SELECT: < 20 мс")
    print("   • COUNT: < 10 мс")
    print("\n⚠️ ЕСЛИ ВРЕМЯ БОЛЬШЕ:")
    print("   • 100-500 мс - база данных тормозит")
    print("   • >500 мс - серьезные проблемы с БД")

if __name__ == "__main__":
    asyncio.run(test_db())