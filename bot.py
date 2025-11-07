# bot.py
"""
Главный файл WhatsApp бота для 360dialog API.
Запускает Flask сервер и регистрирует webhook.
"""
import logging
from flask import Flask
from webhook import webhook_bp
from config import SERVER_HOST, SERVER_PORT

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

