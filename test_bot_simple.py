import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA" # Вставьте токен сюда напрямую

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("✅ Бот работает!")

async def main():
    print("🚀 Запускаем тестового бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())