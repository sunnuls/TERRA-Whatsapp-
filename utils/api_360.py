# utils/api_360.py
"""
Взаимодействие с API 360dialog для отправки сообщений.
"""
import logging
import requests
from typing import List, Dict, Optional
from config import D360_API_KEY, D360_BASE_URL

logger = logging.getLogger(__name__)


def send_text_message(user_id: str, text: str) -> bool:
    """
    Отправить текстовое сообщение пользователю.
    
    Args:
        user_id: Номер телефона получателя (формат: 79991234567)
        text: Текст сообщения (поддерживает WhatsApp форматирование)
    
    Returns:
        True если отправлено успешно, False в случае ошибки
    """
    url = f"{D360_BASE_URL}/v1/messages"
    
    headers = {
        "D360-API-KEY": D360_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "recipient_type": "individual",
        "to": user_id,
        "type": "text",
        "text": {
            "body": text
        }
    }
    
    try:
        logger.info(f"📤 Отправка текста пользователю {user_id}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200 or response.status_code == 201:
            logger.info(f"✅ Сообщение отправлено {user_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Исключение при отправке: {e}", exc_info=True)
        return False


def send_buttons(user_id: str, text: str, buttons: List[Dict[str, str]]) -> bool:
    """
    Отправить сообщение с кнопками (interactive message).
    
    Args:
        user_id: Номер телефона получателя
        text: Текст сообщения
        buttons: Список кнопок [{"id": "btn1", "title": "Кнопка 1"}, ...]
                 Максимум 3 кнопки по ограничениям WhatsApp
    
    Returns:
        True если отправлено успешно
    """
    url = f"{D360_BASE_URL}/v1/messages"
    
    headers = {
        "D360-API-KEY": D360_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Формируем кнопки в формате 360dialog
    button_components = []
    for btn in buttons[:3]:  # Максимум 3 кнопки
        button_components.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["title"][:20]  # Максимум 20 символов
            }
        })
    
    payload = {
        "recipient_type": "individual",
        "to": user_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": button_components
            }
        }
    }
    
    try:
        logger.info(f"📤 Отправка кнопок пользователю {user_id}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200 or response.status_code == 201:
            logger.info(f"✅ Кнопки отправлены {user_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки кнопок: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Исключение при отправке кнопок: {e}", exc_info=True)
        return False


def send_list_message(user_id: str, text: str, button_text: str, sections: List[Dict]) -> bool:
    """
    Отправить сообщение со списком (list message).
    
    Args:
        user_id: Номер телефона получателя
        text: Текст сообщения
        button_text: Текст кнопки открытия списка
        sections: Список секций с элементами
    
    Returns:
        True если отправлено успешно
    """
    url = f"{D360_BASE_URL}/v1/messages"
    
    headers = {
        "D360-API-KEY": D360_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "recipient_type": "individual",
        "to": user_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {
                "text": text
            },
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    }
    
    try:
        logger.info(f"📤 Отправка списка пользователю {user_id}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200 or response.status_code == 201:
            logger.info(f"✅ Список отправлен {user_id}")
            return True
        else:
            logger.error(f"❌ Ошибка отправки списка: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Исключение при отправке списка: {e}", exc_info=True)
        return False


def mark_message_as_read(message_id: str) -> bool:
    """
    Отметить сообщение как прочитанное.
    
    Args:
        message_id: ID сообщения
    
    Returns:
        True если успешно
    """
    url = f"{D360_BASE_URL}/v1/messages/{message_id}/mark_as_read"
    
    headers = {
        "D360-API-KEY": D360_API_KEY
    }
    
    try:
        response = requests.put(url, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ Ошибка mark_as_read: {e}")
        return False

