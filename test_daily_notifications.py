#!/usr/bin/env python3
"""
Тест для проверки ежедневных уведомлений
Проверяет отправку уведомлений как с событиями, так и без них
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import asyncio
from bot import EventGREENBot
from google_sheets_manager import GoogleSheetsManager
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MockEvent:
    """Мок событие для тестирования"""
    name: str
    phone: str
    event_type: str
    event_date: str
    note: str


@dataclass 
class MockUser:
    """Мок пользователь для тестирования"""
    telegram_id: str
    username: str
    status: str
    sheet_url: str


class MockSheetsManager:
    """Мок Google Sheets Manager для тестирования"""
    
    def __init__(self, mock_events: List[MockEvent] = None):
        self.mock_events = mock_events or []
    
    def get_all_trial_and_pro_users(self) -> List[MockUser]:
        """Возвращает тестовых пользователей"""
        return [
            MockUser(
                telegram_id="123456789",
                username="test_user_1", 
                status="trial",
                sheet_url="https://docs.google.com/test1"
            ),
            MockUser(
                telegram_id="987654321",
                username="test_user_2",
                status="pro", 
                sheet_url="https://docs.google.com/test2"
            )
        ]
    
    def get_today_events(self, user: MockUser) -> List[MockEvent]:
        """Возвращает события на сегодня для пользователя"""
        return self.mock_events
    
    def get_congratulations_map(self) -> dict:
        """Возвращает карту поздравлений"""
        return {
            "день рождения": "🎂 Поздравляем с Днем рождения! Желаем счастья, здоровья и успехов!",
            "свадьба": "💍 Поздравляем со свадьбой! Желаем крепкой семьи и вечной любви!",
            "неизвестно": "🎉 Поздравляем с праздником!"
        }


class MockBot:
    """Мок Telegram бота для тестирования"""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_message(self, chat_id: int, text: str, parse_mode=None, disable_web_page_preview=None):
        """Сохраняет отправленное сообщение для проверки"""
        message = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        self.sent_messages.append(message)
        print(f"📤 MOCK: Отправлено сообщение в чат {chat_id}")
        print(f"📝 Текст сообщения:\n{text}")
        print("-" * 50)


class MockApplication:
    """Мок Telegram Application"""
    
    def __init__(self):
        self.bot = MockBot()


async def test_notifications_with_events():
    """Тест уведомлений с событиями"""
    print("🧪 ТЕСТ: Уведомления с событиями")
    print("=" * 50)
    
    # Создаем мок события
    mock_events = [
        MockEvent(
            name="Иван Петров",
            phone="+7 777 123 45 67", 
            event_type="день рождения",
            event_date="31.08",
            note="Важный клиент"
        ),
        MockEvent(
            name="Анна Сидорова", 
            phone="+7 777 987 65 43",
            event_type="свадьба",
            event_date="31.08",
            note="Новая клиентка"
        )
    ]
    
    # Создаем мок менеджер с событиями
    mock_sheets = MockSheetsManager(mock_events)
    
    # Создаем бот с мок компонентами
    bot = EventGREENBot()
    bot.sheets_manager = mock_sheets
    bot.application = MockApplication()
    
    # Запускаем уведомления
    await bot.send_daily_notifications()
    
    # Проверяем результат
    sent_messages = bot.application.bot.sent_messages
    print(f"✅ Отправлено {len(sent_messages)} сообщений")
    
    for msg in sent_messages:
        assert "События на сегодня" in msg['text']
        assert "Иван Петров" in msg['text']
        assert "Анна Сидорова" in msg['text']
        assert "Всего: 2 событий" in msg['text']
    
    print("✅ Тест с событиями ПРОЙДЕН")
    return True


async def test_notifications_without_events():
    """Тест уведомлений без событий"""
    print("\n🧪 ТЕСТ: Уведомления без событий")
    print("=" * 50)
    
    # Создаем мок менеджер БЕЗ событий
    mock_sheets = MockSheetsManager([])  # Пустой список событий
    
    # Создаем бот с мок компонентами
    bot = EventGREENBot()
    bot.sheets_manager = mock_sheets
    bot.application = MockApplication()
    
    # Запускаем уведомления
    await bot.send_daily_notifications()
    
    # Проверяем результат
    sent_messages = bot.application.bot.sent_messages
    print(f"✅ Отправлено {len(sent_messages)} сообщений")
    
    for msg in sent_messages:
        assert "Сегодня праздников нет" in msg['text']
        assert "Отличный день для поиска новых клиентов" in msg['text']
        assert "продуктивной работы" in msg['text']
        # Убеждаемся, что НЕТ информации о событиях
        assert "События на сегодня" not in msg['text']
        assert "Всего:" not in msg['text']
    
    print("✅ Тест без событий ПРОЙДЕН")
    return True


async def main():
    """Основная функция тестирования"""
    print("🚀 ЗАПУСК ТЕСТОВ ЕЖЕДНЕВНЫХ УВЕДОМЛЕНИЙ")
    print("=" * 60)
    
    try:
        # Тест с событиями
        await test_notifications_with_events()
        
        # Тест без событий  
        await test_notifications_without_events()
        
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("📋 Теперь уведомления отправляются по расписанию ВСЕГДА:")
        print("   • С событиями - показывает список событий")
        print("   • Без событий - показывает мотивационное сообщение")
        
    except Exception as e:
        print(f"❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Запускаем тесты
    result = asyncio.run(main())
    
    if result:
        print("\n✅ Тестирование завершено успешно")
        exit(0)
    else:
        print("\n❌ Тестирование провалено")
        exit(1)