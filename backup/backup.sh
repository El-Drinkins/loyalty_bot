#!/bin/bash

# ==========================================
# Скрипт резервного копирования базы данных
# ==========================================

# Настройки
DB_NAME="loyalty"
DB_USER="postgres"
BACKUP_DIR="/root/loyalty_bot/backups"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/loyalty_$DATE.sql.gz"
LOG_FILE="$BACKUP_DIR/backup.log"
DAYS_TO_KEEP=30

# Создаём папку для бэкапов, если её нет
mkdir -p "$BACKUP_DIR"

# Логируем начало
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Начинаем резервное копирование..." >> "$LOG_FILE"

# Создаём дамп базы данных
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Создаём дамп базы данных..." >> "$LOG_FILE"
sudo -u $DB_USER pg_dump $DB_NAME | gzip > "$BACKUP_FILE"

# Проверяем, успешно ли создался файл
if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Бэкап создан: $BACKUP_FILE (размер: $FILE_SIZE)" >> "$LOG_FILE"
    
    # Удаляем старые бэкапы (старше DAYS_TO_KEEP дней)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Удаляем бэкапы старше $DAYS_TO_KEEP дней..." >> "$LOG_FILE"
    find "$BACKUP_DIR" -name "loyalty_*.sql.gz" -type f -mtime +$DAYS_TO_KEEP -delete
    
    # Считаем, сколько осталось файлов
    COUNT=$(find "$BACKUP_DIR" -name "loyalty_*.sql.gz" -type f | wc -l)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Всего бэкапов на сервере: $COUNT" >> "$LOG_FILE"
    
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Ошибка: бэкап не создан!" >> "$LOG_FILE"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========================================" >> "$LOG_FILE"