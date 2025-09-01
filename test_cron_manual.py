#!/usr/bin/env python3
"""
Ручной тест CRON функции для проверки уведомлений
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from bot import EventGREENBot

async def test_cron_manually():
    """Ручной тест CRON функции"""
    print("🧪 РУЧНОЙ ТЕСТ CRON ФУНКЦИИ")
    print("=" * 40)
    
    try:
        # Создаем бот
        bot = EventGREENBot()
        
        print("🔧 Бот создан, запускаем send_daily_notifications...")
        
        # Запускаем функцию ежедневных уведомлений
        await bot.send_daily_notifications()
        
        print("✅ CRON тест завершен успешно")
        
    except Exception as e:
        print(f"❌ Ошибка в CRON тесте: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_cron_manually())