#!/usr/bin/env python3
"""
Простой VCF Normalizer - извлекает весь текст из карточки
Возвращает combined_text и phone для каждого контакта
"""

import vobject
from typing import List, Dict
import re

class SimpleVCFNormalizer:
    """Простой нормализатор VCF файлов"""
    
    def __init__(self):
        pass
    
    def normalize_vcf(self, vcf_content: str) -> List[Dict[str, str]]:
        """
        Нормализует VCF файл в простой формат
        
        Args:
            vcf_content: содержимое VCF файла
            
        Returns:
            Список словарей с combined_text и phone
        """
        contacts = []
        
        try:
            # Парсим VCF
            vcf_objects = vobject.readComponents(vcf_content)
            
            for vcard in vcf_objects:
                contact = self._extract_contact_data(vcard)
                if contact:  # Только если есть хоть какие-то данные
                    contacts.append(contact)
                    
        except Exception as e:
            print(f"Ошибка парсинга VCF: {e}")
            return []
        
        print(f"Извлечено {len(contacts)} контактов из VCF")
        return contacts
    
    def _extract_contact_data(self, vcard) -> Dict[str, str]:
        """Извлекает все данные из одной карточки"""
        
        all_text_parts = []
        phone = ""
        
        # Проходим по всем свойствам карточки
        for property_name in vcard.contents:
            try:
                properties = vcard.contents[property_name]
                
                for prop in properties:
                    # Извлекаем телефон отдельно
                    if property_name.lower() == 'tel':
                        if not phone:  # Берем первый найденный телефон
                            phone = self._clean_phone(str(prop.value))
                    
                    # Все остальное - в combined_text (исключаем N чтобы избежать дублирования с FN)
                    elif property_name.lower() in ['fn', 'org', 'title', 'note', 'nickname', 'email']:
                        text_value = self._extract_text_value(prop)
                        if text_value:
                            all_text_parts.append(text_value)
            
            except Exception as e:
                # Игнорируем ошибки отдельных полей
                continue
        
        # Объединяем весь текст (БЕЗ телефона - он отдельное поле)
        combined_text = ' '.join(all_text_parts).strip()
        
        # Возвращаем только если есть хоть что-то полезное
        if combined_text or phone:
            return {
                'combined_text': combined_text,
                'phone': phone
            }
        
        return None
    
    def _extract_text_value(self, prop) -> str:
        """Извлекает текстовое значение из свойства"""
        try:
            if hasattr(prop, 'value'):
                value = prop.value
                
                # Если это список (например, N - structured name)
                if isinstance(value, list):
                    return ' '.join(str(v) for v in value if str(v).strip())
                
                # Если это строка
                elif isinstance(value, str):
                    return value.strip()
                
                # Если это что-то другое, приводим к строке
                else:
                    return str(value).strip()
            
            return ""
            
        except Exception:
            return ""
    
    def _clean_phone(self, phone: str) -> str:
        """Очищает номер телефона"""
        if not phone:
            return ""
        
        # Убираем все кроме цифр и плюса
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Если номер начинается с 8, заменяем на +7 (для России/Казахстана)
        if cleaned.startswith('8') and len(cleaned) == 11:
            cleaned = '+7' + cleaned[1:]
        
        return cleaned

# Тестирование
if __name__ == "__main__":
    import os
    
    normalizer = SimpleVCFNormalizer()
    
    # Тестируем на реальном файле
    vcf_path = "/home/imort/eventGREEN_v4/Карточки vCard из iCloud(1).vcf"
    
    if os.path.exists(vcf_path):
        print("🧪 ТЕСТ ПРОСТОГО VCF NORMALIZER")
        print("=" * 50)
        
        with open(vcf_path, 'r', encoding='utf-8') as f:
            vcf_content = f.read()
        
        contacts = normalizer.normalize_vcf(vcf_content)
        
        print(f"📊 Обработано контактов: {len(contacts)}")
        
        # Показываем первые 10 для анализа
        print("\n📋 ПЕРВЫЕ 10 КОНТАКТОВ:")
        print("-" * 80)
        for i, contact in enumerate(contacts[:10], 1):
            print(f"{i:2d}. Combined: {contact['combined_text'][:60]}...")
            print(f"    Phone: {contact['phone']}")
            print()
        
        # Статистика
        with_text = sum(1 for c in contacts if c['combined_text'])
        with_phone = sum(1 for c in contacts if c['phone'])
        avg_text_length = sum(len(c['combined_text']) for c in contacts) / len(contacts) if contacts else 0
        
        print(f"📈 СТАТИСТИКА:")
        print(f"   Контактов с текстом: {with_text}")
        print(f"   Контактов с телефоном: {with_phone}")
        print(f"   Средняя длина текста: {avg_text_length:.0f} символов")
        
    else:
        print(f"❌ VCF файл не найден: {vcf_path}")