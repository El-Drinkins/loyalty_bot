cat > /root/loyalty_bot/add_column.py << 'EOF'
import asyncio
from sqlalchemy import text
from app.models import engine

async def add_column():
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE registration_requests 
            ADD COLUMN IF NOT EXISTS instagram_status VARCHAR(20)
        """))
        print("✅ Колонка instagram_status добавлена")

if __name__ == "__main__":
    asyncio.run(add_column())
EOF