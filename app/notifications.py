import httpx
from .config import settings

async def send_telegram_notification(chat_id: int, text: str):
    """Отправляет сообщение пользователю через Telegram Bot API (без Markdown)"""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": None  # Отключаем Markdown, чтобы избежать ошибок форматирования
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                print(f"Failed to send message: {response.text}")
        except Exception as e:
            print(f"Error sending message: {e}")