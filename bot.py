#!/usr/bin/env python3
"""
Запуск EventGREEN Bot с интеграцией новых компонентов
"""

import os
import asyncio
import tempfile
import threading
import schedule
import time
import pytz
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from loguru import logger

# Импорт универсального адаптера уведомлений
from notification_adapter import create_notification_adapter, NotificationAdapter, NotificationUser

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Импортируем наши компоненты
from table_assignment_manager import TableAssignmentManager
from vcf_normalizer_simple import SimpleVCFNormalizer
from ai_event_filter import AIEventFilter
from google_sheets_manager import GoogleSheetsManager, ClientEvent

load_dotenv()

class EventGREENBot:
    """EventGREEN Bot с интеграцией системы назначения таблиц"""
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.admin_id = int(os.getenv('ADMIN_TELEGRAM_ID', 0)) or None
        
        # Инициализируем компоненты
        self.table_manager = TableAssignmentManager()
        self.vcf_normalizer = SimpleVCFNormalizer()
        self.ai_filter = AIEventFilter(self.gemini_api_key)
        self.sheets_manager = GoogleSheetsManager()
        
        # Универсальная система уведомлений (автоматически выбирает планировщик)
        self.notification_adapter = create_notification_adapter(
            user_loader=self._load_notification_users,
            notification_sender=self._send_notifications_async
        )
        
        # Состояния пользователей
        self.user_states = {}
        
        # Создаем приложение с максимальной изоляцией HTTP соединений
        from telegram.request import HTTPXRequest
        
        self.application = (
            Application.builder()
            .token(self.bot_token)
            .concurrent_updates(True)  # Разрешаем параллельную обработку
            .request(HTTPXRequest(
                connection_pool_size=8,  # Достаточный пул соединений
                connect_timeout=15,
                read_timeout=15,
                write_timeout=15,
                pool_timeout=5  # Быстрый таймаут
            ))
            .build()
        )
        self._setup_handlers()
    
    async def safe_reply(self, update: Update, text: str, **kwargs):
        """Безопасная отправка сообщений с защитой от event loop ошибок"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await update.message.reply_text(text, **kwargs)
                return True
            except Exception as e:
                error_msg = str(e)
                if "Event loop is closed" in error_msg or "RuntimeError" in error_msg:
                    logger.warning(f"Попытка {attempt + 1} отправки сообщения: {error_msg}")
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        logger.error(f"Не удалось отправить сообщение после {max_attempts} попыток")
                        return False
                else:
                    # Если это не event loop ошибка, пробрасываем дальше
                    raise e
        return False
    
    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("import", self.import_command))
        self.application.add_handler(CommandHandler("today", self.today_command))
        self.application.add_handler(CommandHandler("potential_clients", self.potential_clients_command))
        self.application.add_handler(CommandHandler("potential_revenue", self.potential_revenue_command))
        self.application.add_handler(CommandHandler("test_notifications", self.test_notifications_command))
        self.application.add_handler(CommandHandler("notifications", self.notifications_command))
        self.application.add_handler(CommandHandler("scheduler_status", self.scheduler_status_command))
        
        # Обработчики файлов и сообщений
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Глобальный обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Глобальный обработчик ошибок"""
        try:
            # Логируем ошибку
            logger.error(f"Exception while handling an update: {context.error}")
            
            # Если это обновление от пользователя
            if isinstance(update, Update) and update.effective_chat:
                error_message = (
                    "🚨 <b>Произошла непредвиденная ошибка</b>\n\n"
                    f"<code>{str(context.error)}</code>\n\n"
                    "📧 Отправьте эту ошибку администратору @aianback"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_message,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {send_error}")
                    
        except Exception as handler_error:
            logger.error(f"Error in error handler: {handler_error}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        telegram_id = str(user.id)
        username = user.username or user.first_name
        
        print(f"👤 Новый пользователь: {username} (ID: {telegram_id})")
        
        # Проверяем, есть ли пользователь в системе
        existing_user = self.sheets_manager.get_user_by_telegram_id(telegram_id)
        
        if existing_user:
            # Считаем оставшиеся дни FREE доступа
            from datetime import datetime
            try:
                expires_date = datetime.strptime(existing_user.expires_at, '%Y-%m-%d %H:%M:%S')
                days_left = (expires_date - datetime.now()).days
                days_left = max(0, days_left)  # Не показываем отрицательные дни
            except:
                days_left = 0
            
            # Пользователь уже есть
            if existing_user.status == 'trial':
                welcome_message = f"""
🎉 С возвращением, {user.first_name}!

🆓 FREE доступ: {days_left} дней осталось

Используйте /menu для просмотра функций.
"""
            else:
                welcome_message = f"""
🎉 С возвращением, {user.first_name}!

💎 PRO статус активен

Используйте /menu для просмотра функций.
"""
        else:
            # Новый пользователь - назначаем таблицу
            assigned_url = self.table_manager.assign_table_to_user(telegram_id, username)
            
            if assigned_url:
                welcome_message = f"""
🎉 Добро пожаловать в EventGREEN Bot, {user.first_name}!

🆓 FREE доступ: 30 дней

🚀 Что я умею:
• 📥 Обрабатывать VCF файлы с контактами
• 🤖 Находить события через AI
• 📊 Сохранять результаты в базу данных
• ⏰ Напоминать о событиях

Отправьте VCF файл или используйте /menu
"""
            else:
                welcome_message = f"""
😔 Извините, {user.first_name}!

❌ Сервис временно недоступен. Попробуйте позже.
"""
        
        keyboard = self._get_main_keyboard()
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        menu_text = """
🏠 <b>Главное меню EventGREEN Bot</b>

🗓 <b>Сегодня</b> - События на сегодняшний день
📥 <b>Импорт VCF</b> - Загрузить файл контактов  
💡 <b>Потенциальные клиенты</b> - База потенциальных клиентов
💰 <b>Потенциальный доход</b> - Анализ доходности

/help - Подробная справка
"""
        
        keyboard = self._get_main_keyboard()
        await update.message.reply_text(
            menu_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    
    async def import_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда импорта VCF"""
        user_id = str(update.effective_user.id)
        
        # Проверяем, есть ли пользователь в системе
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not user:
            await update.message.reply_text(
                "❌ Сначала выполните /start для регистрации в системе"
            )
            return
        
        self.user_states[user_id] = "waiting_vcf"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_import")]
        ])
        
        await update.message.reply_text(
            "📥 <b>Импорт VCF файла</b>\n\n"
            "Отправьте VCF файл с контактами.\n"
            "Файл будет обработан AI для поиска событий.\n\n"
            "<i>Максимальный размер: 20 МБ</i>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда показа событий на сегодня - thread-safe версия"""
        try:
            user_id = str(update.effective_user.id)
            
            # РАДИКАЛЬНОЕ РЕШЕНИЕ: Выполняем ВСЁ в отдельном потоке
            import concurrent.futures
            
            def execute_sheets_operations():
                """Выполняем все операции с Google Sheets в отдельном потоке"""
                try:
                    # Получаем пользователя
                    user = self.sheets_manager.get_user_by_telegram_id(user_id)
                    if not user:
                        return {"error": "user_not_found"}
                    
                    # Получаем события
                    today_events = self.sheets_manager.get_today_events(user)
                    if not today_events:
                        return {"error": "no_events"}
                    
                    # Получаем поздравления
                    congratulations_map = self.sheets_manager.get_congratulations_map()
                    
                    return {
                        "success": True,
                        "events": today_events,
                        "congratulations": congratulations_map
                    }
                    
                except Exception as e:
                    logger.error(f"Ошибка в execute_sheets_operations: {e}")
                    return {"error": f"sheets_error: {e}"}
            
            # Выполняем в executor'е для полной изоляции
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                result = await loop.run_in_executor(executor, execute_sheets_operations)
            
            # Обрабатываем результат
            if "error" in result:
                if result["error"] == "user_not_found":
                    await self.safe_reply(
                        update,
                        "❌ Сначала выполните /start для регистрации в системе"
                    )
                elif result["error"] == "no_events":
                    await self.safe_reply(
                        update,
                        "📅 На сегодня событий не найдено.\n\n"
                        "Загрузите VCF файл для добавления событий."
                    )
                else:
                    await self.safe_reply(
                        update,
                        "❌ Временная ошибка доступа к данным. Попробуйте через минуту."
                    )
                return
            
            # Формируем ответ
            today_events = result["events"]
            congratulations_map = result["congratulations"]
            
            # Формируем заголовок с датой
            from datetime import datetime
            today_date = datetime.now()
            weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
            weekday = weekdays[today_date.weekday()]
            date_str = today_date.strftime('%d.%m.%Y')
            
            response = f"🎉 <b>События на сегодня, {weekday}, {date_str}:</b>\n\n"
            response += "💡 <i>Кликайте на выделенные телефоны и поздравления для быстрого копирования</i>\n\n"
            
            for i, event in enumerate(today_events, 1):
                # Структурированный формат с полями
                name = event.name if event.name and event.name.strip() else "NULL"
                phone = event.phone if event.phone and event.phone.strip() else "NULL"
                event_type = event.event_type if event.event_type and event.event_type.strip() and event.event_type.lower() != "неизвестно" else "NULL"
                note = event.note if event.note and event.note.strip() else "NULL"
                
                # Формируем строку с явными полями
                response += f"{i}. 👤 <b>{name}</b> 📞 <code>📋 {phone}</code> 🎉 {event_type} 📝 {note}\n"
                
                # Готовое поздравление с кликабельным копированием
                event_type_lower = event.event_type.lower() if event.event_type and event.event_type.strip() else "неизвестно"
                congratulation = congratulations_map.get(event_type_lower, congratulations_map.get("неизвестно", "🎉 Поздравляем с праздником! Желаем радости и счастья! ✨"))
                
                response += f"<blockquote>{congratulation}</blockquote>\n"
            
            response += f"\n<b>Всего: {len(today_events)} событий</b>"
            
            await self.safe_reply(
                update,
                response,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Критическая ошибка в today_command: {e}")
            await self.safe_reply(
                update,
                "🚨 Произошла критическая ошибка при получении событий.\n"
                "📧 Сообщите администратору @aianback"
            )
    
    async def potential_revenue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда показа потенциального дохода"""
        user_id = str(update.effective_user.id)
        
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        
        if not user:
            await update.message.reply_text(
                "❌ Сначала выполните /start для регистрации в системе"
            )
            return
        
        # Заглушка для PRO функции
        revenue_text = f"""
💰 <b>Потенциальный доход</b>

🔒 <b>Эта функция доступна только в PRO версии</b>

В PRO версии вы получите:
• 📈 Анализ доходности каждого события
• 💵 Расчет потенциального дохода
• 📊 Статистику по типам мероприятий
• 📱 Инструменты для увеличения продаж

💎 Обновитесь до PRO для доступа к аналитике!
"""
        
        await update.message.reply_text(
            revenue_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    
    async def potential_clients_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда показа потенциальных клиентов"""
        user_id = str(update.effective_user.id)
        
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        
        if not user:
            await update.message.reply_text(
                "❌ Сначала выполните /start для регистрации в системе"
            )
            return
        
        # Заглушка для PRO функции
        clients_text = f"""
💡 <b>Потенциальные клиенты</b>

🔒 <b>Эта функция доступна только в PRO версии</b>

<b>Что такое потенциальные клиенты?</b>
Это контакты, которые AI определил как возможных клиентов, но с неточной или неполной информацией о событиях.

В PRO версии вы получите:
• 👥 Полный доступ к базе потенциальных клиентов
• ✏️ Возможность редактировать базу данных
• 🎉 Создание собственных поздравлений
• 📊 Инструменты для работы с базой

💎 Обновитесь до PRO для доступа к потенциальным клиентам!
"""
        
        await update.message.reply_text(
            clients_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        help_text = """
🆘 <b>Справка EventGREEN Bot</b>

<b>Основные команды:</b>
/start - Регистрация в системе
/menu - Главное меню
/import - Загрузить VCF файл
/today - События на сегодня
/notifications - Настройки уведомлений

<b>Как пользоваться:</b>
1️⃣ Выполните /start для начала работы
2️⃣ Отправьте VCF файл с контактами
3️⃣ AI найдет события и разделит контакты на:
   • ✅ Идеальные клиенты (с датами событий)
   • 💡 Потенциальные клиенты (неточная информация)
4️⃣ Получайте ежедневные уведомления о событиях

<b>Поддерживаемые форматы событий:</b>
• Дни рождения, юбилеи
• Свадьбы, торжества  
• Корпоративы, конференции
• И другие мероприятия

<b>Техподдержка:</b>
По всем вопросам обращайтесь: @aianback

<i>Бот работает 24/7 и обрабатывает файлы любого размера</i>
"""
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML
        )
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик документов"""
        user_id = str(update.effective_user.id)
        document = update.message.document
        
        # Проверяем, ожидаем ли VCF файл
        if self.user_states.get(user_id) != "waiting_vcf":
            await update.message.reply_text(
                "📎 Для загрузки VCF файла используйте команду /import"
            )
            return
        
        # Проверяем расширение файла
        if not document.file_name.lower().endswith('.vcf'):
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте файл с расширением .vcf"
            )
            return
        
        # Проверяем размер файла (лимит 20MB)
        if document.file_size > 20 * 1024 * 1024:
            await update.message.reply_text(
                "❌ Файл слишком большой. Максимальный размер: 20 МБ"
            )
            return
        
        # Убираем состояние ожидания
        self.user_states.pop(user_id, None)
        
        await self.process_vcf_file(update, context, document)
    
    async def process_vcf_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE, document):
        """Обработка VCF файла"""
        user = update.effective_user
        user_id = str(user.id)
        
        # Получаем пользователя из базы
        db_user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not db_user:
            await update.message.reply_text(
                "❌ Ошибка: пользователь не найден в системе. Выполните /start"
            )
            return
        
        try:
            # Сообщение о начале обработки
            progress_message = await update.message.reply_text(
                "📥 Обрабатываю VCF файл...\n⏳ Это может занять несколько минут"
            )
            
            # Скачиваем файл
            file = await context.bot.get_file(document.file_id)
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(suffix='.vcf', delete=False) as temp_file:
                await file.download_to_drive(temp_file.name)
                
                # Читаем содержимое файла
                with open(temp_file.name, 'r', encoding='utf-8') as f:
                    vcf_content = f.read()
                
                # Удаляем временный файл
                os.unlink(temp_file.name)
            
            # Обрабатываем VCF
            await progress_message.edit_text(
                "🔍 Парсинг контактов...\n⏳ Извлекаю данные из VCF"
            )
            
            # VCF нормализатор возвращает массив {combined_text, phone}
            contacts = self.vcf_normalizer.normalize_vcf(vcf_content)
            
            if not contacts:
                await progress_message.edit_text(
                    "❌ В файле не найдено контактов для обработки"
                )
                return
            
            # Сообщаем пользователю сколько контактов и что будем обрабатывать батчами
            await progress_message.edit_text(
                f"📊 Найдено контактов: {len(contacts)}\n"
                f"🤖 Начинаю AI обработку батчами...\n"
                f"⏳ Это может занять несколько минут"
            )
            
            # AI обрабатывает ВСЕ контакты (передаем полные JSON объекты как в промпте)
            ai_results = await self.ai_filter.filter_events_from_contacts(contacts)
            
            if not ai_results:
                await progress_message.edit_text(
                    "❌ AI обработка не удалась. Попробуйте позже или с другим файлом."
                )
                return
            
            # AI вернул готовые ExtractedContact объекты с телефонами
            ideal_clients_data = []
            potential_clients_data = []
            
            for ai_contact in ai_results:
                # Создаем объект для Google Sheets
                contact_dict = {
                    'name': ai_contact.name or 'Неизвестно',
                    'phone': ai_contact.phone,  # Телефон уже есть от AI
                    'event_type': ai_contact.event_type or 'Событие',
                    'event_date': ai_contact.event_date,
                    'note': ai_contact.note or ''
                }
                
                # Разделяем по наличию даты
                if ai_contact.event_date and ai_contact.event_date.strip():
                    ideal_clients_data.append(contact_dict)
                else:
                    potential_clients_data.append(contact_dict)
            
            # Преобразуем в ClientEvent объекты
            ideal_events = []
            for client in ideal_clients_data:
                ideal_events.append(ClientEvent(
                    name=client.get('name', 'Неизвестно'),
                    phone=client.get('phone', ''),
                    event_type=client.get('event_type', 'Событие'),
                    event_date=client.get('event_date', ''),
                    note=client.get('note', '')
                ))
            
            potential_events = []
            for client in potential_clients_data:
                potential_events.append(ClientEvent(
                    name=client.get('name', 'Неизвестно'),
                    phone=client.get('phone', ''),
                    event_type=client.get('event_type', 'Потенциальный интерес'),
                    event_date=None,
                    note=client.get('note', '')
                ))
            
            # Сохраняем в Google Sheets
            await progress_message.edit_text(
                f"💾 Сохраняю результаты в таблицу...\n"
                f"📊 Найдено: {len(ideal_events)} идеальных + {len(potential_events)} потенциальных клиентов"
            )
            
            success = self.sheets_manager.add_clients_to_user_sheet(
                db_user, ideal_events, potential_events
            )
            
            if success:
                # Успешный результат с полной статистикой
                result_text = f"""
✅ <b>VCF файл успешно обработан!</b>

📊 <b>ПОЛНАЯ СТАТИСТИКА:</b>
• Всего контактов в VCF: {len(contacts)}
• Обработано AI батчами: {len(contacts)}
• Найдено событий: {len(ai_results)}
• ✨ Идеальные клиенты (с датами): {len(ideal_events)}
• 💡 Потенциальные клиенты: {len(potential_events)}

💾 Данные сохранены в базу!

Используйте /today для просмотра событий на сегодня.
"""
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗓 События сегодня", callback_data="show_today")]
                ])
                
                await progress_message.edit_text(
                    result_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            else:
                await progress_message.edit_text(
                    "❌ Ошибка сохранения данных. Попробуйте позже."
                )
                
        except Exception as e:
            print(f"Ошибка обработки VCF: {e}")
            await progress_message.edit_text(
                f"❌ Ошибка обработки файла: {str(e)[:200]}...\n\n"
                "Попробуйте еще раз или обратитесь к администратору."
            )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        text = update.message.text.lower()
        
        if "сегодня" in text:
            await self.today_command(update, context)
        elif "импорт" in text or "загрузить" in text:
            await self.import_command(update, context)
        elif "потенциальные клиенты" in text:
            await self.potential_clients_command(update, context)
        elif "потенциальный доход" in text:
            await self.potential_revenue_command(update, context)
        elif "помощь" in text or "справка" in text:
            await self.help_command(update, context)
        else:
            await update.message.reply_text(
                "🤔 Не понимаю. Используйте /menu для просмотра команд."
            )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        data = query.data
        
        if data == "cancel_import":
            self.user_states.pop(user_id, None)
            await query.edit_message_text("❌ Импорт отменен.")
        
        elif data == "show_today":
            # Показываем события на сегодня
            user = self.sheets_manager.get_user_by_telegram_id(user_id)
            if user:
                today_events = self.sheets_manager.get_today_events(user)
                
                if not today_events:
                    await query.edit_message_text("📅 На сегодня событий не найдено.")
                else:
                    # Используем тот же формат что и в команде today
                    from datetime import datetime
                    today_date = datetime.now()
                    weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
                    weekday = weekdays[today_date.weekday()]
                    date_str = today_date.strftime('%d.%m.%Y')
                    
                    congratulations_map = self.sheets_manager.get_congratulations_map()
                    
                    response = f"🎉 <b>События на сегодня, {weekday}, {date_str}:</b>\n\n"
                    response += "💡 <i>Кликайте на выделенные телефоны и поздравления для быстрого копирования</i>\n\n"
                    
                    for i, event in enumerate(today_events, 1):  # Показываем ВСЕ события
                        # Структурированный формат с полями
                        name = event.name if event.name and event.name.strip() else "NULL"
                        phone = event.phone if event.phone and event.phone.strip() else "NULL"
                        event_type = event.event_type if event.event_type and event.event_type.strip() and event.event_type.lower() != "неизвестно" else "NULL"
                        note = event.note if event.note and event.note.strip() else "NULL"
                        
                        # Формируем строку с явными полями
                        response += f"{i}. 👤 <b>{name}</b> 📞 <code>📋 {phone}</code> 🎉 {event_type} 📝 {note}\n"
                        
                        # Готовое поздравление с кликабельным копированием
                        event_type_lower = event.event_type.lower() if event.event_type and event.event_type.strip() else "неизвестно"
                        congratulation = congratulations_map.get(event_type_lower, congratulations_map.get("неизвестно", "🎉 Поздравляем с праздником! Желаем радости и счастья! ✨"))
                        
                        response += f"<blockquote>{congratulation}</blockquote>\n"
                    
                    response += f"\n<b>Всего: {len(today_events)} событий</b>"
                    
                    await query.edit_message_text(response, parse_mode=ParseMode.HTML)
    
    async def test_notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для тестирования уведомлений (только для админа)"""
        user_id = str(update.effective_user.id)
        
        # Проверяем что это админ (можете добавить свой ID)
        if self.admin_id and int(user_id) != self.admin_id:
            await update.message.reply_text("❌ Эта команда доступна только администратору")
            return
        
        await update.message.reply_text("🧪 Запускаю тест ежедневных уведомлений...")
        
        try:
            await self.send_daily_notifications()
            await update.message.reply_text("✅ Тест уведомлений завершен успешно")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при тестировании: {str(e)}")
    
    async def notifications_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда настройки уведомлений"""
        user_id = str(update.effective_user.id)
        
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден. Используйте /start для регистрации.")
            return
        
        # Если есть аргументы - обрабатываем настройку
        if context.args:
            if len(context.args) == 2:
                new_time = context.args[0]
                new_timezone = context.args[1]
                
                # Валидируем время
                try:
                    datetime.strptime(new_time, "%H:%M")
                except ValueError:
                    await update.message.reply_text("❌ Неправильный формат времени. Используйте HH:MM (например, 20:15)")
                    return
                
                # Валидируем временную зону
                try:
                    pytz.timezone(new_timezone)
                except pytz.UnknownTimeZoneError:
                    await update.message.reply_text(f"❌ Неизвестная временная зона: {new_timezone}\n\n"
                                                   f"Примеры правильных зон:\n"
                                                   f"• Asia/Almaty\n"
                                                   f"• Europe/Moscow\n"
                                                   f"• Asia/Tashkent\n"
                                                   f"• Asia/Bishkek")
                    return
                
                # Обновляем настройки в Google Sheets
                try:
                    # Находим строку пользователя и обновляем
                    result = self.sheets_manager.sheets_service.spreadsheets().values().get(
                        spreadsheetId=self.sheets_manager.master_sheet_id,
                        range='A:H'
                    ).execute()
                    
                    values = result.get('values', [])
                    row_number = None
                    
                    for i, row in enumerate(values[1:], start=2):  # начинаем с 2, т.к. пропускаем заголовок
                        if len(row) >= 1 and row[0] == user_id:
                            row_number = i
                            break
                    
                    if row_number:
                        # Обновляем G и H колонки
                        self.sheets_manager.sheets_service.spreadsheets().values().update(
                            spreadsheetId=self.sheets_manager.master_sheet_id,
                            range=f'G{row_number}:H{row_number}',
                            valueInputOption='USER_ENTERED',
                            body={'values': [[new_time, new_timezone]]}
                        ).execute()
                        
                        # Перезагружаем новый планировщик
                        self.notification_adapter.reload_scheduler()
                        
                        await update.message.reply_text(
                            f"✅ Настройки уведомлений обновлены!\n\n"
                            f"🕐 Время: {new_time}\n"
                            f"🌍 Временная зона: {new_timezone}\n\n"
                            f"⚡ Планировщик перезагружен"
                        )
                    else:
                        await update.message.reply_text("❌ Не удалось найти пользователя в таблице")
                        
                except Exception as e:
                    await update.message.reply_text(f"❌ Ошибка обновления настроек: {str(e)}")
                    
            elif len(context.args) == 1 and context.args[0].lower() == "disable":
                # Отключение уведомлений
                try:
                    result = self.sheets_manager.sheets_service.spreadsheets().values().get(
                        spreadsheetId=self.sheets_manager.master_sheet_id,
                        range='A:H'
                    ).execute()
                    
                    values = result.get('values', [])
                    row_number = None
                    
                    for i, row in enumerate(values[1:], start=2):
                        if len(row) >= 1 and row[0] == user_id:
                            row_number = i
                            break
                    
                    if row_number:
                        self.sheets_manager.sheets_service.spreadsheets().values().update(
                            spreadsheetId=self.sheets_manager.master_sheet_id,
                            range=f'G{row_number}',
                            valueInputOption='USER_ENTERED',
                            body={'values': [['disabled']]}
                        ).execute()
                        
                        self.notification_adapter.reload_scheduler()
                        
                        await update.message.reply_text("✅ Уведомления отключены")
                    else:
                        await update.message.reply_text("❌ Не удалось найти пользователя в таблице")
                        
                except Exception as e:
                    await update.message.reply_text(f"❌ Ошибка отключения уведомлений: {str(e)}")
            else:
                await update.message.reply_text(
                    "❌ Неправильный формат команды\n\n"
                    "Используйте:\n"
                    "• `/notifications 20:15 Asia/Almaty` - установить время и зону\n"
                    "• `/notifications disable` - отключить уведомления"
                )
        else:
            # Показываем текущие настройки
            current_time = user.notification_time if hasattr(user, 'notification_time') else "20:15"
            current_timezone = user.timezone if hasattr(user, 'timezone') else "Asia/Almaty"
            
            if current_time == "disabled":
                status = "🔴 Отключены"
            else:
                status = f"🟢 Включены"
            
            await update.message.reply_text(
                f"⚙️ <b>Настройки уведомлений</b>\n\n"
                f"📊 Статус: {status}\n"
                f"🕐 Время: {current_time}\n"
                f"🌍 Временная зона: {current_timezone}\n\n"
                f"<b>Команды:</b>\n"
                f"• <code>/notifications 20:15 Asia/Almaty</code> - установить время\n"
                f"• <code>/notifications disable</code> - отключить\n\n"
                f"<b>Популярные временные зоны:</b>\n"
                f"• Asia/Almaty (Алматы)\n"
                f"• Europe/Moscow (Москва)\n"
                f"• Asia/Tashkent (Ташкент)\n"
                f"• Asia/Bishkek (Бишкек)",
                parse_mode=ParseMode.HTML
            )
    
    async def scheduler_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда проверки статуса планировщика"""
        user_id = str(update.effective_user.id)
        
        # Проверяем что это админ
        if self.admin_id and int(user_id) != self.admin_id:
            await update.message.reply_text("❌ Эта команда доступна только администратору")
            return
        
        try:
            status = self.notification_adapter.get_status()
            # Получаем тип планировщика для отображения
            scheduler_type = self.notification_adapter.get_scheduler_type()
            
            response = f"📊 <b>Статус планировщика уведомлений</b>\n\n"
            response += f"🔧 Планировщик: {scheduler_type}\n"
            response += f"🌍 Workers-совместимый: {'✅' if self.notification_adapter.is_workers_compatible() else '❌'}\n"
            response += f"🕐 Текущее UTC время: {status.get('current_utc_time', 'N/A')}\n\n"
            
            # Отображаем количество уведомлений
            if 'scheduled_notifications' in status:
                response += f"📅 Запланированных уведомлений: {status['scheduled_notifications']}\n"
            elif 'active_tasks' in status:
                response += f"📅 Активных задач: {status['active_tasks']}\n"
            
            # Отображаем уведомления
            if status.get('notifications'):
                response += f"\n<b>Запланированные уведомления:</b>\n"
                for notif in status['notifications'][:5]:
                    response += f"🕐 {notif['utc_time']} UTC - {notif['user_count']} польз.\n"
                    if 'cron_expression' in notif:
                        response += f"   📅 Cron: {notif['cron_expression']}\n"
            elif status.get('tasks'):
                response += f"\n<b>Активные задачи:</b>\n"
                for task in status['tasks'][:3]:
                    response += f"⏰ {task['target_time']} - {task['user_count']} польз.\n"
                    response += f"   ⏳ Осталось: {task['remaining_seconds']} сек\n"
            else:
                response += "\n⚠️ Нет запланированных уведомлений\n"
            
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения статуса: {str(e)}")
    
    def _load_notification_users(self):
        """Загружает пользователей для системы уведомлений"""
        users = self.sheets_manager.get_all_trial_and_pro_users()
        
        notification_users = []
        for user in users:
            notification_users.append(NotificationUser(
                telegram_id=user.telegram_id,
                username=user.username,
                notification_time=getattr(user, 'notification_time', '20:15'),
                timezone=getattr(user, 'timezone', 'Asia/Almaty'),
                status=user.status
            ))
        
        return notification_users
    
    def _send_notifications_async(self, user_ids):
        """Отправляет уведомления асинхронно через планировщик задач"""
        try:
            print(f"📤 Планируем отправку уведомлений для {len(user_ids)} пользователей")
            
            # НИКОГДА не создаём новые event loop'ы и не закрываем их!
            # Вместо этого используем thread-safe подход
            def run_in_thread():
                """Запускаем в отдельном потоке с собственным event loop"""
                try:
                    # Создаём новый event loop только в отдельном потоке
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    
                    # Выполняем задачу
                    new_loop.run_until_complete(self._send_notifications_to_users_impl(user_ids))
                    
                finally:
                    # Закрываем loop только в этом потоке
                    try:
                        new_loop.close()
                    except:
                        pass
                    
            # Запускаем в отдельном потоке, чтобы не влиять на основной event loop
            import threading
            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            
            print("✅ Уведомления запланированы в отдельном потоке")
            
        except Exception as e:
            print(f"❌ Ошибка планирования уведомлений: {e}")
            logger.error(f"Ошибка в _send_notifications_async: {e}")
    
    async def _send_notifications_to_users_impl(self, user_ids: list):
        """Реализация отправки уведомлений конкретным пользователям"""
        try:
            print(f"📤 Отправляем уведомления {len(user_ids)} пользователям")
            
            # Получаем всех пользователей с retry логикой для SSL ошибок
            all_users = []
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    all_users = self.sheets_manager.get_all_trial_and_pro_users()
                    break  # Успешно получили данные
                except Exception as e:
                    print(f"⚠️ Попытка {attempt + 1} получения пользователей не удалась: {e}")
                    if attempt < max_retries - 1:
                        print(f"🔄 Повторяем через 2 секунды...")
                        await asyncio.sleep(2)
                    else:
                        print("❌ Все попытки получения пользователей исчерпаны")
                        return  # Выходим, если не удалось получить данные
            
            if not all_users:
                print("⚠️ Не удалось получить список пользователей")
                return
            
            # Фильтруем только нужных пользователей
            target_users = [user for user in all_users if user.telegram_id in user_ids]
            
            for user in target_users:
                try:
                    # Получаем события на сегодня для этого пользователя с retry логикой
                    today_events = None
                    max_event_retries = 3
                    
                    for attempt in range(max_event_retries):
                        try:
                            today_events = self.sheets_manager.get_today_events(user)
                            break  # Успешно получили события
                        except Exception as e:
                            print(f"⚠️ Попытка {attempt + 1} получения событий для {user.username}: {e}")
                            if attempt < max_event_retries - 1:
                                print(f"🔄 Повторяем через 2 секунды...")
                                await asyncio.sleep(2)
                            else:
                                print(f"❌ Не удалось получить события для {user.username}")
                                today_events = []  # Пустой список если не удалось
                    
                    if today_events:
                        message = await self._format_daily_notification_async(today_events)
                        await self.application.bot.send_message(
                            chat_id=user.telegram_id,
                            text=message,
                            parse_mode=ParseMode.HTML
                        )
                        print(f"✅ Уведомление отправлено пользователю {user.username} ({len(today_events)} событий)")
                    else:
                        print(f"ℹ️ У пользователя {user.username} нет событий на сегодня")
                        
                except Exception as e:
                    print(f"❌ Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
                    continue
            
            print(f"📅 Уведомления для группы завершены ({len(target_users)} пользователей)")
            
        except Exception as e:
            print(f"💥 Ошибка в отправке групповых уведомлений: {e}")
    
    async def _format_daily_notification_async(self, today_events: list) -> str:
        """Форматирует ежедневное уведомление о событиях (асинхронная версия с retry)"""
        # Загружаем поздравления с retry логикой для SSL ошибок
        congratulations_map = {}
        max_congrat_retries = 3
        
        for attempt in range(max_congrat_retries):
            try:
                congratulations_map = self.sheets_manager.get_congratulations_map()
                break  # Успешно получили поздравления
            except Exception as e:
                print(f"⚠️ Попытка {attempt + 1} получения поздравлений: {e}")
                if attempt < max_congrat_retries - 1:
                    print(f"🔄 Повторяем через 2 секунды...")
                    await asyncio.sleep(2)
                else:
                    print("❌ Не удалось получить поздравления, используем стандартные")
                    congratulations_map = {}
        
        # Формируем заголовок с датой
        from datetime import datetime
        today_date = datetime.now()
        weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
        weekday = weekdays[today_date.weekday()]
        date_str = today_date.strftime('%d.%m.%Y')
        
        response = f"🎉 <b>События на сегодня, {weekday}, {date_str}:</b>\n\n"
        response += "💡 <i>Кликайте на выделенные телефоны и поздравления для быстрого копирования</i>\n\n"
        
        for i, event in enumerate(today_events, 1):  # Показываем ВСЕ события
            # Структурированный формат с полями
            name = event.name if event.name and event.name.strip() else "NULL"
            phone = event.phone if event.phone and event.phone.strip() else "NULL"
            event_type = event.event_type if event.event_type and event.event_type.strip() and event.event_type.lower() != "неизвестно" else "NULL"
            note = event.note if event.note and event.note.strip() else "NULL"
            
            # Формируем строку с явными полями
            response += f"{i}. 👤 <b>{name}</b> 📞 <code>📋 {phone}</code> 🎉 {event_type} 📝 {note}\n"
            
            # Готовое поздравление с кликабельным копированием
            event_type_lower = event.event_type.lower() if event.event_type and event.event_type.strip() else "неизвестно"
            congratulation = congratulations_map.get(event_type_lower, congratulations_map.get("неизвестно", "🎉 Поздравляем с праздником! Желаем радости и счастья! ✨"))
            
            response += f"<blockquote>{congratulation}</blockquote>\n"
        
        response += f"\n<b>Всего: {len(today_events)} событий</b>"
        
        return response

    def _format_daily_notification(self, today_events: list) -> str:
        """Форматирует ежедневное уведомление о событиях (синхронная версия)"""
        # Загружаем поздравления
        congratulations_map = self.sheets_manager.get_congratulations_map()
        
        # Формируем заголовок с датой
        from datetime import datetime
        today_date = datetime.now()
        weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
        weekday = weekdays[today_date.weekday()]
        date_str = today_date.strftime('%d.%m.%Y')
        
        response = f"🎉 <b>События на сегодня, {weekday}, {date_str}:</b>\n\n"
        response += "💡 <i>Кликайте на выделенные телефоны и поздравления для быстрого копирования</i>\n\n"
        
        for i, event in enumerate(today_events, 1):  # Показываем ВСЕ события
            # Структурированный формат с полями
            name = event.name if event.name and event.name.strip() else "NULL"
            phone = event.phone if event.phone and event.phone.strip() else "NULL"
            event_type = event.event_type if event.event_type and event.event_type.strip() and event.event_type.lower() != "неизвестно" else "NULL"
            note = event.note if event.note and event.note.strip() else "NULL"
            
            # Формируем строку с явными полями
            response += f"{i}. 👤 <b>{name}</b> 📞 <code>📋 {phone}</code> 🎉 {event_type} 📝 {note}\n"
            
            # Готовое поздравление с кликабельным копированием
            event_type_lower = event.event_type.lower() if event.event_type and event.event_type.strip() else "неизвестно"
            congratulation = congratulations_map.get(event_type_lower, congratulations_map.get("неизвестно", "🎉 Поздравляем с праздником! Желаем радости и счастья! ✨"))
            
            response += f"<blockquote>{congratulation}</blockquote>\n"
        
        response += f"\n<b>Всего: {len(today_events)} событий</b>"
        
        return response
    
    def _extract_name_from_combined_text(self, combined_text: str) -> str:
        """Извлекает имя из combined_text"""
        if not combined_text:
            return "Неизвестно"
        
        # Берем первые несколько слов как имя (до 3 слов)
        words = combined_text.split()
        if len(words) >= 2:
            return ' '.join(words[:2])  # Первые 2 слова
        elif len(words) == 1:
            return words[0]
        else:
            return "Неизвестно"
    
    def _get_main_keyboard(self):
        """Главная клавиатура"""
        keyboard = [
            [KeyboardButton("🗓 Сегодня"), KeyboardButton("📥 Импорт VCF")],
            [KeyboardButton("💡 Потенциальные клиенты"), KeyboardButton("💰 Потенциальный доход")],
            [KeyboardButton("⏰ Настройки уведомлений"), KeyboardButton("🆘 Помощь")]
        ]
        
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=False
        )
    
    def _get_event_emoji(self, event_type: str) -> str:
        """Возвращает эмодзи для типа события"""
        if not event_type:
            return "👤"
        
        event_lower = event_type.lower()
        
        # Дни рождения и юбилеи
        if any(word in event_lower for word in ["день рождения", "birthday", "туған күн", "юбилей"]):
            return "🎂"
        
        # Свадьбы
        if any(word in event_lower for word in ["свадьба", "wedding", "той", "кыз узату"]):
            return "💍"
        
        # Детские события
        if any(word in event_lower for word in ["тусау кесу", "крещение", "baby shower"]):
            return "👶"
        
        # Выпускные и образование
        if any(word in event_lower for word in ["выпускной", "graduation", "школ", "университет"]):
            return "🎓"
        
        # Корпоративные события
        if any(word in event_lower for word in ["корпоратив", "тимбилдинг", "retirement"]):
            return "🏢"
        
        # Праздники
        if any(word in event_lower for word in ["наурыз", "новый год", "8 марта", "23 февраля"]):
            return "🎊"
        
        # Месяцы (потенциальные клиенты)
        if any(word in event_lower for word in ["января", "февраля", "марта", "апреля", "мая", "июня", 
                                               "июля", "августа", "сентября", "октября", "ноября", "декабря"]):
            return "📅"
        
        # По умолчанию
        return "🎉"
    
    async def send_daily_notifications(self):
        """Отправка ежедневных уведомлений всем пользователям"""
        try:
            print("📅 Запуск ежедневных уведомлений...")
            
            # Получаем всех пользователей из мастер таблицы
            users = self.sheets_manager.get_all_trial_and_pro_users()
            
            for user in users:
                if not user.telegram_id or user.telegram_id == "":
                    continue
                    
                try:
                    # Получаем события на сегодня для пользователя
                    today_events = self.sheets_manager.get_today_events(user)
                    
                    # Формируем сообщение с датой (всегда отправляем уведомление)
                    from datetime import datetime
                    today_date = datetime.now()
                    weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
                    weekday = weekdays[today_date.weekday()]
                    date_str = today_date.strftime('%d.%m.%Y')
                    
                    message = "🌅 <b>Доброе утро!</b>\n\n"
                    
                    if today_events:
                        # Есть события на сегодня
                        # Загружаем поздравления для утренних уведомлений
                        congratulations_map = self.sheets_manager.get_congratulations_map()
                        
                        message += f"🎉 <b>События на сегодня, {weekday}, {date_str}:</b>\n\n"
                        message += "💡 <i>Кликайте на выделенные телефоны и поздравления для быстрого копирования</i>\n\n"
                        
                        for i, event in enumerate(today_events, 1):  # Показываем ВСЕ события
                            # Структурированный формат с полями
                            name = event.name if event.name and event.name.strip() else "NULL"
                            phone = event.phone if event.phone and event.phone.strip() else "NULL"
                            event_type = event.event_type if event.event_type and event.event_type.strip() and event.event_type.lower() != "неизвестно" else "NULL"
                            note = event.note if event.note and event.note.strip() else "NULL"
                            
                            # Формируем строку с явными полями
                            message += f"{i}. 👤 <b>{name}</b> 📞 <code>📋 {phone}</code> 🎉 {event_type} 📝 {note}\n"
                            
                            # Поздравление
                            event_type_lower = event.event_type.lower() if event.event_type and event.event_type.strip() else "неизвестно"
                            congratulation = congratulations_map.get(event_type_lower, congratulations_map.get("неизвестно", "🎉 Поздравляем с праздником!"))
                            message += f"<blockquote>{congratulation}</blockquote>\n"
                        
                        message += f"\n<b>Всего: {len(today_events)} событий</b>\n\n"
                        message += "📊 Хорошего дня и успешных продаж! 💪"
                    else:
                        # Нет событий на сегодня
                        message += f"📅 <b>Сегодня, {weekday}, {date_str}</b>\n\n"
                        message += "😌 <b>Сегодня праздников нет</b>\n\n"
                        message += "🔍 Отличный день для поиска новых клиентов!\n"
                        message += "💼 Можете заняться другими важными делами или проанализировать предстоящие события.\n\n"
                        message += "📊 Хорошего дня и продуктивной работы! 💪"
                    
                    # Отправляем уведомление (всегда)
                    await self.application.bot.send_message(
                        chat_id=int(user.telegram_id),
                        text=message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    
                    if today_events:
                        print(f"✅ Уведомление с {len(today_events)} событиями отправлено пользователю {user.telegram_id}")
                    else:
                        print(f"✅ Уведомление без событий отправлено пользователю {user.telegram_id}")
                    
                except Exception as e:
                    print(f"❌ Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
                    continue
            
            print("📅 Ежедневные уведомления завершены")
            
        except Exception as e:
            print(f"💥 Ошибка в ежедневных уведомлениях: {e}")
    
    
    def _schedule_daily_notifications(self):
        """Настройка индивидуального планировщика для каждого пользователя"""
        # Очищаем все предыдущие задачи
        schedule.clear()
        
        # Получаем всех активных пользователей
        active_users = self.sheets_manager.get_all_trial_and_pro_users()
        
        # Группируем пользователей по времени уведомлений (с учетом временных зон)
        notification_groups = {}
        
        for user in active_users:
            if user.notification_time == "disabled":
                continue
                
            try:
                # Парсим время пользователя
                user_time = datetime.strptime(user.notification_time, "%H:%M").time()
                
                # Создаем объект временной зоны
                user_tz = pytz.timezone(user.timezone)
                
                # Получаем текущее время в UTC для сравнения
                now_utc = datetime.now(pytz.UTC)
                
                # Создаем datetime для времени уведомления пользователя в его временной зоне
                today = now_utc.astimezone(user_tz).date()
                user_datetime_tz = user_tz.localize(datetime.combine(today, user_time))
                
                # Конвертируем в UTC для унифицированного планирования
                user_datetime_utc = user_datetime_tz.astimezone(pytz.UTC)
                utc_time_str = user_datetime_utc.strftime("%H:%M")
                
                # Группируем по UTC времени
                if utc_time_str not in notification_groups:
                    notification_groups[utc_time_str] = []
                notification_groups[utc_time_str].append(user.telegram_id)
                
            except Exception as e:
                print(f"❌ Ошибка обработки времени для пользователя {user.telegram_id}: {e}")
                continue
        
        # Создаем задачи для каждой группы времени
        for utc_time, user_ids in notification_groups.items():
            # Исправляем closure проблему - создаем отдельную функцию для каждой группы
            def create_notification_job(users_list):
                def job():
                    # Используем thread-safe подход как в новом методе
                    def run_in_thread():
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            new_loop.run_until_complete(self._send_notifications_to_users_impl(users_list))
                        finally:
                            try:
                                new_loop.close()
                            except:
                                pass
                    
                    import threading
                    thread = threading.Thread(target=run_in_thread, daemon=True)
                    thread.start()
                    
                return job
            
            schedule.every().day.at(utc_time).do(create_notification_job(user_ids.copy()))
            print(f"⏰ Запланированы уведомления на {utc_time} UTC для {len(user_ids)} пользователей")
        
        print(f"📅 Настроено {len(notification_groups)} временных слотов для уведомлений")
    
    def reload_notification_schedule(self):
        """Перезагружает настройки планировщика (можно вызывать из команды)"""
        print("🔄 Перезагружаем настройки планировщика...")
        self._schedule_daily_notifications()
        print("✅ Планировщик обновлен")
    
    def _run_scheduler(self):
        """Запуск планировщика в отдельном потоке"""
        # Перезагружаем настройки каждые 6 часов (на случай изменений в таблице)
        last_reload = time.time()
        reload_interval = 6 * 60 * 60  # 6 часов в секундах
        
        while True:
            schedule.run_pending()
            
            # Проверяем, нужно ли перезагрузить настройки
            current_time = time.time()
            if current_time - last_reload > reload_interval:
                print("🔄 Автоматическая перезагрузка настроек планировщика...")
                self._schedule_daily_notifications()
                last_reload = current_time
            
            time.sleep(60)  # Проверяем каждую минуту
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (меню)"""
        text = update.message.text
        user_id = str(update.effective_user.id)
        
        # Проверяем кнопки меню
        if text == "🗓 Сегодня":
            await self.today_command(update, context)
        elif text == "📥 Импорт VCF":
            await self.import_command(update, context)
        elif text == "💡 Потенциальные клиенты":
            await self.potential_clients_command(update, context)
        elif text == "💰 Потенциальный доход":
            await self.potential_revenue_command(update, context)
        elif text == "⏰ Настройки уведомлений":
            await self.notifications_menu_command(update, context)
        elif text == "🆘 Помощь":
            await self.help_command(update, context)
        else:
            # Проверяем состояние пользователя
            user_state = self.user_states.get(user_id, {})
            
            if user_state.get('state') == 'waiting_for_time':
                # Пользователь вводит время уведомлений
                await self._handle_time_input(update, context, text)
            elif user_state.get('state') == 'waiting_for_timezone':
                # Пользователь вводит временную зону
                await self._handle_timezone_input(update, context, text)
            else:
                # Проверяем если это время в формате HH:MM
                import re
                if re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', text):
                    # Если введено время, пытаемся его обработать
                    await self._handle_time_input(update, context, text)
                else:
                    # Неизвестное сообщение
                    await update.message.reply_text(
                        "❓ Используйте кнопки меню или команды.\n"
                        "Для справки нажмите 🆘 Помощь",
                        reply_markup=self._get_main_keyboard()
                    )
    
    async def notifications_menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню настроек уведомлений"""
        user_id = str(update.effective_user.id)
        
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден. Используйте /start для регистрации.")
            return
        
        # Получаем текущие настройки
        current_time = getattr(user, 'notification_time', '20:15')
        current_timezone = getattr(user, 'timezone', 'Asia/Almaty')
        
        if current_time == "disabled":
            status = "🔴 Отключены"
        else:
            status = "🟢 Включены"
        
        # Создаем inline клавиатуру
        keyboard = [
            [InlineKeyboardButton("⏰ Изменить время", callback_data="change_time")],
            [InlineKeyboardButton("🌍 Изменить зону", callback_data="change_timezone")],
            [InlineKeyboardButton("🔴 Отключить уведомления", callback_data="disable_notifications")] if current_time != "disabled" else [InlineKeyboardButton("🟢 Включить уведомления", callback_data="enable_notifications")],
            [InlineKeyboardButton("📊 Тест уведомления", callback_data="test_notification")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        response = f"⏰ <b>Настройки уведомлений</b>\n\n"
        response += f"📊 Статус: {status}\n"
        response += f"🕐 Время: {current_time}\n"
        response += f"🌍 Временная зона: {current_timezone}\n\n"
        response += f"<i>Выберите действие:</i>"
        
        await update.message.reply_text(
            response,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = str(query.from_user.id)
        
        if data == "change_time":
            # Устанавливаем состояние ожидания времени
            self.user_states[user_id] = {'state': 'waiting_for_time'}
            
            await query.edit_message_text(
                "🕐 <b>Изменение времени уведомлений</b>\n\n"
                "Отправьте новое время в формате <code>HH:MM</code>\n"
                "Например: <code>08:30</code> или <code>20:15</code>\n\n"
                "⏳ Ожидаю ввод времени...",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "change_timezone":
            await query.edit_message_text(
                "🌍 <b>Изменение временной зоны</b>\n\n"
                "Отправьте команду с новой зоной:\n"
                "<code>/notifications [время] [зона]</code>\n\n"
                "<b>Популярные зоны:</b>\n"
                "• Asia/Almaty (Алматы)\n"
                "• Europe/Moscow (Москва)\n"
                "• Asia/Tashkent (Ташкент)\n"
                "• Asia/Bishkek (Бишкек)\n\n"
                "Пример: <code>/notifications 20:15 Europe/Moscow</code>",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "disable_notifications":
            # Отключаем уведомления
            try:
                result = self.sheets_manager.sheets_service.spreadsheets().values().get(
                    spreadsheetId=self.sheets_manager.master_sheet_id,
                    range='A:H'
                ).execute()
                
                values = result.get('values', [])
                row_number = None
                
                for i, row in enumerate(values[1:], start=2):
                    if len(row) >= 1 and row[0] == user_id:
                        row_number = i
                        break
                
                if row_number:
                    self.sheets_manager.sheets_service.spreadsheets().values().update(
                        spreadsheetId=self.sheets_manager.master_sheet_id,
                        range=f'G{row_number}',
                        valueInputOption='USER_ENTERED',
                        body={'values': [['disabled']]}
                    ).execute()
                    
                    self.notification_scheduler.reload_scheduler()
                    
                    await query.edit_message_text("✅ Уведомления отключены")
                else:
                    await query.edit_message_text("❌ Ошибка: пользователь не найден")
                    
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка отключения: {str(e)}")
        
        elif data == "enable_notifications":
            await query.edit_message_text(
                "🟢 <b>Включение уведомлений</b>\n\n"
                "Используйте команду:\n"
                "<code>/notifications 20:15 Asia/Almaty</code>\n\n"
                "Замените время и зону на нужные вам",
                parse_mode=ParseMode.HTML
            )
        
        elif data == "test_notification":
            # Отправляем тестовое уведомление
            try:
                await self._send_notifications_to_users_impl([user_id])
                await query.edit_message_text("✅ Тестовое уведомление отправлено!")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка тестирования: {str(e)}")
        
        elif data == "back_to_menu":
            await query.edit_message_text("Возвращаемся в главное меню")
            await asyncio.sleep(1)
            await query.message.reply_text(
                "📱 Главное меню:",
                reply_markup=self._get_main_keyboard()
            )
    
    async def _handle_time_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, time_text: str):
        """Обработка ввода времени уведомлений"""
        user_id = str(update.effective_user.id)
        
        # Валидируем формат времени
        import re
        if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
            await update.message.reply_text(
                "❌ Неправильный формат времени!\n\n"
                "Используйте формат <code>HH:MM</code>\n"
                "Например: <code>08:30</code> или <code>20:15</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=self._get_main_keyboard()
            )
            return
        
        # Получаем пользователя
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден.", reply_markup=self._get_main_keyboard())
            return
        
        # Сохраняем новое время
        try:
            success = self.sheets_manager.update_user_notification_settings(
                user_id, time_text, getattr(user, 'timezone', 'Asia/Almaty')
            )
            
            if success:
                # Перезагружаем планировщик
                self.notification_adapter.reload_scheduler()
                
                await update.message.reply_text(
                    f"✅ <b>Время уведомлений обновлено!</b>\n\n"
                    f"🕐 Новое время: <code>{time_text}</code>\n"
                    f"🌍 Временная зона: <code>{getattr(user, 'timezone', 'Asia/Almaty')}</code>\n\n"
                    f"⚡ Планировщик перезагружен",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._get_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка обновления настроек. Попробуйте позже.",
                    reply_markup=self._get_main_keyboard()
                )
                
        except Exception as e:
            print(f"Ошибка обновления времени: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении настроек.",
                reply_markup=self._get_main_keyboard()
            )
        
        # Очищаем состояние пользователя
        self.user_states.pop(user_id, None)
    
    async def _handle_timezone_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, timezone_text: str):
        """Обработка ввода временной зоны"""
        user_id = str(update.effective_user.id)
        
        # Валидируем временную зону
        try:
            import pytz
            pytz.timezone(timezone_text)
        except pytz.UnknownTimeZoneError:
            await update.message.reply_text(
                f"❌ Неизвестная временная зона: <code>{timezone_text}</code>\n\n"
                f"<b>Популярные зоны:</b>\n"
                f"• Asia/Almaty (Алматы)\n"
                f"• Europe/Moscow (Москва)\n"
                f"• Asia/Tashkent (Ташкент)\n"
                f"• Asia/Bishkek (Бишкек)",
                parse_mode=ParseMode.HTML,
                reply_markup=self._get_main_keyboard()
            )
            return
        
        # Получаем пользователя  
        user = self.sheets_manager.get_user_by_telegram_id(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден.", reply_markup=self._get_main_keyboard())
            return
        
        # Сохраняем новую зону
        try:
            success = self.sheets_manager.update_user_notification_settings(
                user_id, getattr(user, 'notification_time', '20:15'), timezone_text
            )
            
            if success:
                # Перезагружаем планировщик
                self.notification_adapter.reload_scheduler()
                
                await update.message.reply_text(
                    f"✅ <b>Временная зона обновлена!</b>\n\n"
                    f"🕐 Время: <code>{getattr(user, 'notification_time', '20:15')}</code>\n"
                    f"🌍 Новая зона: <code>{timezone_text}</code>\n\n"
                    f"⚡ Планировщик перезагружен",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._get_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка обновления настроек. Попробуйте позже.",
                    reply_markup=self._get_main_keyboard()
                )
                
        except Exception as e:
            print(f"Ошибка обновления зоны: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении настроек.",
                reply_markup=self._get_main_keyboard()
            )
        
        # Очищаем состояние пользователя
        self.user_states.pop(user_id, None)

    def run(self):
        """Запуск бота с защитой от Event Loop ошибок"""
        print("🚀 Запуск EventGREEN Bot...")
        print(f"📊 Доступно таблиц: {self.table_manager.count_available_tables()}")
        
        # Запускаем новую систему уведомлений
        self.notification_adapter.start_scheduler()
        print("⏰ Новая система индивидуальных уведомлений запущена")
        
        # Запускаем основной бот с защитой от ошибок
        try:
            self.application.run_polling(
                drop_pending_updates=True,  # Сбрасываем старые обновления
                close_loop=False  # НЕ закрываем event loop при остановке
            )
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске бота: {e}")
            # Пытаемся перезапустить
            print("🔄 Попытка перезапуска...")
            try:
                self.application.run_polling(
                    drop_pending_updates=True,
                    close_loop=False
                )
            except Exception as restart_error:
                logger.error(f"Ошибка перезапуска: {restart_error}")
                raise

if __name__ == "__main__":
    try:
        bot = EventGREENBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n❌ Бот остановлен пользователем")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")