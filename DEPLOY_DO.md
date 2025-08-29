# 🚀 Деплой EventGREEN Bot v4 на DigitalOcean Droplet

## 📋 Что нужно сделать (пошаговый гайд для чайника)

### ЭТАП 1: Создание Droplet на DigitalOcean

#### 1.1 Заходим на DigitalOcean
1. Идем на https://www.digitalocean.com/
2. Логинимся или регистрируемся
3. Нажимаем **"Create"** → **"Droplets"**

#### 1.2 Настройка Droplet
1. **Choose an image**: Ubuntu 24.04 (x64) LTS
2. **Choose Size**: 
   - Basic plan → Regular 
   - **$12/месяц** (2GB RAM, 1 vCPU, 50GB SSD) ✅
   - Или **$18/месяц** (2GB RAM, 2 vCPUs, 60GB SSD) для большей производительности
3. **Choose a datacenter region**: 
   - Frankfurt (для Европы/России)
   - New York (для США)
4. **Authentication**: 
   - Выбираем **"SSH keys"**
   - Жмем **"New SSH Key"**

#### 1.3 Создание SSH ключа
**На Windows:**
```bash
# Открываем PowerShell/Git Bash
ssh-keygen -t rsa -b 4096 -c "your-email@example.com"
# Жмем Enter, Enter, Enter (без пароля)
cat ~/.ssh/id_rsa.pub
# Копируем весь вывод
```

**На Mac/Linux:**
```bash
ssh-keygen -t rsa -b 4096 -c "your-email@example.com" 
cat ~/.ssh/id_rsa.pub
# Копируем весь вывод
```

5. Вставляем скопированный ключ в поле на DigitalOcean
6. **Hostname**: `eventgreen-bot` (любое имя)
7. Жмем **"Create Droplet"**

### ЭТАП 2: Подготовка сервера

#### 2.1 Подключение к серверу
```bash
# IP адрес появится на странице дроплета
ssh root@YOUR_DROPLET_IP
```

#### 2.2 Первичная настройка
```bash
# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем нужные пакеты
apt install -y git curl htop ufw

# Настраиваем файрвол
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
```

#### 2.3 Создание пользователя (безопасность)
```bash
# Создаем пользователя
adduser ubuntu
usermod -aG sudo ubuntu

# Копируем SSH ключи
mkdir -p /home/ubuntu/.ssh
cp ~/.ssh/authorized_keys /home/ubuntu/.ssh/
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/authorized_keys
```

#### 2.4 Установка Docker
```bash
# Переключаемся на пользователя ubuntu
su - ubuntu

# Устанавливаем Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Устанавливаем Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# ВАЖНО: Перелогиниваемся для применения группы docker
exit
ssh ubuntu@YOUR_DROPLET_IP
```

### ЭТАП 3: Деплой проекта

#### 3.1 Клонируем репозиторий
```bash
git clone https://github.com/YOUR_USERNAME/eventGREEN_v4.git
cd eventGREEN_v4
```

#### 3.2 Настройка переменных окружения
```bash
# Копируем пример
cp .env.example .env

# Редактируем файл
nano .env
```

Заполняем в .env:
```bash
TELEGRAM_BOT_TOKEN=ваш_токен_от_botfather
GEMINI_API_KEY=ваш_ключ_gemini
ADMIN_TELEGRAM_ID=ваш_telegram_id
# Остальные переменные по необходимости
```

#### 3.3 Загружаем секретные файлы
**С локального компьютера:**
```bash
# Загружаем файлы на сервер
scp credentials.json ubuntu@YOUR_DROPLET_IP:~/eventGREEN_v4/
scp service.json ubuntu@YOUR_DROPLET_IP:~/eventGREEN_v4/
```

#### 3.4 Запуск бота
```bash
# На сервере запускаем деплой
./deploy.sh
```

### ЭТАП 4: Настройка GitHub Actions

#### 4.1 Создание секретов в GitHub
1. Идем в ваш репозиторий на GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Жмем **"New repository secret"** для каждого:

**Обязательные секреты:**
```
DO_HOST = IP_адрес_вашего_дроплета
DO_USER = ubuntu
DO_SSH_KEY = содержимое_файла_~/.ssh/id_rsa (приватный ключ!)
PROJECT_PATH = /home/ubuntu/eventGREEN_v4
ENV_FILE_CONTENT = содержимое_вашего_.env_файла
CREDENTIALS_JSON_CONTENT = содержимое_credentials.json
SERVICE_JSON_CONTENT = содержимое_service.json
```

#### 4.2 Как получить SSH приватный ключ
**На Windows/Mac/Linux:**
```bash
cat ~/.ssh/id_rsa
```
Копируем ВЕСЬ вывод (включая -----BEGIN и -----END строки)

### ЭТАП 5: Проверка и мониторинг

#### 5.1 Проверяем работу
```bash
# На сервере проверяем статус
docker-compose ps
docker-compose logs -f
```

#### 5.2 Делаем коммит для тестирования CI/CD
```bash
# На локальном компьютере
git add .
git commit -m "🚀 Migrate to DigitalOcean Droplet"
git push origin main
```

## 💰 Стоимость сравнения

| Параметр | AWS Lightsail | DigitalOcean |
|----------|---------------|--------------|
| **Цена** | $12/месяц | $12/месяц |
| **RAM** | 2GB | 2GB |
| **vCPU** | 2 | 1-2 |
| **Storage** | 60GB SSD | 50GB SSD |
| **Transfer** | 3TB | 2TB |

**ИТОГ:** Практически одинаково! 💯

## 🔧 Команды для управления

```bash
# Просмотр логов
docker-compose logs -f

# Перезапуск
docker-compose restart

# Остановка
docker-compose down

# Обновление кода
git pull
docker-compose build --no-cache
docker-compose up -d

# Мониторинг ресурсов
htop
df -h
free -h
```

## 🚨 Устранение проблем

### Бот не запускается
```bash
# Проверяем логи
docker-compose logs

# Проверяем .env файл
cat .env

# Проверяем секретные файлы
ls -la credentials.json service.json
```

### Проблемы с GitHub Actions
1. Проверьте все секреты в GitHub
2. Убедитесь что IP адрес правильный
3. Проверьте SSH подключение вручную

### Нет места на диске
```bash
# Очистка Docker
docker system prune -a
docker volume prune

# Проверка места
df -h
```

## ✅ Преимущества DigitalOcean

- 🚀 Быстрее разворачивается
- 💻 Лучший интерфейс управления  
- 📊 Более детальная статистика
- 🔧 Больше возможностей настройки
- 💰 Та же цена что AWS

**Готово! Ваш бот теперь крутится на DigitalOcean!** 🎉