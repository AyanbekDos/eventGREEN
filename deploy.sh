#!/bin/bash

# EventGREEN Bot v4 - Deploy Script для AWS Lightsail
# Использование: ./deploy.sh

set -e  # Выход при ошибке

echo "🚀 EventGREEN Bot v4 - Деплой на AWS Lightsail"
echo "================================================"

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен. Устанавливаем..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker установлен. Перелогинтесь и запустите скрипт заново"
    exit 1
fi

# Проверяем наличие Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен. Устанавливаем..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Скопируйте .env.example в .env и заполните переменные:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# Проверяем наличие credentials.json
if [ ! -f credentials.json ]; then
    echo "❌ Файл credentials.json не найден!"
    echo "📝 Загрузите файл credentials.json для Google Sheets API"
    exit 1
fi

# Проверяем наличие service.json
if [ ! -f service.json ]; then
    echo "❌ Файл service.json не найден!"
    echo "📝 Загрузите файл service.json для Google Service Account"
    exit 1
fi

echo "✅ Все необходимые файлы найдены"

# Останавливаем старые контейнеры
echo "🛑 Останавливаем старые контейнеры..."
docker-compose down || true

# Собираем образ
echo "🔨 Собираем Docker образ..."
docker-compose build --no-cache

# Запускаем контейнер
echo "🚀 Запускаем EventGREEN Bot..."
docker-compose up -d

# Проверяем статус
echo "📊 Проверяем статус контейнера..."
sleep 5
docker-compose ps

# Показываем логи
echo "📋 Последние логи:"
docker-compose logs --tail=20

echo ""
echo "✅ Деплой завершён!"
echo "📊 Мониторинг:"
echo "   docker-compose logs -f     # Просмотр логов"
echo "   docker-compose ps          # Статус контейнеров"
echo "   docker-compose restart     # Перезапуск"
echo "   docker-compose down        # Остановка"