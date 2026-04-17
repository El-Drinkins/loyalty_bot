#!/bin/bash

# ==========================================
# Скрипт отправки бэкапа на Яндекс.Диск
# ==========================================

# Настройки
BACKUP_DIR="/root/loyalty_bot/backups"
TOKEN_FILE="/root/loyalty_bot/backup/yandex_token.txt"
LOG_FILE="$BACKUP_DIR/backup.log"

# Проверяем, существует ли файл с токеном
if [ ! -f "$TOKEN_FILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Файл с токеном не найден: $TOKEN_FILE" >> "$LOG_FILE"
    exit 1
fi

# Читаем токен
YANDEX_TOKEN=$(cat "$TOKEN_FILE")

# Находим самый свежий бэкап
LATEST_BACKUP=$(ls -t $BACKUP_DIR/loyalty_*.sql.gz 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Нет бэкапов для отправки" >> "$LOG_FILE"
    exit 1
fi

BACKUP_NAME=$(basename "$LATEST_BACKUP")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Отправляем $BACKUP_NAME на Яндекс.Диск..." >> "$LOG_FILE"

# Отправляем файл на Яндекс.Диск
curl -s -X PUT \
    -H "Authorization: OAuth $YANDEX_TOKEN" \
    --upload-file "$LATEST_BACKUP" \
    "https://cloud-api.yandex.net/v1/disk/resources/upload?path=app:/$BACKUP_NAME&overwrite=true" \
    | grep -q "error"

if [ $? -eq 0 ]; then
    # Если есть ошибка, пробуем создать папку
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Создаём папку на Яндекс.Диске..." >> "$LOG_FILE"
    curl -s -X PUT \
        -H "Authorization: OAuth $YANDEX_TOKEN" \
        "https://cloud-api.yandex.net/v1/disk/resources?path=app:/&overwrite=false"
    
    # Повторная отправка
    curl -s -X PUT \
        -H "Authorization: OAuth $YANDEX_TOKEN" \
        --upload-file "$LATEST_BACKUP" \
        "https://cloud-api.yandex.net/v1/disk/resources/upload?path=app:/$BACKUP_NAME&overwrite=true" \
        > /dev/null 2>&1
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Бэкап отправлен на Яндекс.Диск: $BACKUP_NAME" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Бэкап отправлен на Яндекс.Диск: $BACKUP_NAME" >> "$LOG_FILE"
fi