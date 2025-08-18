#!/usr/bin/env python3
"""
ОБНОВЛЕННЫЙ МОДУЛЬ УВЕДОМЛЕНИЙ С НАДЕЖНЫМ ПЛАНИРОВЩИКОМ
Заменяет ненадежную библиотеку schedule на threading.Timer
"""

import threading
import time
import pytz
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
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
class TimerTask:
    """Задача для выполнения по таймеру"""
    target_time: datetime  # Точное время выполнения в UTC
    user_ids: List[str]    # ID пользователей для уведомления
    local_info: str        # Информация о локальном времени для логов
    timer: threading.Timer # Сам таймер


class NotificationSchedulerV2:
    """
    Обновленная система планирования уведомлений с надежным таймером
    
    Основные улучшения:
    1. Заменен ненадежный schedule на threading.Timer
    2. Точное выполнение задач в секунду
    3. Подробное логирование всех операций
    4. Автоматическое планирование на следующий день
    """
    
    def __init__(self, 
                 user_loader: Callable[[], List[NotificationUser]],
                 notification_sender: Callable[[List[str]], None]):
        """
        Инициализация надежного планировщика
        
        Args:
            user_loader: Функция для загрузки пользователей из БД
            notification_sender: Функция для отправки уведомлений
        """
        self.user_loader = user_loader
        self.notification_sender = notification_sender
        self.active_tasks: Dict[str, TimerTask] = {}
        self.is_running = False
        
        logger.info("🔧 NotificationSchedulerV2 инициализирован (надежная версия)")
    
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
            timezone_str: Временная зона (например, "Asia/Almaty")
            
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
    
    def calculate_delay_to_time(self, utc_time: str) -> tuple:
        """
        Рассчитывает задержку в секундах до конкретного UTC времени
        
        Args:
            utc_time: Время UTC в формате "HH:MM"
            
        Returns:
            (delay_seconds, target_datetime) или (None, None) при ошибке
        """
        try:
            # Парсим время
            target_time = datetime.strptime(utc_time, "%H:%M").time()
            
            # Получаем текущее время UTC
            now_utc = datetime.now(pytz.UTC)
            
            # Создаем target datetime на сегодня
            target_datetime = datetime.combine(now_utc.date(), target_time)
            target_datetime = pytz.UTC.localize(target_datetime)
            
            # Если время уже прошло, планируем на завтра
            if target_datetime <= now_utc:
                target_datetime += timedelta(days=1)
                logger.info(f"⏭️ Время {utc_time} UTC уже прошло, планируем на завтра")
            
            # Рассчитываем задержку
            delay = (target_datetime - now_utc).total_seconds()
            
            logger.info(f"⏰ Планируем выполнение через {delay:.1f} сек ({target_datetime.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
            
            return delay, target_datetime
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета задержки для {utc_time}: {e}")
            return None, None
    
    def create_notification_task(self, user_ids: List[str], local_info: str, task_id: str):
        """Создает функцию задачи для выполнения по таймеру"""
        def execute_notification():
            logger.info(f"🎯 ВЫПОЛНЕНИЕ уведомлений (task_id: {task_id})")
            logger.info(f"📤 Отправляем {len(user_ids)} пользователям")
            logger.info(f"🌍 Локальная информация: {local_info}")
            
            try:
                # Отправляем уведомления
                self.notification_sender(user_ids)
                logger.info(f"✅ Уведомления отправлены успешно (task_id: {task_id})")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомлений (task_id: {task_id}): {e}")
            
            finally:
                # Удаляем выполненную задачу из активных
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]
                    logger.debug(f"🗑️ Задача {task_id} удалена из активных")
        
        return execute_notification
    
    def schedule_notifications(self):
        """Настраивает планировщик на основе текущих пользователей"""
        try:
            logger.info("🔄 Настройка надежного планировщика уведомлений...")
            
            # Очищаем старые задачи
            self.clear_all_tasks()
            
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
            
            # Создаем таймеры для каждой группы
            current_utc = datetime.now(pytz.UTC)
            scheduled_count = 0
            
            for utc_time, group_data in utc_groups.items():
                # Рассчитываем задержку
                delay, target_datetime = self.calculate_delay_to_time(utc_time)
                
                if delay is None:
                    logger.error(f"❌ Не удалось запланировать группу {utc_time}")
                    continue
                
                # Информация для логов
                local_info_str = ", ".join(group_data["local_info"])
                user_ids = group_data["user_ids"]
                
                # Создаем уникальный ID задачи
                task_id = f"{utc_time}_{len(self.active_tasks)}"
                
                # Создаем функцию задачи
                task_function = self.create_notification_task(user_ids, local_info_str, task_id)
                
                # Создаем таймер
                timer = threading.Timer(delay, task_function)
                timer.daemon = True  # Daemon timer завершится с основным процессом
                
                # Создаем объект задачи
                task = TimerTask(
                    target_time=target_datetime,
                    user_ids=user_ids,
                    local_info=local_info_str,
                    timer=timer
                )
                
                # Сохраняем задачу
                self.active_tasks[task_id] = task
                
                # Запускаем таймер
                timer.start()
                scheduled_count += 1
                
                # Логируем статус
                utc_dt = datetime.strptime(utc_time, "%H:%M").time()
                current_time = current_utc.time()
                
                if utc_dt > current_time:
                    status = "🟢 БУДУЩЕЕ"
                else:
                    status = "🔴 ПРОШЕДШЕЕ (завтра)"
                
                logger.info(f"⏰ {utc_time} UTC - {len(user_ids)} пользователей {status}")
                logger.debug(f"   Локальные времена: {local_info_str}")
                logger.info(f"🔧 Таймер {task_id} запущен (выполнится в {target_datetime.strftime('%H:%M:%S')})")
            
            logger.info(f"🎯 Настроено {scheduled_count} надежных таймеров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки планировщика: {e}")
    
    def clear_all_tasks(self):
        """Очищает все активные задачи"""
        logger.info(f"🧹 Очищаем {len(self.active_tasks)} активных задач")
        
        for task_id, task in self.active_tasks.items():
            task.timer.cancel()
            logger.debug(f"❌ Таймер {task_id} отменен")
        
        self.active_tasks.clear()
    
    def start_scheduler(self):
        """Запускает планировщик"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return
        
        # Настраиваем планировщик
        self.schedule_notifications()
        
        # Отмечаем как запущенный
        self.is_running = True
        
        logger.info("🚀 Надежный планировщик уведомлений запущен")
    
    def stop_scheduler(self):
        """Останавливает планировщик"""
        self.is_running = False
        self.clear_all_tasks()
        logger.info("⏹️ Планировщик уведомлений остановлен")
    
    def reload_scheduler(self):
        """Перезагружает настройки планировщика"""
        logger.info("🔄 Перезагрузка надежного планировщика...")
        self.schedule_notifications()
        logger.info("✅ Планировщик перезагружен")
    
    def get_status(self) -> Dict:
        """Возвращает текущий статус планировщика"""
        now_utc = datetime.now(pytz.UTC)
        
        active_tasks = []
        for task_id, task in self.active_tasks.items():
            if task.target_time > now_utc:
                remaining = (task.target_time - now_utc).total_seconds()
                active_tasks.append({
                    "task_id": task_id,
                    "target_time": task.target_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "remaining_seconds": int(remaining),
                    "user_count": len(task.user_ids),
                    "local_info": task.local_info
                })
        
        return {
            "is_running": self.is_running,
            "active_tasks": len(self.active_tasks),
            "upcoming_tasks": len(active_tasks),
            "current_utc_time": now_utc.strftime("%H:%M:%S"),
            "tasks": active_tasks
        }
    
    def get_next_notifications(self) -> List[Dict]:
        """Возвращает список ближайших уведомлений"""
        notifications = []
        
        for task_id, task in self.active_tasks.items():
            notifications.append({
                "next_run": task.target_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "task_info": f"Task {task_id}: {len(task.user_ids)} users"
            })
        
        # Сортируем по времени выполнения
        notifications.sort(key=lambda x: x["next_run"])
        return notifications