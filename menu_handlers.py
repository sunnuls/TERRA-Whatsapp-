# menu_handlers.py
"""
Обработчики меню и FSM (машина состояний) бота.
"""
import logging
import sys
import os

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.state import get_state, set_state, clear_state, update_user_data, get_user_data, States
from utils.sheets import save_entry

logger = logging.getLogger(__name__)

# Импорт функций отправки (отложенный для избежания циклического импорта)
def get_send_functions():
    """Получить функции отправки сообщений (отложенный импорт)"""
    from bot import send_message, send_buttons, send_list
    return send_message, send_buttons, send_list

# ============================================================================
# КОНСТАНТЫ
# ============================================================================

# Типы работ
WORK_TYPES = {
    "work_field": "Поле",
    "work_zucchini": "Кабачок",
    "work_potato": "Картошка",
    "work_other": "Другое"
}

# Смены
SHIFTS = {
    "shift_1": {"title": "Смена 1 (8-16)", "hours": "8-16"},
    "shift_2": {"title": "Смена 2 (16-00)", "hours": "16-00"},
    "shift_3": {"title": "Смена 3 (00-8)", "hours": "00-8"}
}

# Количество часов
HOURS_OPTIONS = {
    "hours_4": "4",
    "hours_6": "6",
    "hours_8": "8",
    "hours_12": "12"
}

# ============================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК ВХОДЯЩИХ СООБЩЕНИЙ
# ============================================================================

def handle_incoming_message(message: dict):
    """
    Главный обработчик входящих сообщений с поддержкой FSM.
    
    Args:
        message: Словарь с данными сообщения от 360dialog
    """
    try:
        # Извлекаем данные из сообщения
        phone = message.get('from')
        message_type = message.get('type')
        
        logger.info(f"[HANDLER] Обработка сообщения от {phone}, тип: {message_type}")
        
        # Получаем текущее состояние пользователя
        user_state = get_state(phone)
        current_state = user_state.get('state')
        
        logger.info(f"[FSM] Текущее состояние {phone}: {current_state}")
        
        # Обработка текстовых сообщений
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '').strip()
            handle_text_message(phone, text_body, current_state)
        
        # Обработка кнопок (button_reply)
        elif 'button_id' in message:
            button_id = message.get('button_id')
            handle_button_click(phone, button_id, current_state)
        
        # Обработка списков (list_reply)
        elif 'list_id' in message:
            list_id = message.get('list_id')
            handle_list_selection(phone, list_id, current_state)
        
        else:
            logger.info(f"[WARN] Неподдерживаемый тип сообщения: {message_type}")
            send_text_message(phone, "Извините, я поддерживаю только текстовые сообщения и интерактивные элементы.")
    
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
    send_message, _, _ = get_send_functions()
    data = {
        "type": "text",
        "text": {
            "body": text
        }
    }
    return send_message(phone, data)


# ============================================================================
# ОБРАБОТЧИКИ ТЕКСТОВЫХ СООБЩЕНИЙ
# ============================================================================

def handle_text_message(phone: str, text: str, current_state: str):
    """
    Обработка текстовых сообщений с учетом FSM.
    
    Args:
        phone: Номер телефона
        text: Текст сообщения
        current_state: Текущее состояние FSM
    """
    logger.info(f"💬 [TEXT] {phone}: {text} (состояние: {current_state})")
    
    # Команды, которые работают из любого состояния
    text_lower = text.lower()
    
    if text_lower in ['start', 'старт', 'меню', 'menu', '/start']:
        handle_main_menu(phone)
        return
    
    elif text_lower in ['help', 'помощь', '/help']:
        handle_help(phone)
        return
    
    elif text_lower in ['cancel', 'отмена', 'стоп', 'stop']:
        clear_state(phone)
        send_text_message(phone, "Действие отменено. Возвращаю в главное меню.")
        handle_main_menu(phone)
        return
    
    # Обработка в зависимости от состояния FSM
    # (Для текущей реализации не требуется, так как используем интерактивные элементы)
    
    # По умолчанию показываем главное меню
    send_text_message(phone, "Не понял команду. Отправляю главное меню...")
    handle_main_menu(phone)


# ============================================================================
# ОБРАБОТЧИКИ КНОПОК
# ============================================================================

def handle_button_click(phone: str, button_id: str, current_state: str):
    """
    Обработка нажатий на кнопки с учетом FSM.
    
    Args:
        phone: Номер телефона
        button_id: ID нажатой кнопки
        current_state: Текущее состояние FSM
    """
    logger.info(f"[BUTTON] {phone} нажал: {button_id} (состояние: {current_state})")
    
    # Глобальные кнопки (работают из любого состояния)
    if button_id == 'main_menu':
        handle_main_menu(phone)
    
    elif button_id == 'help_menu':
        handle_help(phone)
    
    # Кнопки главного меню
    elif button_id == 'work_menu':
        handle_select_work(phone)
    
    elif button_id == 'hours_menu':
        handle_hours_info(phone)
    
    # Кнопки подтверждения
    elif button_id == 'confirm_yes':
        handle_confirm_save(phone, confirmed=True)
    
    elif button_id == 'confirm_no':
        handle_confirm_save(phone, confirmed=False)
    
    else:
        logger.warning(f"[WARN] Неизвестная кнопка: {button_id}")
        send_text_message(phone, "Команда не распознана. Используйте меню.")
        handle_main_menu(phone)


# ============================================================================
# ОБРАБОТЧИКИ СПИСКОВ
# ============================================================================

def handle_list_selection(phone: str, list_id: str, current_state: str):
    """
    Обработка выбора из списка с учетом FSM.
    
    Args:
        phone: Номер телефона
        list_id: ID выбранной строки списка
        current_state: Текущее состояние FSM
    """
    logger.info(f"[LIST] {phone} выбрал: {list_id} (состояние: {current_state})")
    
    # Обработка в зависимости от состояния FSM
    if current_state == States.SELECT_WORK:
        # Пользователь выбрал тип работы
        if list_id in WORK_TYPES:
            work_name = WORK_TYPES[list_id]
            update_user_data(phone, 'work', work_name)
            update_user_data(phone, 'work_id', list_id)
            logger.info(f"[FSM] {phone}: Работа выбрана - {work_name}")
            handle_select_shift(phone)
        else:
            send_text_message(phone, "Ошибка: неизвестный тип работы.")
            handle_select_work(phone)
    
    elif current_state == States.SELECT_SHIFT:
        # Пользователь выбрал смену
        if list_id in SHIFTS:
            shift_info = SHIFTS[list_id]
            shift_title = shift_info['title']
            shift_hours = shift_info['hours']
            update_user_data(phone, 'shift', shift_hours)
            update_user_data(phone, 'shift_id', list_id)
            logger.info(f"[FSM] {phone}: Смена выбрана - {shift_title}")
            handle_select_hours(phone)
        else:
            send_text_message(phone, "Ошибка: неизвестная смена.")
            handle_select_shift(phone)
    
    elif current_state == States.SELECT_HOURS:
        # Пользователь выбрал количество часов
        if list_id in HOURS_OPTIONS:
            hours = HOURS_OPTIONS[list_id]
            update_user_data(phone, 'hours', hours)
            update_user_data(phone, 'hours_id', list_id)
            logger.info(f"[FSM] {phone}: Часы выбраны - {hours}")
            handle_show_confirmation(phone)
        else:
            send_text_message(phone, "Ошибка: неизвестное количество часов.")
            handle_select_hours(phone)
    
    else:
        logger.warning(f"[WARN] Выбор списка в неожиданном состоянии: {current_state}")
        send_text_message(phone, "Произошла ошибка. Начните сначала.")
        handle_main_menu(phone)


# ============================================================================
# FSM HANDLERS - Обработчики состояний FSM
# ============================================================================

def handle_main_menu(phone: str):
    """
    Состояние: MAIN_MENU
    Главное меню бота с интерактивными кнопками.
    """
    logger.info(f"[FSM] {phone}: MAIN_MENU")
    
    # Устанавливаем состояние
    set_state(phone, States.MAIN_MENU)
    
    # ВРЕМЕННО: отправляем простое текстовое сообщение для проверки API
    text = """Добро пожаловать в TERRA Bot!

Отправьте команду:
1 - Работа
2 - Часы
3 - Помощь"""
    
    send_text_message(phone, text)


def handle_select_work(phone: str):
    """
    Состояние: SELECT_WORK
    Выбор типа работы из списка.
    """
    logger.info(f"[FSM] {phone}: SELECT_WORK")
    
    # Устанавливаем состояние
    set_state(phone, States.SELECT_WORK)
    
    text = "📋 Выберите тип работы:"
    button_text = "Выбрать работу"
    
    sections = [
        {
            "title": "Доступные работы",
            "rows": [
                {
                    "id": "work_field",
                    "title": "🌾 Поле",
                    "description": "Работа на поле"
                },
                {
                    "id": "work_zucchini",
                    "title": "🥒 Кабачок",
                    "description": "Работа с кабачками"
                },
                {
                    "id": "work_potato",
                    "title": "🥔 Картошка",
                    "description": "Работа с картошкой"
                },
                {
                    "id": "work_other",
                    "title": "📦 Другое",
                    "description": "Другой тип работы"
                }
            ]
        }
    ]
    
    _, _, send_list = get_send_functions()
    send_list(phone, text, button_text, sections)


def handle_select_shift(phone: str):
    """
    Состояние: SELECT_SHIFT
    Выбор смены из списка.
    """
    logger.info(f"[FSM] {phone}: SELECT_SHIFT")
    
    # Устанавливаем состояние
    set_state(phone, States.SELECT_SHIFT)
    
    # Получаем выбранную работу
    work = get_user_data(phone, 'work', 'Работа')
    
    text = f"✅ Работа выбрана: {work}\n\n⏰ Теперь выберите смену:"
    button_text = "Выбрать смену"
    
    sections = [
        {
            "title": "Доступные смены",
            "rows": [
                {
                    "id": "shift_1",
                    "title": "☀️ Смена 1 (8-16)",
                    "description": "Дневная смена с 08:00 до 16:00"
                },
                {
                    "id": "shift_2",
                    "title": "🌆 Смена 2 (16-00)",
                    "description": "Вечерняя смена с 16:00 до 00:00"
                },
                {
                    "id": "shift_3",
                    "title": "🌙 Смена 3 (00-8)",
                    "description": "Ночная смена с 00:00 до 08:00"
                }
            ]
        }
    ]
    
    _, _, send_list = get_send_functions()
    send_list(phone, text, button_text, sections)


def handle_select_hours(phone: str):
    """
    Состояние: SELECT_HOURS
    Выбор количества часов из списка.
    """
    logger.info(f"[FSM] {phone}: SELECT_HOURS")
    
    # Устанавливаем состояние
    set_state(phone, States.SELECT_HOURS)
    
    # Получаем выбранные данные
    work = get_user_data(phone, 'work', 'Работа')
    shift = get_user_data(phone, 'shift', 'Смена')
    
    text = f"✅ Работа: {work}\n✅ Смена: {shift}\n\n⏱️ Выберите количество часов:"
    button_text = "Выбрать часы"
    
    sections = [
        {
            "title": "Количество часов",
            "rows": [
                {
                    "id": "hours_4",
                    "title": "4 часа",
                    "description": "Отработано 4 часа"
                },
                {
                    "id": "hours_6",
                    "title": "6 часов",
                    "description": "Отработано 6 часов"
                },
                {
                    "id": "hours_8",
                    "title": "8 часов",
                    "description": "Отработано 8 часов"
                },
                {
                    "id": "hours_12",
                    "title": "12 часов",
                    "description": "Отработано 12 часов"
                }
            ]
        }
    ]
    
    _, _, send_list = get_send_functions()
    send_list(phone, text, button_text, sections)


def handle_show_confirmation(phone: str):
    """
    Состояние: CONFIRM_SAVE
    Показать данные и запросить подтверждение.
    """
    logger.info(f"[FSM] {phone}: CONFIRM_SAVE (показ)")
    
    # Устанавливаем состояние
    set_state(phone, States.CONFIRM_SAVE)
    
    # Получаем все данные
    work = get_user_data(phone, 'work', 'Не указано')
    shift = get_user_data(phone, 'shift', 'Не указано')
    hours = get_user_data(phone, 'hours', 'Не указано')
    
    text = f"""📝 Проверьте данные перед сохранением:

▫️ Работа: {work}
▫️ Смена: {shift}
▫️ Часов: {hours}

Все верно?"""
    
    buttons = [
        {"id": "confirm_yes", "title": "✅ Подтвердить"},
        {"id": "confirm_no", "title": "❌ Отмена"}
    ]
    
    _, send_buttons, _ = get_send_functions()
    send_buttons(phone, text, buttons)


def handle_confirm_save(phone: str, confirmed: bool):
    """
    Обработка подтверждения/отмены сохранения.
    
    Args:
        phone: Номер телефона
        confirmed: True если пользователь подтвердил, False если отменил
    """
    logger.info(f"[FSM] {phone}: CONFIRM_SAVE (обработка: {'Да' if confirmed else 'Нет'})")
    
    if confirmed:
        # Получаем данные из состояния
        work = get_user_data(phone, 'work')
        shift = get_user_data(phone, 'shift')
        hours = get_user_data(phone, 'hours')
        
        if not work or not shift or not hours:
            send_text_message(phone, "❌ Ошибка: не все данные заполнены. Начните сначала.")
            clear_state(phone)
            handle_main_menu(phone)
            return
        
        # Сохраняем запись
        success = save_entry(phone, work, shift, hours)
        
        if success:
            send_text_message(phone, f"""✅ Запись успешно сохранена!

📋 Работа: {work}
⏰ Смена: {shift}
⏱️ Часов: {hours}

Спасибо! Возвращаю в главное меню...""")
        else:
            send_text_message(phone, "❌ Ошибка при сохранении данных. Попробуйте позже.")
        
        # Очищаем состояние и возвращаем в главное меню
        clear_state(phone)
        handle_main_menu(phone)
    
    else:
        # Пользователь отменил
        send_text_message(phone, "❌ Сохранение отменено. Возвращаю в главное меню...")
        clear_state(phone)
        handle_main_menu(phone)


# ============================================================================
# ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ
# ============================================================================

def handle_hours_info(phone: str):
    """
    Информация о часах работы (не меняет состояние FSM).
    """
    logger.info(f"[INFO] {phone}: Информация о часах")
    
    text = """⏰ Информация о рабочих часах

Доступные варианты:
• 4 часа - неполная смена
• 6 часов - сокращенная смена
• 8 часов - стандартная смена
• 12 часов - удлиненная смена

Для учета рабочего времени используйте меню "Работа"."""
    
    send_text_message(phone, text)
    
    # Возвращаем в главное меню
    handle_main_menu(phone)


def handle_help(phone: str):
    """
    Справка по использованию бота.
    """
    logger.info(f"[HELP] {phone}: Помощь")
    
    text = """❓ Справка по боту TERRA

📱 Команды:
• start / menu - Главное меню
• help - Эта справка
• cancel / отмена - Отменить текущее действие

📋 Как пользоваться:
1. Выберите "Работа" в главном меню
2. Укажите тип работы
3. Выберите смену
4. Укажите количество часов
5. Подтвердите сохранение

💡 Используйте кнопки и списки для навигации!

По вопросам обращайтесь к администратору."""
    
    send_text_message(phone, text)
    
    # Показываем главное меню
    handle_main_menu(phone)
