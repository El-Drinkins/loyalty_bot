# 📸 Проект: Бот для программы лояльности фототехники

**Дата последнего обновления:** 17 апреля 2026  
**GitHub:** https://github.com/El-Drinkins/loyalty_bot  
**Новый сервер (основной):** 85.137.251.207 (Cloud4box, Нидерланды)  
**Старый сервер (резервный):** 194.67.102.115 (Reg.ru)  
**Бот:** @Take_a_picBot

---

## 🚀 1. БЫСТРЫЕ КОМАНДЫ (НА НОВОМ СЕРВЕРЕ)

```bash
# Подключение к новому серверу
ssh root@85.137.251.207

# Статус бота
systemctl status telegram-bot.service

# Перезапуск после обновлений
systemctl restart telegram-bot.service

# Логи в реальном времени
journalctl -u telegram-bot.service -f

# Веб-админка
systemctl status telegram-bot-web.service
# Открыть в браузере: http://85.137.251.207:8000/admin/
# Пароль: admin123

# Клиентская веб-версия
# http://85.137.251.207:8000/client/

loyalty_bot/
├── app/
│   ├── handlers/                         # Обработчики команд Telegram
│   │   ├── start.py                      # Регистрация, приветствие, капча, номер телефона
│   │   ├── menu.py                       # Главное меню (баланс, история, помощь)
│   │   ├── referral.py                   # Реферальная система
│   │   ├── referral_codes.py             # Управление реферальными ссылками (админ)
│   │   ├── invite.py                     # Приглашение друзей
│   │   ├── captcha.py                    # Генерация и проверка капчи
│   │   ├── social_verification.py        # Добавление Instagram и VK
│   │   ├── admin_commands.py             # Админ-команды (/admin, /stats, /users, /blacklist)
│   │   ├── admin_review.py               # Модерация заявок в боте
│   │   └── storm.py                      # Защита от массовых регистраций
│   │
│   ├── models/                           # Модели базы данных (SQLAlchemy)
│   │   ├── __init__.py                   # Экспорт всех моделей
│   │   ├── base.py                       # Базовый класс, подключение к БД
│   │   ├── user.py                       # Пользователи, баланс, верификация, пароль
│   │   ├── referral.py                   # Реферальные связи и коды
│   │   ├── transaction.py                # Транзакции, логи
│   │   ├── catalog.py                    # Категории, бренды, модели техники
│   │   ├── rental.py                     # Аренда техники
│   │   ├── security.py                   # Заявки на регистрацию, настройки защиты
│   │   └── web_auth.py                   # Сессии, коды восстановления (для веб-версии)
│   │
│   ├── web/                              # Веб-админка и клиентская часть (FastAPI)
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI приложение
│   │   ├── deps.py                       # Зависимости (БД, шаблоны, require_auth)
│   │   ├── middleware.py                 # AuthMiddleware для админки
│   │   ├── routers/                      # Роутеры веб-админки и клиентской части
│   │   │   ├── __init__.py
│   │   │   ├── auth_routes.py            # Страница входа в админку
│   │   │   ├── main_routes.py            # Главная страница, карточки клиентов
│   │   │   ├── points_routes.py          # Начисление/списание баллов
│   │   │   ├── stats_routes.py           # Общая статистика
│   │   │   ├── admin_routes.py           # Логи админов, черный список
│   │   │   ├── user_routes.py            # Управление пользователями, фин. статистика
│   │   │   ├── api_routes.py             # API для AJAX-запросов
│   │   │   ├── search_routes.py          # Поиск клиентов
│   │   │   ├── mailing_routes.py         # Рассылка сообщений
│   │   │   ├── admin_review_routes.py    # Модерация заявок (веб)
│   │   │   ├── web_client_routes.py      # Веб-версия для клиентов (вход, профиль)
│   │   │   └── catalog/                  # Каталог техники
│   │   │       ├── __init__.py
│   │   │       ├── base_routes.py        # Главная каталога
│   │   │       ├── category_routes.py    # Управление категориями
│   │   │       ├── brand_routes.py       # Управление брендами
│   │   │       ├── model_routes.py       # Управление моделями
│   │   │       ├── rental_routes.py      # Управление арендами
│   │   │       └── stats_routes.py       # Статистика каталога
│   │   │
│   │   ├── templates/                    # HTML-шаблоны (Jinja2)
│   │   │   ├── base.html                 # Базовый шаблон админки
│   │   │   ├── index.html                # Главная страница админки
│   │   │   ├── users.html                # Список пользователей
│   │   │   ├── stats.html                # Общая статистика
│   │   │   ├── spent_stats.html          # Статистика списаний
│   │   │   ├── earned_stats.html         # Статистика начислений
│   │   │   ├── admin_logs.html           # Журнал действий админов
│   │   │   ├── user_logs.html            # Логи пользователей
│   │   │   ├── blacklist.html            # Черный список
│   │   │   ├── search.html               # Поиск клиентов
│   │   │   ├── mailing.html              # Рассылка сообщений
│   │   │   ├── admin/                    # Шаблоны модерации
│   │   │   │   ├── review_dashboard.html # Дашборд модерации
│   │   │   │   ├── review_rejected.html  # Отклонённые заявки
│   │   │   │   └── review_settings.html  # Настройки защиты
│   │   │   ├── client/                   # Карточка клиента (админка)
│   │   │   │   ├── base_client.html
│   │   │   │   ├── main_info.html
│   │   │   │   ├── operations.html
│   │   │   │   ├── controls.html
│   │   │   │   ├── blacklist.html
│   │   │   │   └── danger_zone.html
│   │   │   ├── catalog/                  # Шаблоны каталога (10 файлов)
│   │   │   └── web_client/               # Веб-версия для клиентов
│   │   │       ├── base.html
│   │   │       ├── index.html
│   │   │       ├── friends.html
│   │   │       ├── history.html
│   │   │       ├── regulations.html
│   │   │       ├── profile.html
│   │   │       └── auth/
│   │   │           ├── login.html
│   │   │           ├── telegram_auth.html
│   │   │           └── reset_password.html
│   │   │
│   │   └── public/                       # Статические файлы веб-версии
│   │       ├── css/
│   │       │   └── style.css
│   │       └── js/
│   │           └── script.js
│   │
│   ├── keyboards.py                      # Клавиатуры для бота
│   ├── middleware.py                     # BlacklistMiddleware, UserLoggingMiddleware
│   ├── notifications.py                  # Отправка уведомлений через Telegram API
│   ├── utils.py                          # Вспомогательные функции
│   ├── config.py                         # Настройки через Pydantic
│   ├── bot.py                            # Точка входа (запуск бота)
│   └── __init__.py
│
├── backup/                               # Скрипты бэкапа
│   ├── backup.sh                         # Создание дампа базы
│   ├── upload_to_yandex.sh               # Отправка на Яндекс.Диск
│   ├── send_to_old_server.sh             # Отправка на старый сервер
│   └── yandex_token.txt                  # Токен Яндекс.Диска
│
├── backups/                              # Папка с бэкапами (создаётся автоматически)
│
├── .env                                  # Переменные окружения (НЕ в Git!)
├── requirements.txt                      # Зависимости Python
├── cron_jobs.txt                         # Расписание бэкапов
├── migrate_*.py                          # Скрипты миграции базы данных
└── telegram-bot.service                  # systemd сервис для бота
└── telegram-bot-web.service              # systemd сервис для веб-админки

BOT_TOKEN=8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA
DATABASE_URL=postgresql+asyncpg://loyalty_user:Pa@localhost:5432/loyalty
ADMIN_IDS=[271186601]
WELCOME_BONUS=200
REFERRAL_BONUS=100
POINTS_VALID_DAYS=365
PROXY_URL=

Администраторы
Telegram ID: 271186601 (Яна)

Пароль веб-админки
Пароль: 4Ue768k3u! (хранится в app/web/routers/auth_routes.py)

sudo -u postgres psql -d loyalty

Пользователь БД
Имя: loyalty_user

Пароль: Pa

Основные таблицы
users — пользователи

referrals — реферальные связи

referral_codes — реферальные коды

transactions — операции с баллами

rentals — аренды

categories, brands, models — каталог техники

registration_requests — заявки на регистрацию

user_sessions — сессии веб-версии

password_reset_codes — коды восстановления

telegram_auth_codes — коды входа через Telegram

💾 5. БЭКАПЫ (НАСТРОЕНЫ)
Расписание (cron)
Время	Действие
3:00	Создание бэкапа на новом сервере
3:05	Отправка на Яндекс.Диск
3:10	Отправка на старый сервер (Reg.ru)
15:00	Дополнительный бэкап
15:05	Отправка на Яндекс.Диск
Команды для бэкапов
bash
# Ручное создание бэкапа
/root/loyalty_bot/backup/backup.sh

# Ручная отправка на Яндекс.Диск
/root/loyalty_bot/backup/upload_to_yandex.sh

# Ручная отправка на старый сервер
/root/loyalty_bot/backup/send_to_old_server.sh

# Просмотр бэкапов
ls -la /root/loyalty_bot/backups/

# Просмотр логов бэкапов
cat /root/loyalty_bot/backups/backup.log
Папки бэкапов
На новом сервере: /root/loyalty_bot/backups/

На Яндекс.Диске: папка app/Take_a_picBackup/

На старом сервере: /root/loyalty_bot_backup.sql.gz

🖥️ 6. УПРАВЛЕНИЕ СЕРВИСАМИ
Бот
bash
systemctl status telegram-bot      # статус
systemctl start telegram-bot       # запуск
systemctl stop telegram-bot        # остановка
systemctl restart telegram-bot     # перезапуск
systemctl enable telegram-bot      # автозапуск
Веб-админка
bash
systemctl status telegram-bot-web      # статус
systemctl start telegram-bot-web       # запуск
systemctl stop telegram-bot-web        # остановка
systemctl restart telegram-bot-web     # перезапуск
systemctl enable telegram-bot-web      # автозапуск
Логи
bash
# Логи бота в реальном времени
journalctl -u telegram-bot.service -f

# Логи веб-админки в реальном времени
journalctl -u telegram-bot-web.service -f

# Последние 50 строк логов бота
journalctl -u telegram-bot.service -n 50 --no-pager

🌐 7. ВЕБ-ИНТЕРФЕЙСЫ
Админка
URL: http://85.137.251.207:8000/admin/

Пароль: admin123

Клиентская веб-версия
URL: http://85.137.251.207:8000/client/


🔧 8. НАСТРОЙКА SWAP (ВАЖНО!)
На сервере создан swap-файл 4 ГБ:

bash
# Проверка
free -h

# Должно быть: Swap: 4.0Gi
Команды для управления swap
bash
# Отключить swap
swapoff -a

# Включить swap
swapon -a

# Удалить старый swap-файл
rm -f /swapfile /swapfile2 /swapfile.old

9. ОБНОВЛЕНИЕ КОДА (ЧЕРЕЗ GIT)
На локальном компьютере
bash
cd C:\Users\Яна\Desktop\Loyalty_bot
git add .
git commit -m "Описание изменений"
git push
На сервере
bash
ssh root@85.137.251.207
cd /root/loyalty_bot
git pull
systemctl restart telegram-bot
systemctl restart telegram-bot-web

 10. СТАРЫЙ СЕРВЕР (REG.RU) — РЕЗЕРВНЫЙ
IP: 194.67.102.115

Статус: бот остановлен, код не обновляется

Назначение: резервное хранилище копий базы данных

При переключении на старый сервер:

ssh root@194.67.102.115
cd /root/loyalty_bot
git pull
gunzip -c /root/loyalty_bot_backup.sql.gz | sudo -u postgres psql loyalty
systemctl start telegram-bot
systemctl start telegram-bot-web

11. ИЗВЕСТНЫЕ ПРОБЛЕМЫ
Проблема	Статус	Решение
Нестабильный SSH на новом сервере	⚠️ Не решено	Возможно, проблема у провайдера Cloud4box
Обрывы соединения с ботом	⚠️ Частично решено	Добавлен swap 4 ГБ, но может требовать мониторинга
Память сервера	✅ Решено	Swap 4 ГБ активен

12. КОНТАКТЫ
Поддержка Cloud4box: через личный кабинет

Telegram администратора: @el_drinkins

 13. ПОСЛЕДНИЕ ИЗМЕНЕНИЯ
17.04.2026 — Создан swap-файл 4 ГБ

14.04.2026 — Перенос бота на сервер Cloud4box (Нидерланды)

14.04.2026 — Настройка бэкапов на Яндекс.Диск и старый сервер

10.04.2026 — Настройка веб-версии для клиентов

09.04.2026 — Добавлена финансовая статистика клиента

09.04.2026 — Добавлено выпадающее меню статусов аренд

