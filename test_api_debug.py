import requests
import sys

print("1. Скрипт начал работу")
print("2. Импорт requests выполнен")

BOT_TOKEN = "8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA"
print("3. Токен загружен")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
print(f"4. URL сформирован: {url}")

try:
    print("5. Отправляем запрос...")
    response = requests.get(url, timeout=10)
    print("6. Запрос выполнен")
    
    print(f"7. Статус ответа: {response.status_code}")
    print("8. Текст ответа:")
    print(response.text)
    
except requests.exceptions.Timeout:
    print("❌ Таймаут: сервер не ответил за 10 секунд")
except requests.exceptions.ConnectionError:
    print("❌ Ошибка подключения: не удалось соединиться с сервером")
except Exception as e:
    print(f"❌ Другая ошибка: {type(e).__name__} - {e}")

print("9. Скрипт завершен")