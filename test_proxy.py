import urllib.request
import ssl

# Отключаем проверку SSL для теста
ssl._create_default_https_context = ssl._create_unverified_context

# Используем системный прокси (должен подхватиться автоматически)
url = "https://api.telegram.org/bot8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA/getMe"

try:
    response = urllib.request.urlopen(url, timeout=15)
    print("✅ Подключение успешно!")
    print(response.read().decode())
except Exception as e:
    print(f"❌ Ошибка: {e}")