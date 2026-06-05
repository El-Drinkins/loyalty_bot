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

# Получаем URL для загрузки
UPLOAD_URL=$(curl -s -H "Authorization: OAuth $YANDEX_TOKEN" \
    "https://cloud-api.yandex.net/v1/disk/resources/upload?path=app:/Take_a_picBackup/$BACKUP_NAME&overwrite=true" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('href',''))" 2>/dev/null)

if [ -n "$UPLOAD_URL" ]; then
    # Загружаем файл
    curl -s -T "$LATEST_BACKUP" "$UPLOAD_URL"
    
    # Проверяем, что файл появился на диске
    CHECK=$(curl -s -H "Authorization: OAuth $YANDEX_TOKEN" \
        "https://cloud-api.yandex.net/v1/disk/resources?path=app:/Take_a_picBackup/$BACKUP_NAME")
    
    if echo "$CHECK" | grep -q '"name"'; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Бэкап отправлен: $BACKUP_NAME" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Ошибка отправки: $BACKUP_NAME" >> "$LOG_FILE"
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Не удалось получить URL для загрузки" >> "$LOG_FILE"
fi