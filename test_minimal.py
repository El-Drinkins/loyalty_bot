import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# ==========================================
# ВАШ ТОКЕН - тот же, что и в основном боте
# ==========================================
BOT_TOKEN = "8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA"
# ==========================================

# Создаем минимального бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Счетчик для замера времени
request_times = []

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start
    Замеряет время от получения команды до отправки ответа
    """
    start_time = time.time()
    
    # Отправляем простое сообщение
    await message.answer("✅ Минимальный бот работает!")
    
    total_time = time.time() - start_time
    request_times.append(total_time)
    
    # Выводим время в консоль
    print(f"⏱️ [{len(request_times)}] Ответ за {total_time*1000:.2f}мс")
    
    # Каждые 10 запросов показываем статистику
    if len(request_times) % 10 == 0:
        avg_time = sum(request_times[-10:]) / 10 * 1000
        min_time = min(request_times[-10:]) * 1000
        max_time = max(request_times[-10:]) * 1000
        print(f"📊 Статистика последних 10 запросов:")
        print(f"   Среднее: {avg_time:.2f}мс | Мин: {min_time:.2f}мс | Макс: {max_time:.2f}мс")

@dp.message()
async def echo_all(message: Message):
    """
    Отвечает на любое сообщение (для тестирования)
    """
    start_time = time.time()
    
    await message.answer(f"Вы написали: {message.text}")
    
    total_time = time.time() - start_time
    print(f"⏱️ Эхо: {total_time*1000:.2f}мс")

async def main():
    """
    Запуск бота
    """
    print("="*60)
    print("🚀 ТЕСТ 1: МИНИМАЛЬНЫЙ БОТ")
    print("="*60)
    print("Бот запущен. Отправьте ему команду /start")
    print("Или просто напишите любое сообщение")
    print("-"*60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print("📊 ИТОГОВАЯ СТАТИСТИКА ТЕСТА")
        print("="*60)
        
        if request_times:
            avg_all = sum(request_times) / len(request_times) * 1000
            min_all = min(request_times) * 1000
            max_all = max(request_times) * 1000
            print(f"Всего запросов: {len(request_times)}")
            print(f"Среднее время: {avg_all:.2f}мс")
            print(f"Минимальное:   {min_all:.2f}мс")
            print(f"Максимальное:  {max_all:.2f}мс")
        else:
            print("Не было ни одного запроса /start")