# menu_handlers.py
"""
Обработчики меню и команд бота.
"""
import logging
from utils.state import get_user_state, set_user_state, clear_user_state
from utils.api_360 import send_text_message, send_buttons

logger = logging.getLogger(__name__)


def handle_incoming_message(message: dict):
    """
    Главный обработчик входящих сообщений.
    
    Args:
        message: Словарь с данными сообщения от 360dialog
    """
    try:
        # Извлекаем данные из сообщения
        user_id = message.get('from')
        message_type = message.get('type')
        message_id = message.get('id')
        
        logger.info(f"👤 Сообщение от {user_id}, тип: {message_type}")
        
        # Обработка текстовых сообщений
        if message_type == 'text':
            text_body = message.get('text', {}).get('body', '').strip()
            handle_text_message(user_id, text_body)
        
        # Обработка кнопок (interactive messages)
        elif message_type == 'interactive':
            button_reply = message.get('interactive', {}).get('button_reply', {})
            button_id = button_reply.get('id', '')
            handle_button_click(user_id, button_id)
        
        # Обработка других типов сообщений
        else:
            logger.info(f"⚠️ Неподдерживаемый тип сообщения: {message_type}")
            send_text_message(user_id, "Извините, я поддерживаю только текстовые сообщения и кнопки.")
    
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_incoming_message: {e}", exc_info=True)


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


def handle_button_click(user_id: str, button_id: str):
    """
    Обработка нажатий на кнопки.
    
    Args:
        user_id: ID пользователя
        button_id: ID нажатой кнопки
    """
    logger.info(f"🔘 Кнопка от {user_id}: {button_id}")
    
    # Роутинг по button_id
    if button_id == 'main_menu':
        handle_main_menu(user_id)
    
    elif button_id == 'shift_menu':
        handle_shift_menu(user_id)
    
    elif button_id == 'stats_menu':
        handle_stats_menu(user_id)
    
    elif button_id == 'settings_menu':
        handle_settings_menu(user_id)
    
    else:
        logger.warning(f"⚠️ Неизвестная кнопка: {button_id}")
        send_text_message(user_id, "Команда не распознана. Используйте меню.")


# ============================================================================
# ОБРАБОТЧИКИ МЕНЮ (пустышки для заполнения логикой)
# ============================================================================

def handle_main_menu(user_id: str):
    """
    Главное меню бота.
    """
    logger.info(f"📋 Главное меню для {user_id}")
    
    # Очищаем состояние
    clear_user_state(user_id)
    
    text = """
👋 *Добро пожаловать в TERRA Bot!*

Выберите действие:
"""
    
    buttons = [
        {"id": "shift_menu", "title": "🚜 Смена"},
        {"id": "stats_menu", "title": "📊 Статистика"},
        {"id": "settings_menu", "title": "⚙️ Настройки"}
    ]
    
    send_buttons(user_id, text, buttons)


def handle_shift_menu(user_id: str):
    """
    Меню учёта рабочей смены.
    """
    logger.info(f"🚜 Меню смены для {user_id}")
    
    text = """
🚜 *Учёт рабочей смены*

Выберите действие:
"""
    
    buttons = [
        {"id": "start_shift", "title": "▶️ Начать смену"},
        {"id": "end_shift", "title": "⏹ Завершить смену"},
        {"id": "main_menu", "title": "🔙 Назад"}
    ]
    
    send_buttons(user_id, text, buttons)


def handle_stats_menu(user_id: str):
    """
    Меню статистики.
    """
    logger.info(f"📊 Меню статистики для {user_id}")
    
    text = """
📊 *Статистика*

Выберите период:
"""
    
    buttons = [
        {"id": "stats_today", "title": "📅 Сегодня"},
        {"id": "stats_week", "title": "📆 Неделя"},
        {"id": "main_menu", "title": "🔙 Назад"}
    ]
    
    send_buttons(user_id, text, buttons)


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


def handle_help(user_id: str):
    """
    Справка по использованию бота.
    """
    logger.info(f"❓ Помощь для {user_id}")
    
    text = """
ℹ️ *Справка по боту*

*Доступные команды:*
• start / меню - Главное меню
• help / помощь - Эта справка

*Как пользоваться:*
1. Используйте кнопки меню
2. Следуйте инструкциям бота
3. Для отмены - отправьте "меню"

По вопросам обращайтесь к администратору.
"""
    
    send_text_message(user_id, text)


def handle_name_input(user_id: str, name: str):
    """
    Обработка ввода имени пользователя.
    """
    logger.info(f"✏️ Ввод имени от {user_id}: {name}")
    
    # TODO: Сохранить имя в базу данных
    
    clear_user_state(user_id)
    send_text_message(user_id, f"✅ Имя сохранено: *{name}*")
    handle_main_menu(user_id)


def handle_hours_input(user_id: str, hours_text: str):
    """
    Обработка ввода количества часов.
    """
    logger.info(f"⏰ Ввод часов от {user_id}: {hours_text}")
    
    try:
        hours = int(hours_text)
        
        if hours < 1 or hours > 24:
            send_text_message(user_id, "❌ Количество часов должно быть от 1 до 24.")
            return
        
        # TODO: Сохранить часы в базу данных
        
        clear_user_state(user_id)
        send_text_message(user_id, f"✅ Записано {hours} ч.")
        handle_main_menu(user_id)
        
    except ValueError:
        send_text_message(user_id, "❌ Введите число от 1 до 24.")

