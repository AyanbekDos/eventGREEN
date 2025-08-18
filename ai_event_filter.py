"""
AI Event Filter - фильтрация контактов с событиями через Gemini 2.5 Flash
Определяет контакты с мероприятиями и извлекает структурированные данные
Поддерживает асинхронную обработку больших объемов данных
"""

import json
import asyncio
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger
from datetime import datetime
import re


@dataclass
class ExtractedContact:
    """Структура данных для контакта, извлеченного AI"""
    name: Optional[str]
    phone: str
    event_date: Optional[str]  # Может быть null для потенциальных клиентов
    event_type: Optional[str]
    raw_label: str
    note: Optional[str] = ""  # Дополнительная информация


class AIEventFilter:
    """Класс для фильтрации событий через Gemini API"""
    
    def __init__(self, api_key: str):
        """
        Инициализация AI фильтра
        
        Args:
            api_key: API ключ для Gemini
        """
        self.api_key = api_key
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Системный промпт для фильтрации событий
        self.system_prompt = self._create_system_prompt()
        
        # Семафор для ограничения одновременных запросов (максимум 10)
        self.semaphore = asyncio.Semaphore(10)

    def _create_system_prompt(self) -> str:
        """
        Создает системный промпт для AI фильтрации
        
        Returns:
            str: системный промпт
        """
        return """
Твоя задача — действовать как сверхточный AI-фильтр и парсер. Ты должен проанализировать JSON-массив контактов и вернуть ТОЛЬКО ТЕ, которые содержат информацию о мероприятиях.

**ТВОЕ ГЛАВНОЕ ПРАВИЛО:**
Если контакт не содержит **ни одного** из признаков ниже, ты должен **ПОЛНОСТЬЮ ПРОИГНОРИРОВАТЬ** его и не включать в итоговый JSON.

**ПРИЗНАКИ КЛИЕНТА С МЕРОПРИЯТИЕМ (Ищи хотя бы один):**
1.  **Признак А (Полная дата):** В `combined_text` есть и ЧИСЛО (день), и НАЗВАНИЕ МЕСЯЦА.
2.  **Признак Б (Ключевое слово):** В `combined_text` есть одно из этих слов: `свадьба`, `wedding`, `той`, `юбилей`, `anniversary`, `мерейтой`, `день рождения`, `д.р.`, `birthday`, `туған күн`, `годовщина`, `годик`, `кыз узату`, `тусау кесу`, `выпускной`, `девичник`, `пати`, `туса`, `наурыз`, `тимбилдинг`, `беташар`, `корпоратив`, `садик`.
3.  **Признак В (Только месяц):** В `combined_text` нет полной даты или ключевого слова, но есть название месяца.

---
**ВАЖНОЕ ПРАВИЛО ОБРАБОТКИ ОПЕЧАТОК:**
При поиске названий месяцев (Признак А и В), будь готов к распространенным человеческим опечаткам. **Считай их валидными названиями месяцев.**
Примеры:
- "сенятбрь", "сентебря" -> Сентябрь
- "аппеля" -> Апрель
- "декпбря" -> Декабрь
- "мюня" -> Июнь
- "аагуста" -> Август
Эта логика критически важна для правильного определения даты.

---
**ЛОГИКА ОБРАБОТКИ (Применяется ТОЛЬКО к контактам, у которых нашелся хотя бы один признак):**

1.  **ЕСЛИ НАШЕЛСЯ ПРИЗНАК А (Полная дата, с учетом опечаток):** Это "Идеальный клиент".
    -   `event_date`: Приведи дату к формату `YYYY-MM-DD`. Если год не указан, используй `2025`. **КРИТИЧЕСКИ ВАЖНО: ТОЛЬКО если есть И ЧИСЛО И МЕСЯЦ. Если нет точного дня - это НЕ полная дата, обрабатывай как Признак В.**
    -   `event_type`: Ищи ключевое слово из списка Признака Б. Если не нашел, ставь `"Неизвестно"`.
    -   `name`: Из `combined_text` удали найденную дату и все слова, описывающие событие. То, что останется — это имя. **Если ничего не осталось, ОБЯЗАТЕЛЬНО ставь `"Неизвестно"`.**
    -   `note`: Если после извлечения имени, даты и типа события в `combined_text` остался еще текст — помести его в `note`. Если ничего не осталось — оставь поле пустым.

2.  **ЕСЛИ НАШЕЛСЯ ТОЛЬКО ПРИЗНАК Б или В:** Это "Потенциальный клиент".
    -   `event_date`: Установи значение **`null`**.
    -   `event_type`: Если сработал Признак Б, укажи тип события. Если сработал только Признак В, укажи найденный месяц (например, `"Октябрь"`).
    -   `name`: Извлеки имя по тому же алгоритму. Если не удалось, ставь `"Неизвестно"`.
    -   `note`: Если после извлечения имени и типа события остался текст — помести его в `note`.

---
**ПРАВИЛА ОФОРМЛЕНИЯ И ВЫВОДА:**
-   Ответ — **ТОЛЬКО JSON-массив**, содержащий исключительно обработанные контакты.
-   **ПОСТ-ПРОВЕРКА:** Прежде чем выдать результат, убедись, что все контакты с числом и месяцем (даже с опечаткой, например "19 Мюня") были обработаны по правилам для "Идеального клиента" и имеют конкретную дату, а не `null`.
-   В поле `raw_label` копируй исходный `combined_text`.

**ПРИМЕРЫ:**
-   **Вход:** `{"combined_text": "Наталья Юбилей 30 Аппеля Не говорить о призраках", "phone": "..."}`
    **Мышление:** "Есть 'Аппеля' — это опечатка 'Апреля'. Значит есть Признак А (полная дата). Обрабатываю как Идеального. Имя, дату и тип события разобрали и в сыром тексте осталось 'Не говорить о призраках' значит это note"
    **Выход:** `{"name": "Наталья", "phone": "...", "event_date": "2025-04-30", "event_type": "юбилей", "note": "Не говорить о призраках", "raw_label": "Наталья Юбилей 30 Аппеля Не говорить о призраках"}`

-   **Вход:** `{"combined_text": "19 Мюня Выпускной 19г прикольный", "phone": "..."}`
    **Мышление:** "Есть 'Мюня' — это опечатка 'Июня'. Значит есть Признак А. Обрабатываю как Идеального. Слово 'прикольный' осталось, значит это note"
    **Выход:** `{"name": "Неизвестно", "phone": "...", "event_date": "2019-06-19", "event_type": "выпускной", "note": "прикольный", "raw_label": "19 Мюня Выпускной 19г прикольный"}`

-   **Вход:** `{"combined_text": "Мария Эвент Золл 8 Июля Новосиб", "phone": "..."}`
    **Мышление:** "Есть '8 Июля' — полная дата. Имя 'Мария', событие неясное но есть 'Эвент', после разбора остались 'Золл Новосиб' — это note"
    **Выход:** `{"name": "Мария", "phone": "...", "event_date": "2025-07-08", "event_type": "Неизвестно", "note": "Эвент Золл Новосиб", "raw_label": "Мария Эвент Золл 8 Июля Новосиб"}`

-   **Вход:** `{"combined_text": "Адиль Куленовка", "phone": "..."}`
    **Мышление:** "Признака А, Б или В нет. Игнорирую полностью."
    **Выход:** Не включать в JSON.

    Вот список для обработки:
"""

    async def filter_events_from_contacts(
        self, 
        contacts_data: List[Dict[str, Any]]
    ) -> List[ExtractedContact]:
        """
        Фильтрует события из контактов через Gemini AI
        Использует асинхронную параллельную обработку батчей
        
        Args:
            contacts_data: список контактов с combined_text и phone
            
        Returns:
            List[ExtractedContact]: список контактов с событиями
        """
        if not contacts_data:
            return []

        try:
            # Статичный размер батча - 15 контактов для избежания MAX_TOKENS
            batch_size = 15
            
            # Разбиваем контакты на батчи
            batches = []
            for i in range(0, len(contacts_data), batch_size):
                batch = contacts_data[i:i + batch_size]
                batches.append(batch)
            
            total_batches = len(batches)
            logger.info(f"Начинаем AI фильтрацию {len(contacts_data)} контактов в {total_batches} батчах")
            
            # Создаем асинхронные задачи для всех батчей
            tasks = []
            for batch_num, batch in enumerate(batches, 1):
                task = self._process_batch_async(batch, batch_num, total_batches)
                tasks.append(task)
            
            # Запускаем все батчи параллельно с ограничением через семафор
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Собираем результаты
            all_event_contacts = []
            successful_batches = 0
            
            for batch_num, result in enumerate(batch_results, 1):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка в батче {batch_num}: {result}")
                    continue
                
                if isinstance(result, list):
                    all_event_contacts.extend(result)
                    successful_batches += 1
                    logger.info(f"Батч {batch_num}: найдено {len(result)} событий")
            
            logger.info(f"AI фильтрация завершена: {successful_batches}/{total_batches} батчей успешно, найдено {len(all_event_contacts)} событий")
            
            return all_event_contacts
            
        except Exception as e:
            logger.error(f"Критическая ошибка при AI фильтрации: {e}")
            return []

    async def _process_batch_async(
        self, 
        batch: List[Dict[str, Any]], 
        batch_num: int, 
        total_batches: int
    ) -> List[ExtractedContact]:
        """
        Асинхронно обрабатывает один батч контактов через AI
        
        Args:
            batch: батч контактов для обработки
            batch_num: номер текущего батча
            total_batches: общее количество батчей
            
        Returns:
            List[ExtractedContact]: контакты с событиями из батча
        """
        async with self.semaphore:  # Ограничиваем количество одновременных запросов
            try:
                logger.info(f"AI обрабатывает батч {batch_num}/{total_batches} ({len(batch)} контактов)")
                
                # Подготавливаем данные для AI
                prompt_data = self._prepare_prompt_data(batch)
                
                # Отправляем асинхронный запрос в Gemini
                response = await self._call_ai_async(prompt_data)
                
                # Парсим ответ
                batch_events = self._parse_ai_response(response)
                
                return batch_events
                
            except Exception as e:
                logger.error(f"Ошибка при AI обработке батча {batch_num}: {e}")
                return []

    def _prepare_prompt_data(self, contacts_data: List[Dict[str, Any]]) -> str:
        """
        Подготавливает данные для промпта AI в формате JSON.
        
        Args:
            contacts_data: список контактов с combined_text и phone
            
        Returns:
            str: подготовленные данные в JSON формате
        """
        return json.dumps(contacts_data, ensure_ascii=False, indent=2)

    async def _call_ai_async(self, prompt_data: str) -> str:
        """
        Асинхронно вызывает Gemini API
        
        Args:
            prompt_data: подготовленные данные
            
        Returns:
            str: ответ от AI
        """
        try:
            full_prompt = f"{self.system_prompt}\n\n{prompt_data}"
            
            logger.debug(f"Отправляем асинхронный запрос в AI. Размер промпта: {len(full_prompt)} символов")
            
            response = await self.model.generate_content_async(
                full_prompt,
                generation_config={
                    'temperature': 0.1,
                    'top_k': 1,
                    'top_p': 0.8,
                    'max_output_tokens': 4096,
                }
            )
            
            logger.debug(f"Получен асинхронный ответ от AI. Размер: {len(response.text) if response.text else 'NULL'}")
            
            if not response.text:
                logger.error("AI вернул пустой ответ")
                if hasattr(response, 'candidates') and response.candidates:
                    for i, candidate in enumerate(response.candidates):
                        logger.error(f"Candidate {i}: finish_reason = {candidate.finish_reason}")
            
            return response.text or ""
            
        except Exception as e:
            logger.error(f"Ошибка асинхронного вызова AI API: {e}")
            raise

    def _parse_ai_response(self, response_text: str) -> List[ExtractedContact]:
        """
        Парсит ответ от AI
        
        Args:
            response_text: текст ответа от AI
            
        Returns:
            List[ExtractedContact]: список контактов с событиями
        """
        try:
            # Очищаем ответ от markdown форматирования если есть
            cleaned_response = self._clean_json_response(response_text)
            
            # Парсим JSON
            parsed_data = json.loads(cleaned_response)
            
            if not isinstance(parsed_data, list):
                logger.error("Ответ AI не является массивом")
                return []
            
            extracted_contacts = []
            
            for item in parsed_data:
                try:
                    contact = self._validate_and_create_contact(item)
                    if contact:
                        extracted_contacts.append(contact)
                except Exception as e:
                    logger.warning(f"Не удалось обработать контакт: {item}, ошибка: {e}")
                    continue
            
            return extracted_contacts
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AI: {e}")
            logger.error(f"Ответ AI: {response_text[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Неожиданная ошибка при парсинге ответа AI: {e}")
            return []

    def _clean_json_response(self, response_text: str) -> str:
        """
        Очищает ответ от markdown форматирования
        
        Args:
            response_text: исходный текст ответа
            
        Returns:
            str: очищенный JSON
        """
        # Удаляем markdown код блоки
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        
        # Убираем лишние пробелы и переносы
        response_text = response_text.strip()
        
        return response_text

    def _validate_and_create_contact(self, item: Dict[str, Any]) -> Optional[ExtractedContact]:
        """
        Валидирует и создает объект ExtractedContact
        
        Args:
            item: данные контакта от AI
            
        Returns:
            Optional[ExtractedContact]: валидный контакт или None
        """
        # Проверяем обязательные поля
        phone = item.get('phone', '')  # Телефон должен быть от AI
        event_date = item.get('event_date')
        
        # Валидируем дату только если она не null (для потенциальных клиентов)
        if event_date is not None and not self._is_valid_date(event_date):
            logger.warning(f"Контакт отброшен: невалидная дата {event_date}")
            return None
        
        # Очищаем телефон (если есть)
        cleaned_phone = self._clean_phone(phone) if phone else ''
        
        return ExtractedContact(
            name=item.get('name'),
            phone=cleaned_phone,
            event_date=event_date,
            event_type=item.get('event_type'),
            raw_label=item.get('raw_label', ''),
            note=item.get('note', '')
        )

    def _is_valid_date(self, date_str: str) -> bool:
        """
        Проверяет валидность даты в формате YYYY-MM-DD
        
        Args:
            date_str: строка даты
            
        Returns:
            bool: True если дата валидная
        """
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except (ValueError, TypeError):
            return False

    def _clean_phone(self, phone: str) -> Optional[str]:
        """
        Очищает и валидирует номер телефона
        
        Args:
            phone: исходный номер
            
        Returns:
            Optional[str]: очищенный номер или None
        """
        if not phone or not isinstance(phone, str):
            return None
        
        # Удаляем все символы кроме цифр и +
        cleaned = re.sub(r'[^+\d]', '', phone)
        
        # Проверяем минимальную длину (хотя бы 7 цифр)
        digits_only = re.sub(r'[^\d]', '', cleaned)
        if len(digits_only) < 7:
            return None
        
        return cleaned

    def get_filtering_stats(self, 
                           input_count: int, 
                           output_count: int) -> Dict[str, Any]:
        """
        Возвращает статистику AI фильтрации
        
        Args:
            input_count: количество входящих контактов
            output_count: количество найденных событий
            
        Returns:
            Dict[str, Any]: статистика
        """
        success_rate = 0
        if input_count > 0:
            success_rate = round((output_count / input_count) * 100, 1)
        
        return {
            'input_contacts': input_count,
            'events_found': output_count,
            'success_rate': success_rate,
            'filtered_out': input_count - output_count,
            'processing_time': datetime.now().isoformat()
        }


# Пример использования
if __name__ == "__main__":
    import os
    
    # Инициализация (нужен реальный API ключ)
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Ошибка: установите переменную GEMINI_API_KEY")
        exit(1)
    
    ai_filter = AIEventFilter(api_key)
    
    # Пример данных контактов
    sample_contacts = [
        {
            "combined_text": "Анна Иванова свадьба 25 июня",
            "phone": "+79991234567"
        },
        {
            "combined_text": "Петр Сидоров",
            "phone": "+79997654321"
        },
        {
            "combined_text": "Мария день рождения",
            "phone": "+79995555555"
        }
    ]
    
    # Асинхронная фильтрация
    async def test_filtering():
        events = await ai_filter.filter_events_from_contacts(sample_contacts)
        
        print(f"Найдено событий: {len(events)}")
        for event in events:
            print(f"Имя: {event.name}")
            print(f"Телефон: {event.phone}")
            print(f"Дата: {event.event_date}")
            print(f"Тип: {event.event_type}")
            print(f"Исходный текст: {event.raw_label}")
            print("---")
        
        # Статистика
        stats = ai_filter.get_filtering_stats(len(sample_contacts), len(events))
        print(f"Статистика: {stats}")
    
    # Запуск
    asyncio.run(test_filtering())