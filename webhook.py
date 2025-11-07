# webhook.py
"""
Обработка webhook запросов от 360dialog.
"""
import logging
from flask import Blueprint, request, jsonify
from config import VERIFY_TOKEN
from menu_handlers import handle_incoming_message

logger = logging.getLogger(__name__)

# Создаём Blueprint для webhook
webhook_bp = Blueprint('webhook', __name__)


@webhook_bp.route('/webhook', methods=['GET'])
def webhook_verify():
    """
    GET /webhook - верификация webhook от 360dialog.
    
    360dialog отправляет запрос с параметрами:
    - hub.mode = "subscribe"
    - hub.verify_token = токен для проверки
    - hub.challenge = строка для ответа
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    logger.info(f"📥 Получен запрос верификации webhook: mode={mode}, token={'***' if token else None}")
    
    # Проверяем токен
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("✅ Webhook верифицирован успешно")
        return challenge, 200
    else:
        logger.warning("❌ Ошибка верификации webhook: неверный токен")
        return 'Forbidden', 403


@webhook_bp.route('/webhook', methods=['POST'])
def webhook_receive():
    """
    POST /webhook - приём входящих сообщений от 360dialog.
    
    Структура данных от 360dialog:
    {
        "messages": [{
            "from": "79991234567",
            "id": "message_id",
            "timestamp": "1234567890",
            "type": "text",
            "text": {"body": "Hello"}
        }]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            logger.warning("⚠️ Получен пустой webhook запрос")
            return jsonify({"status": "error", "message": "No data"}), 400
        
        logger.info(f"📨 Получен webhook: {data}")
        
        # Обработка сообщений
        messages = data.get('messages', [])
        
        for message in messages:
            try:
                handle_incoming_message(message)
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)
        
        # Обработка статусов доставки (опционально)
        statuses = data.get('statuses', [])
        if statuses:
            logger.debug(f"📊 Получены статусы: {statuses}")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook_receive: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@webhook_bp.route('/health', methods=['GET'])
def health_check():
    """
    GET /health - проверка работоспособности сервера.
    """
    return jsonify({
        "status": "healthy",
        "service": "WhatsApp Bot 360dialog"
    }), 200

