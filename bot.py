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
    GET /webhook - health-check endpoint для 360dialog.
    Всегда возвращает "OK", 200 для совместимости.
    """
    logger.info("GET /webhook - health-check request")
    # Просто возвращаем OK, без проверки параметров
    return "OK", 200


@app.route('/webhook', methods=['POST'])
def webhook_legacy():
    """
    Legacy webhook endpoint. Работает так же, как '/' для POST.
    """
    try:
        data = request.get_json(force=True, silent=True)
        logger.info("POST /webhook - Incoming webhook payload: %s", data)
        handle_incoming_update(data)
    except Exception as e:
        logger.exception("Error while handling webhook on '/webhook': %s", e)

    return "OK", 200


def handle_incoming_update(data: dict | None) -> None:
    """
    Общая точка входа для обработки входящих webhook-данных от 360dialog.
    data - словарь с JSON телом запроса.
    
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
        data: Словарь с данными от 360dialog (может быть None)
    """
    # Защита от пустых/нестандартных payload'ов
    if not data:
        logger.info("handle_incoming_update called with empty data")
        return
    
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
        logger.error(f"❌ Ошибка в handle_incoming_update: {e}", exc_info=True)


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


@app.route('/', methods=['GET', 'POST'])
def webhook_root():
    """
    Root webhook endpoint for 360dialog.
    GET  - health-check, возвращает "OK".
    POST - приём webhook-событий от 360dialog.
    """
    if request.method == 'GET':
        logger.info("GET / - health-check request")
        return "OK", 200

    # POST - обработка webhook событий
    try:
        data = request.get_json(force=True, silent=True)
        logger.info("POST / - Incoming webhook payload: %s", data)
        handle_incoming_update(data)
    except Exception as e:
        logger.exception("Error while handling webhook on '/': %s", e)

    # Всегда возвращаем 200 OK, чтобы 360dialog не показывал 404/500
    return "OK", 200


if __name__ == '__main__':
    # Чтение переменных окружения для хоста и порта
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", os.getenv("PORT", "8000")))

    logger.info("=============================================")
    logger.info(" WhatsApp Bot Starting...")
    logger.info("  Mode: %s", MODE)
    logger.info("  Server: %s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("=============================================")

    # Запуск без debug режима и reloader для стабильной работы с ngrok
    app.run(host=SERVER_HOST, port=SERVER_PORT)
