#!/usr/bin/env python3
"""
АДАПТЕР ДЛЯ УВЕДОМЛЕНИЙ - УНИВЕРСАЛЬНЫЙ ИНТЕРФЕЙС
Автоматически выбирает подходящий планировщик в зависимости от окружения
"""

import os
import asyncio
from typing import List, Callable, Dict
from loguru import logger
from dataclasses import dataclass


@dataclass
class NotificationUser:
    """Пользователь для системы уведомлений"""
    telegram_id: str
    username: str
    notification_time: str  # "HH:MM" или "disabled"
    timezone: str          # "Asia/Almaty"
    status: str           # "trial", "pro", "expired"


@dataclass
class NotificationConfig:
    """Конфигурация системы уведомлений"""
    workers_mode: bool = False
    fallback_to_local: bool = True
    webhook_url: str = ""
    environment: str = "local"  # "local", "workers", "development"


class NotificationAdapter:
    """
    Универсальный адаптер для системы уведомлений
    Автоматически выбирает подходящий планировщик
    """
    
    def __init__(self, 
                 user_loader: Callable,
                 notification_sender: Callable,
                 config: NotificationConfig = None):
        """
        Инициализация адаптера
        
        Args:
            user_loader: Функция загрузки пользователей
            notification_sender: Функция отправки уведомлений
            config: Конфигурация системы уведомлений
        """
        self.user_loader = user_loader
        self.notification_sender = notification_sender
        self.config = config or self._detect_environment()
        self.scheduler = None
        
        logger.info(f"🔍 Определено окружение: {self.config.environment} (workers_mode: {self.config.workers_mode})")
        self._initialize_scheduler()
        
        logger.info(f"🔧 NotificationAdapter инициализирован (режим: {self.config.environment})")
    
    def _detect_environment(self) -> NotificationConfig:
        """Автоматическое определение окружения"""
        
        # Проверяем переменные окружения Cloudflare Workers
        is_workers = (
            os.getenv('CF_WORKER') == 'true' or
            os.getenv('CLOUDFLARE_WORKER') == 'true' or
            'cloudflare' in os.getenv('ENVIRONMENT', '').lower() or
            os.getenv('WORKERS_MODE') == 'true'
        )
        
        # Проверяем наличие threading
        try:
            import threading
            has_threading = True
        except ImportError:
            has_threading = False
        
        if is_workers or not has_threading:
            environment = "workers"
            workers_mode = True
            logger.info("🌍 Обнаружено окружение Cloudflare Workers")
        else:
            environment = "local"
            workers_mode = False
            logger.info("🖥️ Обнаружено локальное окружение")
        
        return NotificationConfig(
            workers_mode=workers_mode,
            fallback_to_local=not is_workers,
            environment=environment
        )
    
    def _initialize_scheduler(self):
        """Инициализирует подходящий планировщик"""
        try:
            if self.config.workers_mode:
                # Используем Workers-совместимый планировщик
                from notification_scheduler_workers import NotificationSchedulerWorkers
                self.scheduler = NotificationSchedulerWorkers(
                    user_loader=self.user_loader,
                    notification_sender=self.notification_sender,
                    workers_mode=True
                )
                logger.info("✅ Инициализирован Workers-планировщик")
                
            else:
                # Пытаемся использовать локальный планировщик с threading
                try:
                    from notification_scheduler_v2 import NotificationSchedulerV2
                    self.scheduler = NotificationSchedulerV2(
                        user_loader=self.user_loader,
                        notification_sender=self.notification_sender
                    )
                    logger.info("✅ Инициализирован локальный планировщик V2")
                    
                except ImportError as e:
                    logger.warning(f"⚠️ Локальный планировщик недоступен: {e}")
                    if self.config.fallback_to_local:
                        # Fallback к Workers планировщику в локальном режиме
                        from notification_scheduler_workers import NotificationSchedulerWorkers
                        self.scheduler = NotificationSchedulerWorkers(
                            user_loader=self.user_loader,
                            notification_sender=self.notification_sender,
                            workers_mode=False
                        )
                        logger.info("✅ Fallback к Workers-планировщику")
                    else:
                        raise
        
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации планировщика: {e}")
            raise
    
    def schedule_notifications(self):
        """Настраивает планировщик уведомлений"""
        if not self.scheduler:
            logger.error("❌ Планировщик не инициализирован")
            return False
        
        try:
            self.scheduler.schedule_notifications()
            
            # Для Workers режима генерируем конфигурацию
            if self.config.workers_mode and hasattr(self.scheduler, 'save_workers_config'):
                config_path = self.scheduler.save_workers_config()
                logger.info(f"💾 Конфигурация Workers сохранена: {config_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки планировщика: {e}")
            return False
    
    def start_scheduler(self):
        """Запускает планировщик уведомлений"""
        if not self.scheduler:
            logger.error("❌ Планировщик не инициализирован")
            return False
        
        try:
            if hasattr(self.scheduler, 'start_scheduler'):
                self.scheduler.start_scheduler()
            else:
                # Для Workers планировщика просто настраиваем
                self.schedule_notifications()
            
            logger.info("🚀 Планировщик уведомлений запущен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика: {e}")
            return False
    
    def stop_scheduler(self):
        """Останавливает планировщик уведомлений"""
        if not self.scheduler:
            return True
        
        try:
            if hasattr(self.scheduler, 'stop_scheduler'):
                self.scheduler.stop_scheduler()
            
            logger.info("⏹️ Планировщик уведомлений остановлен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика: {e}")
            return False
    
    def reload_scheduler(self):
        """Перезагружает настройки планировщика"""
        if not self.scheduler:
            logger.error("❌ Планировщик не инициализирован")
            return False
        
        try:
            if hasattr(self.scheduler, 'reload_scheduler'):
                self.scheduler.reload_scheduler()
            else:
                # Для Workers планировщика пересоздаем конфигурацию
                self.schedule_notifications()
            
            logger.info("🔄 Планировщик перезагружен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка перезагрузки планировщика: {e}")
            return False
    
    async def execute_notification(self, notification_id: str = None, user_ids: List[str] = None):
        """
        Выполняет уведомление (для webhook вызовов от Workers)
        
        Args:
            notification_id: ID уведомления (для Workers)
            user_ids: Список пользователей (для прямого вызова)
        """
        if not self.scheduler:
            logger.error("❌ Планировщик не инициализирован")
            return False
        
        try:
            if notification_id and hasattr(self.scheduler, 'execute_notification'):
                # Workers режим - выполняем по ID
                return await self.scheduler.execute_notification(notification_id)
            
            elif user_ids:
                # Прямой вызов отправки
                if asyncio.iscoroutinefunction(self.notification_sender):
                    await self.notification_sender(user_ids)
                else:
                    self.notification_sender(user_ids)
                return True
            
            else:
                logger.error("❌ Не указан notification_id или user_ids")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения уведомления: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Возвращает статус планировщика"""
        if not self.scheduler:
            return {
                "error": "Планировщик не инициализирован",
                "environment": self.config.environment,
                "workers_mode": self.config.workers_mode
            }
        
        try:
            status = self.scheduler.get_status()
            status.update({
                "adapter_environment": self.config.environment,
                "adapter_workers_mode": self.config.workers_mode
            })
            return status
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            return {"error": str(e)}
    
    def get_scheduler_type(self) -> str:
        """Возвращает тип используемого планировщика"""
        if not self.scheduler:
            return "none"
        
        scheduler_class = self.scheduler.__class__.__name__
        return f"{scheduler_class} ({self.config.environment})"
    
    def is_workers_compatible(self) -> bool:
        """Проверяет совместимость с Cloudflare Workers"""
        return self.config.workers_mode or hasattr(self.scheduler, 'workers_mode')


# Функция-фабрика для создания адаптера
def create_notification_adapter(user_loader: Callable, 
                              notification_sender: Callable,
                              force_workers: bool = False) -> NotificationAdapter:
    """
    Создает адаптер уведомлений с автоматическим определением окружения
    
    Args:
        user_loader: Функция загрузки пользователей
        notification_sender: Функция отправки уведомлений
        force_workers: Принудительно использовать Workers режим
        
    Returns:
        Настроенный адаптер уведомлений
    """
    config = NotificationConfig()
    
    if force_workers:
        config.workers_mode = True
        config.environment = "workers"
        logger.info("🔧 Принудительно включен Workers режим")
    
    return NotificationAdapter(
        user_loader=user_loader,
        notification_sender=notification_sender,
        config=config
    )