# bot_polya_whatsapp.py
# -*- coding: utf-8 -*-

import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, date
from typing import Dict, Optional, Tuple, List, Callable, Any
from pathlib import Path
from dataclasses import dataclass
import calendar
import logging

from pywa import WhatsApp
from pywa.types import Message as WAMessage, Button
from pywa.filters import text
from dotenv import load_dotenv
from flask import Flask

# Google Sheets API
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scheduler для автоматического экспорта
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# -----------------------------
# Конфиг
# -----------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO)

# WhatsApp настройки
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# WA: critical env check
if not WHATSAPP_TOKEN:
    logging.error("❌ Ошибка: WHATSAPP_TOKEN не найден в .env")
    sys.exit(1)

if not WHATSAPP_PHONE_ID:
    logging.error("❌ Ошибка: WHATSAPP_PHONE_ID не найден в .env")
    sys.exit(1)

if not VERIFY_TOKEN:
    logging.error("VERIFY_TOKEN is not set in environment")
    sys.exit(1)

TZ = os.getenv("TZ", "Europe/Moscow").strip()

def _parse_admin_ids(s: str) -> List[str]:
    out = []
    for part in (s or "").replace(" ", "").split(","):
        if not part:
            continue
        out.append(part.strip())
    return out

ADMIN_IDS = set(_parse_admin_ids(os.getenv("ADMIN_IDS", "")))

DB_PATH = os.path.join(os.getcwd(), "reports_whatsapp.db")

# Google Sheets настройки
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]
OAUTH_CLIENT_JSON = os.getenv("OAUTH_CLIENT_JSON", "oauth_client.json")
TOKEN_JSON_PATH = Path(os.getenv("TOKEN_JSON_PATH", "token.json"))
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")
EXPORT_PREFIX = os.getenv("EXPORT_PREFIX", "WorkLog")

# Расписание автоматического экспорта
AUTO_EXPORT_ENABLED = os.getenv("AUTO_EXPORT_ENABLED", "false").lower() == "true"
AUTO_EXPORT_CRON = os.getenv("AUTO_EXPORT_CRON", "0 9 * * 1")

# -----------------------------
# Константы (дефолтные справочники)
# -----------------------------

DEFAULT_FIELDS = [
    "Северное","Фазенда","5 га","58 га","Фермерское","Сад",
    "Чеки №1","Чеки №2","Чеки №3","Рогачи (б)","Рогачи(М)",
    "Владимирова Аренда","МТФ",
]

DEFAULT_TECH = [
    "пахота","чизелевание","дискование","культивация сплошная",
    "культивация междурядная","опрыскивание","комбайн уборка","сев","барнование",
]

DEFAULT_HAND = [
    "прополка","сбор","полив","монтаж","ремонт",
]

GROUP_TECH = "техника"
GROUP_HAND = "ручная"
GROUP_FIELDS = "поля"
GROUP_WARE = "склад"

# -----------------------------
# Хранилище состояний пользователей (в памяти)
# -----------------------------

user_states: Dict[str, dict] = {}

# TODO: вынести FSM в SQLite (user_state) для надёжности при перезапуске.
def get_state(user_id: str) -> dict:
    if user_id not in user_states:
        user_states[user_id] = {"state": None, "data": {}}
    return user_states[user_id]

# TODO: вынести FSM в SQLite (user_state) для надёжности при перезапуске.
def set_state(user_id: str, state: Optional[str], data: dict = None):
    s = get_state(user_id)
    s["state"] = state
    if data is not None:
        s["data"] = data

# TODO: вынести FSM в SQLite (user_state) для надёжности при перезапуске.
def clear_state(user_id: str):
    user_states[user_id] = {"state": None, "data": {}}

# -----------------------------
# БД (те же функции, что в Telegram версии)
# -----------------------------

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as con, closing(con.cursor()) as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
          user_id    TEXT PRIMARY KEY,
          full_name  TEXT,
          tz         TEXT,
          created_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS activities(
          id    INTEGER PRIMARY KEY AUTOINCREMENT,
          name  TEXT UNIQUE,
          grp   TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS locations(
          id    INTEGER PRIMARY KEY AUTOINCREMENT,
          name  TEXT UNIQUE,
          grp   TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS reports(
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at    TEXT,
          user_id       TEXT,
          reg_name      TEXT,
          location      TEXT,
          location_grp  TEXT,
          activity      TEXT,
          activity_grp  TEXT,
          work_date     TEXT,
          hours         INTEGER
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS google_exports(
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          report_id     INTEGER UNIQUE,
          spreadsheet_id TEXT,
          sheet_name    TEXT,
          row_number    INTEGER,
          exported_at   TEXT,
          last_updated  TEXT,
          FOREIGN KEY (report_id) REFERENCES reports(id)
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS monthly_sheets(
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          year          INTEGER,
          month         INTEGER,
          spreadsheet_id TEXT,
          sheet_url     TEXT,
          created_at    TEXT,
          UNIQUE(year, month)
        )
        """)

        def table_cols(table: str):
            return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}

        lcols = table_cols("locations")
        if "grp" not in lcols:
            c.execute("ALTER TABLE locations ADD COLUMN grp TEXT")
            c.execute("UPDATE locations SET grp=? WHERE (grp IS NULL OR grp='') AND name='Склад'", (GROUP_WARE,))
            c.execute("UPDATE locations SET grp=? WHERE (grp IS NULL OR grp='') AND name<>'Склад'", (GROUP_FIELDS,))

        acols = table_cols("activities")
        if "grp" not in acols:
            c.execute("ALTER TABLE activities ADD COLUMN grp TEXT")
            placeholders = ",".join("?" * len(DEFAULT_TECH))
            if placeholders:
                c.execute(
                    f"UPDATE activities SET grp=? WHERE (grp IS NULL OR grp='') AND name IN ({placeholders})",
                    (GROUP_TECH, *DEFAULT_TECH)
                )
            c.execute("UPDATE activities SET grp=? WHERE (grp IS NULL OR grp='')", (GROUP_HAND,))

        for name in DEFAULT_FIELDS:
            c.execute("INSERT OR IGNORE INTO locations(name, grp) VALUES (?, ?)", (name, GROUP_FIELDS))
        c.execute("INSERT OR IGNORE INTO locations(name, grp) VALUES (?, ?)", ("Склад", GROUP_WARE))

        for name in DEFAULT_TECH:
            c.execute("INSERT OR IGNORE INTO activities(name, grp) VALUES (?, ?)", (name, GROUP_TECH))
        for name in DEFAULT_HAND:
            c.execute("INSERT OR IGNORE INTO activities(name, grp) VALUES (?, ?)", (name, GROUP_HAND))

        con.commit()

def upsert_user(user_id: str, full_name: Optional[str], tz: str):
    now = datetime.now().isoformat()
    with connect() as con, closing(con.cursor()) as c:
        row = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            c.execute("UPDATE users SET full_name=?, tz=?, created_at=? WHERE user_id=?",
                      (full_name, tz, now, user_id))
        else:
            c.execute("INSERT INTO users(user_id, full_name, tz, created_at) VALUES(?,?,?,?)",
                      (user_id, full_name, tz, now))
        con.commit()

def get_user(user_id: str):
    with connect() as con, closing(con.cursor()) as c:
        r = c.execute("SELECT user_id, full_name, tz, created_at FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not r:
            return None
        return {
            "user_id": r[0],
            "full_name": r[1],
            "tz": r[2] or TZ,
            "created_at": r[3],
        }

def list_activities(grp: str) -> List[str]:
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("SELECT name FROM activities WHERE grp=? ORDER BY name", (grp,)).fetchall()
        return [r[0] for r in rows]

def list_activities_with_id(grp: str) -> List[Tuple[int, str]]:
    """
    Возвращает список (id, name) для видов работ в группе.
    Используется для формирования кнопок с ID в callback_data.
    """
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("SELECT id, name FROM activities WHERE grp=? ORDER BY name", (grp,)).fetchall()
        return [(r[0], r[1]) for r in rows]

def get_activity_name(act_id: int) -> Optional[Tuple[str, str]]:
    """
    Возвращает (name, grp) для activity по ID или None, если не найдено.
    """
    with connect() as con, closing(con.cursor()) as c:
        r = c.execute("SELECT name, grp FROM activities WHERE id=?", (act_id,)).fetchone()
        if not r:
            return None
        return (r[0], r[1])

def add_activity(grp: str, name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    with connect() as con, closing(con.cursor()) as c:
        try:
            c.execute("INSERT INTO activities(name, grp) VALUES(?,?)", (name, grp))
            con.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def remove_activity(name: str) -> bool:
    with connect() as con, closing(con.cursor()) as c:
        cur = c.execute("DELETE FROM activities WHERE name=?", (name,))
        con.commit()
        return cur.rowcount > 0

def list_locations(grp: str) -> List[str]:
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("SELECT name FROM locations WHERE grp=? ORDER BY name", (grp,)).fetchall()
        return [r[0] for r in rows]

def list_locations_with_id(grp: str) -> List[Tuple[int, str]]:
    """
    Возвращает список (id, name) для локаций в группе.
    Используется для формирования кнопок с ID в callback_data.
    """
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("SELECT id, name FROM locations WHERE grp=? ORDER BY name", (grp,)).fetchall()
        return [(r[0], r[1]) for r in rows]

def get_location_name(loc_id: int) -> Optional[Tuple[str, str]]:
    """
    Возвращает (name, grp) для location по ID или None, если не найдено.
    """
    with connect() as con, closing(con.cursor()) as c:
        r = c.execute("SELECT name, grp FROM locations WHERE id=?", (loc_id,)).fetchone()
        if not r:
            return None
        return (r[0], r[1])

def add_location(grp: str, name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    with connect() as con, closing(con.cursor()) as c:
        try:
            c.execute("INSERT INTO locations(name, grp) VALUES(?,?)", (name, grp))
            con.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def remove_location(name: str) -> bool:
    with connect() as con, closing(con.cursor()) as c:
        cur = c.execute("DELETE FROM locations WHERE name=?", (name,))
        con.commit()
        return cur.rowcount > 0

def insert_report(user_id:str, reg_name:str, location:str, loc_grp:str,
                  activity:str, act_grp:str, work_date:str, hours:int) -> int:
    now = datetime.now().isoformat()
    with connect() as con, closing(con.cursor()) as c:
        c.execute("""
        INSERT INTO reports(created_at, user_id, reg_name, location, location_grp,
                            activity, activity_grp, work_date, hours)
        VALUES(?,?,?,?,?,?,?,?,?)
        """, (now, user_id, reg_name, location, loc_grp, activity, act_grp, work_date, hours))
        con.commit()
        return c.lastrowid

def get_report(report_id:int):
    with connect() as con, closing(con.cursor()) as c:
        r = c.execute(
            "SELECT id, created_at, user_id, reg_name, location, location_grp, activity, activity_grp, work_date, hours FROM reports WHERE id=?",
            (report_id,)
        ).fetchone()
        if not r:
            return None
        return {
            "id": r[0], "created_at": r[1], "user_id": r[2], "reg_name": r[3],
            "location": r[4], "location_grp": r[5], "activity": r[6], "activity_grp": r[7],
            "work_date": r[8], "hours": r[9]
        }

def sum_hours_for_user_date(user_id:str, work_date:str, exclude_report_id: Optional[int] = None) -> int:
    with connect() as con, closing(con.cursor()) as c:
        if exclude_report_id:
            r = c.execute("SELECT COALESCE(SUM(hours),0) FROM reports WHERE user_id=? AND work_date=? AND id<>?",
                          (user_id, work_date, exclude_report_id)).fetchone()
        else:
            r = c.execute("SELECT COALESCE(SUM(hours),0) FROM reports WHERE user_id=? AND work_date=?",
                          (user_id, work_date)).fetchone()
        return int(r[0] or 0)

def user_recent_24h_reports(user_id:str) -> List[tuple]:
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("""
        SELECT id, work_date, activity, location, hours, created_at
        FROM reports
        WHERE user_id=? AND created_at>=?
        ORDER BY created_at DESC
        """, (user_id, cutoff)).fetchall()
        return rows

def delete_report(report_id:int, user_id:str) -> bool:
    with connect() as con, closing(con.cursor()) as c:
        cur = c.execute("DELETE FROM reports WHERE id=? AND user_id=?", (report_id, user_id))
        con.commit()
        return cur.rowcount > 0

def update_report_hours(report_id:int, user_id:str, new_hours:int) -> bool:
    with connect() as con, closing(con.cursor()) as c:
        cur = c.execute("UPDATE reports SET hours=? WHERE id=? AND user_id=?", (new_hours, report_id, user_id))
        con.commit()
        return cur.rowcount > 0

def fetch_stats_today_all():
    today = date.today().isoformat()
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("""
        SELECT r.user_id, u.full_name, r.location, r.activity, SUM(r.hours) as h
        FROM reports r
        LEFT JOIN users u ON u.user_id=r.user_id
        WHERE r.work_date=?
        GROUP BY r.user_id, r.location, r.activity
        ORDER BY u.full_name, r.location, r.activity
        """, (today,)).fetchall()
        return rows

def fetch_stats_range_for_user(user_id:str, start_date:str, end_date:str):
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("""
        SELECT work_date, location, activity, SUM(hours) as h
        FROM reports
        WHERE user_id=? AND work_date BETWEEN ? AND ?
        GROUP BY work_date, location, activity
        ORDER BY work_date DESC
        """, (user_id, start_date, end_date)).fetchall()
        return rows

def fetch_stats_range_all(start_date:str, end_date:str):
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("""
        SELECT u.full_name, work_date, location, activity, SUM(hours) as h
        FROM reports r
        LEFT JOIN users u ON u.user_id=r.user_id
        WHERE work_date BETWEEN ? AND ?
        GROUP BY u.full_name, work_date, location, activity
        ORDER BY work_date DESC, u.full_name
        """, (start_date, end_date)).fetchall()
        return rows

# -----------------------------
# Google Sheets API (та же логика)
# -----------------------------

def get_google_credentials():
    creds = None
    if TOKEN_JSON_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_JSON_PATH), GOOGLE_SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(OAUTH_CLIENT_JSON).exists():
                logging.error(f"OAuth client file not found: {OAUTH_CLIENT_JSON}")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_JSON, GOOGLE_SCOPES)
            try:
                creds = flow.run_local_server(port=0)
            except Exception:
                creds = flow.run_console()
        TOKEN_JSON_PATH.write_text(creds.to_json(), encoding="utf-8")
    
    return creds

def get_or_create_monthly_sheet(year: int, month: int):
    with connect() as con, closing(con.cursor()) as c:
        row = c.execute(
            "SELECT spreadsheet_id, sheet_url FROM monthly_sheets WHERE year=? AND month=?",
            (year, month)
        ).fetchone()
        
        if row:
            return row[0], row[1]
        
        try:
            creds = get_google_credentials()
            if not creds:
                return None, None
            
            drive = build("drive", "v3", credentials=creds)
            sheets = build("sheets", "v4", credentials=creds)
            
            sheet_name = f"{EXPORT_PREFIX}_WA_{year}_{month:02d}"
            
            file_metadata = {
                "name": sheet_name,
                "mimeType": "application/vnd.google-apps.spreadsheet",
            }
            if DRIVE_FOLDER_ID:
                file_metadata["parents"] = [DRIVE_FOLDER_ID]
            
            file = drive.files().create(
                body=file_metadata,
                fields="id, webViewLink"
            ).execute()
            
            spreadsheet_id = file["id"]
            sheet_url = file["webViewLink"]
            
            headers = [["Дата", "Фамилия Имя", "Место работы", "Вид работы", "Количество часов"]]
            sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="A1:E1",
                valueInputOption="RAW",
                body={"values": headers}
            ).execute()
            
            requests = [{
                "repeatCell": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": 0,
                        "endRowIndex": 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True}
                        }
                    },
                    "fields": "userEnteredFormat.textFormat.bold"
                }
            }]
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ).execute()
            
            c.execute(
                "INSERT INTO monthly_sheets(year, month, spreadsheet_id, sheet_url, created_at) VALUES(?,?,?,?,?)",
                (year, month, spreadsheet_id, sheet_url, datetime.now().isoformat())
            )
            con.commit()
            
            logging.info(f"Created new sheet for {year}-{month:02d}: {sheet_url}")
            return spreadsheet_id, sheet_url
            
        except HttpError as e:
            logging.error(f"Google API error: {e}")
            return None, None
        except Exception as e:
            logging.error(f"Error creating sheet: {e}")
            return None, None

def get_unexported_reports():
    with connect() as con, closing(con.cursor()) as c:
        rows = c.execute("""
        SELECT r.id, r.work_date, r.reg_name, r.location, r.activity, r.hours
        FROM reports r
        LEFT JOIN google_exports ge ON r.id = ge.report_id
        WHERE ge.report_id IS NULL
        ORDER BY r.work_date, r.created_at
        """).fetchall()
        return rows

def export_reports_to_sheets():
    unexported = get_unexported_reports()
    
    if not unexported:
        logging.info("No reports to export")
        return 0, "Нет новых отчетов для экспорта"
    
    try:
        creds = get_google_credentials()
        if not creds:
            return 0, "Ошибка авторизации Google"
        
        sheets_service = build("sheets", "v4", credentials=creds)
        
        reports_by_month = {}
        for report_id, work_date, name, location, activity, hours in unexported:
            d = datetime.fromisoformat(work_date)
            key = (d.year, d.month)
            if key not in reports_by_month:
                reports_by_month[key] = []
            reports_by_month[key].append((report_id, work_date, name, location, activity, hours))
        
        total_exported = 0
        
        for (year, month), reports in reports_by_month.items():
            spreadsheet_id, sheet_url = get_or_create_monthly_sheet(year, month)
            
            if not spreadsheet_id:
                logging.error(f"Failed to get/create sheet for {year}-{month}")
                continue
            
            try:
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range="A:E"
                ).execute()
                existing_values = result.get("values", [])
                next_row = len(existing_values) + 1
            except HttpError:
                next_row = 2
            
            values_to_append = []
            export_records = []
            
            for report_id, work_date, name, location, activity, hours in reports:
                values_to_append.append([work_date, name, location, activity, hours])
                export_records.append((report_id, spreadsheet_id, f"{year}-{month:02d}", next_row))
                next_row += 1
            
            if values_to_append:
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range="A:E",
                    valueInputOption="RAW",
                    body={"values": values_to_append}
                ).execute()
                
                now = datetime.now().isoformat()
                with connect() as con, closing(con.cursor()) as c:
                    for report_id, ss_id, sheet_name, row_num in export_records:
                        c.execute(
                            "INSERT INTO google_exports(report_id, spreadsheet_id, sheet_name, row_number, exported_at, last_updated) VALUES(?,?,?,?,?,?)",
                            (report_id, ss_id, sheet_name, row_num, now, now)
                        )
                    con.commit()
                
                total_exported += len(values_to_append)
                logging.info(f"Exported {len(values_to_append)} reports to {year}-{month:02d}")
        
        return total_exported, f"Экспортировано записей: {total_exported}"
        
    except HttpError as e:
        logging.error(f"Google API error during export: {e}")
        return 0, f"Ошибка Google API: {str(e)}"
    except Exception as e:
        logging.error(f"Error during export: {e}")
        return 0, f"Ошибка экспорта: {str(e)}"

def check_and_create_next_month_sheet():
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    days_until_end = last_day - today.day
    
    if days_until_end <= 3:
        if today.month == 12:
            next_year, next_month = today.year + 1, 1
        else:
            next_year, next_month = today.year, today.month + 1
        
        with connect() as con, closing(con.cursor()) as c:
            row = c.execute(
                "SELECT spreadsheet_id FROM monthly_sheets WHERE year=? AND month=?",
                (next_year, next_month)
            ).fetchone()
            
            if not row:
                logging.info(f"Creating sheet for next month: {next_year}-{next_month:02d}")
                spreadsheet_id, sheet_url = get_or_create_monthly_sheet(next_year, next_month)
                if spreadsheet_id:
                    return True, f"Создана таблица для {next_year}-{next_month:02d}: {sheet_url}"
                else:
                    return False, "Ошибка создания таблицы"
    
    return False, "Не требуется создание таблицы"

# -----------------------------
# WhatsApp бот
# -----------------------------

def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_IDS

# -----------------------------
# Pagination Helper (для соблюдения ограничения WhatsApp ≤3 кнопок)
# -----------------------------

@dataclass
class PaginationButton:
    """Структура для кнопки в пагинации."""
    title: str
    callback_data: str

def send_paginated_buttons(
    client: WhatsApp,
    to: str,
    text: str,
    items: list,
    make_button: Callable[[Any], PaginationButton | Button],
    state_key: str,
    page: int = 0,
    back_cb: Optional[str] = None
) -> None:
    """
    Стабильная пагинация под WhatsApp:
    - максимум 3 кнопки на экран;
    - на странице 1–2 item-кнопки + 1 навкнопка (⬅️ или ➡️) ИЛИ "Назад";
    - страничность не «плавает» — шаг всегда одинаковый.
    """
    if not items:
        client.send_message(to=to, text=f"{text}\n\n_(Список пуст)_")
        return

    base_capacity = 2  # столько item-кнопок помещаем на страницу стабильно
    total_items = len(items)
    total_pages = (total_items + base_capacity - 1) // base_capacity
    page = max(0, min(page, total_pages - 1))

    start = page * base_capacity
    end = min(start + base_capacity, total_items)
    page_items = items[start:end]

    has_prev = page > 0
    has_next = page < total_pages - 1

    # Сконструировать item-кнопки
    btns: list[Button] = []
    for it in page_items:
        b = make_button(it)
        if isinstance(b, Button):
            btns.append(b)
        else:
            btns.append(Button(title=b.title, callback_data=b.callback_data))

    # Навигация: приоритет одной стрелки, чтобы вместе с "Назад" не пробить лимит
    if has_prev and len(btns) < 3:
        btns.append(Button(title="⬅️", callback_data=f"nav:{state_key}:{page-1}"))
    elif has_next and len(btns) < 3:
        btns.append(Button(title="➡️", callback_data=f"nav:{state_key}:{page+1}"))

    if back_cb and len(btns) < 3:
        btns.append(Button(title="🔙 Назад", callback_data=back_cb))

    page_info = f"\n\n_Страница {page+1} из {total_pages}_" if total_pages > 1 else ""
    client.send_message(to=to, text=text + page_info, buttons=btns[:3])

def show_main_menu(wa: WhatsApp, user_id: str, u: dict):
    """
    Отображает главное меню с ограничением ≤3 кнопок.
    
    # WA: WhatsApp позволяет максимум 3 кнопки, поэтому основные действия
    # на первом экране, остальные через "Ещё..."
    """
    name = (u or {}).get("full_name") or "—"
    
    # WA: Первый экран - только 3 основные кнопки
    buttons = [
        Button(title="🚜 Работа", callback_data="menu:work"),
        Button(title="📊 Статистика", callback_data="menu:stats"),
        Button(title="Ещё...", callback_data="menu:more"),
    ]
    
    text = f"👤 *{name}*\n\nВыберите действие:"
    wa.send_message(to=user_id, text=text, buttons=buttons)

def show_more_menu(wa: WhatsApp, user_id: str):
    """
    Отображает дополнительное меню "Ещё..." с остальными опциями.
    
    # WA: Второй экран с дополнительными функциями, гарантированно ≤3 кнопки
    """
    admin = is_admin(user_id)
    
    buttons = []
    buttons.append(Button(title="📝 Перепись", callback_data="menu:edit"))
    buttons.append(Button(title="✏️ Имя", callback_data="menu:name"))
    if admin:
        buttons.append(Button(title="⚙️ Админ", callback_data="menu:admin"))

    # если больше 2 пунктов, делаем: первые 2 + Назад; иначе добавляем Назад третьей
    if len(buttons) > 2:
        buttons = buttons[:2] + [Button(title="🔙 Назад", callback_data="menu:root")]
    else:
        buttons.append(Button(title="🔙 Назад", callback_data="menu:root"))

    wa.send_message(to=user_id, text="Доп. меню:", buttons=buttons)

def render_edit_records_page(client: WhatsApp, user_id: str, records: list, page: int = 0):
    """
    Отображает страницу редактора записей.
    
    # WA: Показываем 1 запись с 2 кнопками действий (Править, Удалить) + навигация
    # Итого максимум 3 кнопки: либо [Править, Удалить, ⬅️/➡️/Назад]
    """
    if not records:
        client.send_message(to=user_id, text="📝 Записей нет.")
        return
    
    total_records = len(records)
    if page < 0:
        page = 0
    if page >= total_records:
        page = total_records - 1
    
    # Текущая запись
    rid, d, act, loc, h, created = records[page]
    
    text = (
        f"📝 *Запись {page + 1} из {total_records}*\n\n"
        f"ID: `#{rid}`\n"
        f"Дата: *{d}*\n"
        f"Место: *{loc}*\n"
        f"Работа: *{act}*\n"
        f"Часы: *{h}*\n"
        f"Создана: _{created[:16]}_\n\n"
        f"Листайте стрелками ⬅️/➡️, чтобы посмотреть другие записи."
    )
    
    buttons = []
    
    # WA: Кнопки действий для текущей записи
    buttons.append(Button(title="🖊 Править", callback_data=f"edit:chg:{rid}:{d}"))
    buttons.append(Button(title="🗑 Удалить", callback_data=f"edit:del:{rid}"))
    
    # WA: Навигация (если записей >1)
    if total_records > 1:
        if page > 0:
            buttons.append(Button(title="⬅️", callback_data=f"nav:edit_records:{page-1}"))
        elif page < total_records - 1:
            buttons.append(Button(title="➡️", callback_data=f"nav:edit_records:{page+1}"))
    
    # Если есть место, добавляем кнопку "Назад"
    if len(buttons) < 3:
        buttons.append(Button(title="🔙 Меню", callback_data="menu:root"))
    
    client.send_message(to=user_id, text=text, buttons=buttons[:3])  # WA: hard limit 3

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация WhatsApp клиента
wa = WhatsApp(
    token=WHATSAPP_TOKEN,
    phone_id=WHATSAPP_PHONE_ID,
    verify_token=VERIFY_TOKEN,
    server=app,
    webhook_endpoint="/webhook",
)

# -----------------------------
# Обработчики команд
# -----------------------------

@wa.on_message(text == "start")
def cmd_start(client: WhatsApp, msg: WAMessage):
    init_db()
    user_id = msg.from_user.wa_id
    upsert_user(user_id, None, TZ)
    u = get_user(user_id)
    
    if not u or not (u.get("full_name") or "").strip():
        set_state(user_id, "waiting_name")
        client.send_message(
            to=user_id,
            text="👋 Для начала введите *Фамилию Имя* (например: *Иванов Иван*)."
        )
        return
    
    show_main_menu(client, user_id, u)

@wa.on_message(text == "menu")
def cmd_menu(client: WhatsApp, msg: WAMessage):
    user_id = msg.from_user.wa_id
    u = get_user(user_id)
    show_main_menu(client, user_id, u)

@wa.on_message(text == "today")
def cmd_today(client: WhatsApp, msg: WAMessage):
    user_id = msg.from_user.wa_id
    admin = is_admin(user_id)
    
    if admin:
        rows = fetch_stats_today_all()
        if not rows:
            text = "📊 Сегодня записей нет."
        else:
            parts = ["📊 *Сегодня (все)*:"]
            cur_uid = None
            subtotal = 0
            for uid, full_name, loc, act, h in rows:
                if uid != cur_uid:
                    if cur_uid is not None:
                        parts.append(f"  — Итого сотрудник: *{subtotal}* ч\n")
                    cur_uid = uid
                    subtotal = 0
                    who = full_name or str(uid)
                    parts.append(f"\n👤 *{who}*")
                parts.append(f"  • {loc} — {act}: *{h}* ч")
                subtotal += h
            if cur_uid is not None:
                parts.append(f"  — Итого сотрудник: *{subtotal}* ч")
            text = "\n".join(parts)
    else:
        today = date.today().isoformat()
        rows = fetch_stats_range_for_user(user_id, today, today)
        if not rows:
            text = "📊 Сегодня у вас записей нет."
        else:
            parts = ["📊 *Сегодня*:"]
            total = 0
            for d, loc, act, h in rows:
                parts.append(f"• {loc} — {act}: *{h}* ч")
                total += h
            parts.append(f"\nИтого: *{total}* ч")
            text = "\n".join(parts)
    
    client.send_message(to=user_id, text=text)

@wa.on_message(text == "my")
def cmd_my(client: WhatsApp, msg: WAMessage):
    user_id = msg.from_user.wa_id
    admin = is_admin(user_id)
    end = date.today()
    start = end - timedelta(days=6)
    
    if admin:
        rows = fetch_stats_range_all(start.isoformat(), end.isoformat())
        if not rows:
            text = "📊 За 7 дней записей нет."
        else:
            parts = [f"📊 *Неделя* ({start.strftime('%d.%m')}–{end.strftime('%d.%m')}):"]
            cur_user = None
            subtotal = 0
            for full_name, d, loc, act, h in rows:
                who = full_name or "—"
                if who != cur_user:
                    if cur_user is not None:
                        parts.append(f"  — Итого сотрудник: *{subtotal}* ч\n")
                    cur_user = who
                    subtotal = 0
                    parts.append(f"\n👤 *{who}*")
                parts.append(f"  • {d} | {loc} — {act}: *{h}* ч")
                subtotal += h
            if cur_user is not None:
                parts.append(f"  — Итого сотрудник: *{subtotal}* ч")
            text = "\n".join(parts)
    else:
        rows = fetch_stats_range_for_user(user_id, start.isoformat(), end.isoformat())
        if not rows:
            text = "📊 За 7 дней у вас записей нет."
        else:
            parts = [f"📊 *Неделя* ({start.strftime('%d.%m')}–{end.strftime('%d.%m')}):"]
            per_day = {}
            total = 0
            for d, loc, act, h in rows:
                per_day.setdefault(d, []).append((loc, act, h))
            for d in sorted(per_day.keys(), reverse=True):
                parts.append(f"\n*{d}*")
                for loc, act, h in per_day[d]:
                    parts.append(f"• {loc} — {act}: *{h}* ч")
                    total += h
            parts.append(f"\nИтого: *{total}* ч")
            text = "\n".join(parts)
    
    client.send_message(to=user_id, text=text)

# -----------------------------
# Обработка callback кнопок
# -----------------------------

@wa.on_callback_button()
def handle_callback(client: WhatsApp, btn):
    user_id = btn.from_user.wa_id
    data = btn.data
    
    # WA: Обработка навигации по страницам (для пагинации)
    if data.startswith("nav:"):
        parts = data.split(":")
        if len(parts) < 3:
            client.send_message(to=user_id, text="❌ Команда устарела. Откройте меню заново.")
            return
        state_key = parts[1]
        try:
            page = int(parts[2])
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела. Откройте меню заново.")
            return
        
        state = get_state(user_id)
        
        if state_key == "acts":
            # Навигация по списку видов работ
            kind = state["data"].get("acts_kind")
            acts = state["data"].get("acts", [])
            send_paginated_buttons(
                client, user_id, "Выберите *вид работы*:",
                items=acts,
                make_button=lambda it: PaginationButton(title=it[1], callback_data=f"work:act:{kind}:{it[0]}"),
                state_key="acts",
                page=page,
                back_cb="menu:work"
            )
        elif state_key == "locs":
            # Навигация по списку локаций
            lg = state["data"].get("locs_group")
            locs = state["data"].get("locs", [])
            send_paginated_buttons(
                client, user_id, "Выберите *место*:",
                items=locs,
                make_button=lambda it: PaginationButton(title=it[1], callback_data=f"work:loc:{lg}:{it[0]}"),
                state_key="locs",
                page=page,
                back_cb="menu:work"
            )
        elif state_key == "hours":
            # Навигация по выбору часов
            hours_opts = state["data"].get("hours_opts", [])
            send_paginated_buttons(
                client, user_id, "Выберите *кол-во часов*:",
                items=hours_opts,
                make_button=lambda h: PaginationButton(title=str(h), callback_data=f"work:hours:{h}"),
                state_key="hours",
                page=page,
                back_cb="menu:work"
            )
        elif state_key == "edit_records":
            # Навигация по редактору записей
            st = get_state(user_id)
            records = (st.get("data") or {}).get("edit_records") or []
            if not records:
                client.send_message(to=user_id, text="📝 Записей нет.")
                u = get_user(user_id)
                show_main_menu(client, user_id, u)
                return
            render_edit_records_page(client, user_id, records, page=page)
        elif state_key == "edit_hours":
            # Навигация по выбору часов при редактировании
            rid = state["data"].get("edit_id")
            work_d = state["data"].get("edit_date")
            hours_opts = state["data"].get("edit_hours_opts", [])
            send_paginated_buttons(
                client, user_id, f"Укажите *новое количество часов* для записи #{rid} ({work_d}):",
                items=hours_opts,
                make_button=lambda h: PaginationButton(title=str(h), callback_data=f"edit:h:{h}"),
                state_key="edit_hours",
                page=page,
                back_cb="menu:edit"
            )
        return
    
    if data == "menu:root":
        u = get_user(user_id)
        clear_state(user_id)
        show_main_menu(client, user_id, u)
    
    elif data == "menu:more":
        show_more_menu(client, user_id)
    
    elif data == "menu:work":
        u = get_user(user_id)
        if not u or not (u.get("full_name") or "").strip():
            set_state(user_id, "waiting_name")
            client.send_message(to=user_id, text="Введите *Фамилию Имя* для регистрации.")
            return
        set_state(user_id, "pick_work_group", {})
        buttons = [
            Button(title="Техника", callback_data="work:grp:tech"),
            Button(title="Ручная", callback_data="work:grp:hand"),
            Button(title="🔙 Назад", callback_data="menu:root"),
        ]
        client.send_message(to=user_id, text="Выберите *тип работы*:", buttons=buttons)
    
    elif data == "menu:stats":
        buttons = [
            Button(title="Сегодня", callback_data="stats:today"),
            Button(title="Неделя", callback_data="stats:week"),
            Button(title="🔙 Назад", callback_data="menu:root"),
        ]
        client.send_message(to=user_id, text="Выберите период статистики:", buttons=buttons)
    
    elif data == "menu:edit":
        rows = user_recent_24h_reports(user_id)
        if not rows:
            client.send_message(to=user_id, text="📝 За последние 24 часа записей нет.")
            return
        
        # WA: Показываем по 1 записи на странице с 2 кнопками действий (Править/Удалить)
        # Сохраняем список записей в состояние для пагинации
        state = get_state(user_id)
        state["data"]["edit_records"] = rows
        set_state(user_id, "viewing_edit", state["data"])
        
        render_edit_records_page(client, user_id, rows, page=0)
    
    elif data == "menu:name":
        set_state(user_id, "waiting_name")
        client.send_message(to=user_id, text="✏️ Введите *Фамилию Имя* для изменения (например: *Иванов Иван*):")
    
    elif data == "menu:admin":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        
        # WA: Максимум 3 кнопки - используем пагинацию или разбиваем на подменю
        buttons = [
            Button(title="➕➖ Работы", callback_data="adm:menu:activities"),
            Button(title="➕➖ Локации", callback_data="adm:menu:locations"),
            Button(title="📤 Экспорт", callback_data="adm:export"),
        ]
        client.send_message(to=user_id, text="⚙️ *Админ-панель*:", buttons=buttons)
    
    elif data == "adm:menu:activities":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        buttons = [
            Button(title="➕ Добавить работу", callback_data="adm:add:act"),
            Button(title="➖ Удалить работу", callback_data="adm:del:act"),
            Button(title="🔙 Админ", callback_data="menu:admin"),
        ]
        client.send_message(to=user_id, text="⚙️ *Управление работами*:", buttons=buttons)
    
    elif data == "adm:menu:locations":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        buttons = [
            Button(title="➕ Добавить локацию", callback_data="adm:add:loc"),
            Button(title="➖ Удалить локацию", callback_data="adm:del:loc"),
            Button(title="🔙 Админ", callback_data="menu:admin"),
        ]
        client.send_message(to=user_id, text="⚙️ *Управление локациями*:", buttons=buttons)
    
    elif data == "stats:today":
        cmd_today(client, btn)
    
    elif data == "stats:week":
        cmd_my(client, btn)
    
    elif data.startswith("work:grp:"):
        kind = data.split(":")[2]
        grp_name = GROUP_TECH if kind == "tech" else GROUP_HAND
        state = get_state(user_id)
        state["data"]["work"] = {"grp": grp_name}
        set_state(user_id, "pick_activity", state["data"])
        
        # WA: Используем ID вместо названий в callback_data, применяем пагинацию
        activities = list_activities_with_id(grp_name)
        state["data"]["acts"] = activities
        state["data"]["acts_kind"] = kind
        set_state(user_id, "pick_activity", state["data"])
        
        send_paginated_buttons(
            client, user_id, "Выберите *вид работы*:",
            items=activities,
            make_button=lambda it: PaginationButton(title=it[1], callback_data=f"work:act:{kind}:{it[0]}"),
            state_key="acts",
            page=0,
            back_cb="menu:work"
        )
    
    elif data.startswith("work:act:"):
        # WA: Получаем название activity по ID из БД, а не из callback_data
        try:
            _, _, kind, act_id_str = data.split(":", 3)
            act_id = int(act_id_str)
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        result = get_activity_name(act_id)
        if not result:
            client.send_message(to=user_id, text="❌ Вид работы не найден. Начните заново.")
            clear_state(user_id)
            return
        
        activity_name, grp_name = result
        
        state = get_state(user_id)
        work_data = state["data"].get("work", {})
        work_data["grp"] = grp_name
        work_data["activity"] = activity_name
        state["data"]["work"] = work_data
        set_state(user_id, "pick_loc_group", state["data"])
        
        # WA: Максимум 3 кнопки
        buttons = [
            Button(title="Поля", callback_data="work:locgrp:fields"),
            Button(title="Склад", callback_data="work:locgrp:ware"),
            Button(title="🔙 Назад", callback_data="menu:work"),
        ]
        client.send_message(to=user_id, text="Выберите *локацию*:", buttons=buttons)
    
    elif data.startswith("work:locgrp:"):
        lg = data.split(":")[2]
        grp = GROUP_FIELDS if lg == "fields" else GROUP_WARE
        state = get_state(user_id)
        work_data = state["data"].get("work", {})
        work_data["loc_grp"] = grp
        
        if lg == "ware":
            work_data["location"] = "Склад"
            state["data"]["work"] = work_data
            set_state(user_id, "pick_date", state["data"])
            
            # WA: Показываем даты с ограничением по кнопкам (максимум 2 даты + назад = 3)
            today = date.today()
            buttons = []
            for i in range(2):  # WA: только 2 даты, чтобы влезла кнопка "Назад"
                d = today - timedelta(days=i)
                label = "Сегодня" if i == 0 else "Вчера"
                buttons.append(Button(title=label, callback_data=f"work:date:{d.isoformat()}"))
            buttons.append(Button(title="🔙 Назад", callback_data="menu:work"))
            client.send_message(to=user_id, text="Выберите *дату*:", buttons=buttons[:3])
        else:
            state["data"]["work"] = work_data
            set_state(user_id, "pick_location", state["data"])
            
            # WA: Используем ID вместо названий в callback_data, применяем пагинацию
            locations = list_locations_with_id(GROUP_FIELDS)
            state["data"]["locs"] = locations
            state["data"]["locs_group"] = lg
            set_state(user_id, "pick_location", state["data"])
            
            send_paginated_buttons(
                client, user_id, "Выберите *место*:",
                items=locations,
                make_button=lambda it: PaginationButton(title=it[1], callback_data=f"work:loc:{lg}:{it[0]}"),
                state_key="locs",
                page=0,
                back_cb="menu:work"
            )
    
    elif data.startswith("work:loc:"):
        # WA: Получаем название location по ID из БД, а не из callback_data
        try:
            _, _, lg, loc_id_str = data.split(":", 3)
            loc_id = int(loc_id_str)
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        result = get_location_name(loc_id)
        if not result:
            client.send_message(to=user_id, text="❌ Локация не найдена. Начните заново.")
            clear_state(user_id)
            return
        
        location_name, grp = result
        
        state = get_state(user_id)
        work_data = state["data"].get("work", {})
        work_data["loc_grp"] = grp
        work_data["location"] = location_name
        state["data"]["work"] = work_data
        set_state(user_id, "pick_date", state["data"])
        
        # WA: Показываем даты с ограничением по кнопкам (максимум 2 даты + назад = 3)
        today = date.today()
        buttons = []
        for i in range(2):  # WA: только 2 даты, чтобы влезла кнопка "Назад"
            d = today - timedelta(days=i)
            label = "Сегодня" if i == 0 else "Вчера"
            buttons.append(Button(title=label, callback_data=f"work:date:{d.isoformat()}"))
        buttons.append(Button(title="🔙 Назад", callback_data="menu:work"))
        client.send_message(to=user_id, text="Выберите *дату*:", buttons=buttons[:3])
    
    elif data.startswith("work:date:"):
        try:
            d = data.split(":")[2]
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        state = get_state(user_id)
        work_data = state["data"].get("work", {})
        work_data["work_date"] = d
        state["data"]["work"] = work_data
        set_state(user_id, "pick_hours", state["data"])
        
        # WA: Используем пагинацию для выбора часов (максимум 3 кнопки)
        hours_options = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 24]
        state["data"]["hours_opts"] = hours_options
        set_state(user_id, "pick_hours", state["data"])
        
        send_paginated_buttons(
            client, user_id, "Выберите *кол-во часов*:",
            items=hours_options,
            make_button=lambda h: PaginationButton(title=str(h), callback_data=f"work:hours:{h}"),
            state_key="hours",
            page=0,
            back_cb="menu:work"
        )
    
    elif data.startswith("work:hours:"):
        try:
            hours = int(data.split(":")[2])
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        state = get_state(user_id)
        work_data = state["data"].get("work", {})
        
        if not all(k in work_data for k in ("grp", "activity", "loc_grp", "location", "work_date")):
            client.send_message(to=user_id, text="Что-то пошло не так. Начните заново.")
            clear_state(user_id)
            return
        
        # Улучшенная валидация с подробным сообщением об ошибке
        already = sum_hours_for_user_date(user_id, work_data["work_date"])
        if already + hours > 24:
            max_can_add = 24 - already
            error_msg = (
                f"❗ *Превышен лимит часов*\n\n"
                f"Сейчас учтено: *{already}* ч\n"
                f"Попытка добавить: *{hours}* ч\n"
                f"Максимум в сутки: *24* ч\n\n"
                f"Вы можете добавить не более *{max_can_add}* ч."
            )
            client.send_message(to=user_id, text=error_msg)
            return
        
        u = get_user(user_id)
        rid = insert_report(
            user_id=user_id,
            reg_name=(u.get("full_name") or ""),
            location=work_data["location"],
            loc_grp=work_data["loc_grp"],
            activity=work_data["activity"],
            act_grp=work_data["grp"],
            work_date=work_data["work_date"],
            hours=hours
        )
        
        text = (
            f"✅ *Сохранено*\n\n"
            f"Дата: *{work_data['work_date']}*\n"
            f"Место: *{work_data['location']}*\n"
            f"Работа: *{work_data['activity']}*\n"
            f"Часы: *{hours}*\n"
            f"ID записи: `#{rid}`"
        )
        clear_state(user_id)
        client.send_message(to=user_id, text=text)
        show_main_menu(client, user_id, u)
    
    elif data.startswith("edit:del:"):
        try:
            rid = int(data.split(":")[2])
        except Exception:
            client.send_message(to=user_id, text="❌ Не удалось разобрать команду.")
            return

        ok = delete_report(rid, user_id)
        st = get_state(user_id)
        records = [r for r in st["data"].get("edit_records", []) if r[0] != rid]
        st["data"]["edit_records"] = records

        if ok and records:
            # возвращаемся к первой странице или сохраняем текущую, если храните индекс
            render_edit_records_page(client, user_id, records, page=0)
        elif ok:
            client.send_message(to=user_id, text="✅ Удалено\n\n📝 Записей нет.")
        else:
            client.send_message(to=user_id, text="❌ Не получилось удалить")
        return
    
    elif data.startswith("edit:chg:"):
        try:
            _, _, rid, work_d = data.split(":", 3)
            rid = int(rid)
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        # WA: Используем пагинацию для выбора часов (максимум 3 кнопки)
        hours_options = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 24]
        state = get_state(user_id)
        state["data"]["edit_id"] = rid
        state["data"]["edit_date"] = work_d
        state["data"]["edit_hours_opts"] = hours_options
        set_state(user_id, "edit_hours", state["data"])
        
        send_paginated_buttons(
            client, user_id, f"Укажите *новое количество часов* для записи #{rid} ({work_d}):",
            items=hours_options,
            make_button=lambda h: PaginationButton(title=str(h), callback_data=f"edit:h:{h}"),
            state_key="edit_hours",
            page=0,
            back_cb="menu:edit"
        )
    
    elif data.startswith("edit:h:"):
        try:
            new_h = int(data.split(":")[2])
        except Exception:
            client.send_message(to=user_id, text="❌ Команда устарела или повреждена. Откройте меню заново.")
            return
        
        state = get_state(user_id)
        try:
            rid = int(state["data"].get("edit_id"))
            work_d = state["data"].get("edit_date")
        except Exception:
            client.send_message(to=user_id, text="❌ Данные сессии устарели. Откройте меню заново.")
            return
        
        # Улучшенная валидация с подробным сообщением об ошибке
        already = sum_hours_for_user_date(user_id, work_d, exclude_report_id=rid)
        if already + new_h > 24:
            max_can_add = 24 - already
            error_msg = (
                f"❗ *Превышен лимит часов*\n\n"
                f"Сейчас учтено (без этой записи): *{already}* ч\n"
                f"Попытка установить: *{new_h}* ч\n"
                f"Максимум в сутки: *24* ч\n\n"
                f"Вы можете установить не более *{max_can_add}* ч."
            )
            client.send_message(to=user_id, text=error_msg)
            return
        
        ok = update_report_hours(rid, user_id, new_h)
        if ok:
            clear_state(user_id)
            rows = user_recent_24h_reports(user_id)
            if rows:
                st = get_state(user_id)
                st["data"]["edit_records"] = rows
                set_state(user_id, "viewing_edit", st["data"])
                client.send_message(to=user_id, text="✅ Обновлено")
                render_edit_records_page(client, user_id, rows, page=0)
            else:
                client.send_message(to=user_id, text="✅ Обновлено\n\n📝 Записей нет.")
        else:
            client.send_message(to=user_id, text="❌ Не получилось обновить")
    
    elif data == "adm:add:act":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        set_state(user_id, "adm_wait_act_add")
        client.send_message(to=user_id, text="Введите название *работы* для добавления:")

    elif data == "adm:del:act":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        set_state(user_id, "adm_wait_act_del")
        client.send_message(to=user_id, text="Введите точное название *работы* для удаления:")

    elif data == "adm:add:loc":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        set_state(user_id, "adm_wait_loc_add")
        client.send_message(to=user_id, text="Введите название *локации* для добавления:")

    elif data == "adm:del:loc":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        set_state(user_id, "adm_wait_loc_del")
        client.send_message(to=user_id, text="Введите точное название *локации* для удаления:")

    elif data == "adm:export":
        if not is_admin(user_id):
            client.send_message(to=user_id, text="❌ Нет прав")
            return
        
        client.send_message(to=user_id, text="⏳ Экспортирую отчеты в Google Sheets...")
        try:
            count, message = export_reports_to_sheets()
            text = f"✅ {message}" if count > 0 else f"ℹ️ {message}"
            created, sheet_msg = check_and_create_next_month_sheet()
            if created:
                text += f"\n\n📅 {sheet_msg}"
        except Exception as e:
            logging.error(f"Export error: {e}")
            text = f"❌ Ошибка экспорта: {str(e)}"
        
        client.send_message(to=user_id, text=text)

# -----------------------------
# Обработка текстовых сообщений (FSM)
# -----------------------------

@wa.on_message(text)
def handle_text(client: WhatsApp, msg: WAMessage):
    user_id = msg.from_user.wa_id
    message_text = (msg.text or "").strip()
    logging.info(f"[TEXT] {user_id}: {message_text}")
    normalized = message_text.lower()

    if normalized in {"start", "старт"}:
        cmd_start(client, msg)
        return
    if normalized in {"menu", "меню"}:
        cmd_menu(client, msg)
        return
    if normalized in {"today", "сегодня"}:
        cmd_today(client, msg)
        return
    if normalized in {"my", "мои"}:
        cmd_my(client, msg)
        return

    state = get_state(user_id)
    current_state = state.get("state")
    
    if current_state == "waiting_name":
        if len(message_text) < 3 or " " not in message_text:
            client.send_message(to=user_id, text="Введите Фамилию и Имя (через пробел). Пример: *Иванов Иван*")
            return
        
        old_user = get_user(user_id)
        is_new_user = not old_user or not (old_user.get("full_name") or "").strip()
        
        upsert_user(user_id, message_text, TZ)
        u = get_user(user_id)
        clear_state(user_id)
        
        if is_new_user:
            client.send_message(to=user_id, text=f"✅ Зарегистрировано как: *{message_text}*")
        else:
            client.send_message(to=user_id, text=f"✏️ Имя изменено на: *{message_text}*")
        
        show_main_menu(client, user_id, u)
    
    elif current_state == "adm_wait_act_add":
        ok = add_activity(GROUP_HAND, message_text)  # добавляем в группу "ручная"
        clear_state(user_id)
        client.send_message(to=user_id, text="✅ Добавлено" if ok else "⚠️ Уже существует")
        return

    elif current_state == "adm_wait_act_del":
        ok = remove_activity(message_text)
        clear_state(user_id)
        client.send_message(to=user_id, text="✅ Удалено" if ok else "❌ Не найдено")
        return

    elif current_state == "adm_wait_loc_add":
        ok = add_location(GROUP_FIELDS, message_text)  # добавляем в группу "поля"
        clear_state(user_id)
        client.send_message(to=user_id, text="✅ Добавлено" if ok else "⚠️ Уже существует")
        return

    elif current_state == "adm_wait_loc_del":
        ok = remove_location(message_text)
        clear_state(user_id)
        client.send_message(to=user_id, text="✅ Удалено" if ok else "❌ Не найдено")
        return
    
    else:
        # Дефолтное поведение - показать меню
        u = get_user(user_id)
        if u:
            show_main_menu(client, user_id, u)
        else:
            cmd_start(client, msg)

# -----------------------------
# Автоматический экспорт
# -----------------------------

def scheduled_export():
    try:
        logging.info("Running scheduled export...")
        count, message = export_reports_to_sheets()
        logging.info(f"Scheduled export result: {message}")
        
        created, sheet_msg = check_and_create_next_month_sheet()
        if created:
            logging.info(sheet_msg)
    except Exception as e:
        logging.error(f"Scheduled export error: {e}")

# -----------------------------
# Запуск
# -----------------------------

if __name__ == "__main__":
    init_db()
    
    # Настройка автоматического экспорта
    if AUTO_EXPORT_ENABLED:
        scheduler = BackgroundScheduler(timezone=TZ)
        cron_parts = AUTO_EXPORT_CRON.split()
        if len(cron_parts) == 5:
            minute, hour, day, month, day_of_week = cron_parts
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week
            )
            scheduler.add_job(scheduled_export, trigger)
            scheduler.start()
            logging.info(f"Scheduled export enabled: {AUTO_EXPORT_CRON}")
        else:
            logging.warning(f"Invalid cron expression: {AUTO_EXPORT_CRON}")
    
    logging.info("🤖 WhatsApp бот запущен!")
    logging.info("📡 Слушаю на %s:%s", SERVER_HOST, SERVER_PORT)
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)


