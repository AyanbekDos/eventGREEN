#!/usr/bin/env python3
"""
Google Sheets Manager для EventGREEN Bot
Управление мастер-таблицей и клиентскими таблицами
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


@dataclass
class User:
    """Структура данных пользователя из мастер-таблицы"""
    telegram_id: str
    username: str
    sheet_url: str
    status: str  # trial, pro, expired
    expires_at: str
    created_at: str
    notification_time: str = "20:15"  # время уведомлений (по умолчанию 20:15)
    timezone: str = "Asia/Almaty"     # временная зона (по умолчанию Алматы)


@dataclass
class ClientEvent:
    """Структура данных события клиента"""
    name: str
    phone: str
    event_type: str
    event_date: Optional[str]  # None для потенциальных клиентов
    note: str


class GoogleSheetsManager:
    """Менеджер для работы с Google Sheets"""
    
    def __init__(self, service_account_path: str = 'service.json'):
        """
        Инициализация менеджера Google Sheets
        
        Args:
            service_account_path: путь к файлу service account
        """
        self.service_account_path = service_account_path
        self.master_sheet_url = os.getenv('MASTER_SHEET_URL')
        self.client_template_id = os.getenv('CLIENT_TEMPLATE_ID')
        
        # Извлекаем ID мастер-таблицы из URL
        if self.master_sheet_url:
            self.master_sheet_id = self._extract_sheet_id(self.master_sheet_url)
        else:
            self.master_sheet_id = None
        
        # Инициализируем сервисы
        self.sheets_service = None
        self.drive_service = None
        self._init_services()
    
    def _extract_sheet_id(self, url: str) -> str:
        """Извлекает ID таблицы из URL"""
        try:
            # URL вида: https://docs.google.com/spreadsheets/d/ID/edit...
            return url.split('/d/')[1].split('/')[0]
        except (IndexError, AttributeError):
            logger.error(f"Не удалось извлечь ID из URL: {url}")
            return ""
    
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
            self.drive_service = build('drive', 'v3', credentials=credentials)
            
            logger.info("✅ Google API сервисы инициализированы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google API: {e}")
            raise
    
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        """
        Получает пользователя из мастер-таблицы по telegram_id
        
        Args:
            telegram_id: ID пользователя в Telegram
            
        Returns:
            User объект или None если не найден
        """
        try:
            if not self.master_sheet_id:
                logger.error("Master sheet ID не настроен")
                return None
            
            # Читаем все данные из мастер-таблицы (теперь включая G и H колонки)
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:H'  # telegram_id, username, sheet_url, status, expires_at, created_at, notification_time, timezone
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                logger.warning("Мастер-таблица пуста")
                return None
            
            # Пропускаем заголовок и ищем пользователя
            for row in values[1:]:
                if len(row) >= 6 and row[0] == telegram_id:
                    # Читаем новые поля с дефолтными значениями если пусто
                    notification_time = row[6] if len(row) > 6 and row[6].strip() else "20:15"
                    timezone = row[7] if len(row) > 7 and row[7].strip() else "Asia/Almaty"
                    
                    return User(
                        telegram_id=row[0],
                        username=row[1],
                        sheet_url=row[2],
                        status=row[3],
                        expires_at=row[4],
                        created_at=row[5],
                        notification_time=notification_time,
                        timezone=timezone
                    )
            
            logger.info(f"Пользователь {telegram_id} не найден в мастер-таблице")
            return None
            
        except HttpError as e:
            logger.error(f"Ошибка чтения мастер-таблицы: {e}")
            return None
    
    def create_new_user(self, telegram_id: str, username: str, user_sheet_url: str = None) -> Optional[User]:
        """
        Создает нового пользователя в мастер-таблице
        
        Args:
            telegram_id: ID пользователя в Telegram
            username: имя пользователя в Telegram
            user_sheet_url: URL таблицы созданной пользователем (опционально)
            
        Returns:
            User объект созданного пользователя или None при ошибке
        """
        try:
            logger.info(f"Создаю нового пользователя: {telegram_id} (@{username})")
            
            # Если URL таблицы не предоставлен, пользователь должен создать её сам
            if not user_sheet_url:
                user_sheet_url = "PENDING_USER_CREATION"
                logger.info("URL таблицы не предоставлен - пользователь должен создать таблицу сам")
            
            # Создаем запись в мастер-таблице
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            
            new_user_data = [
                telegram_id,
                username,
                user_sheet_url,
                'trial',
                expires_at,
                current_time,
                '20:15',        # дефолтное время уведомлений
                'Asia/Almaty'   # дефолтная временная зона
            ]
            
            # Добавляем строку в мастер-таблицу (теперь включая G и H колонки)
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.master_sheet_id,
                range='A:H',
                valueInputOption='USER_ENTERED',
                body={'values': [new_user_data]}
            ).execute()
            
            logger.info(f"✅ Пользователь {telegram_id} создан с пробным периодом до {expires_at}")
            
            return User(
                telegram_id=telegram_id,
                username=username,
                sheet_url=user_sheet_url,
                status='trial',
                expires_at=expires_at,
                created_at=current_time,
                notification_time='20:15',
                timezone='Asia/Almaty'
            )
            
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            return None
    
    def _copy_client_template(self, username: str) -> Optional[str]:
        """
        Копирует шаблон клиентской таблицы для нового пользователя
        
        Args:
            username: имя пользователя для названия таблицы
            
        Returns:
            ID новой таблицы или None при ошибке
        """
        try:
            if not self.client_template_id or self.client_template_id == "TEMPLATE_ID_PLACEHOLDER":
                logger.error("Client template ID не настроен")
                return None
            
            # Копируем файл
            copy_body = {
                'name': f'EventGREEN - {username} - База клиентов'
            }
            
            copied_file = self.drive_service.files().copy(
                fileId=self.client_template_id,
                body=copy_body
            ).execute()
            
            new_sheet_id = copied_file['id']
            logger.info(f"✅ Клиентская таблица скопирована для {username}: {new_sheet_id}")
            
            return new_sheet_id
            
        except HttpError as e:
            logger.error(f"Ошибка копирования шаблона: {e}")
            return None
    
    def _get_sheet_url(self, sheet_id: str) -> str:
        """
        Получает URL таблицы по её ID
        
        Args:
            sheet_id: ID таблицы
            
        Returns:
            URL таблицы
        """
        try:
            file_meta = self.drive_service.files().get(
                fileId=sheet_id,
                fields="webViewLink"
            ).execute()
            
            return file_meta.get('webViewLink', '')
            
        except Exception as e:
            logger.error(f"Ошибка получения URL таблицы {sheet_id}: {e}")
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    
    def add_clients_to_user_sheet(self, user: User, ideal_clients: List[ClientEvent], potential_clients: List[ClientEvent]) -> bool:
        """
        Добавляет клиентов в таблицу пользователя
        
        Args:
            user: пользователь
            ideal_clients: список идеальных клиентов (с датами)
            potential_clients: список потенциальных клиентов (без дат)
            
        Returns:
            True если успешно добавлено
        """
        try:
            user_sheet_id = self._extract_sheet_id(user.sheet_url)
            
            # Добавляем идеальных клиентов
            if ideal_clients:
                ideal_data = []
                for client in ideal_clients:
                    ideal_data.append([
                        client.name or 'Неизвестно',
                        client.phone,
                        client.event_type or 'Событие',
                        client.event_date or '',
                        client.note or ''
                    ])
                
                self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=user_sheet_id,
                    range="'✅ Идеальные клиенты'!A:E",
                    valueInputOption='USER_ENTERED',
                    body={'values': ideal_data}
                ).execute()
                
                logger.info(f"✅ Добавлено {len(ideal_clients)} идеальных клиентов")
            
            # Добавляем потенциальных клиентов
            if potential_clients:
                potential_data = []
                for client in potential_clients:
                    potential_data.append([
                        client.name or 'Неизвестно',
                        client.phone,
                        client.event_type or 'Потенциальный интерес',
                        '',  # Дата пустая для потенциальных
                        client.note or ''
                    ])
                
                self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=user_sheet_id,
                    range="'💡 Потенциальные клиенты'!A:E",
                    valueInputOption='USER_ENTERED',
                    body={'values': potential_data}
                ).execute()
                
                logger.info(f"✅ Добавлено {len(potential_clients)} потенциальных клиентов")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления клиентов в таблицу пользователя: {e}")
            return False
    
    def get_congratulations_map(self) -> Dict[str, str]:
        """
        Загружает карту поздравлений из мастер таблицы
        
        Returns:
            Dict[str, str]: словарь {тип_события: текст_поздравления}
        """
        try:
            # Читаем лист "Поздравления" из мастер таблицы
            range_name = "Поздравления!A2:B1000"  # Пропускаем заголовок
            
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            congratulations = {}
            
            for row in values:
                if len(row) >= 2 and row[0] and row[1]:
                    event_type = row[0].strip().lower()
                    congratulation_text = row[1].strip()
                    congratulations[event_type] = congratulation_text
            
            logger.info(f"Загружено {len(congratulations)} поздравлений")
            return congratulations
            
        except Exception as e:
            logger.error(f"Ошибка загрузки поздравлений: {e}")
            return {}
    
    def get_today_events(self, user: User) -> List[ClientEvent]:
        """
        Получает события на сегодня для пользователя
        
        Args:
            user: пользователь
            
        Returns:
            Список событий на сегодня
        """
        try:
            user_sheet_id = self._extract_sheet_id(user.sheet_url)
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Читаем лист "Идеальные клиенты"
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=user_sheet_id,
                range="'✅ Идеальные клиенты'!A:E"
            ).execute()
            
            values = result.get('values', [])
            today_events = []
            
            # Пропускаем заголовок и ищем события на сегодня
            for row in values[1:]:
                if len(row) >= 4:
                    event_date = row[3] if len(row) > 3 else ''
                    
                    # Проверяем различные форматы дат
                    if self._is_today(event_date, today):
                        today_events.append(ClientEvent(
                            name=row[0] if len(row) > 0 else 'Неизвестно',
                            phone=row[1] if len(row) > 1 else '',
                            event_type=row[2] if len(row) > 2 else 'Событие',
                            event_date=event_date,
                            note=row[4] if len(row) > 4 else ''
                        ))
            
            logger.info(f"Найдено {len(today_events)} событий на сегодня")
            return today_events
            
        except Exception as e:
            logger.error(f"Ошибка получения событий на сегодня: {e}")
            return []
    
    def _is_today(self, event_date: str, today: str) -> bool:
        """
        Проверяет соответствует ли дата события сегодняшнему дню
        
        Args:
            event_date: дата события в различных форматах
            today: сегодняшняя дата в формате YYYY-MM-DD
            
        Returns:
            True если дата сегодняшняя
        """
        if not event_date:
            return False
        
        # Пробуем разные форматы дат
        date_formats = ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y']
        
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(event_date, date_format)
                return parsed_date.strftime('%Y-%m-%d') == today
            except ValueError:
                continue
        
        return False
    
    def get_potential_clients(self, user: User) -> List[ClientEvent]:
        """
        Получает потенциальных клиентов пользователя
        
        Args:
            user: пользователь
            
        Returns:
            Список потенциальных клиентов
        """
        try:
            user_sheet_id = self._extract_sheet_id(user.sheet_url)
            
            # Читаем лист "Потенциальные клиенты"
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=user_sheet_id,
                range="'💡 Потенциальные клиенты'!A:E"
            ).execute()
            
            values = result.get('values', [])
            potential_clients = []
            
            # Пропускаем заголовок
            for row in values[1:]:
                if len(row) >= 2:  # Минимум имя и телефон
                    potential_clients.append(ClientEvent(
                        name=row[0] if len(row) > 0 else 'Неизвестно',
                        phone=row[1] if len(row) > 1 else '',
                        event_type=row[2] if len(row) > 2 else 'Потенциальный интерес',
                        event_date=None,  # Потенциальные клиенты без дат
                        note=row[4] if len(row) > 4 else ''
                    ))
            
            logger.info(f"Получено {len(potential_clients)} потенциальных клиентов")
            return potential_clients
            
        except Exception as e:
            logger.error(f"Ошибка получения потенциальных клиентов: {e}")
            return []
    
    def count_potential_clients(self, user: User) -> int:
        """
        Подсчитывает количество потенциальных клиентов
        
        Args:
            user: пользователь
            
        Returns:
            Количество потенциальных клиентов
        """
        return len(self.get_potential_clients(user))
    
    def get_all_trial_and_pro_users(self) -> List[User]:
        """
        Получает всех пользователей со статусом trial или pro для CRON рассылки
        
        Returns:
            Список пользователей
        """
        try:
            if not self.master_sheet_id:
                logger.error("Master sheet ID не настроен")
                return []
            
            # Читаем все данные из мастер-таблицы (теперь включая G и H колонки)
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:H'
            ).execute()
            
            values = result.get('values', [])
            active_users = []
            
            # Пропускаем заголовок и фильтруем по статусу
            for row in values[1:]:
                if len(row) >= 6:
                    status = row[3].lower()
                    if status in ['trial', 'pro']:
                        # Читаем новые поля с дефолтными значениями если пусто
                        notification_time = row[6] if len(row) > 6 and row[6].strip() else "20:15"
                        timezone = row[7] if len(row) > 7 and row[7].strip() else "Asia/Almaty"
                        
                        active_users.append(User(
                            telegram_id=row[0],
                            username=row[1],
                            sheet_url=row[2],
                            status=row[3],
                            expires_at=row[4],
                            created_at=row[5],
                            notification_time=notification_time,
                            timezone=timezone
                        ))
            
            logger.info(f"Найдено {len(active_users)} активных пользователей")
            return active_users
            
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []

    def update_user_notification_settings(self, telegram_id: str, notification_time: str, timezone: str) -> bool:
        """
        Обновляет настройки уведомлений пользователя в мастер-таблице
        
        Args:
            telegram_id: ID пользователя в Telegram
            notification_time: Время уведомлений в формате HH:MM
            timezone: Временная зона (например, Asia/Almaty)
            
        Returns:
            True если обновление прошло успешно, False в случае ошибки
        """
        try:
            if not self.master_sheet_id:
                logger.error("Master sheet ID не настроен")
                return False
            
            # Получаем все данные из мастер-таблицы
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.master_sheet_id,
                range='A:H'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.error("Мастер-таблица пуста")
                return False
            
            # Ищем пользователя по telegram_id
            user_row_index = None
            for i, row in enumerate(values):
                if len(row) > 0 and row[0] == telegram_id:
                    user_row_index = i + 1  # +1 для Google Sheets индексации (начинается с 1)
                    break
            
            if user_row_index is None:
                logger.error(f"Пользователь с telegram_id {telegram_id} не найден")
                return False
            
            # Обновляем колонки G (notification_time) и H (timezone)
            updates = [
                {
                    'range': f'G{user_row_index}',
                    'values': [[notification_time]]
                },
                {
                    'range': f'H{user_row_index}',
                    'values': [[timezone]]
                }
            ]
            
            # Выполняем batch update
            body = {
                'valueInputOption': 'RAW',
                'data': updates
            }
            
            self.sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.master_sheet_id,
                body=body
            ).execute()
            
            logger.info(f"Настройки уведомлений обновлены для пользователя {telegram_id}: {notification_time} {timezone}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления настроек уведомлений для {telegram_id}: {e}")
            return False


# Тестирование
if __name__ == "__main__":
    import sys
    
    # Инициализация
    try:
        sheets_manager = GoogleSheetsManager()
        print("✅ GoogleSheetsManager инициализирован")
        
        # Тест чтения мастер-таблицы
        test_user = sheets_manager.get_user_by_telegram_id('12345')
        if test_user:
            print(f"✅ Тестовый пользователь найден: {test_user.username}")
        else:
            print("⚠️  Тестовый пользователь не найден")
        
        print("🎉 Все тесты пройдены!")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        sys.exit(1)