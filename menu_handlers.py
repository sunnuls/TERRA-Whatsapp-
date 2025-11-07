# menu_handlers.py
"""
Обработчики меню и команд бота.
"""
import logging
import sys
import os

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.state import get_user_state, set_user_state, clear_user_state
from bot import send_message, send_buttons, send_list

logger = logging.getLogger(__name__)


def handle_incoming_message(message: dict):
    """
    Главный обработчик входящих сообщений.
    
    Args:
        message: Словарь с данными сообщения от 360dialog
    """
    try:
        # Извлекаем данные из сообщения
        phone = message.get('from')
        message_type = message.get('type')
        
        logger.info(f"[HANDLER] Обработка сообщения от {phone}, тип: {message_type}")
        
        # Обработка текстовых сообщений
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '').strip()
            handle_text_message(phone, text_body)
        
        # Обработка кнопок (button_reply)
        elif 'button_id' in message:
            button_id = message.get('button_id')
            handle_button_click(phone, button_id)
        
        # Обработка списков (list_reply)
        elif 'list_id' in message:
            list_id = message.get('list_id')
            handle_list_selection(phone, list_id)
        
        # Обработка других типов сообщений
        else:
            logger.info(f"[WARN] Неподдерживаемый тип сообщения: {message_type}")
            send_text_message(phone, "Извините, я поддерживаю только текстовые сообщения и кнопки.")
    
    except Exception as e:
        logger.error(f"[ERROR] Ошибка в handle_incoming_message: {e}", exc_info=True)


def send_text_message(phone: str, text: str) -> bool:
    """
    Отправить текстовое сообщение.
    
    Args:
        phone: Номер телефона
        text: Текст сообщения
    
    Returns:
        bool: True если отправлено успешно
    """
    data = {
        "type": "text",
        "text": {
            "body": text
        }
    }
    return send_message(phone, data)


def handle_text_message(user_id: str, text: str):
    """
    Обработка текстовых сообщений.
    
    Args:
        user_id: ID пользователя (номер телефона)
        text: Текст сообщения
    """
    logger.info(f"💬 Текст от {user_id}: {text}")
    
    # Получаем состояние пользователя
    state = get_user_state(user_id)
    current_state = state.get('state')
    
    # Команды
    if text.lower() in ['start', 'старт', 'меню', 'menu']:
        handle_main_menu(user_id)
    
    elif text.lower() in ['help', 'помощь']:
        handle_help(user_id)
    
    # Обработка состояний FSM
    elif current_state == 'waiting_name':
        handle_name_input(user_id, text)
    
    elif current_state == 'waiting_hours':
        handle_hours_input(user_id, text)
    
    else:
        # По умолчанию показываем главное меню
        handle_main_menu(user_id)


def handle_button_click(phone: str, button_id: str):
    """
    Обработка нажатий на кнопки.
    
    Args:
        phone: Номер телефона
        button_id: ID нажатой кнопки
    """
    logger.info(f"[BUTTON] Кнопка от {phone}: {button_id}")
    
    # Роутинг по button_id
    if button_id == 'main_menu':
        handle_main_menu(phone)
    
    elif button_id == 'work_menu':
        handle_shift_menu(phone)
    
    elif button_id == 'hours_menu':
        handle_hours_menu(phone)
    
    elif button_id == 'help_menu':
        handle_help(phone)
    
    elif button_id == 'stats_menu':
        handle_stats_menu(phone)
    
    elif button_id == 'settings_menu':
        handle_settings_menu(phone)
    
    else:
        logger.warning(f"[WARN] Неизвестная кнопка: {button_id}")
        send_text_message(phone, "Команда не распознана. Используйте меню.")


def handle_list_selection(phone: str, list_id: str):
    """
    Обработка выбора из списка.
    
    Args:
        phone: Номер телефона
        list_id: ID выбранной строки списка
    """
    logger.info(f"[LIST] Выбор от {phone}: {list_id}")
    
    # Роутинг по list_id
    if list_id.startswith('shift_'):
        # Обработка выбора смены
        shift_number = list_id.replace('shift_', '')
        handle_shift_selected(phone, shift_number)
    
    else:
        logger.warning(f"[WARN] Неизвестный list_id: {list_id}")
        send_text_message(phone, "Команда не распознана. Используйте меню.")


# ============================================================================
# ОБРАБОТЧИКИ МЕНЮ (пустышки для заполнения логикой)
# ============================================================================

def handle_main_menu(phone: str):
    """
    Главное меню бота с интерактивными кнопками.
    """
    logger.info(f"[MENU] Главное меню для {phone}")
    
    # Очищаем состояние
    clear_user_state(phone)
    
    text = "Добро пожаловать в TERRA Bot!\n\nВыберите действие:"
    
    buttons = [
        {"id": "work_menu", "title": "Работа"},
        {"id": "hours_menu", "title": "Часы"},
        {"id": "help_menu", "title": "Помощь"}
    ]
    
    send_buttons(phone, text, buttons)


def handle_shift_menu(phone: str):
    """
    Меню учёта рабочей смены - отправляет список (list message) со сменами.
    """
    logger.info(f"[MENU] Меню смены для {phone}")
    
    text = "Выберите смену для начала работы:"
    button_text = "Выбрать смену"
    
    sections = [
        {
            "title": "Доступные смены",
            "rows": [
                {
                    "id": "shift_1",
                    "title": "Смена 1 (8-16)",
                    "description": "Дневная смена с 08:00 до 16:00"
                },
                {
                    "id": "shift_2",
                    "title": "Смена 2 (16-00)",
                    "description": "Вечерняя смена с 16:00 до 00:00"
                },
                {
                    "id": "shift_3",
                    "title": "Смена 3 (00-8)",
                    "description": "Ночная смена с 00:00 до 08:00"
                }
            ]
        }
    ]
    
    send_list(phone, text, button_text, sections)


def handle_hours_menu(phone: str):
    """
    Меню учёта часов.
    """
    logger.info(f"[MENU] Меню часов для {phone}")
    
    text = "Учёт рабочих часов\n\nВведите количество часов:"
    
    # Устанавливаем состояние ожидания ввода часов
    set_user_state(phone, "waiting_hours")
    
    send_text_message(phone, text)


def handle_stats_menu(phone: str):
    """
    Меню статистики.
    """
    logger.info(f"[MENU] Меню статистики для {phone}")
    
    text = "Статистика работы\n\nВыберите период:"
    
    buttons = [
        {"id": "stats_today", "title": "Сегодня"},
        {"id": "stats_week", "title": "Неделя"},
        {"id": "main_menu", "title": "Назад"}
    ]
    
    send_buttons(phone, text, buttons)


def handle_settings_menu(user_id: str):
    """
    Меню настроек.
    """
    logger.info(f"⚙️ Меню настроек для {user_id}")
    
    text = """
⚙️ *Настройки*

Доступные опции:
"""
    
    buttons = [
        {"id": "change_name", "title": "✏️ Изменить имя"},
        {"id": "view_profile", "title": "👤 Профиль"},
        {"id": "main_menu", "title": "🔙 Назад"}
    ]
    
    send_buttons(user_id, text, buttons)


def handle_shift_selected(phone: str, shift_number: str):
    """
    Обработка выбранной смены.
    
    Args:
        phone: Номер телефона
        shift_number: Номер смены (1, 2, или 3)
    """
    logger.info(f"[SHIFT] Выбрана смена {shift_number} для {phone}")
    
    shift_info = {
        "1": "Смена 1 (8-16)",
        "2": "Смена 2 (16-00)",
        "3": "Смена 3 (00-8)"
    }
    
    shift_name = shift_info.get(shift_number, "Неизвестная смена")
    
    # Сохраняем выбранную смену в состояние
    set_user_state(phone, "shift_selected", {"shift": shift_number})
    
    text = f"Вы выбрали: {shift_name}\n\nСмена начата. Удачной работы!"
    
    send_text_message(phone, text)
    
    # Возвращаем в главное меню
    handle_main_menu(phone)


def handle_help(phone: str):
    """
    Справка по использованию бота.
    """
    logger.info(f"[HELP] Помощь для {phone}")
    
    text = """Справка по боту TERRA

Доступные команды:
• start / menu - Главное меню
• help - Эта справка

Как пользоваться:
1. Используйте кнопки меню
2. Следуйте инструкциям бота
3. Для возврата в меню отправьте "menu"

По вопросам обращайтесь к администратору."""
    
    send_text_message(phone, text)
    
    # Показываем главное меню
    handle_main_menu(phone)


def handle_name_input(phone: str, name: str):
    """
    Обработка ввода имени пользователя.
    """
    logger.info(f"[INPUT] Ввод имени от {phone}: {name}")
    
    # TODO: Сохранить имя в базу данных
    
    clear_user_state(phone)
    send_text_message(phone, f"Имя сохранено: {name}")
    handle_main_menu(phone)


def handle_hours_input(phone: str, hours_text: str):
    """
    Обработка ввода количества часов.
    """
    logger.info(f"[INPUT] Ввод часов от {phone}: {hours_text}")
    
    try:
        hours = int(hours_text)
        
        if hours < 1 or hours > 24:
            send_text_message(phone, "Ошибка: количество часов должно быть от 1 до 24.")
            return
        
        # TODO: Сохранить часы в базу данных
        
        clear_user_state(phone)
        send_text_message(phone, f"Записано {hours} ч. работы.")
        handle_main_menu(phone)
        
    except ValueError:
        send_text_message(phone, "Ошибка: введите число от 1 до 24.")

