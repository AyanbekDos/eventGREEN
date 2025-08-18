# Настройка EventGREEN Bot для Cloudflare Workers

## Обзор решения

Создана универсальная система уведомлений, которая автоматически выбирает подходящий планировщик в зависимости от окружения:

- **Локальная разработка**: Использует `threading.Timer` для точного планирования
- **Cloudflare Workers**: Использует cron triggers для планирования уведомлений

## Архитектура

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│   Python Bot        │    │  Notification        │    │  Cloudflare Workers │
│   (основной)        │    │  Adapter             │    │  (планировщик)      │
├─────────────────────┤    ├──────────────────────┤    ├─────────────────────┤
│ • Обработка команд  │    │ • Автоопределение    │    │ • Cron triggers     │
│ • Управление меню   │ -> │   окружения          │ -> │ • HTTP endpoints    │
│ • Google Sheets API │    │ • Универсальный API  │    │ • Отправка через    │
│ • Пользовательский  │    │ • Workers/Local      │    │   Telegram API      │
│   интерфейс         │    │   совместимость      │    │                     │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘
```

## Файлы системы

### 1. `notification_adapter.py` 
Универсальный адаптер, автоматически выбирающий планировщик:
- Определяет окружение (Workers vs Local)
- Предоставляет единый API для планирования
- Поддерживает fallback для локальной разработки

### 2. `notification_scheduler_workers.py`
Workers-совместимый планировщик:
- Генерирует cron expressions из времени уведомлений
- Создает JSON конфигурацию для Workers
- Поддерживает ручное выполнение уведомлений

### 3. `cloudflare_worker_example.js`
Пример Cloudflare Worker:
- Обрабатывает cron triggers
- HTTP API для ручного управления
- Интеграция с Telegram Bot API

## Настройка для локальной разработки

### 1. Установка зависимостей
```bash
# Активируем виртуальное окружение
source venv/bin/activate

# Устанавливаем зависимости
pip install loguru pytz python-telegram-bot
```

### 2. Запуск бота
```bash
# Бот автоматически определит локальное окружение
python run_bot.py
```

## Настройка для Cloudflare Workers

### 1. Установка Wrangler CLI
```bash
npm install -g wrangler
wrangler login
```

### 2. Генерация конфигурации Workers
```bash
# Запускаем Python скрипт для генерации конфигурации
python -c "
from notification_adapter import create_notification_adapter
from run_bot import EventGREENBot

# Создаем бота и генерируем конфигурацию Workers
bot = EventGREENBot()
adapter = create_notification_adapter(
    user_loader=bot._load_notification_users,
    notification_sender=bot._send_notifications_async,
    force_workers=True
)
adapter.schedule_notifications()
print('Конфигурация Workers сохранена в /tmp/workers_notifications.json')
"
```

### 3. Создание wrangler.toml
```toml
name = "eventgreen-notifications"
compatibility_date = "2023-10-30"

[env.production.vars]
TELEGRAM_BOT_TOKEN = "your_bot_token_here"
GOOGLE_SHEETS_API_KEY = "your_sheets_api_key"

# Cron triggers будут добавлены автоматически
[[triggers.crons]]
cron = "15 20 * * *"  # 20:15 UTC для примера

[[triggers.crons]]
cron = "0 12 * * *"   # 12:00 UTC для примера
```

### 4. Развертывание Worker
```bash
# Копируем worker код
cp cloudflare_worker_example.js worker.js

# Развертываем
wrangler deploy
```

## API интерфейс

### Endpoints Cloudflare Worker

#### `GET /health`
Проверка состояния Worker
```json
{
  "status": "ok",
  "timestamp": "2025-08-17T17:18:58.000Z",
  "notifications_count": 2
}
```

#### `POST /notifications/trigger`
Ручной запуск уведомления
```json
{
  "notification_id": "notification_09_53"
}
```

#### `GET /notifications/status`
Статус системы уведомлений
```json
{
  "notifications_count": 2,
  "cron_triggers_count": 2,
  "notifications": { ... },
  "current_utc": "2025-08-17T17:18:58.000Z"
}
```

## Интеграция с основным ботом

### В `run_bot.py`:
```python
# Импорт универсального адаптера
from notification_adapter import create_notification_adapter

# В классе EventGREENBot
def __init__(self):
    # ... другая инициализация ...
    
    # Универсальная система уведомлений (автоматически выбирает планировщик)
    self.notification_adapter = create_notification_adapter(
        user_loader=self._load_notification_users,
        notification_sender=self._send_notifications_async
    )

# Использование
def start_bot(self):
    self.notification_adapter.start_scheduler()
    self.application.run_polling()
```

## Переменные окружения

### Для локальной разработки:
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export GEMINI_API_KEY="your_gemini_key"
export ADMIN_TELEGRAM_ID="your_admin_id"
```

### Для Cloudflare Workers:
```bash
# Устанавливаем через wrangler
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put GOOGLE_SHEETS_API_KEY
```

## Мониторинг и отладка

### Команды бота для проверки:
- `/scheduler_status` - статус планировщика
- `/test_notifications` - тестовая отправка
- `/notifications HH:MM timezone` - настройка времени

### Логи Cloudflare Workers:
```bash
# Просмотр логов в реальном времени
wrangler tail

# Просмотр логов в дашборде
# https://dash.cloudflare.com -> Workers -> Logs
```

## Автоматическое обновление конфигурации

Для автоматического обновления cron triggers при изменении настроек пользователей:

1. Python бот генерирует новую конфигурацию
2. Конфигурация загружается в Cloudflare KV или отправляется через API
3. Worker автоматически подхватывает новые настройки

## Преимущества решения

✅ **Универсальность**: Работает локально и в Workers  
✅ **Автоматическое определение**: Не требует ручной настройки окружения  
✅ **Обратная совместимость**: Поддерживает старый API  
✅ **Масштабируемость**: Cloudflare Workers обрабатывают любое количество пользователей  
✅ **Надежность**: Cron triggers гарантированно выполняются  
✅ **Простота развертывания**: Минимальная настройка для Workers

## Миграция с существующей системы

1. Заменить импорт в `run_bot.py`:
   ```python
   # Старый код
   from notification_scheduler_v2 import NotificationSchedulerV2
   
   # Новый код  
   from notification_adapter import create_notification_adapter
   ```

2. Обновить инициализацию:
   ```python
   # Старый код
   self.notification_scheduler = NotificationSchedulerV2(...)
   
   # Новый код
   self.notification_adapter = create_notification_adapter(...)
   ```

3. Запустить тест для проверки:
   ```bash
   python test_notification_adapter.py
   ```

4. Развернуть Worker для продакшен использования

## Troubleshooting

### Проблема: Worker не выполняет cron
**Решение**: Проверить правильность cron expression и настройки wrangler.toml

### Проблема: Локальный планировщик не работает
**Решение**: Проверить доступность threading module и активность venv

### Проблема: Уведомления не отправляются
**Решение**: Проверить TELEGRAM_BOT_TOKEN и права бота на отправку сообщений