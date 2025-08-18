#!/usr/bin/env python3
"""
CLOUDFLARE WORKERS СОВМЕСТИМЫЙ ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ
Заменяет threading.Timer на cron-based подход
"""

import pytz
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class NotificationUser:
    """Пользователь для системы уведомлений"""
    telegram_id: str
    username: str
    notification_time: str  # "HH:MM" или "disabled"
    timezone: str          # "Asia/Almaty"
    status: str           # "trial", "pro", "expired"


@dataclass
class ScheduledNotification:
    """Запланированное уведомление для Workers"""
    utc_time: str          # "HH:MM" время в UTC
    user_ids: List[str]    # ID пользователей
    local_info: str        # Информация о локальных временах
    cron_expression: str   # Cron выражение для Workers
    created_at: str        # Время создания


class NotificationSchedulerWorkers:
    """
    Cloudflare Workers совместимый планировщик уведомлений
    
    Основной подход:
    1. Генерирует cron expressions для каждого времени уведомлений
    2. Сохраняет конфигурацию в JSON для Workers
    3. Предоставляет fallback через webhook для локальной разработки
    """
    
    def __init__(self, 
                 user_loader: Callable[[], List[NotificationUser]],
                 notification_sender: Callable[[List[str]], None],
                 workers_mode: bool = False):
        """
        Инициализация Workers-совместимого планировщика
        
        Args:
            user_loader: Функция для загрузки пользователей
            notification_sender: Функция для отправки уведомлений
            workers_mode: True для Cloudflare Workers, False для локальной разработки
        """
        self.user_loader = user_loader
        self.notification_sender = notification_sender
        self.workers_mode = workers_mode
        self.scheduled_notifications: Dict[str, ScheduledNotification] = {}
        
        logger.info(f"🌍 NotificationSchedulerWorkers инициализирован (workers_mode: {workers_mode})")
    
    def load_users(self) -> List[NotificationUser]:
        """Загружает список пользователей с настройками уведомлений"""
        try:
            users = self.user_loader()
            logger.info(f"📊 Загружено {len(users)} пользователей")
            return users
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки пользователей: {e}")
            return []
    
    def convert_to_utc(self, local_time: str, timezone_str: str) -> Optional[str]:
        """
        Конвертирует локальное время в UTC
        
        Args:
            local_time: Время в формате "HH:MM"
            timezone_str: Временная зона
            
        Returns:
            UTC время в формате "HH:MM" или None при ошибке
        """
        try:
            # Парсим локальное время
            local_dt = datetime.strptime(local_time, "%H:%M").time()
            
            # Создаем timezone объект
            user_tz = pytz.timezone(timezone_str)
            
            # Берем сегодняшнюю дату
            today = datetime.now().date()
            
            # Создаем datetime в локальной зоне
            naive_dt = datetime.combine(today, local_dt)
            local_dt_tz = user_tz.localize(naive_dt)
            
            # Конвертируем в UTC
            utc_dt = local_dt_tz.astimezone(pytz.UTC)
            utc_time_str = utc_dt.strftime("%H:%M")
            
            logger.debug(f"🔄 {local_time} {timezone_str} -> {utc_time_str} UTC")
            return utc_time_str
            
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации времени {local_time} {timezone_str}: {e}")
            return None
    
    def time_to_cron(self, utc_time: str) -> str:
        """
        Конвертирует время UTC в cron expression
        
        Args:
            utc_time: Время в формате "HH:MM"
            
        Returns:
            Cron expression (например, "15 20 * * *" для 20:15)
        """
        try:
            hour, minute = utc_time.split(":")
            # Формат: минута час день месяц день_недели
            cron_expr = f"{minute} {hour} * * *"
            logger.debug(f"🕐 {utc_time} UTC -> cron: {cron_expr}")
            return cron_expr
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания cron для {utc_time}: {e}")
            return "0 0 * * *"  # fallback - полночь
    
    def generate_workers_config(self) -> Dict:
        """
        Генерирует конфигурацию для Cloudflare Workers
        
        Returns:
            Словарь с cron triggers и соответствующими уведомлениями
        """
        workers_config = {
            "cron_triggers": [],
            "notifications": {},
            "generated_at": datetime.now().isoformat(),
            "timezone": "UTC"
        }
        
        for notification_id, notification in self.scheduled_notifications.items():
            # Добавляем cron trigger
            cron_trigger = {
                "cron": notification.cron_expression,
                "notification_id": notification_id
            }
            workers_config["cron_triggers"].append(cron_trigger)
            
            # Добавляем данные уведомления
            workers_config["notifications"][notification_id] = asdict(notification)
        
        logger.info(f"🔧 Сгенерирована конфигурация для {len(workers_config['cron_triggers'])} cron triggers")
        return workers_config
    
    def save_workers_config(self, file_path: str = "/tmp/workers_notifications.json"):
        """Сохраняет конфигурацию Workers в файл"""
        try:
            config = self.generate_workers_config()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Конфигурация Workers сохранена: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфигурации: {e}")
            return None
    
    def schedule_notifications(self):
        """Настраивает планировщик на основе текущих пользователей"""
        try:
            logger.info("🔄 Настройка Workers-совместимого планировщика...")
            
            # Очищаем старые уведомления
            self.scheduled_notifications.clear()
            
            # Загружаем пользователей
            users = self.load_users()
            if not users:
                logger.warning("⚠️ Нет пользователей для планирования")
                return
            
            # Группируем пользователей по UTC времени
            utc_groups = {}
            
            for user in users:
                # Пропускаем отключенные уведомления
                if user.notification_time == "disabled":
                    logger.debug(f"⏸️ Пользователь {user.username} отключил уведомления")
                    continue
                
                # Пропускаем неактивных пользователей
                if user.status not in ['trial', 'pro']:
                    logger.debug(f"⏸️ Пользователь {user.username} неактивен ({user.status})")
                    continue
                
                # Конвертируем время в UTC
                utc_time = self.convert_to_utc(user.notification_time, user.timezone)
                if not utc_time:
                    continue
                
                # Группируем по UTC времени
                if utc_time not in utc_groups:
                    utc_groups[utc_time] = {
                        "user_ids": [],
                        "local_info": []
                    }
                
                utc_groups[utc_time]["user_ids"].append(user.telegram_id)
                utc_groups[utc_time]["local_info"].append(f"{user.notification_time} {user.timezone}")
                
                logger.debug(f"👤 {user.username}: {user.notification_time} {user.timezone} -> {utc_time} UTC")
            
            # Создаем запланированные уведомления
            notification_count = 0
            
            for utc_time, group_data in utc_groups.items():
                # Генерируем cron expression
                cron_expr = self.time_to_cron(utc_time)
                
                # Информация для логов
                local_info_str = ", ".join(group_data["local_info"])
                user_ids = group_data["user_ids"]
                
                # Создаем ID уведомления
                notification_id = f"notification_{utc_time.replace(':', '_')}"
                
                # Создаем запланированное уведомление
                scheduled_notification = ScheduledNotification(
                    utc_time=utc_time,
                    user_ids=user_ids,
                    local_info=local_info_str,
                    cron_expression=cron_expr,
                    created_at=datetime.now().isoformat()
                )
                
                # Сохраняем уведомление
                self.scheduled_notifications[notification_id] = scheduled_notification
                notification_count += 1
                
                logger.info(f"📅 {utc_time} UTC ({cron_expr}) - {len(user_ids)} пользователей")
                logger.debug(f"   Локальные времена: {local_info_str}")
            
            logger.info(f"🎯 Настроено {notification_count} уведомлений для Workers")
            
            # Сохраняем конфигурацию Workers
            if self.workers_mode:
                self.save_workers_config()
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки планировщика: {e}")
    
    async def execute_notification(self, notification_id: str):
        """
        Выполняет уведомление по ID (для Workers и webhook)
        
        Args:
            notification_id: ID уведомления для выполнения
        """
        if notification_id not in self.scheduled_notifications:
            logger.error(f"❌ Уведомление {notification_id} не найдено")
            return False
        
        notification = self.scheduled_notifications[notification_id]
        
        logger.info(f"🎯 ВЫПОЛНЕНИЕ уведомления: {notification_id}")
        logger.info(f"📤 Отправляем {len(notification.user_ids)} пользователям")
        logger.info(f"🌍 Локальная информация: {notification.local_info}")
        
        try:
            # Отправляем уведомления
            if asyncio.iscoroutinefunction(self.notification_sender):
                await self.notification_sender(notification.user_ids)
            else:
                self.notification_sender(notification.user_ids)
            
            logger.info(f"✅ Уведомления отправлены успешно: {notification_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомлений {notification_id}: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Возвращает текущий статус планировщика"""
        now_utc = datetime.now(pytz.UTC)
        
        scheduled_notifications = []
        for notification_id, notification in self.scheduled_notifications.items():
            scheduled_notifications.append({
                "notification_id": notification_id,
                "utc_time": notification.utc_time,
                "cron_expression": notification.cron_expression,
                "user_count": len(notification.user_ids),
                "local_info": notification.local_info
            })
        
        return {
            "workers_mode": self.workers_mode,
            "scheduled_notifications": len(self.scheduled_notifications),
            "current_utc_time": now_utc.strftime("%H:%M:%S"),
            "notifications": scheduled_notifications
        }
    
    def get_workers_wrangler_config(self) -> str:
        """
        Генерирует wrangler.toml конфигурацию для Cloudflare Workers
        
        Returns:
            Строка с конфигурацией wrangler.toml
        """
        wrangler_config = """
# Cloudflare Workers конфигурация для EventGREEN Bot
name = "eventgreen-notifications"
compatibility_date = "2023-10-30"

# Cron triggers для уведомлений
"""
        
        for notification_id, notification in self.scheduled_notifications.items():
            wrangler_config += f"""
[[triggers.crons]]
cron = "{notification.cron_expression}"
# {notification.local_info} -> {notification.utc_time} UTC
"""
        
        return wrangler_config.strip()


# Вспомогательная функция для создания планировщика
def create_scheduler(user_loader: Callable, notification_sender: Callable, workers_mode: bool = False):
    """
    Создает подходящий планировщик в зависимости от окружения
    
    Args:
        user_loader: Функция загрузки пользователей
        notification_sender: Функция отправки уведомлений  
        workers_mode: True для Cloudflare Workers
        
    Returns:
        Экземпляр планировщика
    """
    if workers_mode:
        logger.info("🌍 Создаем Workers-совместимый планировщик")
        return NotificationSchedulerWorkers(user_loader, notification_sender, workers_mode=True)
    else:
        logger.info("🖥️ Создаем локальный планировщик с fallback")
        # Импорт локального планировщика только при необходимости
        try:
            from notification_scheduler_v2 import NotificationSchedulerV2
            return NotificationSchedulerV2(user_loader, notification_sender)
        except ImportError:
            logger.warning("⚠️ Локальный планировщик недоступен, используем Workers режим")
            return NotificationSchedulerWorkers(user_loader, notification_sender, workers_mode=False)