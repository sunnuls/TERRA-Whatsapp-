# bot.py
"""
Главный файл WhatsApp-бота на Flask с интеграцией 360dialog.
Обрабатывает вебхуки GET/POST, роутинг сообщений и интерактивные элементы.
"""

import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from menu_handlers import (
    send_main_menu,
    handle_main_menu_button,
    handle_shift_selection
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация Flask приложения
app = Flask(__name__)

# Получение конфигурации из переменных окружения
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PORT = int(os.getenv("PORT", 8000))
MODE = os.getenv("MODE", "dev")

# Проверка обязательных параметров
if not VERIFY_TOKEN:
    logger.error("❌ ОШИБКА: VERIFY_TOKEN не найден в .env файле!")
    exit(1)

if not os.getenv("D360_API_KEY"):
    logger.error("❌ ОШИБКА: D360_API_KEY не найден в .env файле!")
    exit(1)


@app.route('/webhook', methods=['GET'])
def webhook_verify():
    """
    GET /webhook - верификация вебхука от 360dialog.
    
    360dialog отправляет GET запрос с параметрами:
    - hub.mode: должен быть "subscribe"
    - hub.verify_token: должен совпадать с VERIFY_TOKEN
    - hub.challenge: строка, которую нужно вернуть для подтверждения
    
    Returns:
        - hub.challenge если токен совпадает
        - 403 если токен не совпадает
    """
    # Получаем параметры из query string
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    logger.info(f"📥 GET /webhook - mode={mode}, token={'***' if token else None}, challenge={'***' if challenge else None}")
    
    # Проверяем токен
    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("✅ Webhook verified successfully!")
            # Возвращаем challenge для подтверждения
            return challenge if challenge else "ok", 200
        else:
            logger.warning("⚠️ Verification token mismatch!")
            return "Forbidden", 403
    
    logger.warning("⚠️ Missing verification parameters")
    return "Bad Request", 400


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """
    POST /webhook - обработка входящих сообщений от 360dialog.
    
    Получает JSON payload с данными о входящих сообщениях, статусах и т.д.
    Всегда возвращает 200 OK в течение 3 секунд (требование WhatsApp).
    
    Returns:
        JSON response с статусом 200
    """
    # Безопасное чтение JSON (silent=True предотвращает exception при невалидном JSON)
    data = request.get_json(silent=True)
    
    # Логируем полный payload для отладки
    logger.info(f"📨 POST /webhook - Получен payload: {data}")
    
    # Проверяем что данные есть
    if not data:
        logger.warning("⚠️ Пустой или невалидный JSON payload")
        return jsonify({"status": "ok"}), 200
    
    # Обрабатываем входящие сообщения в отдельной функции
    try:
        handle_incoming_message(data)
    except Exception as e:
        # Ловим все исключения чтобы всегда вернуть 200
        logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)
    
    # Всегда возвращаем 200 OK (требование WhatsApp API)
    return jsonify({"status": "ok"}), 200


def handle_incoming_message(data: dict):
    """
    Обрабатывает входящие сообщения из webhook payload.
    
    Структура payload от 360dialog/WhatsApp:
    {
      "entry": [
        {
          "changes": [
            {
              "value": {
                "messages": [
                  {
                    "from": "79991234567",
                    "type": "text" | "interactive",
                    "text": {"body": "текст"},
                    "interactive": {
                      "type": "button_reply" | "list_reply",
                      "button_reply": {"id": "BTN_ID", "title": "Кнопка"},
                      "list_reply": {"id": "LIST_ID", "title": "Элемент"}
                    }
                  }
                ]
              }
            }
          ]
        }
      ]
    }
    
    Args:
        data: Словарь с данными от 360dialog
    """
    # Защита от пустых/нестандартных payload'ов
    try:
        # Проходим по всем entry (обычно один элемент)
        entries = data.get("entry", [])
        if not entries:
            logger.info("ℹ️ Нет entry в payload")
            return
        
        for entry in entries:
            # Проходим по всем changes
            changes = entry.get("changes", [])
            for change in changes:
                # Получаем value с сообщениями
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                # Обрабатываем каждое сообщение
                for msg in messages:
                    process_single_message(msg)
                    
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_incoming_message: {e}", exc_info=True)


def process_single_message(msg: dict):
    """
    Обрабатывает одно входящее сообщение.
    
    Args:
        msg: Словарь с данными сообщения
    """
    try:
        # Получаем номер отправителя (без +)
        from_ = msg.get("from")
        if not from_:
            logger.warning("⚠️ Сообщение без поля 'from'")
            return
        
        # Получаем тип сообщения
        msg_type = msg.get("type")
        
        logger.info(f"💬 Сообщение от {from_}, тип: {msg_type}")
        
        # Обработка текстового сообщения
        if msg_type == "text":
            text_body = msg.get("text", {}).get("body", "").strip().lower()
            logger.info(f"📝 Текст: {text_body}")
            
            # Команды запуска бота
            if text_body in ["меню", "menu", "start", "старт", "привет"]:
                send_main_menu(from_)
            else:
                # На любой другой текст тоже показываем меню
                send_main_menu(from_)
        
        # Обработка интерактивных элементов (кнопки/списки)
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            itype = interactive.get("type")
            
            logger.info(f"🎯 Интерактив, подтип: {itype}")
            
            # Обработка button_reply (ответ на кнопку)
            if itype == "button_reply":
                button_reply = interactive.get("button_reply", {})
                button_id = button_reply.get("id")
                button_title = button_reply.get("title")
                
                logger.info(f"🔘 Кнопка: id={button_id}, title={button_title}")
                
                # Обрабатываем кнопку главного меню
                if button_id:
                    handle_main_menu_button(from_, button_id)
            
            # Обработка list_reply (выбор из списка)
            elif itype == "list_reply":
                list_reply = interactive.get("list_reply", {})
                list_id = list_reply.get("id")
                list_title = list_reply.get("title")
                
                logger.info(f"📋 Список: id={list_id}, title={list_title}")
                
                # Обрабатываем выбор смены
                if list_id:
                    handle_shift_selection(from_, list_id, list_title)
        
        else:
            logger.info(f"ℹ️ Неподдерживаемый тип сообщения: {msg_type}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка в process_single_message: {e}", exc_info=True)


@app.route('/health', methods=['GET'])
def health_check():
    """
    Простой health check endpoint для проверки работоспособности сервера.
    
    Returns:
        JSON с информацией о статусе
    """
    return jsonify({
        "status": "ok",
        "service": "whatsapp-bot",
        "mode": MODE
    }), 200


@app.route('/', methods=['GET'])
def index():
    """
    Корневой endpoint для проверки что сервер запущен.
    
    Returns:
        Простой текстовый ответ
    """
    return "WhatsApp Bot is running! 🤖", 200


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 WhatsApp Bot Starting...")
    logger.info("=" * 50)
    logger.info(f"📡 Mode: {MODE}")
    logger.info(f"🔐 Verify Token: {'***' if VERIFY_TOKEN else 'NOT SET'}")
    logger.info(f"🔑 API Key: {'***' if os.getenv('D360_API_KEY') else 'NOT SET'}")
    logger.info(f"🌐 Server: 0.0.0.0:{PORT}")
    logger.info("=" * 50)
    
    # Запуск Flask приложения
    # host=0.0.0.0 позволяет принимать соединения извне (не только localhost)
    app.run(host="0.0.0.0", port=PORT, debug=(MODE == "dev"))
