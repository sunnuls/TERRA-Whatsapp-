# bot.py
"""
Главный файл WhatsApp бота для 360dialog API.
Запускает Flask сервер и регистрирует webhook.
"""
import logging
import requests
from flask import Flask
from webhook import webhook_bp
from config import SERVER_HOST, SERVER_PORT, D360_BASE_URL, get_headers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Создание Flask приложения
app = Flask(__name__)

# Регистрация Blueprint с webhook
app.register_blueprint(webhook_bp)


def send_message(to: str, data: dict) -> bool:
    """
    Отправить сообщение через 360dialog API.
    
    Args:
        to: Номер телефона получателя (формат: 79991234567)
        data: Данные сообщения (text, interactive, и т.д.)
    
    Returns:
        bool: True если отправлено успешно
    """
    url = f"{D360_BASE_URL}/v1/messages"
    
    payload = {
        "recipient_type": "individual",
        "to": to,
        **data
    }
    
    try:
        logger.info(f"[SEND] Отправка сообщения {to}")
        response = requests.post(url, json=payload, headers=get_headers(), timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"[OK] Сообщение отправлено {to}")
            return True
        else:
            logger.error(f"[ERROR] Ошибка отправки: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"[ERROR] Исключение при отправке: {e}", exc_info=True)
        return False


def send_buttons(to: str, text: str, buttons: list) -> bool:
    """
    Отправить сообщение с интерактивными кнопками.
    
    Args:
        to: Номер телефона
        text: Текст сообщения
        buttons: Список кнопок [{"id": "btn1", "title": "Кнопка 1"}, ...]
                 Максимум 3 кнопки
    
    Returns:
        bool: True если отправлено успешно
    """
    button_components = []
    for btn in buttons[:3]:  # Максимум 3 кнопки
        button_components.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["title"][:20]  # Максимум 20 символов
            }
        })
    
    data = {
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
    
    return send_message(to, data)


def send_list(to: str, text: str, button_text: str, sections: list) -> bool:
    """
    Отправить сообщение со списком (list message).
    
    Args:
        to: Номер телефона
        text: Текст сообщения
        button_text: Текст кнопки открытия списка
        sections: Список секций со строками
            Example:
            [
                {
                    "title": "Секция 1",
                    "rows": [
                        {"id": "row1", "title": "Строка 1", "description": "Описание 1"},
                        {"id": "row2", "title": "Строка 2", "description": "Описание 2"}
                    ]
                }
            ]
    
    Returns:
        bool: True если отправлено успешно
    """
    data = {
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
    
    return send_message(to, data)


@app.route('/')
def index():
    """
    Главная страница (для проверки работы сервера).
    """
    return '''
    <html>
        <head>
            <title>WhatsApp Bot 360dialog</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                    background: #f5f5f5;
                }
                .container {
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                h1 { color: #25D366; }
                .status { 
                    color: #25D366; 
                    font-weight: bold;
                }
                ul { 
                    line-height: 2;
                    list-style: none;
                }
                li:before {
                    content: "✅ ";
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 WhatsApp Bot 360dialog</h1>
                <p class="status">✅ Сервер работает</p>
                <h3>Доступные endpoints:</h3>
                <ul>
                    <li><code>GET /webhook</code> - верификация webhook</li>
                    <li><code>POST /webhook</code> - приём сообщений</li>
                    <li><code>GET /health</code> - проверка здоровья</li>
                </ul>
            </div>
        </body>
    </html>
    '''


def main():
    """
    Запуск Flask сервера.
    """
    logger.info("=" * 60)
    logger.info("🚀 Запуск WhatsApp бота для 360dialog")
    logger.info("=" * 60)
    logger.info(f"📡 Сервер: http://{SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"🔗 Webhook URL: http://{SERVER_HOST}:{SERVER_PORT}/webhook")
    logger.info("=" * 60)
    
    # Инициализация Google Sheets
    logger.info("📊 Инициализация Google Sheets...")
    from utils.sheets import init_sheets
    if init_sheets():
        logger.info("✅ Google Sheets готов к работе")
    else:
        logger.warning("⚠️ Google Sheets не инициализирован (работа продолжится без сохранения в таблицу)")
    
    logger.info("=" * 60)
    
    try:
        # Запуск Flask сервера
        app.run(
            host=SERVER_HOST,
            port=SERVER_PORT,
            debug=False,  # В продакшене должен быть False
            use_reloader=False
        )
    except KeyboardInterrupt:
        logger.info("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    main()

