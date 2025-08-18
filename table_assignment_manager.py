#!/usr/bin/env python3
"""
Менеджер назначения готовых таблиц пользователям
Работает с заранее созданными 37 таблицами
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()

@dataclass
class AvailableTable:
    """Структура доступной таблицы"""
    telegram_id: str  # временный ID или заглушка
    username: str     # временный username
    sheet_url: str    # URL таблицы
    status: str       # 'available' или 'assigned'
    expires_at: str   # дата истечения
    created_at: str   # дата создания

class TableAssignmentManager:
    """Менеджер назначения таблиц из готового пула"""
    
    def __init__(self, service_account_path: str = 'service.json'):
        self.service_account_path = service_account_path
        self.master_sheet_id = os.getenv('MASTER_SHEET_ID')
        self._init_services()
    
    def _init_services(self):
        """Инициализирует сервисы Google API"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_path,
                scopes=[
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            )
            
            self.sheets_service = build('sheets', 'v4', credentials=credentials)
            print("✅ Google API сервисы инициализированы")
            
        except Exception as e:
            print(f"❌ Ошибка инициализации Google API: {e}")
            raise
    
    def get_available_table(self) -> Optional[AvailableTable]:
        """
        Находит первую доступную таблицу из пула
        
        Returns:
            AvailableTable объект или None если нет доступных
        """
        try:
            if not self.master_sheet_id:
                print("❌ MASTER_SHEET_ID не настроен")
                return None
            
            # Читаем все данные из мастер-таблицы
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:F'
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                print("❌ Мастер-таблица пуста")
                return None
            
            # Ищем первую доступную таблицу (пустой telegram_id или TABLE_XX)
            for i, row in enumerate(values[1:], start=2):  # Пропускаем заголовок
                if len(row) >= 3 and row[2].startswith('https://'):  # Есть URL таблицы
                    telegram_id = row[0] if len(row) > 0 else ''
                    
                    # Таблица доступна если:
                    # 1. telegram_id пустой или начинается с TABLE_
                    # 2. Или статус 'available' 
                    is_available = (
                        not telegram_id or 
                        telegram_id.startswith('TABLE_') or
                        (len(row) > 3 and row[3] and row[3].lower() == 'available')
                    )
                    
                    if is_available:
                        return AvailableTable(
                            telegram_id=telegram_id,
                            username=row[1] if len(row) > 1 else '',
                            sheet_url=row[2],
                            status=row[3] if len(row) > 3 else '',
                            expires_at=row[4] if len(row) > 4 else '',
                            created_at=row[5] if len(row) > 5 else ''
                        ), i  # Возвращаем также номер строки
            
            print("❌ Нет доступных таблиц")
            return None, None
            
        except HttpError as e:
            print(f"❌ Ошибка чтения мастер-таблицы: {e}")
            return None, None
    
    def assign_table_to_user(self, telegram_id: str, username: str) -> Optional[str]:
        """
        Назначает доступную таблицу пользователю
        
        Args:
            telegram_id: ID пользователя в Telegram
            username: имя пользователя в Telegram
            
        Returns:
            URL назначенной таблицы или None при ошибке
        """
        try:
            print(f"🔍 Ищу доступную таблицу для {username} ({telegram_id})...")
            
            # Находим доступную таблицу
            table_info = self.get_available_table()
            if not table_info or len(table_info) != 2:
                print("❌ Нет доступных таблиц в пуле")
                return None
            
            available_table, row_number = table_info
            
            # Обновляем строку в мастер-таблице
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            
            updated_row = [
                telegram_id,              # новый telegram_id
                username,                 # новый username
                available_table.sheet_url, # тот же URL таблицы
                'trial',                  # статус пользователя
                expires_at,               # новая дата истечения
                current_time              # дата назначения
            ]
            
            # Обновляем строку
            range_name = f'A{row_number}:F{row_number}'
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.master_sheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body={'values': [updated_row]}
            ).execute()
            
            print(f"✅ Таблица назначена пользователю {username}")
            print(f"🔗 URL: {available_table.sheet_url}")
            print(f"📅 Пробный период до: {expires_at}")
            
            return available_table.sheet_url
            
        except Exception as e:
            print(f"❌ Ошибка назначения таблицы: {e}")
            return None
    
    def count_available_tables(self) -> int:
        """
        Подсчитывает количество доступных таблиц
        
        Returns:
            Количество доступных таблиц
        """
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:F'
            ).execute()
            
            values = result.get('values', [])
            count = 0
            
            for row in values[1:]:  # Пропускаем заголовок
                if len(row) >= 3 and row[2].startswith('https://'):  # Есть URL таблицы
                    telegram_id = row[0] if len(row) > 0 else ''
                    
                    # Таблица доступна если:
                    # 1. telegram_id пустой или начинается с TABLE_
                    # 2. Или статус 'available'
                    is_available = (
                        not telegram_id or 
                        telegram_id.startswith('TABLE_') or
                        (len(row) > 3 and row[3] and row[3].lower() == 'available')
                    )
                    
                    if is_available:
                        count += 1
            
            return count
            
        except Exception as e:
            print(f"❌ Ошибка подсчета таблиц: {e}")
            return 0
    
    def get_user_table_url(self, telegram_id: str) -> Optional[str]:
        """
        Получает URL таблицы пользователя
        
        Args:
            telegram_id: ID пользователя в Telegram
            
        Returns:
            URL таблицы или None если не найден
        """
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:F'
            ).execute()
            
            values = result.get('values', [])
            
            for row in values[1:]:  # Пропускаем заголовок
                if len(row) >= 3 and row[0] == telegram_id:
                    return row[2]  # sheet_url
            
            return None
            
        except Exception as e:
            print(f"❌ Ошибка поиска таблицы пользователя: {e}")
            return None

# Тестирование
if __name__ == "__main__":
    print("🧪 ТЕСТ: Table Assignment Manager")
    print("=" * 50)
    
    try:
        manager = TableAssignmentManager()
        
        # Проверяем количество доступных таблиц
        available_count = manager.count_available_tables()
        print(f"📊 Доступных таблиц: {available_count}")
        
        # Тестовое назначение (закомментировано чтобы не испортить данные)
        # test_url = manager.assign_table_to_user("TEST_USER_123", "TestUser")
        # if test_url:
        #     print(f"✅ Тестовая таблица назначена: {test_url}")
        
        print("✅ Все тесты прошли успешно")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")