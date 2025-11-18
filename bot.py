import os
import sys
import json
import traceback

from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests

# Загружаем .env
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "terra_bot_verify_token_2024")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

if not WHATSAPP_TOKEN:
    print("❌ ERROR: WHATSAPP_TOKEN is not set in .env")
    sys.exit(1)

# v2 API
API_URL = "https://waba-v2.360dialog.io/messages"

HEADERS = {
    "D360-API-KEY": WHATSAPP_TOKEN,
    "Content-Type": "application/json"
}

app = Flask(__name__)


def log_request(label: str, data):
    """Красиво логируем входящие/исходящие данные"""
    print(f"\n=== {label} ===")
    try:
        print(json.dumps(data, indent=4, ensure_ascii=False))
    except Exception:
        print(str(data))
    print("=== END ===\n")


def send_text_message(to: str, text: str):
    """Отправка обычного текстового сообщения через 360dialog v2"""
    payload = {
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "body": text,
            "preview_url": False
        }
    }

    log_request("SEND TEXT PAYLOAD", payload)
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    try:
        body = resp.json()
    except Exception:
        body = resp.text

    print(f"SEND TEXT RESPONSE: {resp.status_code} {body}")
    return resp


def send_menu_buttons(to: str):
    """Отправка меню с кнопками BTN_START и BTN_MENU"""
    payload = {
        "to": to,
        "type": "interactive",
        "recipient_type": "individual",
        "interactive": {
            "type": "button",
            "body": {
                "text": "Выберите действие:"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "BTN_START",
                            "title": "Старт"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "BTN_MENU",
                            "title": "Меню"
                        }
                    }
                ]
            }
        }
    }

    log_request("SEND MENU PAYLOAD", payload)
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    try:
        body = resp.json()
    except Exception:
        body = resp.text

    print(f"SEND BUTTONS RESPONSE: {resp.status_code} {body}")
    return resp


def normalize_text(text: str) -> str:
    return (text or "").strip().lower()


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Верификация webhook 360dialog (GET)"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print(f"Webhook VERIFY: mode={mode}, token={token}, challenge={challenge}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification token mismatch", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Основной обработчик входящих сообщений WhatsApp"""
    data = request.get_json(force=True, silent=True) or {}
    log_request("INCOMING", data)

    try:
        # Структура 360dialog / Meta:
        # object -> entry[0] -> changes[0] -> value
        entry = (data.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value", {})

        messages = value.get("messages", [])
        contacts = value.get("contacts", [])

        if not messages:
            return jsonify({"status": "no messages"}), 200

        msg = messages[0]

        # Определяем wa_id пользователя
        wa_id = None
        if contacts:
            wa_id = contacts[0].get("wa_id")
        if not wa_id:
            wa_id = msg.get("from")

        msg_type = msg.get("type")

        # --- ТЕКСТОВЫЕ СООБЩЕНИЯ ---
        if msg_type == "text":
            text_body = msg.get("text", {}).get("body", "")
            norm = normalize_text(text_body)

            print(f"➡ TEXT from {wa_id}: {text_body} (norm: {norm})")

            if norm in ("start", "/start", "старт"):
                send_text_message(wa_id, "Привет! Это Terra Bot 🌱")
                send_menu_buttons(wa_id)

            elif norm in ("menu", "меню"):
                send_menu_buttons(wa_id)

            else:
                # Можно просто ничего не отвечать или отправлять дефолт
                send_text_message(
                    wa_id,
                    "Я тебя понял, но пока реагирую только на команды: start / меню."
                )

        # --- НАЖАТИЯ КНОПОК ---
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})

            button_id = None

            # Вариант 1: button_reply (Meta / 360dialog)
            if "button_reply" in interactive:
                button_id = interactive["button_reply"].get("id")

            # Вариант 2: button.reply.id
            elif "button" in interactive and "reply" in interactive["button"]:
                button_id = interactive["button"]["reply"].get("id")

            print(f"➡ BUTTON from {wa_id}: {button_id}")

            if button_id == "BTN_START":
                send_text_message(wa_id, "🚀 Запуск! Бот готов работать.")
                send_menu_buttons(wa_id)

            elif button_id == "BTN_MENU":
                send_menu_buttons(wa_id)

        else:
            print(f"❔ Unsupported message type: {msg_type}")

    except Exception as e:
        print("❌ ERROR in handle_webhook:", repr(e))
        traceback.print_exc()

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    print(f"Starting Terra Bot on {SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT)
