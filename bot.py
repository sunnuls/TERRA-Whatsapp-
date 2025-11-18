# bot.py
"""
WhatsApp Bot using Flask + 360dialog API
Handles webhook events and sends automatic replies
"""

import os
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configuration
D360_API_KEY = os.getenv("D360_API_KEY")
D360_BASE_URL = "https://waba.360dialog.io/v1/messages"

# Validate required environment variables
if not D360_API_KEY:
    print("ERROR: D360_API_KEY not found in .env file!")
    exit(1)


def send_whatsapp_message(to, text):
    """
    Sends a text message via 360dialog API.
    
    Args:
        to: Phone number of recipient (format: 79991234567)
        text: Message text to send
    """
    payload = {
        "to": to,
        "type": "text",
        "text": {
            "body": text
        }
    }
    
    headers = {
        "D360-API-KEY": D360_API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            D360_BASE_URL,
            json=payload,
            headers=headers,
            timeout=20
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ Message sent successfully to {to}")
        else:
            print(f"❌ Error sending message: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Exception while sending message: {e}")


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    """
    Webhook endpoint to receive events from 360dialog.
    GET: Health check / verification
    POST: Parses ALL incoming events and sends automatic reply for text messages.
    """
    if request.method == "GET":
        return "OK", 200
    
    # POST request handling
    data = request.json
    print("Incoming:", json.dumps(data, indent=4, ensure_ascii=False))

    try:
        # Extract messages from different payload formats
        messages = []
        
        # Format 1: messages directly in root
        if "messages" in data:
            messages = data["messages"]
        
        # Format 2: messages in entry -> changes -> value
        elif "entry" in data:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        messages.extend(value["messages"])
        
        # Process each message
        for message in messages:
            sender = message.get("from")
            msg_type = message.get("type")
            
            # Extract text content if present
            text = ""
            if msg_type == "text":
                text = message.get("text", {}).get("body", "")
            
            # Send automatic reply for text messages
            if sender and text:
                send_whatsapp_message(sender, f"Ты написал: {text}")
            elif sender:
                # Log other message types (location, contacts, etc.)
                print(f"Received {msg_type} message from {sender} (not replying)")

    except Exception as e:
        print("Error:", e)

    return jsonify({"status": "ok"})


@app.route("/", methods=["GET"])
def root():
    """
    Root endpoint for health check.
    """
    return "OK", 200


if __name__ == "__main__":
    # Run Flask server on port 8000
    app.run(host="0.0.0.0", port=8000)
