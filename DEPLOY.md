# 🚀 Инструкция по развертыванию EventGREEN Bot

## 📋 Обзор

EventGREEN Bot - это Telegram бот для управления личными базами клиентов с событиями, который работает на Cloudflare Workers. Бот автоматически обрабатывает VCF файлы, использует AI для фильтрации событий и создает персональные Google Sheets таблицы.

## 🔧 Предварительные требования

### 1. Установите необходимые инструменты
```bash
# Node.js 18+ (рекомендуется 20+)
node --version

# Wrangler CLI
npm install -g wrangler

# Python 3.12+ (для разработки и тестирования)
python --version
```

### 2. Создайте аккаунты и получите API ключи

#### Telegram Bot
1. Найдите @BotFather в Telegram
2. Создайте бота: `/newbot`
3. Сохраните токен бота

#### Google Cloud Platform
1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Включите Google Sheets API и Google Drive API
3. Создайте Service Account и скачайте JSON ключ
4. Создайте мастер-таблицу Google Sheets и дайте доступ Service Account

#### Google AI (Gemini)
1. Получите API ключ в [Google AI Studio](https://aistudio.google.com/app/apikey)

#### Cloudflare Workers
1. Зарегистрируйтесь на [Cloudflare](https://cloudflare.com/)
2. Авторизуйтесь: `wrangler auth login`

## 📦 Установка и настройка

### 1. Клонирование проекта
```bash
git clone <repository-url>
cd eventgreen-bot
```

### 2. Установка зависимостей
```bash
# Python зависимости (для разработки)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Node.js зависимости (для деплоя)
npm install
```

### 3. Настройка переменных окружения
```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Отредактируйте .env файл
nano .env
```

Заполните следующие переменные:
- `TELEGRAM_BOT_TOKEN` - токен вашего Telegram бота
- `MASTER_SHEET_ID` - ID мастер Google Sheets таблицы
- `GEMINI_API_KEY` - ключ Google AI API
- `ADMIN_USER_ID` - ваш Telegram ID (опционально)

### 4. Настройка Service Account
```bash
# Поместите service.json в корень проекта
# Этот файл содержит ключи Google Cloud Service Account
```

## 🧪 Тестирование

### 1. Локальное тестирование компонентов
```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Тестируйте VCF обработку
python vcf_normalizer.py

# Тестируйте AI фильтрацию
python ai_event_filter.py

# Тестируйте Google Sheets
python src/google_sheets_manager.py

# Запустите все тесты
python -m pytest tests/ -v
```

### 2. Локальный запуск бота
```bash
# Запуск в режиме polling (для тестирования)
python src/telegram_bot.py
```

## 🌐 Развертывание на Cloudflare Workers

### 1. Настройка секретов
```bash
# Установите секретные переменные
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put MASTER_SHEET_ID  
wrangler secret put GEMINI_API_KEY
wrangler secret put ADMIN_USER_ID
wrangler secret put CRON_SECRET

# Установите содержимое service.json как строку
wrangler secret put SERVICE_ACCOUNT_JSON
# Вставьте содержимое service.json файла как одну строку
```

### 2. Настройка webhook Telegram
```bash
# Замените YOUR_WORKER_URL на реальный URL вашего worker
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://YOUR_WORKER_URL.workers.dev/webhook"}'
```

### 3. Деплой
```bash
# Разверните worker
wrangler deploy

# Проверьте статус
wrangler tail --format=pretty
```

### 4. Проверка работы
```bash
# Проверьте health check
curl https://YOUR_WORKER_URL.workers.dev/health

# Проверьте webhook Telegram
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

## ⚙️ Настройка домена (опционально)

### 1. Добавьте домен в Cloudflare
1. Добавьте ваш домен в Cloudflare Dashboard
2. Обновите DNS записи

### 2. Настройте маршрутизацию
```bash
# Добавьте маршрут
wrangler route add "bot.yourdomain.com/*" eventgreen-bot

# Обновите webhook URL
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://bot.yourdomain.com/webhook"}'
```

## 📊 Мониторинг и логирование

### 1. Просмотр логов
```bash
# Реальные логи worker
wrangler tail --format=pretty

# Метрики Cloudflare
# Посетите Cloudflare Dashboard > Workers > Analytics
```

### 2. Health Check
```bash
# Проверка состояния системы
curl https://YOUR_WORKER_URL.workers.dev/health | jq .
```

### 3. Тестирование CRON
```bash
# Ручной запуск CRON задачи (для тестирования)
curl -X POST https://YOUR_WORKER_URL.workers.dev/cron \
  -H "CF-Cron: true"
```

## 🛠️ Обслуживание

### 1. Обновление кода
```bash
# Обновите код
git pull origin main

# Переразверните
wrangler deploy
```

### 2. Обновление секретов
```bash
# Обновите секреты при необходимости
wrangler secret put TELEGRAM_BOT_TOKEN
```

### 3. Масштабирование
- Cloudflare Workers автоматически масштабируется
- Для больших нагрузок рассмотрите увеличение лимитов CPU и памяти

## 🔧 Устранение неисправностей

### Частые проблемы

#### 1. Бот не отвечает на сообщения
```bash
# Проверьте webhook
curl "https://api.telegram.org/bot$TOKEN/getWebhookInfo"

# Проверьте логи
wrangler tail
```

#### 2. CRON не выполняется
- Проверьте triggers в `wrangler.toml`
- Убедитесь, что worker развернут
- Проверьте логи: `wrangler tail`

#### 3. Google Sheets ошибки
- Проверьте права доступа Service Account
- Убедитесь, что API включены в Google Cloud
- Проверьте корректность `SERVICE_ACCOUNT_JSON`

#### 4. AI обработка не работает
- Проверьте `GEMINI_API_KEY`
- Убедитесь, что API квоты не исчерпаны
- Проверьте логи на ошибки AI

### Полезные команды
```bash
# Просмотр конфигурации
wrangler whoami

# Просмотр секретов (названия)
wrangler secret list

# Удаление секрета
wrangler secret delete SECRET_NAME

# Откат к предыдущей версии
wrangler rollback
```

## 📈 Оптимизация производительности

### 1. Кэширование
- Используйте KV хранилище для кэширования частых запросов
- Настройте TTL для кэша

### 2. Батчинг
- Система автоматически оптимизирует размер батчей
- Для больших VCF файлов включается адаптивная обработка

### 3. Мониторинг
- Следите за CPU и памятью в Cloudflare Analytics
- Настройте алерты для критических ошибок

## 🔐 Безопасность

### 1. Секреты
- Никогда не коммитьте секреты в git
- Используйте `wrangler secret` для безопасного хранения
- Регулярно ротируйте API ключи

### 2. Webhook безопасность
- Рассмотрите добавление webhook secret для Telegram
- Используйте HTTPS для всех запросов

## 📞 Поддержка

### Логи и диагностика
```bash
# Детальные логи
wrangler tail --format=json

# Статус системы
curl https://YOUR_WORKER_URL.workers.dev/health
```

### Контакты
- GitHub Issues: [Ссылка на issues]
- Email: support@eventgreen.com
- Telegram: @eventgreen_support

## 📄 Лицензия

MIT License - см. файл LICENSE для подробностей.