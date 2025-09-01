# 🔧 Исправление SSH деплоя для GitHub Actions

## Проблема
SSH ключ в GitHub Actions не работает:
- `ssh: no key found` 
- `ssh: unable to authenticate`

## Решение 1: Проверить формат SSH ключа

SSH ключ в GitHub Secrets должен быть в формате OpenSSH:
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABFwAAAAdzc2gtcn...
...
-----END OPENSSH PRIVATE KEY-----
```

## Решение 2: Создать новый SSH ключ

### На локальной машине:
```bash
# Генерируем новый SSH ключ
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/eventgreen_deploy

# Получаем приватный ключ (для GitHub Secrets)
cat ~/.ssh/eventgreen_deploy

# Получаем публичный ключ (для сервера)
cat ~/.ssh/eventgreen_deploy.pub
```

### На DigitalOcean сервере:
```bash
# Добавляем публичный ключ в authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..." >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### В GitHub Secrets:
- `DO_SSH_KEY` = содержимое ~/.ssh/eventgreen_deploy (приватный ключ)
- `DO_HOST` = IP адрес DigitalOcean сервера  
- `DO_USER` = имя пользователя на сервере
- `PROJECT_PATH` = путь к проекту на сервере

## Решение 3: Альтернативный деплой

Если SSH не работает, можно использовать:
1. DigitalOcean App Platform
2. Docker Registry + webhook
3. Ручной деплой через SSH

## Быстрая проверка SSH

Тест подключения с локальной машины:
```bash
ssh -i ~/.ssh/eventgreen_deploy user@your-server-ip "echo 'SSH работает!'"
```