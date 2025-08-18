# 🎉 EventGREEN Bot v4

**Умный Telegram бот для управления событиями и автоматических уведомлений**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-green)](https://www.python.org/)
[![AWS](https://img.shields.io/badge/AWS-Lightsail-orange)](https://aws.amazon.com/lightsail/)

## ✨ Возможности

🤖 **Умная обработка контактов**
- Импорт VCF файлов из телефона
- AI-фильтрация событий через Google Gemini
- Автоматическое определение типов событий

📅 **Гибкая система уведомлений**
- Индивидуальное время уведомлений для каждого пользователя
- Поддержка часовых поясов
- Надёжный планировщик на основе threading.Timer

📊 **Интеграция с Google Sheets**
- Автоматическое создание и управление таблицами
- Синхронизация данных в реальном времени
- Персональные поздравления для разных типов событий

⚡ **Production-Ready**
- Docker контейнеризация
- Автоматический деплой на AWS Lightsail
- Мониторинг и логирование
- Защита от Event Loop ошибок

## 📁 Структура проекта

### 🤖 Основные модули
- `run_bot.py` - Главный файл запуска бота
- `google_sheets_manager.py` - Работа с Google Sheets API
- `table_assignment_manager.py` - Управление пулом таблиц
- `vcf_normalizer_simple.py` - Обработка vCard файлов
- `ai_event_filter.py` - AI-анализ событий через Gemini

### ⏰ Система уведомлений
- `notification_adapter.py` - Универсальный адаптер (автовыбор планировщика)
- `notification_scheduler_v2.py` - Локальный планировщик (threading.Timer)
- `notification_scheduler_workers.py` - Cloudflare Workers планировщик (cron)

### 📦 Дополнительно
- `examples/` - Примеры конфигурации для Cloudflare Workers
- `tests/` - Тесты и отладочные скрипты

## ⚡ Быстрый старт

### 1. Установка
```bash
git clone <repository>
cd eventGREEN_v4
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Конфигурация
Создайте файл `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
ADMIN_TELEGRAM_ID=your_admin_telegram_id
```

### 3. Настройка Google Sheets API
1. Поместите `credentials.json` в корень проекта
2. Первый запуск создаст `token.json` автоматически

### 4. Запуск
```bash
python run_bot.py
```

## 🌍 Развертывание

### Локально (для разработки)
```bash
python run_bot.py
# Автоматически использует threading.Timer для точных уведомлений
```

### Cloudflare Workers (для продакшена)
```bash
# Подробные инструкции в CLOUDFLARE_WORKERS_SETUP.md
wrangler deploy
```

## 📋 Команды бота

- `/start` - Начало работы с ботом
- `/menu` - Главное меню с интерактивными кнопками
- `/import` - Импорт vCard файла
- `/today` - События на сегодня
- `/potential_clients` - Потенциальные клиенты
- `/potential_revenue` - Потенциальная прибыль
- `/notifications HH:MM timezone` - Настройка уведомлений
- `/scheduler_status` - Статус системы уведомлений

## 🔧 Настройка уведомлений

Каждый пользователь может настроить:
- 🕐 **Время уведомлений** (например: 20:15)
- 🌍 **Временную зону** (например: Asia/Almaty)
- ⏸️ **Отключение уведомлений** (notification_time = "disabled")

Примеры:
```
/notifications 09:00 Europe/Moscow
/notifications 14:30 Asia/Almaty  
/notifications disabled
```

Также доступно удобное меню через кнопку **"⏰ Настройки уведомлений"**.

## 🧪 Тестирование

```bash
# Активируем виртуальное окружение
source venv/bin/activate

# Тест системы уведомлений
python tests/test_notification_adapter.py

# Другие тесты в папке tests/
```

## 📖 Документация

- `CLOUDFLARE_WORKERS_SETUP.md` - Настройка для Cloudflare Workers
- `DEPLOY.md` - Инструкции по развертыванию
- `prd.md` - Техническое задание

## 🏗️ Архитектура

### Система уведомлений
- **Универсальный адаптер** - автоматически выбирает планировщик
- **Локальный режим** - threading.Timer для точного выполнения
- **Workers режим** - cron triggers для масштабирования
- **Индивидуальные настройки** - время и временная зона для каждого пользователя

### Обработка данных
- **vCard парсинг** - извлечение контактов из файлов
- **AI-анализ** - Gemini API для выделения событий
- **Google Sheets** - автоматическое создание и управление таблицами
- **Пул таблиц** - эффективное распределение ресурсов

## 🛠️ Требования

- Python 3.8+
- Google Sheets API credentials
- Telegram Bot Token
- Gemini API Key

## 📄 Лицензия

MIT License - проект с открытым исходным кодом.

---

<div align="center">

**EventGREEN Bot v4** - Профессиональная система управления событиями

Made with ❤️ for efficient event management

</div>