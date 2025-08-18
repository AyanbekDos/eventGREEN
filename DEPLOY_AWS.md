# 🚀 Деплой EventGREEN Bot v4 на AWS Lightsail

## 📋 Предварительные требования

- AWS Lightsail сервер (Ubuntu 24.04 LTS)
- 2GB RAM, 2 vCPUs, 60GB SSD ($12/месяц)
- SSH доступ к серверу

## 🛠 Настройка сервера

### 1. Подключение к серверу
```bash
ssh ubuntu@your-server-ip
```

### 2. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Установка Git
```bash
sudo apt install git -y
```

## 📦 Деплой бота

### 1. Клонирование репозитория
```bash
git clone https://github.com/AyanbekDos/eventGREEN.git
cd eventGREEN
```

### 2. Настройка переменных окружения
```bash
cp .env.example .env
nano .env
```

Заполните:
- `TELEGRAM_BOT_TOKEN` - токен от @BotFather
- `GEMINI_API_KEY` - ключ Google Gemini API
- `ADMIN_TELEGRAM_ID` - ваш Telegram ID

### 3. Загрузка Google API файлов
Скопируйте на сервер файлы:
- `credentials.json` - Google Sheets API credentials
- `service.json` - Google Service Account credentials

```bash
# Используйте scp для загрузки файлов:
scp credentials.json ubuntu@your-server-ip:~/eventGREEN/
scp service.json ubuntu@your-server-ip:~/eventGREEN/
```

### 4. Запуск деплоя
```bash
./deploy.sh
```

Скрипт автоматически:
- ✅ Установит Docker и Docker Compose
- ✅ Соберёт контейнер
- ✅ Запустит бота
- ✅ Покажет логи

## 📊 Управление ботом

### Просмотр логов
```bash
docker-compose logs -f
```

### Перезапуск бота
```bash
docker-compose restart
```

### Остановка бота
```bash
docker-compose down
```

### Обновление кода
```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

## 🔒 Безопасность

### Настройка файрвола
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### Настройка автоматических обновлений
```bash
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

## 📈 Мониторинг

### Проверка статуса
```bash
docker-compose ps
docker-compose logs --tail=50
```

### Мониторинг ресурсов
```bash
htop
df -h
free -h
```

## 🚨 Устранение проблем

### Если бот не запускается
1. Проверьте логи: `docker-compose logs`
2. Проверьте .env файл
3. Проверьте Google API файлы

### Если нет уведомлений
1. Проверьте настройки планировщика в логах
2. Проверьте доступ к Google Sheets
3. Проверьте часовой пояс

## 💰 Стоимость

**AWS Lightsail $12/месяц включает:**
- 2GB RAM, 2 vCPUs
- 60GB SSD
- 3TB трафика
- Статический IP

**Итого: ~$144/год** 🎯

Отличная цена для стабильной работы бота!