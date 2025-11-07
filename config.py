# config.py
"""
Конфигурация бота из переменных окружения.
"""
import os
from dotenv import load_dotenv

# Загрузка переменных из .env
load_dotenv()

# 360dialog API настройки
D360_API_KEY = os.getenv("D360_API_KEY")
D360_BASE_URL = os.getenv("D360_BASE_URL", "https://waba-v2.360dialog.io")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# Google Sheets настройки
SHEETS_CREDENTIALS = os.getenv("SHEETS_CREDENTIALS", "credentials.json")
SHEET_ID = os.getenv("SHEET_ID", "")

# Сервер настройки
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Админы (номера телефонов)
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")
ADMIN_IDS = [admin_id.strip() for admin_id in ADMIN_IDS if admin_id.strip()]

# База данных
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Таймзона
TZ = os.getenv("TZ", "Europe/Moscow")

# Проверка обязательных параметров
if not D360_API_KEY:
    raise ValueError("❌ D360_API_KEY не найден в .env файле!")

if not VERIFY_TOKEN:
    raise ValueError("❌ VERIFY_TOKEN не найден в .env файле!")

print("✅ Конфигурация загружена успешно")
print(f"📡 360dialog API URL: {D360_BASE_URL}")
print(f"🔑 API Key: {D360_API_KEY[:10]}...")
print(f"👥 Админов: {len(ADMIN_IDS)}")

