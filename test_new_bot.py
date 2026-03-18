import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

# ==========================================
# ВСТАВЬТЕ СЮДА НОВЫЙ ТОКЕН ОТ BOTFATHER
# ==========================================
BOT_TOKEN = "7234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"  # ЗАМЕНИТЕ НА ВАШ!
# ==========================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    start = time.time()
    await message.answer("✅ Новый тестовый бот работает!")
    total = time.time() - start
    print(f"⏱️ Ответ за {total*1000:.2f}мс")

@dp.message()
async def echo_all(message: Message):
    start = time.time()
    await message.answer(f"Эхо: {message.text}")
    total = time.time() - start
    print(f"⏱️ Эхо за {total*1000:.2f}мс")

async def main():
    print("="*60)
    print("🚀 ТЕСТ НОВОГО БОТА")
    print("="*60)
    print(f"Бот: @{(await bot.get_me()).username}")
    print("-"*60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())