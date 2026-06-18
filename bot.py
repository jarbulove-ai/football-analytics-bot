from __future__ import annotations

import logging
import os
import re
import asyncio
import hashlib
import hmac
import json
import threading
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask, jsonify, request as flask_request
from openai import OpenAI
import psycopg2
import requests
from psycopg2.extras import Json, RealDictCursor
from telegram import (
    BotCommand,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
THESPORTSDB_BASE_URL = "https://www.thesportsdb.com/api/v1/json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
# Render Background Worker:
# RUN_TELEGRAM_BOT=true
# ENABLE_MINIAPP_API=false
#
# Render Web Service:
# RUN_TELEGRAM_BOT=false
# ENABLE_MINIAPP_API=true
RUN_TELEGRAM_BOT = os.getenv("RUN_TELEGRAM_BOT", "true").lower() == "true"
ENABLE_MINIAPP_API = os.getenv("ENABLE_MINIAPP_API", "false").lower() == "true"
MINIAPP_API_HOST = os.getenv("MINIAPP_API_HOST", "0.0.0.0")
MINIAPP_API_PORT = int(os.getenv("PORT", os.getenv("MINIAPP_API_PORT", "8000")))
ADMIN_TELEGRAM_IDS = set(
    int(item.strip())
    for item in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if item.strip().isdigit()
)
FREE_AI_LIMIT_MONTHLY = int(os.getenv("FREE_AI_LIMIT_MONTHLY", "5"))
AI_PACK_30_PRICE_KZT = int(os.getenv("AI_PACK_30_PRICE_KZT", "499"))
AI_PACK_30_LIMIT = int(os.getenv("AI_PACK_30_LIMIT", "30"))
PREMIUM_30_PRICE_KZT = int(os.getenv("PREMIUM_30_PRICE_KZT", "990"))
PREMIUM_30_DAYS = int(os.getenv("PREMIUM_30_DAYS", "30"))
PREMIUM_30_AI_LIMIT = int(os.getenv("PREMIUM_30_AI_LIMIT", "100"))
PREMIUM_90_PRICE_KZT = int(os.getenv("PREMIUM_90_PRICE_KZT", "2490"))
PREMIUM_90_DAYS = int(os.getenv("PREMIUM_90_DAYS", "90"))
PREMIUM_90_AI_LIMIT = int(os.getenv("PREMIUM_90_AI_LIMIT", "300"))
PAYMENT_PHONE = os.getenv("PAYMENT_PHONE", "")
PAYMENT_RECEIVER_NAME = os.getenv("PAYMENT_RECEIVER_NAME", "")
ALMATY_TZ = timezone(timedelta(hours=5))
MAX_MATCHES = 20
MAX_TOP_MATCHES = 15
TOP_LEAGUE_IDS = [
    2,
    3,
    848,
    39,
    140,
    78,
    135,
    61,
    88,
    94,
    203,
    389,
    1,
    15,
]
STANDINGS_LEAGUES = {
    "🇬🇧 АПЛ": {
        "id": 39,
        "season": 2025,
        "name": "Premier League",
        "country": "England",
    },
    "🇪🇸 Ла Лига": {
        "id": 140,
        "season": 2025,
        "name": "La Liga",
        "country": "Spain",
    },
    "🇮🇹 Серия А": {
        "id": 135,
        "season": 2025,
        "name": "Serie A",
        "country": "Italy",
    },
    "🇩🇪 Бундеслига": {
        "id": 78,
        "season": 2025,
        "name": "Bundesliga",
        "country": "Germany",
    },
    "🇫🇷 Лига 1": {
        "id": 61,
        "season": 2025,
        "name": "Ligue 1",
        "country": "France",
    },
    "🇵🇹 Португалия": {
        "id": 94,
        "season": 2025,
        "name": "Primeira Liga",
        "country": "Portugal",
    },
    "🇳🇱 Эредивизи": {
        "id": 88,
        "season": 2025,
        "name": "Eredivisie",
        "country": "Netherlands",
    },
    "🇹🇷 Турция": {
        "id": 203,
        "season": 2025,
        "name": "Süper Lig",
        "country": "Turkey",
    },
    "🇰🇿 Казахстан": {
        "id": 389,
        "season": 2026,
        "name": "Premier League",
        "country": "Kazakhstan",
    },
}

FAVORITE_TEAM_LEAGUES = {
    "🇬🇧 АПЛ": [
        "Arsenal",
        "Manchester City",
        "Liverpool",
        "Chelsea",
        "Tottenham",
        "Manchester United",
    ],
    "🇪🇸 Ла Лига": [
        "Barcelona",
        "Real Madrid",
        "Atletico Madrid",
        "Villarreal",
        "Real Betis",
        "Real Sociedad",
    ],
    "🇮🇹 Серия А": [
        "Inter",
        "AC Milan",
        "Juventus",
        "Napoli",
        "Roma",
        "Lazio",
    ],
    "🇩🇪 Бундеслига": [
        "Bayern Munich",
        "Borussia Dortmund",
        "Bayer Leverkusen",
        "RB Leipzig",
        "Eintracht Frankfurt",
        "Stuttgart",
    ],
    "🇫🇷 Лига 1": [
        "Paris Saint Germain",
        "Marseille",
        "Monaco",
        "Lyon",
        "Lille",
        "Nice",
    ],
}
TEAM_ALIASES = {
    "ливерпуль": "Liverpool",
    "арсенал": "Arsenal",
    "челси": "Chelsea",
    "тоттенхэм": "Tottenham",
    "тоттенхем": "Tottenham",
    "ман сити": "Manchester City",
    "мансити": "Manchester City",
    "манчестер сити": "Manchester City",
    "мс": "Manchester City",
    "ман юнайтед": "Manchester United",
    "манчестер юнайтед": "Manchester United",
    "мю": "Manchester United",
    "реал": "Real Madrid",
    "реал мадрид": "Real Madrid",
    "барса": "Barcelona",
    "барселона": "Barcelona",
    "атлетико": "Atletico Madrid",
    "атлетико мадрид": "Atletico Madrid",
    "интер": "Inter",
    "милан": "AC Milan",
    "ювентус": "Juventus",
    "юве": "Juventus",
    "наполи": "Napoli",
    "рома": "Roma",
    "лацио": "Lazio",
    "бавария": "Bayern Munich",
    "боруссия": "Borussia Dortmund",
    "боруссия д": "Borussia Dortmund",
    "боруссия дортмунд": "Borussia Dortmund",
    "байер": "Bayer Leverkusen",
    "байер леверкузен": "Bayer Leverkusen",
    "лейпциг": "RB Leipzig",
    "псж": "Paris Saint Germain",
    "пари сен жермен": "Paris Saint Germain",
    "марсель": "Marseille",
    "монако": "Monaco",
    "лион": "Lyon",
    "лилль": "Lille",
    "кайрат": "Kairat Almaty",
    "астана": "FC Astana",
}
FAVORITE_MANUAL_INPUT_BUTTON = "⌨️ Ввести вручную"
FAVORITE_BACK_TO_LEAGUES_BUTTON = "⬅️ К лигам"
FAVORITE_OPEN_PROFILE_BUTTON = "📋 Открыть профиль"
FAVORITE_CHANGE_TEAM_BUTTON = "🔄 Сменить команду"
MATCH_AI_ANALYSIS_BUTTON = "🤖 AI-разбор"
PREMIUM_BUTTON = "💎 Подписка"
AI_PACK_30_BUTTON = f"⚡ 30 AI — {AI_PACK_30_PRICE_KZT} ₸"
PREMIUM_30_BUTTON = f"💎 1 месяц — {PREMIUM_30_PRICE_KZT} ₸"
PREMIUM_90_BUTTON = f"🏆 3 месяца — {PREMIUM_90_PRICE_KZT:,} ₸".replace(",", " ")
PAYMENT_PACKAGE_BUTTONS = {
    AI_PACK_30_BUTTON,
    PREMIUM_30_BUTTON,
    PREMIUM_90_BUTTON,
}
PAYMENT_PACKAGES = {
    "ai_30": {
        "title": "⚡ Пакет 30 AI",
        "button": AI_PACK_30_BUTTON,
        "amount_kzt": AI_PACK_30_PRICE_KZT,
        "ai_credits": AI_PACK_30_LIMIT,
        "admin_command": "add_ai_limit",
    },
    "premium_30": {
        "title": "💎 Premium 1 месяц",
        "button": PREMIUM_30_BUTTON,
        "amount_kzt": PREMIUM_30_PRICE_KZT,
        "days": PREMIUM_30_DAYS,
        "ai_limit": PREMIUM_30_AI_LIMIT,
        "admin_command": "grant_premium",
    },
    "premium_90": {
        "title": "🏆 Premium 3 месяца",
        "button": PREMIUM_90_BUTTON,
        "amount_kzt": PREMIUM_90_PRICE_KZT,
        "days": PREMIUM_90_DAYS,
        "ai_limit": PREMIUM_90_AI_LIMIT,
        "admin_command": "grant_premium",
    },
}
MINIAPP_PAYMENT_PACKAGE_CODES = {
    "ai_30": "ai_30",
    "month_1": "premium_30",
    "months_3": "premium_90",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
miniapp_api = Flask("matchlab_miniapp_api")


@miniapp_api.after_request
def add_miniapp_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers[
        "Access-Control-Allow-Headers"
    ] = "Content-Type, X-Telegram-Init-Data"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def normalize_team_name(team_name: str) -> str:
    stripped_team_name = team_name.strip()
    normalized_team_name = stripped_team_name.lower().replace("ё", "е")
    normalized_team_name = re.sub(r"\s+", " ", normalized_team_name)

    return TEAM_ALIASES.get(normalized_team_name, stripped_team_name)


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def init_db() -> None:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; user settings will be in-memory only"
        )
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    telegram_user_id BIGINT PRIMARY KEY,
                    favorite_team TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_users (
                    telegram_user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_events (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_events_user_id_created_at
                ON user_events (telegram_user_id, created_at DESC);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_events_type_created_at
                ON user_events (event_type, created_at DESC);
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    telegram_user_id BIGINT PRIMARY KEY,
                    plan TEXT NOT NULL DEFAULT 'free',
                    premium_until TIMESTAMP,
                    ai_limit_monthly INT NOT NULL DEFAULT 5,
                    ai_used_monthly INT NOT NULL DEFAULT 0,
                    usage_period TEXT NOT NULL,
                    extra_ai_credits INT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_requests (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    package_code TEXT NOT NULL,
                    amount_kzt INT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    receipt_file_id TEXT,
                    receipt_file_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        connection.commit()
    except Exception:
        logger.exception("Failed to initialize database")
    finally:
        if connection is not None:
            connection.close()


def upsert_bot_user(user) -> None:
    database_url = get_database_url()
    if not database_url or not user:
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO bot_users (
                    telegram_user_id,
                    username,
                    first_name,
                    last_name,
                    language_code,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_user_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    language_code = EXCLUDED.language_code,
                    last_seen_at = CURRENT_TIMESTAMP;
                """,
                (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                ),
            )
        connection.commit()
    except Exception:
        logger.error("Failed to upsert bot user", exc_info=True)
    finally:
        if connection is not None:
            connection.close()


def make_json_safe(data: dict | None) -> dict | None:
    if data is None:
        return None

    try:
        return json.loads(json.dumps(data, ensure_ascii=False, default=str))
    except Exception:
        logger.error("Failed to serialize analytics event data", exc_info=True)
        return None


def log_user_event(
    telegram_user_id: int,
    event_type: str,
    event_data: dict | None = None,
) -> None:
    database_url = get_database_url()
    if not database_url:
        return

    connection = None
    safe_event_data = make_json_safe(event_data)

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_events (
                    telegram_user_id,
                    event_type,
                    event_data
                )
                VALUES (%s, %s, %s);
                """,
                (
                    telegram_user_id,
                    event_type,
                    Json(safe_event_data) if safe_event_data is not None else None,
                ),
            )
        connection.commit()
    except Exception:
        logger.error("Failed to log user event", exc_info=True)
    finally:
        if connection is not None:
            connection.close()


def track_user_action(
    update: Update,
    event_type: str,
    event_data: dict | None = None,
) -> None:
    if not update.effective_user:
        return

    upsert_bot_user(update.effective_user)
    log_user_event(update.effective_user.id, event_type, event_data)


def is_admin_user(telegram_user_id: int) -> bool:
    return telegram_user_id in ADMIN_TELEGRAM_IDS


def get_almaty_period_start(days_back: int = 0) -> datetime:
    now_almaty = datetime.now(ALMATY_TZ)
    target_date = now_almaty.date() - timedelta(days=days_back)
    return datetime.combine(
        target_date,
        datetime.min.time(),
        tzinfo=ALMATY_TZ,
    ).astimezone(timezone.utc).replace(tzinfo=None)


def format_db_datetime(value) -> str:
    if not value:
        return "-"

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(ALMATY_TZ)
        return value.strftime("%d.%m %H:%M")

    return str(value)


def get_user_display_name(row: dict) -> str:
    username = row.get("username")
    if username:
        return f"@{username}"

    full_name = " ".join(
        part
        for part in (
            row.get("first_name"),
            row.get("last_name"),
        )
        if part
    ).strip()
    return full_name or "Без имени"


def format_event_line(row: dict) -> str:
    event_type = row.get("event_type") or "-"
    event_data = row.get("event_data") or {}
    suffix = ""

    if isinstance(event_data, dict) and event_type == "match_selected":
        home = event_data.get("home")
        away = event_data.get("away")
        if home and away:
            suffix = f" — {home} - {away}"

    return f"• {format_db_datetime(row.get('created_at'))} — {event_type}{suffix}"


async def deny_non_admin(update: Update) -> bool:
    if not update.effective_user or not is_admin_user(update.effective_user.id):
        await update.message.reply_text("Команда недоступна.")
        return True

    return False


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    database_url = get_database_url()
    if not database_url:
        await update.message.reply_text("База данных не подключена.")
        return

    today_start = get_almaty_period_start()
    seven_days_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=7
    )
    event_types = {
        "today_clicked": "Сегодня",
        "tomorrow_clicked": "Завтра",
        "top_clicked": "Топ матчи",
        "match_selected": "Выбрали матч",
        "ai_analysis_clicked": "AI-разборы",
        "premium_clicked": "Premium нажали",
    }

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT COUNT(*) AS value FROM bot_users;")
            total_users = cursor.fetchone()["value"]

            cursor.execute(
                """
                SELECT COUNT(*) AS value
                FROM bot_users
                WHERE last_seen_at >= %s;
                """,
                (today_start,),
            )
            active_today = cursor.fetchone()["value"]

            cursor.execute(
                """
                SELECT COUNT(*) AS value
                FROM bot_users
                WHERE last_seen_at >= %s;
                """,
                (seven_days_start,),
            )
            active_7_days = cursor.fetchone()["value"]

            event_counts = {}
            for event_type in event_types:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM user_events
                    WHERE event_type = %s
                    AND created_at >= %s;
                    """,
                    (event_type, today_start),
                )
                event_counts[event_type] = cursor.fetchone()["value"]
    except Exception:
        logger.exception("Failed to load admin stats")
        await update.message.reply_text("Статистика временно недоступна.")
        return
    finally:
        if connection is not None:
            connection.close()

    lines = [
        "📊 Статистика MatchLab",
        "",
        f"Пользователей всего: {total_users}",
        f"Активных сегодня: {active_today}",
        f"Активных за 7 дней: {active_7_days}",
        "",
        "События сегодня:",
    ]
    lines.extend(
        f"• {label}: {event_counts[event_type]}"
        for event_type, label in event_types.items()
    )

    await update.message.reply_text("\n".join(lines))


async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    database_url = get_database_url()
    if not database_url:
        await update.message.reply_text("База данных не подключена.")
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT telegram_user_id, username, first_name, last_name, last_seen_at
                FROM bot_users
                ORDER BY last_seen_at DESC
                LIMIT 10;
                """
            )
            rows = cursor.fetchall()
    except Exception:
        logger.exception("Failed to load admin users")
        await update.message.reply_text("Список пользователей временно недоступен.")
        return
    finally:
        if connection is not None:
            connection.close()

    lines = ["👥 Последние пользователи", ""]
    if not rows:
        lines.append("Пользователи не найдены.")
    else:
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. {get_user_display_name(row)} — "
                f"{row['telegram_user_id']} — {format_db_datetime(row['last_seen_at'])}"
            )

    await update.message.reply_text("\n".join(lines))


async def user_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Использование: /user telegram_id")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Использование: /user telegram_id")
        return

    database_url = get_database_url()
    if not database_url:
        await update.message.reply_text("База данных не подключена.")
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM bot_users
                WHERE telegram_user_id = %s;
                """,
                (telegram_user_id,),
            )
            user_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT event_type, event_data, created_at
                FROM user_events
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC
                LIMIT 5;
                """,
                (telegram_user_id,),
            )
            event_rows = cursor.fetchall()
    except Exception:
        logger.exception("Failed to load admin user card")
        await update.message.reply_text("Карточка пользователя временно недоступна.")
        return
    finally:
        if connection is not None:
            connection.close()

    if not user_row:
        await update.message.reply_text("Пользователь не найден.")
        return

    full_name = " ".join(
        part
        for part in (
            user_row.get("first_name"),
            user_row.get("last_name"),
        )
        if part
    ).strip() or "Без имени"
    lines = [
        "👤 Пользователь",
        "",
        f"ID: {user_row['telegram_user_id']}",
        f"Username: {('@' + user_row['username']) if user_row.get('username') else '-'}",
        f"Имя: {full_name}",
        f"Первый запуск: {format_db_datetime(user_row.get('first_seen_at'))}",
        f"Последняя активность: {format_db_datetime(user_row.get('last_seen_at'))}",
        "",
        "Последние действия:",
    ]
    if event_rows:
        lines.extend(format_event_line(row) for row in event_rows)
    else:
        lines.append("Нет событий.")

    await update.message.reply_text("\n".join(lines))


async def events_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Использование: /events telegram_id")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Использование: /events telegram_id")
        return

    database_url = get_database_url()
    if not database_url:
        await update.message.reply_text("База данных не подключена.")
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT event_type, event_data, created_at
                FROM user_events
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC
                LIMIT 20;
                """,
                (telegram_user_id,),
            )
            rows = cursor.fetchall()
    except Exception:
        logger.exception("Failed to load admin events")
        await update.message.reply_text("События временно недоступны.")
        return
    finally:
        if connection is not None:
            connection.close()

    lines = ["🧾 Последние события", ""]
    if rows:
        lines.extend(format_event_line(row) for row in rows)
    else:
        lines.append("События не найдены.")

    await update.message.reply_text("\n".join(lines))


def get_current_usage_period() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y-%m")


def get_now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_free_subscription(telegram_user_id: int) -> dict:
    return {
        "telegram_user_id": telegram_user_id,
        "plan": "free",
        "premium_until": None,
        "ai_limit_monthly": FREE_AI_LIMIT_MONTHLY,
        "ai_used_monthly": 0,
        "usage_period": get_current_usage_period(),
        "extra_ai_credits": 0,
        "updated_at": get_now_utc_naive(),
    }


def normalize_subscription_row(row: dict | None, telegram_user_id: int) -> dict:
    if not row:
        return get_free_subscription(telegram_user_id)

    subscription = dict(row)
    subscription["telegram_user_id"] = telegram_user_id
    subscription["plan"] = subscription.get("plan") or "free"
    subscription["ai_limit_monthly"] = int(
        subscription.get("ai_limit_monthly") or FREE_AI_LIMIT_MONTHLY
    )
    subscription["ai_used_monthly"] = int(subscription.get("ai_used_monthly") or 0)
    subscription["extra_ai_credits"] = int(
        subscription.get("extra_ai_credits") or 0
    )
    subscription["usage_period"] = (
        subscription.get("usage_period") or get_current_usage_period()
    )
    return subscription


def is_premium_active(subscription: dict) -> bool:
    if not subscription or subscription.get("plan") != "premium":
        return False

    premium_until = subscription.get("premium_until")
    if not isinstance(premium_until, datetime):
        return False

    if premium_until.tzinfo is None:
        premium_until = premium_until.replace(tzinfo=timezone.utc)

    return premium_until > datetime.now(timezone.utc)


def get_or_create_subscription(telegram_user_id: int) -> dict:
    database_url = get_database_url()
    if not database_url:
        return get_free_subscription(telegram_user_id)

    connection = None
    usage_period = get_current_usage_period()

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    telegram_user_id,
                    plan,
                    premium_until,
                    ai_limit_monthly,
                    ai_used_monthly,
                    usage_period,
                    extra_ai_credits,
                    updated_at
                )
                VALUES (%s, 'free', NULL, %s, 0, %s, 0, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_user_id) DO NOTHING;
                """,
                (telegram_user_id, FREE_AI_LIMIT_MONTHLY, usage_period),
            )
            cursor.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE telegram_user_id = %s;
                """,
                (telegram_user_id,),
            )
            subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )

            needs_update = False
            if subscription["usage_period"] != usage_period:
                subscription["usage_period"] = usage_period
                subscription["ai_used_monthly"] = 0
                needs_update = True

            if (
                subscription["plan"] == "premium"
                and subscription.get("premium_until")
                and not is_premium_active(subscription)
            ):
                subscription["plan"] = "free"
                subscription["premium_until"] = None
                subscription["ai_limit_monthly"] = FREE_AI_LIMIT_MONTHLY
                needs_update = True

            if needs_update:
                cursor.execute(
                    """
                    UPDATE subscriptions
                    SET plan = %s,
                        premium_until = %s,
                        ai_limit_monthly = %s,
                        ai_used_monthly = %s,
                        usage_period = %s,
                        extra_ai_credits = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *;
                    """,
                    (
                        subscription["plan"],
                        subscription.get("premium_until"),
                        subscription["ai_limit_monthly"],
                        subscription["ai_used_monthly"],
                        subscription["usage_period"],
                        subscription["extra_ai_credits"],
                        telegram_user_id,
                    ),
                )
                subscription = normalize_subscription_row(
                    cursor.fetchone(),
                    telegram_user_id,
                )
        connection.commit()
        return subscription
    except Exception:
        logger.error("Failed to get or create subscription", exc_info=True)
        return get_free_subscription(telegram_user_id)
    finally:
        if connection is not None:
            connection.close()


def get_ai_available_count(subscription: dict) -> int:
    monthly_left = max(
        0,
        int(subscription.get("ai_limit_monthly") or 0)
        - int(subscription.get("ai_used_monthly") or 0),
    )
    return monthly_left + int(subscription.get("extra_ai_credits") or 0)


def get_ai_usage_text(subscription: dict) -> str:
    used = int(subscription.get("ai_used_monthly") or 0)
    limit = int(subscription.get("ai_limit_monthly") or 0)
    lines = [f"AI-разборы: {used} / {limit}"]
    extra_ai_credits = int(subscription.get("extra_ai_credits") or 0)
    if extra_ai_credits > 0:
        lines.append(f"Доп. AI-разборы: {extra_ai_credits}")
    return "\n".join(lines)


def can_use_ai_analysis(telegram_user_id: int) -> tuple[bool, str, dict]:
    subscription = get_or_create_subscription(telegram_user_id)
    if int(subscription.get("extra_ai_credits") or 0) > 0:
        return True, "", subscription

    ai_limit_monthly = int(subscription.get("ai_limit_monthly") or 0)
    ai_used_monthly = int(subscription.get("ai_used_monthly") or 0)
    if ai_used_monthly >= ai_limit_monthly:
        return False, "monthly_limit_reached", subscription

    return True, "", subscription


def increment_ai_usage(telegram_user_id: int) -> dict:
    database_url = get_database_url()
    if not database_url:
        subscription = get_or_create_subscription(telegram_user_id)
        subscription["ai_used_monthly"] = int(
            subscription.get("ai_used_monthly") or 0
        ) + 1
        return subscription

    connection = None
    subscription = get_or_create_subscription(telegram_user_id)

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            if int(subscription.get("extra_ai_credits") or 0) > 0:
                cursor.execute(
                    """
                    UPDATE subscriptions
                    SET extra_ai_credits = GREATEST(extra_ai_credits - 1, 0),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *;
                    """,
                    (telegram_user_id,),
                )
            else:
                cursor.execute(
                    """
                    UPDATE subscriptions
                    SET ai_used_monthly = ai_used_monthly + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *;
                    """,
                    (telegram_user_id,),
                )
            updated_subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )
        connection.commit()
        return updated_subscription
    except Exception:
        logger.error("Failed to increment AI usage", exc_info=True)
        return subscription
    finally:
        if connection is not None:
            connection.close()


def grant_premium(telegram_user_id: int, days: int, ai_limit: int) -> dict:
    database_url = get_database_url()
    current_subscription = get_or_create_subscription(telegram_user_id)
    if not database_url:
        return current_subscription

    usage_period = get_current_usage_period()
    now_utc = get_now_utc_naive()
    current_until = current_subscription.get("premium_until")
    if isinstance(current_until, datetime):
        if current_until.tzinfo is not None:
            current_until = current_until.astimezone(timezone.utc).replace(tzinfo=None)
        base_date = max(now_utc, current_until)
    else:
        base_date = now_utc
    premium_until = base_date + timedelta(days=days)
    ai_used_monthly = (
        0
        if current_subscription.get("usage_period") != usage_period
        else int(current_subscription.get("ai_used_monthly") or 0)
    )

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    telegram_user_id,
                    plan,
                    premium_until,
                    ai_limit_monthly,
                    ai_used_monthly,
                    usage_period,
                    extra_ai_credits,
                    updated_at
                )
                VALUES (%s, 'premium', %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_user_id)
                DO UPDATE SET
                    plan = 'premium',
                    premium_until = EXCLUDED.premium_until,
                    ai_limit_monthly = EXCLUDED.ai_limit_monthly,
                    ai_used_monthly = EXCLUDED.ai_used_monthly,
                    usage_period = EXCLUDED.usage_period,
                    extra_ai_credits = subscriptions.extra_ai_credits,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *;
                """,
                (
                    telegram_user_id,
                    premium_until,
                    ai_limit,
                    ai_used_monthly,
                    usage_period,
                    int(current_subscription.get("extra_ai_credits") or 0),
                ),
            )
            subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )
        connection.commit()
        return subscription
    except Exception:
        logger.error("Failed to grant premium", exc_info=True)
        return current_subscription
    finally:
        if connection is not None:
            connection.close()


def revoke_premium(telegram_user_id: int) -> dict:
    database_url = get_database_url()
    current_subscription = get_or_create_subscription(telegram_user_id)
    if not database_url:
        return current_subscription

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE subscriptions
                SET plan = 'free',
                    premium_until = NULL,
                    ai_limit_monthly = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                RETURNING *;
                """,
                (FREE_AI_LIMIT_MONTHLY, telegram_user_id),
            )
            subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )
        connection.commit()
        return subscription
    except Exception:
        logger.error("Failed to revoke premium", exc_info=True)
        return current_subscription
    finally:
        if connection is not None:
            connection.close()


def add_ai_limit(telegram_user_id: int, amount: int) -> dict:
    database_url = get_database_url()
    current_subscription = get_or_create_subscription(telegram_user_id)
    if not database_url:
        current_subscription["extra_ai_credits"] = int(
            current_subscription.get("extra_ai_credits") or 0
        ) + amount
        return current_subscription

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    telegram_user_id,
                    plan,
                    premium_until,
                    ai_limit_monthly,
                    ai_used_monthly,
                    usage_period,
                    extra_ai_credits,
                    updated_at
                )
                VALUES (%s, 'free', NULL, %s, 0, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_user_id)
                DO UPDATE SET
                    extra_ai_credits = subscriptions.extra_ai_credits
                        + EXCLUDED.extra_ai_credits,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *;
                """,
                (
                    telegram_user_id,
                    FREE_AI_LIMIT_MONTHLY,
                    get_current_usage_period(),
                    amount,
                ),
            )
            subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )
        connection.commit()
        return subscription
    except Exception:
        logger.error("Failed to add AI limit", exc_info=True)
        return current_subscription
    finally:
        if connection is not None:
            connection.close()


def format_kzt(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def get_payment_package_by_button(
    button_text: str,
) -> tuple[str | None, dict | None]:
    for package_code, package in PAYMENT_PACKAGES.items():
        if package["button"] == button_text:
            return package_code, package
    return None, None


def get_admin_activation_command(telegram_user_id: int, package_code: str) -> str:
    if package_code == "ai_30":
        return f"/add_ai_limit {telegram_user_id} {AI_PACK_30_LIMIT}"
    if package_code == "premium_90":
        return f"/grant_premium {telegram_user_id} {PREMIUM_90_DAYS}"
    return f"/grant_premium {telegram_user_id} {PREMIUM_30_DAYS}"


def create_payment_request(
    telegram_user_id: int,
    package_code: str,
    amount_kzt: int,
) -> dict | None:
    database_url = get_database_url()
    if not database_url:
        return None

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO payment_requests (
                    telegram_user_id,
                    package_code,
                    amount_kzt,
                    status,
                    updated_at
                )
                VALUES (%s, %s, %s, 'pending', CURRENT_TIMESTAMP)
                RETURNING *;
                """,
                (telegram_user_id, package_code, amount_kzt),
            )
            payment_request = cursor.fetchone()
        connection.commit()
        return payment_request
    except Exception:
        logger.error("Failed to create payment request", exc_info=True)
        return None
    finally:
        if connection is not None:
            connection.close()


def update_latest_payment_request_with_receipt(
    telegram_user_id: int,
    receipt_file_id: str,
    receipt_file_name: str,
) -> dict | None:
    database_url = get_database_url()
    if not database_url:
        return None

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE payment_requests
                SET status = 'receipt_received',
                    receipt_file_id = %s,
                    receipt_file_name = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id
                    FROM payment_requests
                    WHERE telegram_user_id = %s
                    AND status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                RETURNING *;
                """,
                (receipt_file_id, receipt_file_name, telegram_user_id),
            )
            payment_request = cursor.fetchone()
        connection.commit()
        return payment_request
    except Exception:
        logger.error("Failed to update payment request receipt", exc_info=True)
        return None
    finally:
        if connection is not None:
            connection.close()


def approve_latest_payment_request(telegram_user_id: int) -> None:
    database_url = get_database_url()
    if not database_url:
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE payment_requests
                SET status = 'approved',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id
                    FROM payment_requests
                    WHERE telegram_user_id = %s
                    AND status IN (
                        'receipt_received',
                        'pending',
                        'processing'
                    )
                    ORDER BY created_at DESC
                    LIMIT 1
                );
                """,
                (telegram_user_id,),
            )
        connection.commit()
    except Exception:
        logger.error("Failed to approve payment request", exc_info=True)
    finally:
        if connection is not None:
            connection.close()


def claim_payment_request_for_activation(
    telegram_user_id: int,
    package_code: str,
) -> dict | None:
    database_url = get_database_url()
    if not database_url:
        return None

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE payment_requests
                SET status = 'processing',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id
                    FROM payment_requests
                    WHERE telegram_user_id = %s
                    AND package_code = %s
                    AND status = 'receipt_received'
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *;
                """,
                (telegram_user_id, package_code),
            )
            payment_request = cursor.fetchone()
        connection.commit()
        return payment_request
    except Exception:
        logger.error(
            "Failed to claim payment request for activation",
            exc_info=True,
        )
        return None
    finally:
        if connection is not None:
            connection.close()


def update_payment_request_status(
    payment_request_id: int,
    status: str,
) -> None:
    database_url = get_database_url()
    if not database_url:
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE payment_requests
                SET status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (status, payment_request_id),
            )
        connection.commit()
    except Exception:
        logger.error("Failed to update payment request status", exc_info=True)
    finally:
        if connection is not None:
            connection.close()


def build_subscription_profile_block(telegram_user_id: int) -> str:
    if is_admin_user(telegram_user_id):
        return "\n".join(
            [
                "Тариф: Admin",
                "AI-разборы: без лимита",
                f"Telegram ID: {telegram_user_id}",
            ]
        )

    subscription = get_or_create_subscription(telegram_user_id)
    plan_text = "Premium" if is_premium_active(subscription) else "Free"
    lines = [
        f"Тариф: {plan_text}",
    ]

    if is_premium_active(subscription):
        lines.append(
            f"Premium до: {format_db_datetime(subscription.get('premium_until'))}"
        )

    lines.append(
        f"AI-разборы: {int(subscription.get('ai_used_monthly') or 0)} / "
        f"{int(subscription.get('ai_limit_monthly') or 0)}"
    )
    lines.append(
        f"Доп. AI-разборы: {int(subscription.get('extra_ai_credits') or 0)}"
    )
    lines.append(f"Telegram ID: {telegram_user_id}")
    return "\n".join(lines)


def format_user_for_admin(user) -> str:
    if not user:
        return "ID: неизвестно\nUsername: нет\nИмя: нет"

    full_name = " ".join(
        part
        for part in (user.first_name, user.last_name)
        if part
    ).strip()
    return "\n".join(
        [
            f"ID: {user.id}",
            f"Username: @{user.username}" if user.username else "Username: нет",
            f"Имя: {full_name or 'нет'}",
        ]
    )


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not ADMIN_TELEGRAM_IDS:
        return

    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            logger.error("Failed to notify admin %s", admin_id, exc_info=True)


def build_ai_limit_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[PREMIUM_BUTTON], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def build_premium_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [AI_PACK_30_BUTTON],
            [PREMIUM_30_BUTTON],
            [PREMIUM_90_BUTTON],
            ["📋 Профиль"],
            ["⬅️ Назад"],
        ],
        resize_keyboard=True,
    )


def build_payment_instruction_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[PREMIUM_BUTTON], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def build_payment_instruction_text(
    telegram_user_id: int,
    package_code: str,
    package: dict,
) -> str:
    if not PAYMENT_PHONE or not PAYMENT_RECEIVER_NAME:
        return (
            f"{package['title']}\n\n"
            "Реквизиты оплаты скоро появятся. "
            "Для тестового доступа напишите администратору."
        )

    amount_text = format_kzt(package["amount_kzt"])
    if package_code == "ai_30":
        benefit_text = f"{package['ai_credits']} полных AI-разборов"
        activation_text = "После проверки AI-разборы будут добавлены."
    else:
        benefit_text = (
            f"{package['ai_limit']} полных AI-разборов "
            f"на {package['days']} дней"
        )
        activation_text = "После проверки Premium будет активирован."

    return (
        f"{package['title']}\n\n"
        f"Стоимость: {amount_text} ₸\n"
        f"Что получите: {benefit_text}\n\n"
        "Как оплатить:\n\n"
        f"1. Переведите {amount_text} ₸ через Kaspi "
        "или межбанковским переводом на карту.\n"
        f"2. Получатель: {PAYMENT_RECEIVER_NAME}\n"
        f"3. Карта / номер: {PAYMENT_PHONE}\n"
        f"4. Комментарий к переводу: MatchLab {telegram_user_id}\n"
        "5. После оплаты отправьте PDF-чек в этот бот.\n\n"
        "Если перевод не проходит, напишите администратору — "
        "подберём удобный способ оплаты.\n\n"
        "⏱ Проверка обычно занимает 5–15 минут.\n"
        f"{activation_text}"
    )


async def show_premium_screen(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    telegram_user_id = update.effective_user.id if update.effective_user else 0
    await notify_admins(
        context,
        "🔔 Пользователь открыл Premium\n\n"
        f"{format_user_for_admin(update.effective_user)}\n"
        f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}\n\n"
        "Пользователь посмотрел условия подписки.",
    )

    message = (
        "💎 MatchLab Premium\n\n"
        "Во всех платных вариантах AI-разбор одинаковый по качеству.\n"
        "Отличается только количество AI-разборов и срок доступа.\n\n"
        "Free:\n"
        "• обычный анализ матчей\n"
        "• матчи Сегодня / Завтра / Топ матчи\n"
        f"• {FREE_AI_LIMIT_MONTHLY} AI-разборов в месяц\n\n"
        f"⚡ Пакет {AI_PACK_30_LIMIT} AI — {format_kzt(AI_PACK_30_PRICE_KZT)} ₸\n"
        f"• {AI_PACK_30_LIMIT} полных AI-разборов\n"
        "• Без подписки\n"
        "• Можно использовать для матчей Сегодня / Завтра / Топ матчи\n"
        "• Подходит, чтобы попробовать Premium-разбор\n\n"
        f"💎 Premium 1 месяц — {format_kzt(PREMIUM_30_PRICE_KZT)} ₸\n"
        f"• {PREMIUM_30_AI_LIMIT} полных AI-разборов на {PREMIUM_30_DAYS} дней\n"
        "• Турнирная мотивация\n"
        "• Тоталы, форы, угловые, карточки\n"
        "• Главное направление и что лучше пропустить\n\n"
        f"🏆 Premium 3 месяца — {format_kzt(PREMIUM_90_PRICE_KZT)} ₸\n"
        f"• {PREMIUM_90_AI_LIMIT} полных AI-разборов на {PREMIUM_90_DAYS} дней\n"
        "• Всё, что входит в Premium\n"
        "• Выгоднее, чем платить каждый месяц\n\n"
        "Выберите пакет ниже.\n\n"
        f"Ваш Telegram ID: {telegram_user_id}"
    )

    await update.message.reply_text(message, reply_markup=build_premium_markup())


async def handle_payment_package_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    package_code: str,
    package: dict,
) -> None:
    if not update.effective_user:
        return

    telegram_user_id = update.effective_user.id
    payment_request = create_payment_request(
        telegram_user_id,
        package_code,
        package["amount_kzt"],
    )
    if not payment_request:
        await update.message.reply_text(
            "Заявка на оплату временно недоступна. Попробуйте позже.",
            reply_markup=build_premium_markup(),
        )
        return

    context.user_data["selected_payment_package"] = package_code
    event_data = {
        "package_code": package_code,
        "package_title": package["title"],
        "amount_kzt": package["amount_kzt"],
    }
    track_user_action(update, "payment_package_selected", event_data)

    await notify_admins(
        context,
        "💳 Пользователь выбрал пакет\n\n"
        f"{format_user_for_admin(update.effective_user)}\n"
        f"Пакет: {package['title']}\n"
        f"Сумма: {format_kzt(package['amount_kzt'])} ₸\n"
        f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}\n\n"
        "Ожидаем PDF-чек.\n\n"
        "Готовая команда после проверки:\n"
        f"{get_admin_activation_command(telegram_user_id, package_code)}",
    )

    await update.message.reply_text(
        build_payment_instruction_text(telegram_user_id, package_code, package),
        reply_markup=build_payment_instruction_markup(),
    )


async def payment_receipt_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message or not update.message.document or not update.effective_user:
        return

    document = update.message.document
    file_name = document.file_name or "receipt.pdf"
    mime_type = document.mime_type or ""
    is_pdf = mime_type == "application/pdf" or file_name.lower().endswith(".pdf")
    if not is_pdf:
        return

    telegram_user_id = update.effective_user.id
    file_size = document.file_size
    track_user_action(
        update,
        "pdf_receipt_sent",
        {
            "file_name": file_name,
            "file_size": file_size,
        },
    )
    payment_request = update_latest_payment_request_with_receipt(
        telegram_user_id,
        document.file_id,
        file_name,
    )

    if payment_request:
        package_code = payment_request["package_code"]
        package = PAYMENT_PACKAGES.get(package_code, {})
        package_title = package.get("title", package_code)
        admin_command = get_admin_activation_command(telegram_user_id, package_code)
        await update.message.reply_text(
            "✅ PDF-чек получен.\n\n"
            "Проверка обычно занимает 5–15 минут.\n"
            "После подтверждения доступ будет активирован.",
            reply_markup=build_main_menu_markup(),
        )
        await notify_admins(
            context,
            "🧾 Получен PDF-чек на проверку\n\n"
            f"{format_user_for_admin(update.effective_user)}\n"
            f"Пакет: {package_title}\n"
            f"Сумма: {format_kzt(payment_request['amount_kzt'])} ₸\n"
            f"Файл: {file_name}\n"
            f"Размер: {file_size}\n"
            f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}\n\n"
            "Проверь оплату и активируй доступ:\n"
            f"{admin_command}",
        )
        return

    await update.message.reply_text(
        "✅ PDF-чек получен.\n\n"
        "Но пакет не выбран. Нажмите “💎 Подписка” и выберите нужный пакет, "
        "чтобы мы могли быстрее проверить оплату.",
        reply_markup=build_payment_instruction_markup(),
    )
    await notify_admins(
        context,
        "🧾 Получен PDF-чек без выбранного пакета\n\n"
        f"{format_user_for_admin(update.effective_user)}\n"
        f"Файл: {file_name}\n"
        f"Размер: {file_size}\n"
        f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}\n\n"
        "Проверь вручную.",
    )


async def grant_premium_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Использование: /grant_premium telegram_id days")
        return

    try:
        telegram_user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else PREMIUM_30_DAYS
    except ValueError:
        await update.message.reply_text("Использование: /grant_premium telegram_id days")
        return

    if days <= 0:
        await update.message.reply_text("Количество дней должно быть больше 0.")
        return

    ai_limit = PREMIUM_90_AI_LIMIT if days == PREMIUM_90_DAYS else PREMIUM_30_AI_LIMIT
    subscription = grant_premium(telegram_user_id, days, ai_limit)
    approve_latest_payment_request(telegram_user_id)
    log_user_event(
        telegram_user_id,
        "premium_granted",
        {
            "days": days,
            "ai_limit": ai_limit,
            "admin_id": update.effective_user.id if update.effective_user else None,
        },
    )

    await update.message.reply_text(
        "✅ Premium выдан пользователю "
        f"{telegram_user_id} до {format_db_datetime(subscription.get('premium_until'))}"
    )


async def revoke_premium_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Использование: /revoke_premium telegram_id")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Использование: /revoke_premium telegram_id")
        return

    revoke_premium(telegram_user_id)
    await update.message.reply_text(
        f"✅ Premium отключён для пользователя {telegram_user_id}"
    )


async def add_ai_limit_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /add_ai_limit telegram_id amount")
        return

    try:
        telegram_user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Использование: /add_ai_limit telegram_id amount")
        return

    if amount <= 0:
        await update.message.reply_text("Количество AI-разборов должно быть больше 0.")
        return

    subscription = add_ai_limit(telegram_user_id, amount)
    approve_latest_payment_request(telegram_user_id)
    log_user_event(
        telegram_user_id,
        "ai_limit_added",
        {
            "amount": amount,
            "admin_id": update.effective_user.id if update.effective_user else None,
        },
    )

    await update.message.reply_text(
        f"✅ Добавлено {amount} AI-разборов пользователю {telegram_user_id}. "
        f"Доп. AI-разборы: {subscription.get('extra_ai_credits', 0)}"
    )


async def subscription_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if await deny_non_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Использование: /subscription telegram_id")
        return

    try:
        telegram_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Использование: /subscription telegram_id")
        return

    subscription = get_or_create_subscription(telegram_user_id)
    await update.message.reply_text(
        "💎 Подписка пользователя\n\n"
        f"plan: {subscription.get('plan')}\n"
        f"premium_until: {format_db_datetime(subscription.get('premium_until'))}\n"
        "ai_used_monthly / ai_limit_monthly: "
        f"{subscription.get('ai_used_monthly')} / "
        f"{subscription.get('ai_limit_monthly')}\n"
        f"extra_ai_credits: {subscription.get('extra_ai_credits')}\n"
        f"usage_period: {subscription.get('usage_period')}"
    )


def get_favorite_team_from_db(user_id: int) -> str | None:
    database_url = get_database_url()
    if not database_url:
        return None

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT favorite_team
                FROM user_settings
                WHERE telegram_user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
    except Exception:
        logger.exception("Failed to get favorite team from database")
        return None
    finally:
        if connection is not None:
            connection.close()

    if not row:
        return None

    return row["favorite_team"]


def save_favorite_team_to_db(user_id: int, team_name: str) -> None:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; favorite team was not persisted"
        )
        return

    connection = None

    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_settings (
                    telegram_user_id,
                    favorite_team,
                    updated_at
                )
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_user_id)
                DO UPDATE SET
                    favorite_team = EXCLUDED.favorite_team,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, team_name),
            )
        connection.commit()
    except Exception:
        logger.exception("Failed to save favorite team to database")
    finally:
        if connection is not None:
            connection.close()


def get_current_favorite_team(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> str | None:
    favorite_team = context.user_data.get("favorite_team")
    if favorite_team:
        return favorite_team

    if not update.effective_user:
        return None

    favorite_team = get_favorite_team_from_db(update.effective_user.id)
    if favorite_team:
        context.user_data["favorite_team"] = favorite_team
        return favorite_team

    return None


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def build_main_menu_markup() -> ReplyKeyboardMarkup:
    keyboard = [
        ["📅 Сегодня", "📆 Завтра"],
        ["🔥 Топ матчи"],
        ["⚽ Команда", "📊 Результаты"],
        ["⭐ Моя команда", "📋 Профиль"],
        ["🏆 Таблица", PREMIUM_BUTTON],
    ]
    if WEBAPP_URL:
        keyboard.insert(
            0,
            [
                KeyboardButton(
                    text="🚀 Открыть MatchLab",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
        )

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


def build_miniapp_inline_keyboard(
    screen: str | None = None,
) -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL:
        return None

    button_url = WEBAPP_URL
    button_text = "🚀 Открыть MatchLab"
    if screen:
        url_parts = urlsplit(WEBAPP_URL)
        query_params = dict(
            parse_qsl(url_parts.query, keep_blank_values=True)
        )
        query_params["screen"] = screen
        button_url = urlunsplit(
            (
                url_parts.scheme,
                url_parts.netloc,
                url_parts.path,
                urlencode(query_params),
                url_parts.fragment,
            )
        )
        if screen == "profile":
            button_text = "👤 Открыть профиль"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    button_text,
                    web_app=WebAppInfo(url=button_url),
                )
            ]
        ]
    )


def build_match_analysis_back_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["⬅️ Назад"]],
        resize_keyboard=True,
    )


def build_match_analysis_ai_markup() -> ReplyKeyboardMarkup:
    keyboard = []
    if OPENAI_API_KEY:
        keyboard.append([MATCH_AI_ANALYSIS_BUTTON])
    keyboard.append(["⬅️ Назад"])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.text and update.message.text.startswith("/start"):
        track_user_action(update, "start")
    reply_markup = build_main_menu_markup()

    await update.message.reply_text(
        "⚽ MatchLab\n\n"
        "📅 Сегодня — матчи на сегодня\n"
        "📆 Завтра — матчи на завтра\n"
        "🔥 Топ матчи — самые интересные игры\n"
        "⚽ Команда — ближайшие матчи команды\n"
        "📊 Результаты — последние результаты команды\n"
        "📋 Профиль — тариф, AI-лимиты и Telegram ID\n"
        "⭐ Моя команда — выбрать или изменить любимую команду\n"
        "🏆 Таблица — турнирные таблицы лиг",
        reply_markup=reply_markup,
    )

    miniapp_markup = build_miniapp_inline_keyboard()
    if miniapp_markup:
        await update.message.reply_text(
            "🚀 Mini App доступен здесь:",
            reply_markup=miniapp_markup,
        )


def fetch_fixtures_for_date(api_key: str, date_value: datetime) -> list[dict]:
    response = requests.get(
        f"{API_FOOTBALL_BASE_URL}/fixtures",
        headers={"x-apisports-key": api_key},
        params={
            "date": date_value.strftime("%Y-%m-%d"),
            "timezone": "UTC",
        },
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football error: {errors}")

    return payload.get("response", [])


def get_matches_next_24_hours(api_key: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=24)

    fixtures = []
    for date_value in (now, until):
        fixtures.extend(fetch_fixtures_for_date(api_key, date_value))

    matches_by_id = {}
    for item in fixtures:
        fixture = item.get("fixture", {})
        fixture_id = fixture.get("id")
        timestamp = fixture.get("timestamp")

        if fixture_id is None or timestamp is None:
            continue

        kickoff = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if now <= kickoff <= until:
            matches_by_id[fixture_id] = item

    return sorted(
        matches_by_id.values(),
        key=lambda item: item["fixture"]["timestamp"],
    )[:MAX_MATCHES]


def get_top_matches_next_24_hours(api_key: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    first_window_end = now + timedelta(hours=24)
    second_window_end = now + timedelta(hours=48)

    top_matches = get_top_matches_between(api_key, now, first_window_end)

    if len(top_matches) < 5:
        second_window_matches = get_top_matches_between(
            api_key,
            first_window_end,
            second_window_end,
        )
        existing_fixture_ids = {
            match.get("fixture", {}).get("id")
            for match in top_matches
        }
        for match in second_window_matches:
            fixture_id = match.get("fixture", {}).get("id")
            if fixture_id not in existing_fixture_ids:
                top_matches.append(match)
                existing_fixture_ids.add(fixture_id)
            if len(top_matches) >= MAX_TOP_MATCHES:
                break

    return sorted(
        top_matches,
        key=lambda item: item["fixture"]["timestamp"],
    )[:MAX_TOP_MATCHES]


def get_top_matches_between(
    api_key: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    fixtures = []
    for date_value in (start_time, end_time):
        fixtures.extend(fetch_fixtures_for_date(api_key, date_value))

    matches_by_id = {}
    for match in fixtures:
        fixture = match.get("fixture", {})
        fixture_id = fixture.get("id")
        timestamp = fixture.get("timestamp")

        if fixture_id is None or timestamp is None:
            continue

        kickoff = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        kickoff_almaty = kickoff.astimezone(ALMATY_TZ)
        start_almaty = start_time.astimezone(ALMATY_TZ)
        end_almaty = end_time.astimezone(ALMATY_TZ)
        teams = match.get("teams", {})
        home = teams.get("home", {}).get("name", "")
        away = teams.get("away", {}).get("name", "")
        included = start_almaty <= kickoff_almaty <= end_almaty
        logger.debug(
            "Match %s - %s | kickoff_utc=%s | kickoff_almaty=%s | included=%s",
            home,
            away,
            kickoff,
            kickoff_almaty,
            included,
        )
        if included:
            matches_by_id[fixture_id] = match

    matches = sorted(
        matches_by_id.values(),
        key=lambda item: item["fixture"]["timestamp"],
    )

    for match in matches[:20]:
        league = match.get("league", {})
        logger.info(
            "Fixture league: id=%s, name=%s",
            league.get("id"),
            league.get("name"),
        )

    return [
        match
        for match in matches
        if match.get("league", {}).get("id") in TOP_LEAGUE_IDS
    ]


def fetch_thesportsdb_events_for_date(api_key: str, date_value: datetime) -> list[dict]:
    response = requests.get(
        f"{THESPORTSDB_BASE_URL}/{api_key}/eventsday.php",
        params={"d": date_value.strftime("%Y-%m-%d"), "s": "Soccer"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("events") or []


def parse_thesportsdb_event_time(event: dict) -> datetime | None:
    timestamp = event.get("strTimestamp")
    if timestamp:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    date_value = event.get("dateEvent")
    time_value = event.get("strTime") or "00:00:00"

    if not date_value:
        return None

    if len(time_value) == 5:
        time_value = f"{time_value}:00"

    dt = datetime.fromisoformat(f"{date_value}T{time_value}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def get_thesportsdb_next_football_matches(api_key: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    events_by_id = {}

    EXCLUDED_WORDS = [
        "Women",
        "Youth",
        "U17",
        "U18",
        "U19",
        "U20",
        "U21",
        "Reserve",
        "Reserves",
        "Regional",
    ]

    for day_offset in range(3):
        date_value = now + timedelta(days=day_offset)

        for event in fetch_thesportsdb_events_for_date(api_key, date_value):
            event_time = parse_thesportsdb_event_time(event)
            event_id = event.get("idEvent")

            if event_time is None or event_time < now:
                continue

            league_name = event.get("strLeague") or ""

            if any(
                word.lower() in league_name.lower()
                for word in EXCLUDED_WORDS
            ):
                continue

            events_by_id[
                event_id or f"{event.get('strEvent')}-{event_time}"
            ] = event

    return sorted(
        events_by_id.values(),
        key=lambda event: parse_thesportsdb_event_time(event) or datetime.max.replace(
            tzinfo=timezone.utc
        ),
    )[:10]


def get_dates_for_almaty_window(
    start_almaty: datetime,
    end_almaty: datetime,
) -> list[datetime]:
    dates = set()
    start_utc = start_almaty.astimezone(timezone.utc)
    end_utc = end_almaty.astimezone(timezone.utc)

    current_date = start_almaty.date()
    while current_date <= end_almaty.date():
        dates.add(current_date)
        current_date += timedelta(days=1)

    current_date = start_utc.date()
    while current_date <= end_utc.date():
        dates.add(current_date)
        current_date += timedelta(days=1)

    return [
        datetime.combine(date_value, datetime.min.time(), tzinfo=timezone.utc)
        for date_value in sorted(dates)
    ]


def get_thesportsdb_football_matches_between(
    api_key: str,
    start_almaty: datetime,
    end_almaty: datetime,
    limit: int | None = None,
) -> list[dict]:
    events_by_id = {}

    EXCLUDED_WORDS = [
        "Women",
        "Youth",
        "U17",
        "U18",
        "U19",
        "U20",
        "U21",
        "Reserve",
        "Reserves",
        "Regional",
    ]

    for date_value in get_dates_for_almaty_window(start_almaty, end_almaty):
        for event in fetch_thesportsdb_events_for_date(api_key, date_value):
            event_time = parse_thesportsdb_event_time(event)
            if event_time is None:
                continue

            kickoff_almaty = event_time.astimezone(ALMATY_TZ)
            home = event.get("strHomeTeam") or ""
            away = event.get("strAwayTeam") or ""
            included = start_almaty <= kickoff_almaty <= end_almaty

            logger.debug(
                "Match %s - %s | kickoff_utc=%s | kickoff_almaty=%s | included=%s",
                home,
                away,
                event_time,
                kickoff_almaty,
                included,
            )

            if not included:
                continue

            league_name = event.get("strLeague") or ""
            if any(
                word.lower() in league_name.lower()
                for word in EXCLUDED_WORDS
            ):
                continue

            event_id = event.get("idEvent")
            events_by_id[
                event_id or f"{event.get('strEvent')}-{event_time}"
            ] = event

    matches = sorted(
        events_by_id.values(),
        key=lambda event: parse_thesportsdb_event_time(event) or datetime.max.replace(
            tzinfo=timezone.utc
        ),
    )

    if limit is not None:
        return matches[:limit]

    return matches


def format_thesportsdb_event(event: dict) -> str:
    home_team = event.get("strHomeTeam") or "Неизвестная команда"
    away_team = event.get("strAwayTeam") or "Неизвестная команда"
    tournament = event.get("strLeague") or "Неизвестный турнир"
    country = event.get("strCountry") or "Неизвестная страна"

    event_time = parse_thesportsdb_event_time(event)
    if event_time is None:
        kickoff_text = "Время неизвестно"
    else:
        kickoff_text = event_time.astimezone(ALMATY_TZ).strftime("%d.%m %H:%M")

    return (
        f"⚽ {home_team} - {away_team}\n"
        f"🏆 {tournament}\n"
        f"🌍 {country}\n"
        f"🕒 {kickoff_text}\n"
    )


def request_api_football(endpoint: str, params: dict) -> list[dict]:
    api_key = os.getenv("FOOTBALL_API_KEY")
    if not api_key:
        raise RuntimeError("FOOTBALL_API_KEY is not configured")

    response = requests.get(
        f"{API_FOOTBALL_BASE_URL}{endpoint}",
        headers={"x-apisports-key": api_key},
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football error: {errors}")

    return payload.get("response", [])


def is_top_or_allowed_match(fixture_item: dict) -> bool:
    league = fixture_item.get("league", {})
    league_id = league.get("id")
    league_name = (league.get("name") or "").lower()

    return (
        league_id in TOP_LEAGUE_IDS
        or "world cup" in league_name
        or "uefa champions league" in league_name
        or "uefa europa league" in league_name
        or "uefa conference league" in league_name
    )


def is_excluded_league_or_match(fixture_item: dict) -> bool:
    if is_top_or_allowed_match(fixture_item):
        return False

    league = fixture_item.get("league", {})
    teams = fixture_item.get("teams", {})
    home_team = teams.get("home", {})
    away_team = teams.get("away", {})

    text = " ".join(
        [
            league.get("name") or "",
            league.get("country") or "",
            home_team.get("name") or "",
            away_team.get("name") or "",
        ]
    ).lower()

    excluded_terms = [
        "women",
        "w league",
        "female",
        "youth",
        "u17",
        "u18",
        "u19",
        "u20",
        "u21",
        "u23",
        "reserve",
        "reserves",
        "b team",
        "regional",
        "amateur",
        "primera c",
        "primera b metropolitana",
        "serie b",
        "serie c",
        "serie d",
        "league two",
        "usl w",
        "usl league two",
        "paraibano u20",
        "mineiro - 2",
        "paulista série b",
        "catarinense - 2",
        "carioca - 2",
        "goiano - 2",
        "pernambucano - 2",
    ]

    if any(term in text for term in excluded_terms):
        return True

    return re.search(r"(?<![a-z0-9])ii(?![a-z0-9])", text) is not None


def get_api_football_matches_between(
    start_almaty: datetime,
    end_almaty: datetime,
    only_top: bool = False,
    allowed_only: bool = False,
) -> list[dict]:
    fixtures_by_id = {}

    for date_value in get_dates_for_almaty_window(start_almaty, end_almaty):
        fixtures = request_api_football(
            "/fixtures",
            {
                "date": date_value.strftime("%Y-%m-%d"),
                "timezone": "UTC",
            },
        )

        for fixture_item in fixtures:
            fixture = fixture_item.get("fixture", {})
            fixture_id = fixture.get("id")
            timestamp = fixture.get("timestamp")

            if fixture_id is None or timestamp is None:
                continue

            kickoff_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            kickoff_almaty = kickoff_utc.astimezone(ALMATY_TZ)
            teams = fixture_item.get("teams", {})
            home = teams.get("home", {}).get("name", "")
            away = teams.get("away", {}).get("name", "")
            included = start_almaty <= kickoff_almaty <= end_almaty

            logger.debug(
                "Match %s - %s | kickoff_utc=%s | kickoff_almaty=%s | included=%s",
                home,
                away,
                kickoff_utc,
                kickoff_almaty,
                included,
            )

            if not included:
                continue

            if is_excluded_league_or_match(fixture_item):
                continue

            if allowed_only and not is_top_or_allowed_match(fixture_item):
                continue

            if only_top and not is_top_or_allowed_match(fixture_item):
                continue

            fixtures_by_id[fixture_id] = fixture_item

    return sorted(
        fixtures_by_id.values(),
        key=lambda item: item.get("fixture", {}).get("timestamp") or 0,
    )


def format_api_football_match_card(fixture_item: dict) -> str:
    teams = fixture_item.get("teams", {})
    league = fixture_item.get("league", {})
    fixture = fixture_item.get("fixture", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")
    country = league.get("country", "Неизвестная страна")

    timestamp = fixture.get("timestamp")
    if timestamp is None:
        kickoff_text = "Время неизвестно"
    else:
        kickoff_text = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).astimezone(ALMATY_TZ).strftime("%d.%m %H:%M")

    return (
        f"⚽ {home_team} - {away_team}\n"
        f"🏆 {tournament}\n"
        f"🌍 {country}\n"
        f"🕒 {kickoff_text}"
    )


def build_numbered_match_list_message(
    title: str,
    fixtures: list[dict],
    analysis_hint: str = "🧠 Для анализа матча отправьте его номер.",
    example_hint: str = "Например: 2",
    limit_note: str | None = None,
) -> tuple[str, dict]:
    lines = [title, ""]
    options = {}

    for index, fixture_item in enumerate(fixtures, start=1):
        number = str(index)
        teams = fixture_item.get("teams", {})
        league = fixture_item.get("league", {})
        fixture = fixture_item.get("fixture", {})
        venue = fixture.get("venue") or {}

        home_team = teams.get("home", {}).get("name", "Неизвестная команда")
        away_team = teams.get("away", {}).get("name", "Неизвестная команда")
        tournament = league.get("name", "Неизвестный турнир")
        country = league.get("country", "Неизвестная страна")
        fixture_id = fixture.get("id")
        timestamp = fixture.get("timestamp")

        if timestamp is None:
            kickoff_text = "Время неизвестно"
        else:
            kickoff_text = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).astimezone(ALMATY_TZ).strftime("%d.%m %H:%M")

        options[number] = {
            "home": home_team,
            "away": away_team,
            "fixture_id": fixture_id,
            "league_id": league.get("id"),
            "league_name": tournament,
            "league_country": country,
            "league_season": league.get("season"),
            "league_round": league.get("round"),
            "kickoff": kickoff_text,
            "venue_name": venue.get("name"),
            "venue_city": venue.get("city"),
        }

        lines.extend(
            [
                f"{number}. {home_team} - {away_team}",
                f"    🏆 {tournament}",
                f"    🌍 {country}",
                f"    🕒 {kickoff_text}",
            ]
        )

    lines.extend(
        [
            "",
            analysis_hint,
            example_hint,
        ]
    )
    if limit_note:
        lines.extend(["", limit_note])

    return "\n".join(lines), options


async def show_numbered_analysis_matches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    title: str,
    fixtures: list[dict],
    source: str,
    limit: int,
) -> None:
    visible_fixtures = fixtures[:limit]
    message, options = build_numbered_match_list_message(
        title,
        visible_fixtures,
        analysis_hint="Введите номер матча для анализа",
        example_hint="или нажмите ⬅️ Назад",
        limit_note=(
            f"Показаны первые {limit} матчей."
            if len(fixtures) > limit
            else None
        ),
    )
    context.user_data["analysis_match_options"] = options
    context.user_data["analysis_match_source"] = source
    context.user_data["waiting_match_number_for_analysis"] = bool(options)

    await update.message.reply_text(
        message,
        reply_markup=build_match_analysis_back_markup(),
    )


def search_api_football_team(team_name: str) -> dict | None:
    team_name = normalize_team_name(team_name)
    results = request_api_football("/teams", {"search": team_name})
    if not results:
        return None

    normalized_name = team_name.strip().lower()
    selected = None

    for item in results:
        team = item.get("team", {})
        if team.get("name", "").strip().lower() == normalized_name:
            selected = item
            break

    if selected is None:
        selected = results[0]

    team = selected.get("team")
    if not team:
        return None

    logger.info(
        "API-Football selected team: id=%s, name=%s, country=%s",
        team.get("id"),
        team.get("name"),
        team.get("country"),
    )

    return team


def get_api_football_next_fixtures(team_id: int) -> list[dict]:
    return request_api_football(
        "/fixtures",
        {
            "team": team_id,
            "next": 5,
            "timezone": "UTC",
        },
    )


def get_api_football_recent_finished_fixtures(
    team_id: int,
    limit: int = 20,
) -> list[dict]:
    fixtures = request_api_football(
        "/fixtures",
        {
            "team": team_id,
            "last": limit,
            "timezone": "UTC",
        },
    )

    finished_statuses = {"FT", "AET", "PEN"}
    finished = [
        fixture
        for fixture in fixtures
        if fixture.get("fixture", {}).get("status", {}).get("short")
        in finished_statuses
    ]

    return sorted(
        finished,
        key=lambda item: item.get("fixture", {}).get("timestamp") or 0,
        reverse=True,
    )[:5]


def format_api_football_fixture(
    item: dict,
    include_score: bool = False,
) -> str:
    teams = item.get("teams", {})
    league = item.get("league", {})
    fixture = item.get("fixture", {})
    goals = item.get("goals", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")
    country = league.get("country", "Неизвестная страна")

    if (
        include_score
        and goals.get("home") is not None
        and goals.get("away") is not None
    ):
        teams_text = (
            f"{home_team} {goals.get('home')}-{goals.get('away')} {away_team}"
        )
    else:
        teams_text = f"{home_team} - {away_team}"

    timestamp = fixture.get("timestamp")
    if timestamp is None:
        kickoff_text = "Время неизвестно"
    else:
        almaty_tz = timezone(timedelta(hours=5))
        kickoff_text = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).astimezone(almaty_tz).strftime("%d.%m %H:%M")

    return (
        f"⚽ {teams_text}\n"
        f"🏆 {tournament}\n"
        f"🌍 {country}\n"
        f"🕒 {kickoff_text}"
    )


def calculate_api_football_form(
    fixtures: list[dict],
    team_id: int,
) -> tuple[int, int, int, list[str]]:
    stats = calculate_team_recent_stats(fixtures, team_id)

    return (
        stats["wins"],
        stats["draws"],
        stats["losses"],
        list(stats["form_icons"]),
    )


def calculate_team_recent_stats(fixtures: list[dict], team_id: int) -> dict:
    wins = 0
    draws = 0
    losses = 0
    goals_for = 0
    goals_against = 0
    total_goals_sum = 0
    both_teams_scored_count = 0
    over_25_count = 0
    matches_count = 0
    form_icons = []

    for item in fixtures[:5]:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue

        if home_id == team_id:
            team_goals = home_goals
            opponent_goals = away_goals
        elif away_id == team_id:
            team_goals = away_goals
            opponent_goals = home_goals
        else:
            continue

        if team_goals > opponent_goals:
            wins += 1
            form_icons.append("✅")
        elif team_goals == opponent_goals:
            draws += 1
            form_icons.append("➖")
        else:
            losses += 1
            form_icons.append("❌")

        goals_for += team_goals
        goals_against += opponent_goals
        total_goals_sum += home_goals + away_goals
        matches_count += 1

        if home_goals > 0 and away_goals > 0:
            both_teams_scored_count += 1

        if (home_goals + away_goals) >= 3:
            over_25_count += 1

    if matches_count:
        avg_goals_for = goals_for / matches_count
        avg_goals_against = goals_against / matches_count
        avg_total_goals = total_goals_sum / matches_count
    else:
        avg_goals_for = 0
        avg_goals_against = 0
        avg_total_goals = 0

    return {
        "form_icons": "".join(form_icons),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_goals_for": avg_goals_for,
        "avg_goals_against": avg_goals_against,
        "avg_total_goals": avg_total_goals,
        "both_teams_scored_count": both_teams_scored_count,
        "over_25_count": over_25_count,
        "matches_count": matches_count,
    }


def get_head_to_head_fixtures(home_team_id: int, away_team_id: int) -> list[dict]:
    fixtures = request_api_football(
        "/fixtures/headtohead",
        {
            "h2h": f"{home_team_id}-{away_team_id}",
            "last": 5,
            "timezone": "UTC",
        },
    )

    finished_statuses = {"FT", "AET", "PEN"}
    finished = [
        fixture
        for fixture in fixtures
        if fixture.get("fixture", {}).get("status", {}).get("short")
        in finished_statuses
    ]

    return sorted(
        finished,
        key=lambda item: item.get("fixture", {}).get("timestamp") or 0,
        reverse=True,
    )


def get_api_football_finished_fixtures(team_id: int) -> list[dict]:
    return get_api_football_recent_finished_fixtures(team_id)[:5]


def calculate_head_to_head_stats(fixtures: list[dict]) -> dict:
    h2h_btts_count = 0
    h2h_over_25_count = 0
    h2h_matches_count = 0
    match_lines = []

    for item in fixtures[:5]:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        home_team = teams.get("home", {}).get("name", "Неизвестная команда")
        away_team = teams.get("away", {}).get("name", "Неизвестная команда")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue

        match_lines.append(f"{home_team} {home_goals}-{away_goals} {away_team}")
        h2h_matches_count += 1

        if home_goals > 0 and away_goals > 0:
            h2h_btts_count += 1

        if (home_goals + away_goals) >= 3:
            h2h_over_25_count += 1

    return {
        "h2h_btts_count": h2h_btts_count,
        "h2h_over_25_count": h2h_over_25_count,
        "h2h_matches_count": h2h_matches_count,
        "match_lines": match_lines,
    }


def get_fixture_prediction(fixture_id: int) -> dict | None:
    try:
        response = request_api_football("/predictions", {"fixture": fixture_id})
    except Exception:
        logger.exception("Failed to get fixture prediction")
        return None

    if not response:
        return None

    prediction_data = response[0]
    if not isinstance(prediction_data, dict):
        return None

    predictions = prediction_data.get("predictions")
    if not isinstance(predictions, dict):
        return None

    return prediction_data


def build_prediction_block(prediction_data: dict | None) -> str:
    if not prediction_data:
        return ""

    predictions = prediction_data.get("predictions") or {}
    winner = predictions.get("winner") or {}
    percent = predictions.get("percent") or {}
    goals = predictions.get("goals") or {}
    lines = ["🤖 Алгоритмический прогноз:"]

    recommendation_parts = []
    advice = predictions.get("advice")
    winner_name = winner.get("name")
    winner_comment = winner.get("comment")
    unavailable_text = "no predictions available"

    raw_recommendation_parts = [
        str(value).strip()
        for value in (advice, winner_name, winner_comment)
        if value
    ]
    if any(
        unavailable_text in value.lower()
        for value in raw_recommendation_parts
    ):
        return ""

    if advice:
        recommendation_parts.append(str(advice))
    elif winner_name:
        recommendation_parts.append(str(winner_name))

    if winner_comment:
        recommendation_parts.append(str(winner_comment))

    if predictions.get("win_or_draw") is True:
        recommendation_parts.append("победа или ничья")

    if recommendation_parts:
        lines.append(f"📌 Рекомендация: {'; '.join(recommendation_parts)}")

    probability_parts = []
    percent_values = {
        "home": parse_stat_number(percent.get("home")),
        "draw": parse_stat_number(percent.get("draw")),
        "away": parse_stat_number(percent.get("away")),
    }
    has_useful_recommendation = bool(recommendation_parts)
    is_fake_even_split = all(
        value is not None and round(value) == 33
        for value in percent_values.values()
    )
    if is_fake_even_split and not has_useful_recommendation:
        return ""

    if percent.get("home"):
        probability_parts.append(f"П1 {percent['home']}")
    if percent.get("draw"):
        probability_parts.append(f"X {percent['draw']}")
    if percent.get("away"):
        probability_parts.append(f"П2 {percent['away']}")
    if probability_parts:
        lines.append(f"📊 Вероятности: {' / '.join(probability_parts)}")

    under_over = predictions.get("under_over")
    if under_over:
        lines.append(f"⚽ Тотал: {under_over}")

    expected_goals_parts = []
    if goals.get("home"):
        expected_goals_parts.append(f"хозяева {goals['home']}")
    if goals.get("away"):
        expected_goals_parts.append(f"гости {goals['away']}")
    if expected_goals_parts:
        lines.append(f"🥅 Ожидаемые голы: {' / '.join(expected_goals_parts)}")

    if len(lines) == 1 or not has_useful_recommendation:
        return ""

    return "\n".join(lines)


def get_fixture_injuries(fixture_id: int) -> list[dict]:
    try:
        return request_api_football("/injuries", {"fixture": fixture_id})
    except Exception:
        logger.exception("Failed to get fixture injuries")
        return []


def build_injuries_block(
    injuries: list[dict],
    home_team_name: str,
    away_team_name: str,
) -> str:
    if not injuries:
        return (
            "🚑 Потери:\n"
            "Данных по травмам/дисквалификациям для этого матча пока нет."
        )

    grouped = {
        home_team_name: [],
        away_team_name: [],
    }
    normalized_names = {
        home_team_name.strip().lower(): home_team_name,
        away_team_name.strip().lower(): away_team_name,
    }

    for item in injuries:
        team_name = (item.get("team") or {}).get("name")
        player = item.get("player") or {}
        player_name = player.get("name")
        if not team_name or not player_name:
            continue

        display_team_name = normalized_names.get(team_name.strip().lower())
        if not display_team_name:
            continue

        position = player.get("position")
        reason = player.get("reason")
        line = f"• {player_name}"
        if position:
            line += f", {position}"
        if reason:
            line += f" — {reason}"
        grouped[display_team_name].append(line)

    lines = ["🚑 Потери:"]
    has_injuries = False
    for team_name in (home_team_name, away_team_name):
        team_lines = grouped.get(team_name) or []
        if not team_lines:
            continue
        has_injuries = True
        lines.extend(["", f"{team_name}:"])
        lines.extend(team_lines)

    if not has_injuries:
        return (
            "🚑 Потери:\n"
            "Данных по травмам/дисквалификациям для этого матча пока нет."
        )

    return "\n".join(lines)


def get_fixture_statistics(fixture_id: int) -> list[dict]:
    try:
        return request_api_football("/fixtures/statistics", {"fixture": fixture_id})
    except Exception:
        logger.warning(
            "Failed to get fixture statistics for fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
        return []


def parse_stat_number(value) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("%", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def extract_stat_value(
    team_statistics: list[dict],
    stat_names: list[str],
) -> float | None:
    normalized_names = {name.lower() for name in stat_names}

    for item in team_statistics:
        stat_type = str(item.get("type") or "").strip().lower()
        if stat_type not in normalized_names:
            continue

        value = parse_stat_number(item.get("value"))
        if value is not None:
            return value

    return None


def calculate_team_advanced_stats(fixtures: list[dict], team_id: int) -> dict:
    sums = {
        "corners": 0.0,
        "yellow_cards": 0.0,
        "red_cards": 0.0,
        "fouls": 0.0,
        "total_shots": 0.0,
        "shots_on_goal": 0.0,
        "xg": 0.0,
        "xga": 0.0,
    }
    counts = {key: 0 for key in sums}
    matches_with_stats = 0

    for fixture_item in fixtures[:5]:
        fixture_id = fixture_item.get("fixture", {}).get("id")
        if fixture_id is None:
            continue

        statistics = get_fixture_statistics(fixture_id)
        if not statistics:
            continue

        team_entry = None
        opponent_entry = None
        for entry in statistics:
            current_team_id = (entry.get("team") or {}).get("id")
            if current_team_id == team_id:
                team_entry = entry
            else:
                opponent_entry = entry

        if not team_entry:
            continue

        team_stats = team_entry.get("statistics") or []
        opponent_stats = (opponent_entry or {}).get("statistics") or []
        extracted_values = {
            "corners": extract_stat_value(team_stats, ["Corner Kicks"]),
            "yellow_cards": extract_stat_value(team_stats, ["Yellow Cards"]),
            "red_cards": extract_stat_value(team_stats, ["Red Cards"]),
            "fouls": extract_stat_value(
                team_stats,
                [
                    "Fouls",
                    "Fouls committed",
                    "Fouls Committed",
                ],
            ),
            "total_shots": extract_stat_value(
                team_stats,
                [
                    "Total Shots",
                    "Shots Total",
                    "Shots total",
                    "Total shots",
                ],
            ),
            "shots_on_goal": extract_stat_value(team_stats, ["Shots on Goal"]),
            "xg": extract_stat_value(team_stats, ["Expected Goals", "xG"]),
            "xga": extract_stat_value(opponent_stats, ["Expected Goals", "xG"]),
        }

        has_any_value = False
        for key, value in extracted_values.items():
            if value is None:
                continue
            sums[key] += value
            counts[key] += 1
            has_any_value = True

        if has_any_value:
            matches_with_stats += 1

    return {
        "matches_with_stats": matches_with_stats,
        "matches_count": matches_with_stats,
        "avg_corners": (
            sums["corners"] / counts["corners"]
            if counts["corners"]
            else None
        ),
        "avg_yellow_cards": (
            sums["yellow_cards"] / counts["yellow_cards"]
            if counts["yellow_cards"]
            else None
        ),
        "avg_red_cards": (
            sums["red_cards"] / counts["red_cards"]
            if counts["red_cards"]
            else None
        ),
        "avg_fouls": sums["fouls"] / counts["fouls"] if counts["fouls"] else None,
        "avg_total_shots": (
            sums["total_shots"] / counts["total_shots"]
            if counts["total_shots"]
            else None
        ),
        "avg_shots_on_goal": (
            sums["shots_on_goal"] / counts["shots_on_goal"]
            if counts["shots_on_goal"]
            else None
        ),
        "avg_xg": sums["xg"] / counts["xg"] if counts["xg"] else None,
        "avg_xga": sums["xga"] / counts["xga"] if counts["xga"] else None,
        "avg_xg_for": sums["xg"] / counts["xg"] if counts["xg"] else None,
        "avg_xg_against": sums["xga"] / counts["xga"] if counts["xga"] else None,
    }


def format_optional_average(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def format_ai_numeric_value(
    value: int | float | None,
    digits: int = 2,
    no_data_text: str = "нет данных",
) -> str:
    if value is None:
        return no_data_text
    return f"{value:.{digits}f}"


def build_ai_team_numeric_basis_lines(
    team_name: str,
    recent_stats: dict,
    advanced_stats: dict,
) -> list[str]:
    recent_matches_count = recent_stats.get("matches_count") or 0
    advanced_matches_count = (
        advanced_stats.get("matches_count")
        or advanced_stats.get("matches_with_stats")
        or 0
    )
    avg_goals_for = (
        recent_stats.get("avg_goals_for")
        if recent_matches_count
        else None
    )
    avg_goals_against = (
        recent_stats.get("avg_goals_against")
        if recent_matches_count
        else None
    )
    lines = [
        f"{team_name}, последние {recent_matches_count} матчей:",
        (
            "• забивает: "
            f"{format_ai_numeric_value(avg_goals_for)} за матч"
        ),
        (
            "• пропускает: "
            f"{format_ai_numeric_value(avg_goals_against)} за матч"
        ),
        f"• xG: {format_ai_numeric_value(advanced_stats.get('avg_xg_for'))}",
        f"• xGA: {format_ai_numeric_value(advanced_stats.get('avg_xg_against'))}",
        f"• удары: {format_ai_numeric_value(advanced_stats.get('avg_total_shots'))}",
        (
            "• удары в створ: "
            f"{format_ai_numeric_value(advanced_stats.get('avg_shots_on_goal'))}"
        ),
        f"• угловые: {format_ai_numeric_value(advanced_stats.get('avg_corners'))}",
        (
            "• жёлтые карточки: "
            f"{format_ai_numeric_value(advanced_stats.get('avg_yellow_cards'))}"
        ),
        (
            "• красные карточки: "
            f"{format_ai_numeric_value(advanced_stats.get('avg_red_cards'))}"
        ),
        f"• фолы: {format_ai_numeric_value(advanced_stats.get('avg_fouls'))}",
        (
            "• период расширенной статистики: последние "
            f"{advanced_matches_count} матчей, где доступна статистика"
        ),
    ]

    if recent_matches_count < 3 or advanced_matches_count < 3:
        lines.append("• Выборка маленькая, выводы по форме менее надёжны.")

    return lines


def build_ai_numeric_basis_block(
    home_team_name: str,
    away_team_name: str,
    home_stats: dict,
    away_stats: dict,
) -> str:
    home_recent_stats = home_stats.get("recent") or {}
    away_recent_stats = away_stats.get("recent") or {}
    home_advanced_stats = home_stats.get("advanced") or {}
    away_advanced_stats = away_stats.get("advanced") or {}
    lines = ["📊 Цифры, на которые опирается анализ", ""]
    lines.extend(
        build_ai_team_numeric_basis_lines(
            home_team_name,
            home_recent_stats,
            home_advanced_stats,
        )
    )
    lines.append("")
    lines.extend(
        build_ai_team_numeric_basis_lines(
            away_team_name,
            away_recent_stats,
            away_advanced_stats,
        )
    )

    return "\n".join(lines)


def describe_cards_profile(
    home_advanced_stats: dict,
    away_advanced_stats: dict,
) -> str:
    card_values = [
        value
        for value in (
            home_advanced_stats.get("avg_yellow_cards"),
            away_advanced_stats.get("avg_yellow_cards"),
        )
        if value is not None
    ]
    red_values = [
        value
        for value in (
            home_advanced_stats.get("avg_red_cards"),
            away_advanced_stats.get("avg_red_cards"),
        )
        if value is not None
    ]
    foul_values = [
        value
        for value in (
            home_advanced_stats.get("avg_fouls"),
            away_advanced_stats.get("avg_fouls"),
        )
        if value is not None
    ]

    if not card_values and not red_values and not foul_values:
        return ""

    total_yellow_cards = sum(card_values) if card_values else 0
    total_red_cards = sum(red_values) if red_values else 0
    total_fouls = sum(foul_values) if foul_values else 0

    if total_yellow_cards >= 5 or total_red_cards >= 0.5 or total_fouls >= 28:
        profile = "жёстко"
    elif total_yellow_cards >= 3 or total_red_cards > 0 or total_fouls >= 18:
        profile = "умеренно"
    else:
        profile = "спокойно"

    return f"🟨 Характер по карточкам: {profile}"


def build_advanced_stats_block(
    home_team_name: str,
    away_team_name: str,
    home_advanced_stats: dict,
    away_advanced_stats: dict,
) -> str:
    rows = []

    stat_rows = [
        ("🚩 Угловые за матч", "avg_corners", 1),
        ("🟨 Жёлтые карточки за матч", "avg_yellow_cards", 1),
        ("🟥 Красные карточки за матч", "avg_red_cards", 1),
        ("🧯 Фолы за матч", "avg_fouls", 1),
        ("🎯 Удары всего за матч", "avg_total_shots", 1),
        ("🥅 Удары в створ за матч", "avg_shots_on_goal", 1),
    ]

    for label, key, digits in stat_rows:
        home_value = home_advanced_stats.get(key)
        away_value = away_advanced_stats.get(key)
        if home_value is None and away_value is None:
            continue
        rows.append(
            f"{label}: {home_team_name} "
            f"{format_optional_average(home_value, digits)} / "
            f"{away_team_name} {format_optional_average(away_value, digits)}"
        )

    home_corners = home_advanced_stats.get("avg_corners")
    away_corners = away_advanced_stats.get("avg_corners")
    if home_corners is not None or away_corners is not None:
        total_corners = (home_corners or 0) + (away_corners or 0)
        rows.append(
            "🚩 Общий средний тотал угловых: "
            f"{format_optional_average(total_corners, 1)}"
        )

    cards_profile = describe_cards_profile(
        home_advanced_stats,
        away_advanced_stats,
    )
    if cards_profile:
        rows.append(cards_profile)

    home_xg = home_advanced_stats.get("avg_xg")
    home_xga = home_advanced_stats.get("avg_xga")
    away_xg = away_advanced_stats.get("avg_xg")
    away_xga = away_advanced_stats.get("avg_xga")
    if any(value is not None for value in (home_xg, home_xga, away_xg, away_xga)):
        rows.append(
            f"📈 xG/xGA: {home_team_name} "
            f"{format_optional_average(home_xg, 2)}/"
            f"{format_optional_average(home_xga, 2)} / "
            f"{away_team_name} {format_optional_average(away_xg, 2)}/"
            f"{format_optional_average(away_xga, 2)}"
        )

    if not rows:
        return ""

    return "\n".join(
        [
            "📎 Средние показатели:",
            "расчёт по последним 5 матчам, где доступна статистика",
            *rows,
        ]
    )


def calculate_statistical_team_score(
    recent_stats: dict,
    advanced_stats: dict | None,
    home_away_stats: dict | None,
) -> float:
    advanced_stats = advanced_stats or {}
    home_away_stats = home_away_stats or {}

    score = 0.0
    score += recent_stats.get("wins", 0) * 2
    score += recent_stats.get("draws", 0)
    score -= recent_stats.get("losses", 0)
    score += recent_stats.get("avg_goals_for", 0) * 0.8
    score -= recent_stats.get("avg_goals_against", 0) * 0.6

    avg_xg = advanced_stats.get("avg_xg")
    if avg_xg is not None:
        score += avg_xg * 0.8

    avg_xga = advanced_stats.get("avg_xga")
    if avg_xga is not None:
        score -= avg_xga * 0.6

    avg_shots_on_goal = advanced_stats.get("avg_shots_on_goal")
    if avg_shots_on_goal is not None:
        score += avg_shots_on_goal * 0.2

    if home_away_stats.get("matches_count"):
        score += home_away_stats.get("wins", 0) * 1.2
        score += home_away_stats.get("draws", 0) * 0.5
        score -= home_away_stats.get("losses", 0) * 0.8
        score += home_away_stats.get("goals_for", 0) * 0.15
        score -= home_away_stats.get("goals_against", 0) * 0.12

    return score


def build_statistical_assessment_block(
    home_team_name: str,
    away_team_name: str,
    home_stats: dict,
    away_stats: dict,
    home_advanced_stats: dict | None = None,
    away_advanced_stats: dict | None = None,
    home_home_stats: dict | None = None,
    away_away_stats: dict | None = None,
    h2h_stats: dict | None = None,
) -> str:
    home_advanced_stats = home_advanced_stats or {}
    away_advanced_stats = away_advanced_stats or {}
    home_home_stats = home_home_stats or {}
    away_away_stats = away_away_stats or {}
    h2h_stats = h2h_stats or {}

    home_score = calculate_statistical_team_score(
        home_stats,
        home_advanced_stats,
        home_home_stats,
    )
    away_score = calculate_statistical_team_score(
        away_stats,
        away_advanced_stats,
        away_away_stats,
    )
    score_diff = home_score - away_score

    if abs(score_diff) < 2:
        advantage_text = "примерно равные шансы"
    elif abs(score_diff) < 5:
        advantage_team = home_team_name if score_diff > 0 else away_team_name
        advantage_text = f"небольшое преимущество {advantage_team}"
    else:
        advantage_team = home_team_name if score_diff > 0 else away_team_name
        advantage_text = f"преимущество {advantage_team}"

    home_total = home_stats.get("avg_total_goals", 0)
    away_total = away_stats.get("avg_total_goals", 0)
    average_total = (home_total + away_total) / 2
    home_matches = home_stats.get("matches_count") or 0
    away_matches = away_stats.get("matches_count") or 0
    home_over_rate = (
        home_stats.get("over_25_count", 0) / home_matches
        if home_matches
        else 0
    )
    away_over_rate = (
        away_stats.get("over_25_count", 0) / away_matches
        if away_matches
        else 0
    )
    average_over_rate = (home_over_rate + away_over_rate) / 2

    if average_total >= 2.8 or average_over_rate >= 0.6:
        goals_text = "ближе к ТБ 2.5"
    elif average_total >= 1.8:
        goals_text = "ближе к ТБ 1.5"
    else:
        goals_text = "осторожнее с тоталом"

    home_btts_rate = (
        home_stats.get("both_teams_scored_count", 0) / home_matches
        if home_matches
        else 0
    )
    away_btts_rate = (
        away_stats.get("both_teams_scored_count", 0) / away_matches
        if away_matches
        else 0
    )
    average_btts_rate = (home_btts_rate + away_btts_rate) / 2
    if average_btts_rate >= 0.65:
        btts_text = "вероятно"
    elif average_btts_rate >= 0.35:
        btts_text = "умеренно"
    else:
        btts_text = "осторожно"

    reasons = []
    if home_stats.get("wins", 0) != away_stats.get("wins", 0):
        reasons.append("лучше форма")
    if abs(
        home_stats.get("avg_goals_for", 0)
        - away_stats.get("avg_goals_for", 0)
    ) >= 0.3:
        reasons.append("выше средняя результативность")
    if abs(
        home_stats.get("avg_goals_against", 0)
        - away_stats.get("avg_goals_against", 0)
    ) >= 0.3:
        reasons.append("меньше пропускает")

    home_shots_on_goal = home_advanced_stats.get("avg_shots_on_goal")
    away_shots_on_goal = away_advanced_stats.get("avg_shots_on_goal")
    if (
        home_shots_on_goal is not None
        and away_shots_on_goal is not None
        and abs(home_shots_on_goal - away_shots_on_goal) >= 1
    ):
        reasons.append("больше ударов в створ")

    if (
        home_home_stats.get("matches_count")
        or away_away_stats.get("matches_count")
    ):
        reasons.append("учтена домашняя/гостевая форма")

    home_xg = home_advanced_stats.get("avg_xg")
    away_xg = away_advanced_stats.get("avg_xg")
    if home_xg is not None and away_xg is not None and abs(home_xg - away_xg) >= 0.25:
        reasons.append("выше xG")

    if h2h_stats.get("h2h_matches_count"):
        reasons.append("есть очные встречи")

    if not reasons:
        reasons.append("данных немного, оценка осторожная")

    return "\n".join(
        [
            "🤖 Статистическая оценка:",
            f"📌 По текущим данным: {advantage_text}",
            f"⚽ По голам: {goals_text}",
            f"🎯 ОЗ: {btts_text}",
            f"💬 Основание: {', '.join(reasons[:3])}.",
        ]
    )


def get_rate(count: int | float | None, total: int | float | None) -> float:
    if not total:
        return 0
    return (count or 0) / total


def append_unique_signal(signals: list[str], signal: str) -> None:
    if signal not in signals:
        signals.append(signal)


def build_analytical_signals_block(
    home_team_name: str,
    away_team_name: str,
    home_stats: dict,
    away_stats: dict,
    home_advanced_stats: dict | None = None,
    away_advanced_stats: dict | None = None,
    home_home_stats: dict | None = None,
    away_away_stats: dict | None = None,
    h2h_stats: dict | None = None,
) -> str:
    home_advanced_stats = home_advanced_stats or {}
    away_advanced_stats = away_advanced_stats or {}
    home_home_stats = home_home_stats or {}
    away_away_stats = away_away_stats or {}
    h2h_stats = h2h_stats or {}

    home_score = calculate_statistical_team_score(
        home_stats,
        home_advanced_stats,
        home_home_stats,
    )
    away_score = calculate_statistical_team_score(
        away_stats,
        away_advanced_stats,
        away_away_stats,
    )
    score_diff = home_score - away_score
    advantage_team_name = None
    advantage_stats = None
    if abs(score_diff) >= 2:
        if score_diff > 0:
            advantage_team_name = home_team_name
            advantage_stats = home_stats
        else:
            advantage_team_name = away_team_name
            advantage_stats = away_stats

    home_matches = home_stats.get("matches_count") or 0
    away_matches = away_stats.get("matches_count") or 0
    total_matches = home_matches + away_matches
    if total_matches == 0:
        return (
            "🧭 Аналитические сигналы:\n"
            "Недостаточно данных для аккуратной оценки."
        )

    home_total = home_stats.get("avg_total_goals", 0)
    away_total = away_stats.get("avg_total_goals", 0)
    average_total = (home_total + away_total) / 2
    home_over_rate = get_rate(home_stats.get("over_25_count"), home_matches)
    away_over_rate = get_rate(away_stats.get("over_25_count"), away_matches)
    combined_over_rate = (home_over_rate + away_over_rate) / 2
    home_btts_rate = get_rate(
        home_stats.get("both_teams_scored_count"),
        home_matches,
    )
    away_btts_rate = get_rate(
        away_stats.get("both_teams_scored_count"),
        away_matches,
    )
    combined_btts_rate = (home_btts_rate + away_btts_rate) / 2

    cautious_signals = []
    medium_risk_signals = []
    high_risk_signals = []

    if average_total >= 2.0 or combined_over_rate >= 0.35:
        append_unique_signal(cautious_signals, "ТБ 1.5 по матчу")

    if advantage_team_name and abs(score_diff) >= 4:
        append_unique_signal(cautious_signals, f"{advantage_team_name} не проиграет")

    if (
        advantage_team_name
        and advantage_stats
        and advantage_stats.get("avg_goals_for", 0) >= 1.2
    ):
        append_unique_signal(
            cautious_signals,
            f"{advantage_team_name} забьёт больше 0.5",
        )

    if advantage_team_name and abs(score_diff) >= 3:
        append_unique_signal(
            medium_risk_signals,
            f"Преимущество {advantage_team_name} по статистике",
        )

    if average_total >= 2.8 or combined_over_rate >= 0.6:
        append_unique_signal(medium_risk_signals, "ТБ 2.5 по матчу")
    elif average_total < 2.3 and combined_over_rate < 0.45:
        append_unique_signal(high_risk_signals, "ТБ 2.5 — рискованно")

    if (
        combined_btts_rate >= 0.45
        or (
            home_stats.get("avg_goals_for", 0) >= 1
            and away_stats.get("avg_goals_for", 0) >= 1
            and home_stats.get("avg_goals_against", 0) >= 0.8
            and away_stats.get("avg_goals_against", 0) >= 0.8
        )
    ):
        append_unique_signal(medium_risk_signals, "ОЗ — умеренно")
    else:
        append_unique_signal(high_risk_signals, "ОЗ — рискованно")

    if advantage_team_name:
        append_unique_signal(high_risk_signals, f"Победа {advantage_team_name}")

    if total_matches < 4:
        append_unique_signal(high_risk_signals, "Любые точные исходы — рискованно")

    sections = [
        ("🟢 Осторожно:", cautious_signals[:2]),
        ("🟡 Средний риск:", medium_risk_signals[:2]),
        ("🔴 Рискованно:", high_risk_signals[:2]),
    ]
    lines = ["🧭 Аналитические сигналы:"]
    has_signals = False

    for title, signals in sections:
        if not signals:
            continue
        has_signals = True
        lines.extend(["", title])
        lines.extend(f"• {signal}" for signal in signals)

    if not has_signals:
        return ""

    lines.extend(
        [
            "",
            "🟢 Осторожно — более мягкий статистический сигнал",
            "🟡 Средний риск — сигнал есть, но требует осторожности",
            "🔴 Рискованно — слабый или нестабильный сигнал",
        ]
    )

    return "\n".join(lines)


def calculate_team_home_away_stats(
    fixtures: list[dict],
    team_id: int,
    mode: str,
) -> dict:
    wins = 0
    draws = 0
    losses = 0
    goals_for = 0
    goals_against = 0
    matches_count = 0

    for item in fixtures:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue

        if mode == "home" and home_id == team_id:
            team_goals = home_goals
            opponent_goals = away_goals
        elif mode == "away" and away_id == team_id:
            team_goals = away_goals
            opponent_goals = home_goals
        else:
            continue

        if team_goals > opponent_goals:
            wins += 1
        elif team_goals == opponent_goals:
            draws += 1
        else:
            losses += 1

        goals_for += team_goals
        goals_against += opponent_goals
        matches_count += 1

        if matches_count >= 5:
            break

    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "matches_count": matches_count,
    }


def build_home_away_block(
    home_team_name: str,
    away_team_name: str,
    home_home_stats: dict,
    away_away_stats: dict,
) -> str:
    lines = ["🏠/✈️ Дом/гость:"]

    if home_home_stats.get("matches_count"):
        lines.append(
            f"{home_team_name} дома: "
            f"{home_home_stats['wins']}В / "
            f"{home_home_stats['draws']}Н / "
            f"{home_home_stats['losses']}П, "
            f"голы {home_home_stats['goals_for']}-"
            f"{home_home_stats['goals_against']}"
        )

    if away_away_stats.get("matches_count"):
        lines.append(
            f"{away_team_name} в гостях: "
            f"{away_away_stats['wins']}В / "
            f"{away_away_stats['draws']}Н / "
            f"{away_away_stats['losses']}П, "
            f"голы {away_away_stats['goals_for']}-"
            f"{away_away_stats['goals_against']}"
        )

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


def get_home_away_context_type(
    league_name: str | None,
    league_country: str | None,
    league_round: str | None,
    venue_name: str | None = None,
    venue_city: str | None = None,
) -> str:
    league_text = (league_name or "").strip().lower()
    country_text = (league_country or "").strip().lower()
    round_text = (league_round or "").strip().lower()
    combined_text = " ".join(
        value
        for value in (
            league_text,
            country_text,
            round_text,
            (venue_name or "").strip().lower(),
            (venue_city or "").strip().lower(),
        )
        if value
    )

    if not combined_text:
        return "unknown"

    leg_markers = ("1st leg", "2nd leg", "first leg", "second leg")
    is_two_legged = any(marker in round_text for marker in leg_markers)
    non_final_knockout_markers = ("semi", "quarter", "round of")
    is_final_round = (
        "finalissima" in round_text
        or "3rd place" in round_text
        or "third place" in round_text
        or round_text in {"final", "finals"}
        or round_text.endswith(" final")
        or round_text.endswith(" finals")
    )
    if (
        is_final_round
        and not is_two_legged
        and not any(marker in round_text for marker in non_final_knockout_markers)
    ):
        return "neutral_or_conditional"

    neutral_tournaments = (
        "world cup",
        "fifa world cup",
        "european championship",
        "copa america",
        "africa cup of nations",
        "afcon",
        "asian cup",
        "gold cup",
        "nations league",
        "confederations cup",
        "club world cup",
    )
    neutral_patterns = (
        r"\buefa euro\b",
        r"\beuro\b",
    )
    if any(name in combined_text for name in neutral_tournaments) or any(
        re.search(pattern, combined_text)
        for pattern in neutral_patterns
    ):
        return "neutral_or_conditional"

    european_club_tournaments = (
        "uefa champions league",
        "champions league",
        "uefa europa league",
        "europa league",
        "uefa europa conference league",
        "conference league",
    )
    if any(name in league_text for name in european_club_tournaments):
        return "strong_home_away"

    domestic_leagues = (
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "eredivisie",
        "primeira liga",
        "süper lig",
        "super lig",
        "kazakhstan premier league",
    )
    if any(name in league_text for name in domestic_leagues):
        return "strong_home_away"

    domestic_cups = (
        "fa cup",
        "efl cup",
        "copa del rey",
        "coppa italia",
        "dfb pokal",
        "coupe de france",
        "taca de portugal",
        "taça de portugal",
        "turkish cup",
        "kazakhstan cup",
    )
    if (
        any(name in league_text for name in domestic_cups)
        or " cup" in f" {league_text}"
        or "кубок" in league_text
    ):
        return "strong_home_away"

    if country_text == "world":
        return "neutral_or_conditional"

    if league_text and country_text and country_text != "world":
        return "strong_home_away"

    return "unknown"


def build_home_away_context_text(context_type: str) -> str:
    if context_type == "strong_home_away":
        return (
            "Контекст поля: home/away выглядит рабочим фактором для этого турнира."
        )
    if context_type == "neutral_or_conditional":
        return (
            "Контекст поля: home/away может быть условным, сильный вывод по "
            "домашнему полю лучше не делать."
        )

    return "Контекст поля: недостаточно данных, учитываем осторожно."


def build_full_match_analysis_text(analysis_data: dict) -> str:
    home_team = analysis_data["home_team"]
    away_team = analysis_data["away_team"]
    home_stats = analysis_data["home_stats"]
    away_stats = analysis_data["away_stats"]
    h2h_stats = analysis_data["h2h_stats"]
    home_matches_count = home_stats["matches_count"]
    away_matches_count = away_stats["matches_count"]
    h2h_matches_count = h2h_stats["h2h_matches_count"]
    match_context = analysis_data.get("match_context") or {}
    lines = [
        "🧠 Анализ матча",
        "",
        f"{home_team['name']} - {away_team['name']}",
    ]

    tournament_lines = []
    if match_context.get("league_name"):
        tournament_lines.append(f"Турнир: {match_context['league_name']}")
    if match_context.get("league_round"):
        tournament_lines.append(f"Раунд: {match_context['league_round']}")
    if match_context.get("kickoff"):
        tournament_lines.append(f"Время: {match_context['kickoff']}")
    venue_parts = [
        part
        for part in (
            match_context.get("venue_name"),
            match_context.get("venue_city"),
        )
        if part
    ]
    if venue_parts:
        tournament_lines.append(f"Стадион/город: {', '.join(venue_parts)}")
    if analysis_data.get("home_away_context_text"):
        tournament_lines.append(analysis_data["home_away_context_text"])
    if tournament_lines:
        lines.extend(["", "🏆 Турнирный контекст:", *tournament_lines])

    if analysis_data.get("numeric_basis_block"):
        lines.extend(["", analysis_data["numeric_basis_block"]])

    lines.extend(
        [
        "",
        "📊 Форма последних 5:",
        f"{home_team['name']}: {home_stats['form_icons'] or 'Нет данных'}",
        f"{away_team['name']}: {away_stats['form_icons'] or 'Нет данных'}",
        "",
        "🏆 Баланс последних 5:",
        (
            f"{home_team['name']}: {home_stats['wins']}В / "
            f"{home_stats['draws']}Н / {home_stats['losses']}П"
        ),
        (
            f"{away_team['name']}: {away_stats['wins']}В / "
            f"{away_stats['draws']}Н / {away_stats['losses']}П"
        ),
        "",
        "⚽ Голы:",
        (
            f"{home_team['name']}: забито {home_stats['goals_for']} / "
            f"пропущено {home_stats['goals_against']}"
        ),
        (
            f"{away_team['name']}: забито {away_stats['goals_for']} / "
            f"пропущено {away_stats['goals_against']}"
        ),
        "",
        "📈 Среднее за матч:",
        (
            f"{home_team['name']}: {home_stats['avg_goals_for']:.1f} забивает / "
            f"{home_stats['avg_goals_against']:.1f} пропускает / "
            f"тотал {home_stats['avg_total_goals']:.1f}"
        ),
        (
            f"{away_team['name']}: {away_stats['avg_goals_for']:.1f} забивает / "
            f"{away_stats['avg_goals_against']:.1f} пропускает / "
            f"тотал {away_stats['avg_total_goals']:.1f}"
        ),
        "",
        "🎯 Тренды:",
        (
            f"{home_team['name']}: ОЗ {home_stats['both_teams_scored_count']}/"
            f"{home_matches_count} / ТБ 2.5 {home_stats['over_25_count']}/"
            f"{home_matches_count}"
        ),
        (
            f"{away_team['name']}: ОЗ {away_stats['both_teams_scored_count']}/"
            f"{away_matches_count} / ТБ 2.5 {away_stats['over_25_count']}/"
            f"{away_matches_count}"
        ),
        ]
    )

    for block in (
        analysis_data["home_away_block"],
        analysis_data["assessment_block"],
        analysis_data["analytical_signals_block"],
        analysis_data["injuries_block"],
        analysis_data["advanced_stats_block"],
    ):
        if block:
            lines.extend(["", block])

    lines.extend(["", "🤝 Очные встречи:"])

    if h2h_stats["match_lines"]:
        lines.extend(h2h_stats["match_lines"])
        lines.extend(
            [
                "",
                f"ОЗ: {h2h_stats['h2h_btts_count']}/{h2h_matches_count}",
                f"ТБ 2.5: {h2h_stats['h2h_over_25_count']}/{h2h_matches_count}",
            ]
        )
    else:
        lines.append("Недостаточно данных.")

    lines.extend(
        [
            "",
            "🧩 Составы:",
            "Обычно становятся доступны примерно за 30–60 минут до начала матча.",
            "Если составов ещё нет — проверьте ближе к старту.",
            "",
            "⚠️ Анализ основан на статистике и алгоритмической оценке. "
            "Это не обещание результата.",
        ]
    )

    return "\n".join(lines)


def describe_public_match_picture(
    home_team_name: str,
    away_team_name: str,
    home_stats: dict,
    away_stats: dict,
    home_advanced_stats: dict,
    away_advanced_stats: dict,
    home_home_stats: dict,
    away_away_stats: dict,
) -> str:
    home_score = calculate_statistical_team_score(
        home_stats,
        home_advanced_stats,
        home_home_stats,
    )
    away_score = calculate_statistical_team_score(
        away_stats,
        away_advanced_stats,
        away_away_stats,
    )
    score_diff = home_score - away_score

    if abs(score_diff) < 2:
        return "команды примерно равны"
    if score_diff > 0:
        if home_stats.get("avg_goals_for", 0) > away_stats.get("avg_goals_for", 0):
            return f"{home_team_name} выглядит активнее в атаке"
        return f"{home_team_name} выглядит стабильнее"

    if away_stats.get("avg_goals_for", 0) > home_stats.get("avg_goals_for", 0):
        return f"{away_team_name} выглядит активнее в атаке"
    return f"{away_team_name} выглядит стабильнее"


def describe_public_goals_direction(home_stats: dict, away_stats: dict) -> str:
    home_matches = home_stats.get("matches_count") or 0
    away_matches = away_stats.get("matches_count") or 0
    average_total = (
        home_stats.get("avg_total_goals", 0)
        + away_stats.get("avg_total_goals", 0)
    ) / 2
    over_rate = (
        get_rate(home_stats.get("over_25_count"), home_matches)
        + get_rate(away_stats.get("over_25_count"), away_matches)
    ) / 2

    if average_total >= 2.8 or over_rate >= 0.6:
        return "матч может быть результативным"
    if average_total >= 2.0 or over_rate >= 0.35:
        return "умеренно"
    return "осторожно"


def describe_public_btts_direction(home_stats: dict, away_stats: dict) -> str:
    home_matches = home_stats.get("matches_count") or 0
    away_matches = away_stats.get("matches_count") or 0
    btts_rate = (
        get_rate(home_stats.get("both_teams_scored_count"), home_matches)
        + get_rate(away_stats.get("both_teams_scored_count"), away_matches)
    ) / 2

    if btts_rate >= 0.65:
        return "вероятно"
    if btts_rate >= 0.35:
        return "умеренно"
    return "осторожно"


def describe_public_home_away_line(team_name: str, stats: dict, label: str) -> str:
    if not stats.get("matches_count"):
        return f"{team_name} {label}: данных мало"

    return (
        f"{team_name} {label}: {stats['wins']}В / {stats['draws']}Н / "
        f"{stats['losses']}П, голы {stats['goals_for']}-{stats['goals_against']}"
    )


def count_team_injuries(injuries: list[dict], team_name: str) -> int:
    normalized_team_name = team_name.strip().lower()
    count = 0

    for item in injuries:
        current_team_name = (item.get("team") or {}).get("name")
        player_name = (item.get("player") or {}).get("name")
        if (
            current_team_name
            and player_name
            and current_team_name.strip().lower() == normalized_team_name
        ):
            count += 1

    return count


def build_public_injuries_summary(
    injuries: list[dict],
    home_team_name: str,
    away_team_name: str,
) -> str:
    if not injuries:
        return "🚑 Потери:\nДанных по потерям пока нет."

    home_count = count_team_injuries(injuries, home_team_name)
    away_count = count_team_injuries(injuries, away_team_name)
    if not home_count and not away_count:
        return "🚑 Потери:\nДанных по потерям пока нет."

    return "\n".join(
        [
            "🚑 Потери:",
            (
                f"{home_team_name}: есть потери"
                if home_count
                else f"{home_team_name}: данных нет"
            ),
            (
                f"{away_team_name}: есть потери"
                if away_count
                else f"{away_team_name}: данных нет"
            ),
        ]
    )


def build_public_match_analysis_text(analysis_data: dict) -> str:
    home_team = analysis_data["home_team"]
    away_team = analysis_data["away_team"]
    home_stats = analysis_data["home_stats"]
    away_stats = analysis_data["away_stats"]
    home_name = home_team["name"]
    away_name = away_team["name"]
    picture = describe_public_match_picture(
        home_name,
        away_name,
        home_stats,
        away_stats,
        analysis_data["home_advanced_stats"],
        analysis_data["away_advanced_stats"],
        analysis_data["home_home_stats"],
        analysis_data["away_away_stats"],
    )
    goals_direction = describe_public_goals_direction(home_stats, away_stats)
    btts_direction = describe_public_btts_direction(home_stats, away_stats)

    lines = [
        "🧠 Анализ матча",
        "",
        f"{home_name} - {away_name}",
        "",
        "📊 Форма последних 5:",
        f"{home_name}: {home_stats['form_icons'] or 'Нет данных'}",
        f"{away_name}: {away_stats['form_icons'] or 'Нет данных'}",
        "",
        "⚽ Общая картина:",
        f"{picture}.",
        f"По голам: {goals_direction}.",
        f"ОЗ: {btts_direction}.",
        "",
        "🏠/✈️ Контекст:",
        analysis_data.get("home_away_context_text")
        or build_home_away_context_text("unknown"),
        describe_public_home_away_line(
            home_name,
            analysis_data["home_home_stats"],
            "дома",
        ),
        describe_public_home_away_line(
            away_name,
            analysis_data["away_away_stats"],
            "в гостях",
        ),
        "",
        build_public_injuries_summary(
            analysis_data["injuries"],
            home_name,
            away_name,
        ),
        "",
        "📎 Детальная статистика:",
        "Доступна в AI-разборе.",
        "",
        "⚠️ Анализ основан на статистике и алгоритмической оценке. "
        "Это не обещание результата.",
    ]

    return "\n".join(lines)


def build_match_analysis_data(
    home_team_name: str,
    away_team_name: str,
    fixture_id: int | None = None,
    match_context: dict | None = None,
) -> dict:
    match_context = match_context or {}
    home_team_name = normalize_team_name(home_team_name)
    away_team_name = normalize_team_name(away_team_name)
    home_team = search_api_football_team(home_team_name)
    away_team = search_api_football_team(away_team_name)

    if not home_team or not away_team:
        error_text = "Команда не найдена 😕\nПопробуйте выбрать другой матч."
        return {
            "error": error_text,
            "full_analysis_text": error_text,
            "public_analysis_text": error_text,
        }

    home_recent_fixtures = get_api_football_recent_finished_fixtures(home_team["id"])
    away_recent_fixtures = get_api_football_recent_finished_fixtures(away_team["id"])
    home_fixtures = home_recent_fixtures[:5]
    away_fixtures = away_recent_fixtures[:5]
    home_stats = calculate_team_recent_stats(home_fixtures, home_team["id"])
    away_stats = calculate_team_recent_stats(away_fixtures, away_team["id"])
    home_home_stats = calculate_team_home_away_stats(
        home_recent_fixtures,
        home_team["id"],
        "home",
    )
    away_away_stats = calculate_team_home_away_stats(
        away_recent_fixtures,
        away_team["id"],
        "away",
    )
    h2h_fixtures = get_head_to_head_fixtures(home_team["id"], away_team["id"])
    h2h_stats = calculate_head_to_head_stats(h2h_fixtures)

    prediction_block = ""
    injuries = []
    injuries_block = ""
    if fixture_id is not None:
        prediction_block = build_prediction_block(get_fixture_prediction(fixture_id))
        injuries = get_fixture_injuries(fixture_id)
        injuries_block = build_injuries_block(
            injuries,
            home_team["name"],
            away_team["name"],
        )

    home_advanced_stats = calculate_team_advanced_stats(
        home_fixtures,
        home_team["id"],
    )
    away_advanced_stats = calculate_team_advanced_stats(
        away_fixtures,
        away_team["id"],
    )
    numeric_basis_block = build_ai_numeric_basis_block(
        home_team["name"],
        away_team["name"],
        {
            "recent": home_stats,
            "advanced": home_advanced_stats,
        },
        {
            "recent": away_stats,
            "advanced": away_advanced_stats,
        },
    )
    advanced_stats_block = build_advanced_stats_block(
        home_team["name"],
        away_team["name"],
        home_advanced_stats,
        away_advanced_stats,
    )
    home_away_block = build_home_away_block(
        home_team["name"],
        away_team["name"],
        home_home_stats,
        away_away_stats,
    )
    assessment_block = prediction_block or build_statistical_assessment_block(
        home_team["name"],
        away_team["name"],
        home_stats,
        away_stats,
        home_advanced_stats,
        away_advanced_stats,
        home_home_stats,
        away_away_stats,
        h2h_stats,
    )
    analytical_signals_block = build_analytical_signals_block(
        home_team["name"],
        away_team["name"],
        home_stats,
        away_stats,
        home_advanced_stats,
        away_advanced_stats,
        home_home_stats,
        away_away_stats,
        h2h_stats,
    )
    home_away_context_type = get_home_away_context_type(
        match_context.get("league_name"),
        match_context.get("league_country"),
        match_context.get("league_round"),
        match_context.get("venue_name"),
        match_context.get("venue_city"),
    )
    analysis_data = {
        "home_team_name": home_team["name"],
        "away_team_name": away_team["name"],
        "fixture_id": fixture_id,
        "match_context": match_context,
        "home_away_context_type": home_away_context_type,
        "home_away_context_text": build_home_away_context_text(
            home_away_context_type
        ),
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": home_stats,
        "away_stats": away_stats,
        "home_advanced_stats": home_advanced_stats,
        "away_advanced_stats": away_advanced_stats,
        "home_home_stats": home_home_stats,
        "away_away_stats": away_away_stats,
        "h2h_stats": h2h_stats,
        "injuries": injuries,
        "prediction_block": prediction_block,
        "assessment_block": assessment_block,
        "analytical_signals_block": analytical_signals_block,
        "injuries_block": injuries_block,
        "numeric_basis_block": numeric_basis_block,
        "advanced_stats_block": advanced_stats_block,
        "home_away_block": home_away_block,
    }
    analysis_data["full_analysis_text"] = build_full_match_analysis_text(
        analysis_data
    )
    analysis_data["public_analysis_text"] = build_public_match_analysis_text(
        analysis_data
    )

    return analysis_data


def build_match_analysis_message(
    home_team_name: str,
    away_team_name: str,
    fixture_id: int | None = None,
) -> str:
    return build_match_analysis_data(
        home_team_name,
        away_team_name,
        fixture_id,
    )["full_analysis_text"]


def build_api_football_team_message(team_name: str) -> str | None:
    team_name = normalize_team_name(team_name)
    team = search_api_football_team(team_name)
    if not team:
        return None

    fixtures = get_api_football_next_fixtures(team["id"])
    if not fixtures:
        return f"⚽ {team['name']}\n\nБлижайшие матчи не найдены."

    return f"⚽ {team['name']}\n\n" + "\n\n".join(
        format_api_football_fixture(fixture)
        for fixture in fixtures[:5]
    )


def get_fixture_league_standings(
    league_id: int | None,
    season: int | None,
) -> list[dict]:
    if not league_id or not season:
        return []

    try:
        response = request_api_football(
            "/standings",
            {
                "league": league_id,
                "season": season,
            },
        )
    except Exception:
        logger.exception("Failed to get fixture league standings")
        return []

    if not response:
        return []

    standings_groups = response[0].get("league", {}).get("standings", [])
    standings = []
    for group_rows in standings_groups:
        for row in group_rows or []:
            row_copy = dict(row)
            if row_copy.get("group") is None and group_rows:
                row_copy["group"] = (group_rows[0] or {}).get("group")
            standings.append(row_copy)

    return standings


def normalize_standings_team_name(team_name: str | None) -> str:
    return (team_name or "").strip().lower().replace("ё", "е")


def find_standings_row(standings: list[dict], team_name: str) -> dict | None:
    normalized_team_name = normalize_standings_team_name(team_name)
    if not normalized_team_name:
        return None

    for row in standings:
        row_team_name = normalize_standings_team_name(
            (row.get("team") or {}).get("name")
        )
        if not row_team_name:
            continue
        if row_team_name == normalized_team_name:
            return row
        if (
            normalized_team_name in row_team_name
            or row_team_name in normalized_team_name
        ):
            return row

    return None


def format_standings_context_row(row: dict | None) -> dict | None:
    if not row:
        return None

    return {
        "rank": row.get("rank"),
        "points": row.get("points"),
        "played": (row.get("all") or {}).get("played"),
        "goalsDiff": row.get("goalsDiff"),
        "form": row.get("form"),
    }


def extract_match_standings_context(
    standings: list[dict],
    home_team_name: str,
    away_team_name: str,
) -> dict:
    home_row = find_standings_row(standings, home_team_name)
    away_row = find_standings_row(standings, away_team_name)
    if not home_row and not away_row:
        return {}

    context = {}
    home_context = format_standings_context_row(home_row)
    away_context = format_standings_context_row(away_row)
    if home_context:
        context["home"] = home_context
    if away_context:
        context["away"] = away_context

    group = None
    if home_row and home_row.get("group"):
        group = home_row.get("group")
    elif away_row and away_row.get("group"):
        group = away_row.get("group")
    context["group"] = group

    return context


def format_tournament_context_team_line(
    team_name: str,
    team_context: dict | None,
) -> str:
    if not team_context:
        return f"* {team_name}: данных нет"

    return (
        f"* {team_name}: место {team_context.get('rank', '-')}, "
        f"очки {team_context.get('points', '-')}, "
        f"матчи {team_context.get('played', '-')}, "
        f"разница {team_context.get('goalsDiff', '-')}, "
        f"форма {team_context.get('form') or '-'}"
    )


def build_tournament_context_for_ai(match_data: dict) -> str:
    context_type = get_home_away_context_type(
        match_data.get("league_name"),
        match_data.get("league_country"),
        match_data.get("league_round"),
        match_data.get("venue_name"),
        match_data.get("venue_city"),
    )
    venue_name = match_data.get("venue_name") or "не указан"
    venue_city = match_data.get("venue_city") or "не указан"
    lines = [
        "Турнир:",
        f"* Название: {match_data.get('league_name') or 'не указано'}",
        f"* Страна/контекст: {match_data.get('league_country') or 'не указано'}",
        f"* Раунд: {match_data.get('league_round') or 'не указан'}",
        f"* Стадион: {venue_name}",
        f"* Город: {venue_city}",
        f"* {build_home_away_context_text(context_type)}",
        "",
        "Таблица/мотивация:",
    ]

    standings = get_fixture_league_standings(
        match_data.get("league_id"),
        match_data.get("league_season"),
    )
    standings_context = extract_match_standings_context(
        standings,
        match_data.get("home") or "",
        match_data.get("away") or "",
    )
    match_data["standings_context"] = standings_context
    match_data["home_away_context_type"] = context_type

    if not standings_context:
        lines.append("Данных по таблице/мотивации нет.")
        return "\n".join(lines)

    lines.append(
        format_tournament_context_team_line(
            match_data.get("home") or "Команда 1",
            standings_context.get("home"),
        )
    )
    lines.append(
        format_tournament_context_team_line(
            match_data.get("away") or "Команда 2",
            standings_context.get("away"),
        )
    )
    lines.append(f"* Группа: {standings_context.get('group') or 'нет данных'}")

    return "\n".join(lines)


def build_ai_prompt(match_data: dict) -> str:
    home_team = match_data.get("home") or "Команда 1"
    away_team = match_data.get("away") or "Команда 2"
    league_name = match_data.get("league_name") or "не указан"
    league_round = match_data.get("league_round") or "не указан"
    kickoff = match_data.get("kickoff") or "не указано"
    venue_name = match_data.get("venue_name") or "не указан"
    venue_city = match_data.get("venue_city") or "не указан"
    tournament_context_text = (
        match_data.get("tournament_context_text")
        or "Данных по турнирному контексту нет."
    )
    numeric_basis_block = (
        match_data.get("numeric_basis_block")
        or "📊 Цифры, на которые опирается анализ\nнет данных"
    )
    analysis_text = match_data.get("analysis_text") or ""

    return (
        "Ты футбольный аналитический помощник MatchLab.\n"
        "Сделай профессиональное матч-превью на русском: коротко, структурно, "
        "с цифрами и понятными выводами. Не копируй стиль конкретных сервисов.\n"
        "Обязательно используй блок '📊 Цифры, на которые опирается анализ'. "
        "В начале AI-разбора покажи реальные цифры по голам, пропущенным, "
        "xG/xGA, ударам, ударам в створ, угловым, карточкам и фолам. "
        "Если xG/xGA нет, честно напиши 'нет данных' и не делай выводы на "
        "основе xG.\n"
        "Не выдумывай отсутствующие данные, xG/xGA, судью, составы, потери, "
        "проценты модели или факты, которых нет во внутренних данных.\n"
        "Если процентная оценка модели по исходам, ОЗ или тоталам есть в "
        "данных — покажи её. Если нет — напиши: Процентная оценка модели по "
        "рынкам недоступна, поэтому вывод строится на форме и статистике "
        "команд.\n"
        "Каждый вывод по голам, тоталам и ОЗ должен опираться на конкретные "
        "цифры: средние забитые, средние пропущенные, xG/xGA если есть, удары "
        "и удары в створ. Если xG или xGA нет в numeric_basis_block, запрещено "
        "придумывать xG. Нужно писать: xG нет в доступных данных, поэтому "
        "вывод по моментам строится по голам, ударам и ударам в створ.\n"
        "Если выборка меньше 3 матчей или в numeric_basis_block есть "
        "предупреждение о маленькой выборке — явно предупреди, что выводы менее "
        "надёжны.\n"
        "Если данных по судье нет — напиши: Данных по судье нет, поэтому вывод "
        "по карточкам строится только по командной статистике. Если данных по "
        "угловым нет — напиши: Данных по угловым недостаточно, поэтому "
        "направление по угловым лучше не усиливать.\n"
        "Контекст поля учитывай осторожно: если поле нейтральное или home/away "
        "условный, не пиши про сильное домашнее преимущество.\n"
        "Дополнительные направления выбирай строго из списка: двойной шанс "
        "1X / X2 / 12; фора 0, +0.5, -0.5, +1.0, -1.0; команда забьёт; "
        "ИТБ 0.5 / 1.0 / 1.5; ИТМ 1.5; гол в 1 тайме; ТБ 0.5 в 1 тайме; "
        "ТМ 1.5 в 1 тайме; угловые только если есть данные; карточки только "
        "если есть данные.\n"
        "Не используй слова: ставка, ставить, экспресс, купон, железно, "
        "гарантия, 100%. Не обещай результат. Не упоминай API-Football.\n"
        "Пиши компактно: каждый блок 2-4 строки, только блок цифр может быть "
        "длиннее. Не повторяй одно и то же.\n"
        "Ответ дай строго в таком порядке:\n\n"
        "🤖 AI-разбор MatchLab\n\n"
        "🏆 Контекст матча\n"
        "Кто играет, турнир, стадия/тур/группа, поле, фаворит по модели или "
        "по базовой оценке без обещаний. Добавь строку '📊 Оценка модели', "
        "если проценты есть; если нет — напиши, что процентная оценка "
        "недоступна.\n\n"
        "📊 Цифры, на которые опирается анализ\n"
        "Покажи цифры из numeric_basis_block: период расчёта, забивает, "
        "пропускает, xG/xGA или нет данных, удары, удары в створ, угловые, "
        "жёлтые/красные карточки, фолы. Не меняй смысл цифр.\n\n"
        f"📈 Форма {home_team}\n"
        "Последние матчи, средние забитые/пропущенные, проблемы атаки/обороны "
        "по цифрам.\n\n"
        f"📉 Форма {away_team}\n"
        "Последние матчи, средние забитые/пропущенные, проблемы атаки/обороны "
        "по цифрам.\n\n"
        "🤝 Очные встречи\n"
        "Если H2H есть — кратко последние очные матчи. Если мало или нет — "
        "напиши: Очных встреч мало, поэтому H2H не должен быть главным фактором "
        "анализа.\n\n"
        "🧩 Игровой стиль и ключевые факторы\n"
        "Объясни через удары, удары в створ, голы, пропущенные и xG/xGA если "
        "есть: кто давит, кто опасен в переходах, где преимущество и риск. "
        "Если данных мало — пиши осторожно.\n\n"
        "🟨 Судья, карточки и угловые\n"
        "Используй жёлтые, красные, фолы, угловые и судью только если данные "
        "есть. Судью не выдумывать.\n\n"
        "⚽ Голы и тоталы:\n"
        "Вывод по ТБ 1.5, ТБ 2.5, индивидуальным тоталам только с числовым "
        "обоснованием.\n\n"
        "🎯 ОЗ\n"
        "Осторожно / умеренно / вероятно. Объясни средними голами, "
        "пропущенными, ударами и xG/xGA если есть.\n\n"
        "📌 Дополнительные направления:\n"
        "3-5 направлений максимум. Формат: • 🟢 Направление — причина в 1 "
        "предложении. Используй нейтральные слова: направление, сигнал, "
        "статистически выглядит, можно рассмотреть, лучше пропустить.\n\n"
        "⭐ Главное направление\n"
        "Выбери одно основное направление и объясни его цифрами. Если сильного "
        "варианта нет — так и напиши.\n\n"
        "🚫 Что лучше пропустить\n"
        "Укажи 1-3 направления, которые лучше не трогать из-за малого объёма "
        "данных или высокого риска.\n\n"
        "💬 Итог:\n"
        "2-3 предложения: итоговая оценка и главный риск.\n\n"
        "В конце обязательно:\n"
        "⚠️ Это статистический обзор, а не обещание результата.\n\n"
        f"Матч: {home_team} - {away_team}\n"
        f"Турнир: {league_name}\n"
        f"Раунд: {league_round}\n"
        f"Время: {kickoff}\n\n"
        f"Стадион: {venue_name}\n"
        f"Город: {venue_city}\n\n"
        "Турнирный контекст и мотивация:\n"
        f"{tournament_context_text}\n\n"
        "numeric_basis_block:\n"
        f"{numeric_basis_block}\n\n"
        "Полные внутренние статистические данные MatchLab:\n"
        f"{analysis_text}"
    )


def sanitize_ai_analysis_text(text: str) -> str:
    replacements = {
        r"\bставка\b": "сигнал",
        r"\bставки\b": "сигналы",
        r"\bставить\b": "рассматривать",
        r"\bэкспресс\b": "подборка",
        r"\bкупон\b": "подборка",
        r"\bжелезно\b": "сильно",
        r"\bгарантия\b": "оценка",
        r"100%": "высокая уверенность",
        r"API-Football": "статистика",
    }
    sanitized_text = text
    for pattern, replacement in replacements.items():
        sanitized_text = re.sub(
            pattern,
            replacement,
            sanitized_text,
            flags=re.IGNORECASE,
        )

    return sanitized_text.strip()


def get_openai_response_field(item, field_name: str):
    if isinstance(item, dict):
        return item.get(field_name)

    return getattr(item, field_name, None)


def extract_openai_response_text(response) -> str:
    output_text = get_openai_response_field(response, "output_text")
    if output_text and str(output_text).strip():
        return str(output_text).strip()

    output_items = get_openai_response_field(response, "output") or []
    text_parts = []

    for output_item in output_items:
        content_items = get_openai_response_field(output_item, "content") or []
        if isinstance(content_items, str):
            text_parts.append(content_items)
            continue

        for content_item in content_items:
            if isinstance(content_item, str):
                text_parts.append(content_item)
                continue

            text = get_openai_response_field(content_item, "text")
            if text is None:
                text = get_openai_response_field(content_item, "value")
            if text is None:
                continue

            text_parts.append(str(text))

    return "\n".join(part.strip() for part in text_parts if part.strip()).strip()


def is_unsupported_reasoning_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "reasoning" in message
        and (
            "unsupported" in message
            or "not supported" in message
            or "unknown parameter" in message
            or "unexpected keyword" in message
        )
    )


def get_openai_ai_analysis(match_data: dict) -> str:
    if not OPENAI_API_KEY:
        return "AI-разбор пока не подключён."

    response = None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратный футбольный аналитик. Отвечай на русском, "
                            "кратко и нейтрально."
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_ai_prompt(match_data),
                    },
                ],
                reasoning={"effort": "minimal"},
                max_output_tokens=1500,
            )
            content = extract_openai_response_text(response)
        except AttributeError:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратный футбольный аналитик. Отвечай на русском, "
                            "кратко и нейтрально."
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_ai_prompt(match_data),
                    },
                ],
                max_completion_tokens=1500,
            )
            content = response.choices[0].message.content or ""
        except Exception as e:
            if not is_unsupported_reasoning_error(e):
                raise

            response = client.responses.create(
                model=OPENAI_MODEL,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратный футбольный аналитик. Отвечай на русском, "
                            "кратко и нейтрально."
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_ai_prompt(match_data),
                    },
                ],
                max_output_tokens=1500,
            )
            content = extract_openai_response_text(response)
    except Exception as e:
        logger.exception("OpenAI match analysis failed: %s", e)
        return "AI-разбор временно недоступен."

    if not content.strip():
        logger.error("OpenAI returned empty AI analysis response")
        logger.error("OpenAI empty response: %s", response)
        return "AI-разбор временно недоступен."

    content = sanitize_ai_analysis_text(content)
    if not content.strip():
        logger.error("OpenAI returned empty AI analysis response")
        return "AI-разбор временно недоступен."

    if content.startswith("🤖 AI-разбор MatchLab"):
        return content

    return f"🤖 AI-разбор MatchLab\n\n{content}"


def build_api_football_results_message(team_name: str) -> str | None:
    team_name = normalize_team_name(team_name)
    team = search_api_football_team(team_name)
    if not team:
        return None

    fixtures = get_api_football_finished_fixtures(team["id"])
    if not fixtures:
        return f"📊 {team['name']}\n\nПоследние матчи не найдены."

    return f"📊 {team['name']}\n\n" + "\n\n".join(
        format_api_football_fixture(fixture, include_score=True)
        for fixture in fixtures[:5]
    )


def build_api_football_profile_message(team_name: str) -> str | None:
    team_name = normalize_team_name(team_name)
    team = search_api_football_team(team_name)
    if not team:
        return None

    team_id = team["id"]
    next_fixtures = get_api_football_next_fixtures(team_id)
    last_fixtures = get_api_football_finished_fixtures(team_id)
    wins, draws, losses, form = calculate_api_football_form(
        last_fixtures,
        team_id,
    )
    goals_for = 0
    goals_against = 0
    total_goals_sum = 0
    completed_matches_count = 0
    both_teams_scored_count = 0
    over_25_count = 0
    home_wins = 0
    home_draws = 0
    home_losses = 0
    away_wins = 0
    away_draws = 0
    away_losses = 0

    for fixture in last_fixtures[:5]:
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue

        if home_id == team_id:
            team_goals = home_goals
            opponent_goals = away_goals
            if team_goals > opponent_goals:
                home_wins += 1
            elif team_goals == opponent_goals:
                home_draws += 1
            else:
                home_losses += 1
        elif away_id == team_id:
            team_goals = away_goals
            opponent_goals = home_goals
            if team_goals > opponent_goals:
                away_wins += 1
            elif team_goals == opponent_goals:
                away_draws += 1
            else:
                away_losses += 1
        else:
            team_goals = away_goals
            opponent_goals = home_goals

        goals_for += team_goals
        goals_against += opponent_goals
        total_goals_sum += home_goals + away_goals
        completed_matches_count += 1

        if home_goals > 0 and away_goals > 0:
            both_teams_scored_count += 1

        if (home_goals + away_goals) >= 3:
            over_25_count += 1

    if completed_matches_count:
        average_goals_for = goals_for / completed_matches_count
        average_goals_against = goals_against / completed_matches_count
        average_total_goals = total_goals_sum / completed_matches_count
    else:
        average_goals_for = 0
        average_goals_against = 0
        average_total_goals = 0

    message = (
        "📋 Профиль\n\n"
        f"⭐ Любимая команда: {team['name']}\n\n"
        "📅 Ближайшие 5 матчей\n\n"
    )

    if next_fixtures:
        message += "\n\n".join(
            format_api_football_fixture(fixture)
            for fixture in next_fixtures[:5]
        )
    else:
        message += "Ближайшие матчи не найдены."

    message += "\n\n📊 Последние 5 матчей\n\n"

    if last_fixtures:
        message += "\n\n".join(
            format_api_football_fixture(fixture, include_score=True)
            for fixture in last_fixtures[:5]
        )
    else:
        message += "Последние матчи не найдены."

    message += (
        "\n\n🔥 Форма команды\n\n"
        f"{''.join(form) or 'Нет данных'}\n\n"
        f"🏆 Побед: {wins}\n"
        f"🤝 Ничьих: {draws}\n"
        f"😔 Поражений: {losses}\n\n"
        "📈 Статистика последних 5 матчей\n\n"
        f"⚽ Забито: {goals_for}\n"
        f"🥅 Пропущено: {goals_against}\n\n"
        "📊 Среднее за матч:\n"
        f"⚽ {average_goals_for:.1f}\n"
        f"🥅 {average_goals_against:.1f}\n"
        f"⚽ Средний тотал: {average_total_goals:.1f}\n\n"
        "🎯 Тренды последних 5 матчей\n\n"
        f"⚽ ОЗ прошло: {both_teams_scored_count}/5\n"
        f"🔥 ТБ 2.5 прошло: {over_25_count}/5\n\n"
        f"🏠 Дома: {home_wins}В / {home_draws}Н / {home_losses}П\n"
        f"✈️ В гостях: {away_wins}В / {away_draws}Н / {away_losses}П\n\n"
        "В — выигрыш, Н — ничья, П — поражение"
    )

    return message


def build_api_football_standings_message(
    league_id: int,
    season: int,
    league_name: str,
    country: str,
) -> str:
    response = request_api_football(
        "/standings",
        {
            "league": league_id,
            "season": season,
        },
    )

    if not response:
        return (
            "🏆 Таблица\n\n"
            f"{league_name}\n"
            f"🌍 {country}\n\n"
            "Таблица не найдена."
        )

    standings_groups = response[0].get("league", {}).get("standings", [])
    standings = standings_groups[0] if standings_groups else []

    if not standings:
        return (
            "🏆 Таблица\n\n"
            f"{league_name}\n"
            f"🌍 {country}\n\n"
            "Таблица не найдена."
        )

    lines = [
        "🏆 Таблица",
        "",
        league_name,
        f"🌍 {country}",
        "",
    ]
    table_lines = []
    table_lines.append(
        f"{'#':<3}{'Команда':<18}{'Очки':>5}{'Игры':>6}{'+/-':>6}  {'Форма'}"
    )

    for row in standings[:20]:
        rank = row.get("rank", "-")
        team_name = row.get("team", {}).get("name", "Неизвестная команда")
        points = row.get("points", 0)
        played = row.get("all", {}).get("played", 0)
        goals_diff = row.get("goalsDiff")
        form = row.get("form")

        if goals_diff is None:
            goals_diff_text = "-"
        elif goals_diff > 0:
            goals_diff_text = f"+{goals_diff}"
        else:
            goals_diff_text = str(goals_diff)

        if form:
            form_text = (
                form
                .replace("W", "✅")
                .replace("D", "➖")
                .replace("L", "❌")
            )
        else:
            form_text = "нет формы"

        short_team_name = team_name
        if len(short_team_name) > 17:
            short_team_name = short_team_name[:17]

        table_lines.append(
            f"{rank:<3}"
            f"{short_team_name:<18}"
            f"{points:>5}"
            f"{played:>6}"
            f"{goals_diff_text:>6}  "
            f"{form_text}"
        )

    lines.append("```")
    lines.extend(table_lines)
    lines.append("```")

    lines.extend(
        [
            "",
            "📌 Формат:",
            "Очки — количество очков",
            "Игры — сыгранные матчи",
            "+/- — разница голов",
            "✅ — победа, ➖ — ничья, ❌ — поражение",
        ]
    )

    return "\n".join(lines)


def format_match(item: dict) -> str:
    teams = item.get("teams", {})
    league = item.get("league", {})
    fixture = item.get("fixture", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")
    country = league.get("country", "Неизвестная страна")

    kickoff = datetime.fromtimestamp(
        fixture["timestamp"],
        tz=timezone.utc
    ).astimezone(ALMATY_TZ)
    kickoff_text = kickoff.strftime("%d.%m %H:%M")

    return (
        f"⚽ {home_team} - {away_team}\n"
        f"🏆 Турнир: {tournament}\n"
        f"🌍 Страна: {country}\n"
        f"🕒 Начало: {kickoff_text}"
    )


def format_top_match(item: dict) -> str:
    teams = item.get("teams", {})
    league = item.get("league", {})
    fixture = item.get("fixture", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")
    country = league.get("country", "Неизвестная страна")

    kickoff = datetime.fromtimestamp(
        fixture["timestamp"],
        tz=timezone.utc
    ).astimezone(ALMATY_TZ)
    kickoff_text = kickoff.strftime("%d.%m %H:%M")

    return (
        f"⚽ {home_team} - {away_team}\n"
        f"🏆 {tournament} ({country})\n"
        f"🕒 {kickoff_text}"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user_action(update, "today_clicked")
    context.user_data["analysis_match_options"] = []
    context.user_data["analysis_match_source"] = None
    context.user_data["waiting_match_number_for_analysis"] = False
    context.user_data["last_match_for_ai"] = None

    try:
        now_almaty = datetime.now(ALMATY_TZ)
        today_start = now_almaty
        today_end = datetime.combine(
            now_almaty.date(),
            datetime.max.time(),
            tzinfo=ALMATY_TZ,
        )
        api_matches = get_api_football_matches_between(
            today_start,
            today_end,
            only_top=False,
            allowed_only=True,
        )
        if not api_matches:
            await update.message.reply_text(
                "На сегодня матчей не найдено.",
                reply_markup=build_main_menu_markup(),
            )
            return

        await show_numbered_analysis_matches(
            update,
            context,
            "📅 Матчи сегодня",
            api_matches,
            "today",
            15,
        )
        return
    except Exception:
        logger.exception("API-Football today matches failed, using TheSportsDB fallback")

    api_key = os.getenv("THESPORTSDB_API_KEY")

    if not api_key:
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        matches = get_thesportsdb_next_football_matches(api_key)
        ALLOWED_COUNTRIES = {
            "England",
            "Spain",
            "Germany",
            "Italy",
            "France",
            "Netherlands",
            "Portugal",
            "Turkey",
            "Switzerland",
            "Norway",
            "Sweden",
            "Czech Republic",
            "Serbia",
            "Latvia",
            "Lithuania",
            "Azerbaijan",
            "Kazakhstan",
            "Mexico",
            "Brazil",
            "Argentina",
            "Japan",
            "South Korea",
        }

        matches = [
            match
            for match in matches
            if (match.get("strCountry") or "") in ALLOWED_COUNTRIES
        ]
    except requests.RequestException:
        logger.exception("Failed to request events from TheSportsDB")
        await update.message.reply_text("Не удалось получить матчи. Попробуй позже.")
        return
    except Exception:
        logger.exception("Failed to process events from TheSportsDB")
        await update.message.reply_text("Не удалось обработать список матчей.")
        return

    if not matches:
        await update.message.reply_text(
            "На сегодня матчей не найдено.",
            reply_markup=build_main_menu_markup(),
        )
        return

    message = "\n\n".join(
    format_thesportsdb_event(match)
    for match in matches[:MAX_MATCHES]
    )
    await update.message.reply_text(message)

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user_action(update, "tomorrow_clicked")
    context.user_data["analysis_match_options"] = []
    context.user_data["analysis_match_source"] = None
    context.user_data["waiting_match_number_for_analysis"] = False
    context.user_data["last_match_for_ai"] = None

    try:
        now_almaty = datetime.now(ALMATY_TZ)
        tomorrow_date = (now_almaty + timedelta(days=1)).date()
        tomorrow_start = datetime.combine(
            tomorrow_date,
            datetime.min.time(),
            tzinfo=ALMATY_TZ,
        )
        tomorrow_end = datetime.combine(
            tomorrow_date,
            datetime.max.time(),
            tzinfo=ALMATY_TZ,
        )
        api_matches = get_api_football_matches_between(
            tomorrow_start,
            tomorrow_end,
            only_top=False,
            allowed_only=True,
        )
        if not api_matches:
            await update.message.reply_text(
                "На завтра матчей не найдено.",
                reply_markup=build_main_menu_markup(),
            )
            return

        await show_numbered_analysis_matches(
            update,
            context,
            "📆 Матчи завтра",
            api_matches,
            "tomorrow",
            15,
        )
        return
    except Exception:
        logger.exception("API-Football tomorrow matches failed, using TheSportsDB fallback")

    api_key = os.getenv("THESPORTSDB_API_KEY")

    if not api_key:
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        now_almaty = datetime.now(ALMATY_TZ)
        tomorrow_date = (now_almaty + timedelta(days=1)).date()
        tomorrow_start = datetime.combine(
            tomorrow_date,
            datetime.min.time(),
            tzinfo=ALMATY_TZ,
        )
        tomorrow_end = datetime.combine(
            tomorrow_date,
            datetime.max.time(),
            tzinfo=ALMATY_TZ,
        )
        tomorrow_matches = get_thesportsdb_football_matches_between(
            api_key,
            tomorrow_start,
            tomorrow_end,
        )
    except Exception:
        logger.exception("Failed to process events from TheSportsDB")
        await update.message.reply_text("Не удалось получить матчи.")
        return

    if not tomorrow_matches:
        await update.message.reply_text(
            "На завтра матчей не найдено.",
            reply_markup=build_main_menu_markup(),
        )
        return

    message = "📆 Матчи на завтра\n\n"

    for match in tomorrow_matches[:MAX_MATCHES]:
        message += format_thesportsdb_event(match) + "\n\n"

    await update.message.reply_text(message)

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    text = update.message.text
    if (
        context.user_data.get("waiting_match_number_for_analysis")
        and text == "⬅️ Назад"
    ):
        track_user_action(update, "back_clicked")
        context.user_data["waiting_match_number_for_analysis"] = False
        context.user_data["analysis_match_options"] = []
        context.user_data["analysis_match_source"] = None
        context.user_data["last_match_for_ai"] = None
        await start(update, context)
        return

    if text == MATCH_AI_ANALYSIS_BUTTON:
        await ai_match_analysis(update, context)
        return

    if context.user_data.get("team_select_mode"):
        mode = context.user_data["team_select_mode"]

        if text == "⬅️ Назад":
            track_user_action(update, "back_clicked")
            context.user_data["team_select_mode"] = None
            context.user_data["team_selected_league"] = None
            context.user_data["waiting_team"] = False
            context.user_data["waiting_results"] = False
            context.user_data["waiting_favorite_team"] = False
            await start(update, context)
            return

        if text == FAVORITE_BACK_TO_LEAGUES_BUTTON:
            await show_team_select_leagues(update, context, mode)
            return

        if text == FAVORITE_MANUAL_INPUT_BUTTON:
            context.user_data["waiting_team"] = mode == "matches"
            context.user_data["waiting_results"] = mode == "results"
            context.user_data["waiting_favorite_team"] = False
            context.user_data["team_select_mode"] = None
            context.user_data["team_selected_league"] = None

            await update.message.reply_text(
                "Введите название команды:\n"
                "Например: Liverpool",
                reply_markup=build_main_menu_markup(),
            )
            return

        if text in FAVORITE_TEAM_LEAGUES:
            context.user_data["team_select_mode"] = mode
            context.user_data["team_selected_league"] = text
            context.user_data["waiting_team"] = False
            context.user_data["waiting_results"] = False
            context.user_data["waiting_favorite_team"] = False

            keyboard = [
                [team]
                for team in FAVORITE_TEAM_LEAGUES[text]
            ]
            keyboard.append([FAVORITE_BACK_TO_LEAGUES_BUTTON])

            await update.message.reply_text(
                "Выберите команду:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
            return

        selected_league = context.user_data.get("team_selected_league")
        if (
            selected_league in FAVORITE_TEAM_LEAGUES
            and text in FAVORITE_TEAM_LEAGUES[selected_league]
        ):
            if mode == "matches":
                message = build_api_football_team_message(text)
            elif mode == "results":
                message = build_api_football_results_message(text)
            else:
                message = None

            if not message:
                await update.message.reply_text(
                    "Команда не найдена 😕 Попробуйте ввести название вручную."
                )
                return

            context.user_data["team_select_mode"] = None
            context.user_data["team_selected_league"] = None
            context.user_data["waiting_team"] = False
            context.user_data["waiting_results"] = False

            await update.message.reply_text(
                message,
                reply_markup=build_main_menu_markup(),
            )
            return

    if (
        context.user_data.get("favorite_select_mode")
        or context.user_data.get("favorite_selected_league")
    ):
        if text == "⬅️ Назад":
            track_user_action(update, "back_clicked")
            context.user_data["waiting_favorite_team"] = False
            context.user_data["favorite_select_mode"] = False
            context.user_data["favorite_selected_league"] = None
            await start(update, context)
            return

        if text == FAVORITE_BACK_TO_LEAGUES_BUTTON:
            await show_favorite_team_leagues(update, context)
            return

        if text == FAVORITE_MANUAL_INPUT_BUTTON:
            context.user_data["waiting_favorite_team"] = True
            context.user_data["favorite_select_mode"] = False
            context.user_data["favorite_selected_league"] = None

            await update.message.reply_text(
                "Введите название любимой команды:\n"
                "Например: Liverpool",
                reply_markup=build_main_menu_markup(),
            )
            return

        if text in FAVORITE_TEAM_LEAGUES:
            context.user_data["favorite_select_mode"] = True
            context.user_data["favorite_selected_league"] = text
            context.user_data["waiting_favorite_team"] = False

            keyboard = [
                [team]
                for team in FAVORITE_TEAM_LEAGUES[text]
            ]
            keyboard.append([FAVORITE_BACK_TO_LEAGUES_BUTTON])

            await update.message.reply_text(
                "Выберите команду:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
            return

        selected_league = context.user_data.get("favorite_selected_league")
        if (
            selected_league in FAVORITE_TEAM_LEAGUES
            and text in FAVORITE_TEAM_LEAGUES[selected_league]
        ):
            context.user_data["favorite_team"] = text
            if update.effective_user:
                save_favorite_team_to_db(update.effective_user.id, text)
            context.user_data["favorite_select_mode"] = False
            context.user_data["waiting_favorite_team"] = False
            context.user_data["favorite_selected_league"] = None

            await update.message.reply_text(
                f"⭐ Любимая команда сохранена:\n"
                f"{text}\n\n"
                f"Открывайте ⭐ Моя команда → 📋 Открыть профиль "
                f"для просмотра матчей команды.",
                reply_markup=build_main_menu_markup(),
            )
            return

    menu_buttons = {
        "📅 Сегодня",
        "📆 Завтра",
        "🔥 Топ матчи",
        "🏆 Таблица",
        "⬅️ Назад",
        "⚽ Команда",
        "📋 Профиль",
        "📊 Результаты",
        "⭐ Моя команда",
        PREMIUM_BUTTON,
        FAVORITE_OPEN_PROFILE_BUTTON,
        FAVORITE_CHANGE_TEAM_BUTTON,
        MATCH_AI_ANALYSIS_BUTTON,
    }
    menu_buttons.update(PAYMENT_PACKAGE_BUTTONS)

    favorite_team_buttons = set(FAVORITE_TEAM_LEAGUES.keys())
    for teams in FAVORITE_TEAM_LEAGUES.values():
        favorite_team_buttons.update(teams)
    favorite_team_buttons.add(FAVORITE_MANUAL_INPUT_BUTTON)
    favorite_team_buttons.add(FAVORITE_BACK_TO_LEAGUES_BUTTON)
    favorite_team_buttons.add(FAVORITE_OPEN_PROFILE_BUTTON)
    favorite_team_buttons.add(FAVORITE_CHANGE_TEAM_BUTTON)

    if (
        text not in menu_buttons
        and text not in STANDINGS_LEAGUES
        and text not in favorite_team_buttons
    ):
        return

    event_by_button = {
        "🏆 Таблица": "standings_clicked",
        "⬅️ Назад": "back_clicked",
        "⚽ Команда": "team_clicked",
        "📋 Профиль": "profile_clicked",
        "📊 Результаты": "results_clicked",
        PREMIUM_BUTTON: "premium_clicked",
        FAVORITE_OPEN_PROFILE_BUTTON: "profile_clicked",
    }
    event_type = event_by_button.get(text)
    if event_type:
        track_user_action(update, event_type)

    context.user_data["waiting_team"] = False
    context.user_data["waiting_results"] = False
    context.user_data["waiting_favorite_team"] = False
    context.user_data["waiting_match_number_for_analysis"] = False
    context.user_data["analysis_match_options"] = []
    context.user_data["analysis_match_source"] = None
    context.user_data["last_match_for_ai"] = None
    context.user_data["team_select_mode"] = None
    context.user_data["team_selected_league"] = None
    context.user_data["favorite_select_mode"] = False
    context.user_data["favorite_selected_league"] = None

    if text == "📅 Сегодня":
        await today(update, context)

    elif text == "📆 Завтра":
        await tomorrow(update, context)

    elif text == "🔥 Топ матчи":
        await top(update, context)

    elif text == "🏆 Таблица":
        league_buttons = list(STANDINGS_LEAGUES.keys())
        keyboard = [
            league_buttons[index:index + 2]
            for index in range(0, len(league_buttons), 2)
        ]
        keyboard.append(["⬅️ Назад"])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "🏆 Выберите лигу:",
            reply_markup=reply_markup,
        )

    elif text in STANDINGS_LEAGUES:
        league = STANDINGS_LEAGUES[text]

        try:
            message = build_api_football_standings_message(
                league["id"],
                league["season"],
                league["name"],
                league["country"],
            )
            await update.message.reply_text(message, parse_mode="Markdown")
        except Exception:
            logger.exception("Failed to get standings")
            await update.message.reply_text("🏆 Таблица временно недоступна")

    elif text == "⬅️ Назад":
        await start(update, context)

    elif text == "⚽ Команда":
        await show_team_select_leagues(update, context, "matches")

    elif text == "📋 Профиль":
        await show_subscription_profile(update, context)
        return

    elif text == FAVORITE_OPEN_PROFILE_BUTTON:
        await show_favorite_team_profile(update, context)
        return

    elif text == FAVORITE_CHANGE_TEAM_BUTTON:
        await show_favorite_team_leagues(update, context)
        return
    
    elif text == "📊 Результаты":
        await show_team_select_leagues(update, context, "results")

    elif text == PREMIUM_BUTTON:
        await show_premium_screen(update, context)

    elif text in PAYMENT_PACKAGE_BUTTONS:
        package_code, package = get_payment_package_by_button(text)
        if package_code and package:
            await handle_payment_package_selection(
                update,
                context,
                package_code,
                package,
            )

    elif text == "⭐ Моя команда":
        if get_current_favorite_team(update, context):
            await show_favorite_team_actions(update, context)
        else:
            await update.message.reply_text(
                build_favorite_team_missing_message(),
                reply_markup=build_main_menu_markup(),
            )


def build_team_not_found_retry_message() -> str:
    return (
        "Команда не найдена 😕\n"
        "Попробуйте ввести название ещё раз.\n\n"
        "Например:\n"
        "Liverpool\n"
        "Ливерпуль\n"
        "Реал\n"
        "Бавария\n"
        "ПСЖ"
    )


def search_thesportsdb_team(team_name: str) -> dict | None:
    team_name = normalize_team_name(team_name)
    api_key = os.getenv("THESPORTSDB_API_KEY")

    response = requests.get(
        f"{THESPORTSDB_BASE_URL}/{api_key}/searchteams.php",
        params={"t": team_name},
        timeout=20,
    )

    response.raise_for_status()

    teams = response.json().get("teams")
    if not teams:
        return None

    return teams[0]


async def show_favorite_team_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    context.user_data["waiting_favorite_team"] = False
    context.user_data["favorite_select_mode"] = False
    context.user_data["favorite_selected_league"] = None
    context.user_data["team_select_mode"] = None
    context.user_data["team_selected_league"] = None

    favorite_team = get_current_favorite_team(update, context)

    keyboard = [
        [FAVORITE_OPEN_PROFILE_BUTTON],
        [FAVORITE_CHANGE_TEAM_BUTTON],
        ["⬅️ Назад"],
    ]

    await update.message.reply_text(
        f"⭐ Текущая любимая команда:\n"
        f"{favorite_team}\n\n"
        f"Что хотите сделать?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
        ),
    )


async def show_favorite_team_leagues(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    context.user_data["waiting_favorite_team"] = False
    context.user_data["favorite_select_mode"] = True
    context.user_data["favorite_selected_league"] = None
    context.user_data["team_select_mode"] = None
    context.user_data["team_selected_league"] = None

    keyboard = [
        [league]
        for league in FAVORITE_TEAM_LEAGUES
    ]
    keyboard.append([FAVORITE_MANUAL_INPUT_BUTTON])
    keyboard.append(["⬅️ Назад"])

    await update.message.reply_text(
        "Выберите лигу или введите команду вручную:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
        ),
    )


async def show_team_select_leagues(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
) -> None:
    context.user_data["team_select_mode"] = mode
    context.user_data["team_selected_league"] = None
    context.user_data["waiting_team"] = False
    context.user_data["waiting_results"] = False
    context.user_data["waiting_favorite_team"] = False

    keyboard = [
        [league]
        for league in FAVORITE_TEAM_LEAGUES
    ]
    keyboard.append([FAVORITE_MANUAL_INPUT_BUTTON])
    keyboard.append(["⬅️ Назад"])

    await update.message.reply_text(
        "Выберите лигу или введите команду вручную:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
        ),
    )


async def match_number_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = update.message.text.strip()
    if text == MATCH_AI_ANALYSIS_BUTTON:
        return

    options = context.user_data.get("analysis_match_options") or {}
    if (
        not context.user_data.get("waiting_match_number_for_analysis")
        or not options
    ):
        return

    if not text.isdigit() or text not in options:
        context.user_data["waiting_match_number_for_analysis"] = True
        await update.message.reply_text(
            "Введите номер матча из списка. Например: 2\n"
            "или нажмите ⬅️ Назад",
            reply_markup=build_match_analysis_back_markup(),
        )
        return

    selected_match = options[text]
    track_user_action(
        update,
        "match_selected",
        {
            "source": context.user_data.get("analysis_match_source"),
            "match_number": text,
            "home": selected_match["home"],
            "away": selected_match["away"],
            "fixture_id": selected_match.get("fixture_id"),
            "league_name": selected_match.get("league_name"),
        },
    )

    try:
        analysis_data = build_match_analysis_data(
            selected_match["home"],
            selected_match["away"],
            selected_match.get("fixture_id"),
            selected_match,
        )
        full_analysis_text = analysis_data["full_analysis_text"]
        public_analysis_text = analysis_data["public_analysis_text"]
        context.user_data["last_match_for_ai"] = {
            "home": selected_match["home"],
            "away": selected_match["away"],
            "fixture_id": selected_match.get("fixture_id"),
            "league_id": selected_match.get("league_id"),
            "league_name": selected_match.get("league_name"),
            "league_country": selected_match.get("league_country"),
            "league_season": selected_match.get("league_season"),
            "league_round": selected_match.get("league_round"),
            "kickoff": selected_match.get("kickoff"),
            "venue_name": selected_match.get("venue_name"),
            "venue_city": selected_match.get("venue_city"),
            "numeric_basis_block": analysis_data.get("numeric_basis_block"),
            "analysis_text": full_analysis_text,
        }
        message = public_analysis_text + (
            "\n\n"
            "Введите другой номер из списка для анализа\n"
            "или нажмите ⬅️ Назад"
        )
    except Exception:
        logger.exception("Match analysis failed")
        message = "🧠 Анализ временно недоступен"

    await update.message.reply_text(
        message,
        reply_markup=build_match_analysis_ai_markup(),
    )


async def ai_match_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    match_data = context.user_data.get("last_match_for_ai")
    current_user_id = update.effective_user.id if update.effective_user else None
    is_admin = is_admin_user(current_user_id) if current_user_id is not None else False
    track_user_action(
        update,
        "ai_analysis_clicked",
        {
            "home": (match_data or {}).get("home"),
            "away": (match_data or {}).get("away"),
            "fixture_id": (match_data or {}).get("fixture_id"),
            "league_name": (match_data or {}).get("league_name"),
            "is_admin": is_admin,
        },
    )

    if not OPENAI_API_KEY:
        track_user_action(
            update,
            "ai_analysis_failed",
            {
                "home": (match_data or {}).get("home"),
                "away": (match_data or {}).get("away"),
                "fixture_id": (match_data or {}).get("fixture_id"),
                "league_name": (match_data or {}).get("league_name"),
                "is_admin": is_admin,
            },
        )
        await update.message.reply_text(
            "AI-разбор пока не подключён.",
            reply_markup=build_match_analysis_back_markup(),
        )
        return

    if context.user_data.get("ai_analysis_in_progress"):
        await update.message.reply_text(
            "AI-разбор уже готовится, подождите немного.",
            reply_markup=build_match_analysis_ai_markup(),
        )
        return

    if not match_data:
        await update.message.reply_text(
            "Сначала выберите матч из списка и откройте обычный анализ.",
            reply_markup=build_match_analysis_ai_markup(),
        )
        return

    if not update.effective_user:
        await update.message.reply_text(
            "AI-разбор временно недоступен.",
            reply_markup=build_match_analysis_back_markup(),
        )
        return

    if not is_admin:
        allowed, reason, subscription = can_use_ai_analysis(update.effective_user.id)
    else:
        allowed = True
        reason = ""
        subscription = {}

    if not allowed:
        event_data = {
            "reason": reason,
            "is_admin": is_admin,
            "home": match_data.get("home"),
            "away": match_data.get("away"),
            "fixture_id": match_data.get("fixture_id"),
            "league_name": match_data.get("league_name"),
        }
        track_user_action(update, "ai_limit_reached", event_data)
        await notify_admins(
            context,
            "⚠️ Пользователь достиг лимита AI-разборов\n\n"
            f"{format_user_for_admin(update.effective_user)}\n"
            f"Матч: {match_data.get('home')} - {match_data.get('away')}\n"
            f"Доступно сейчас: {get_ai_available_count(subscription)}\n"
            f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}",
        )
        await update.message.reply_text(
            "Лимит AI-разборов закончился.\n\n"
            f"Free-лимит: {FREE_AI_LIMIT_MONTHLY} AI-разборов в месяц.\n"
            "Можно купить пакет или Premium.\n\n"
            "Нажмите “💎 Подписка”, чтобы выбрать вариант.",
            reply_markup=build_ai_limit_markup(),
        )
        return

    context.user_data["ai_analysis_in_progress"] = True
    try:
        await update.message.reply_text("⏳ Готовлю AI-разбор")
        match_data["tournament_context_text"] = build_tournament_context_for_ai(
            match_data
        )
        message = await asyncio.to_thread(get_openai_ai_analysis, match_data)
        ai_event_data = {
            "home": match_data.get("home"),
            "away": match_data.get("away"),
            "fixture_id": match_data.get("fixture_id"),
            "league_name": match_data.get("league_name"),
            "is_admin": is_admin,
        }
        if message == "AI-разбор временно недоступен.":
            track_user_action(update, "ai_analysis_failed", ai_event_data)
        else:
            if is_admin:
                message = f"{message}\n\nАдмин-режим: AI-разборы не расходуются."
            else:
                subscription = increment_ai_usage(update.effective_user.id)
                message = f"{message}\n\n{get_ai_usage_text(subscription)}"
            track_user_action(update, "ai_analysis_success", ai_event_data)

        await update.message.reply_text(
            message,
            reply_markup=build_match_analysis_back_markup(),
        )
    finally:
        context.user_data["ai_analysis_in_progress"] = False


async def team_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    if update.message.text == "⚽ Команда":
        return

    if context.user_data.get("waiting_results"):
        return

    if context.user_data.get("waiting_favorite_team"):
        return
    
    if not context.user_data.get("waiting_team"):
        return

    team_name = normalize_team_name(update.message.text)
    api_key = os.getenv("THESPORTSDB_API_KEY")

    try:
        message = build_api_football_team_message(team_name)
        if message:
            await update.message.reply_text(message)
            context.user_data["waiting_team"] = False
            return

        logger.info(
            "API-Football team '%s' not found, using TheSportsDB fallback",
            team_name,
        )
    except Exception:
        logger.exception(
            "API-Football team search failed, using TheSportsDB fallback"
        )

    try:
        team = search_thesportsdb_team(team_name)

        if not team:
            context.user_data["waiting_team"] = True
            await update.message.reply_text(build_team_not_found_retry_message())
            return

        team_id = team["idTeam"]

        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/eventsnext.php",
            params={"id": team_id},
            timeout=20,
        )

        response.raise_for_status()

        events = response.json().get("events") or []

        logger.info(
            "Events response: %s",
            response.text[:1000]
        )

        logger.info("Events response: %s", response.text[:1000])
        
        if not events:
            await update.message.reply_text(
                "Ближайшие матчи не найдены."
            )
            context.user_data["waiting_team"] = False
            return

        message = f"⚽ {team['strTeam']}\n\n"

        for event in events[:5]:
            message += format_thesportsdb_event(event)
            message += "\n\n"

        await update.message.reply_text(message)
        context.user_data["waiting_team"] = False

    except Exception:
        logger.exception("Team search failed")
        await update.message.reply_text(
            "Ошибка при поиске команды."
        )
        
async def team_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    if update.message.text == "📊 Результаты":
        return

    if context.user_data.get("waiting_favorite_team"):
        return
    
    if not context.user_data.get("waiting_results"):
        return

    team_name = normalize_team_name(update.message.text)
    api_key = os.getenv("THESPORTSDB_API_KEY")

    try:
        message = build_api_football_results_message(team_name)
        if message:
            await update.message.reply_text(message)
            context.user_data["waiting_results"] = False
            return

        logger.info(
            "API-Football team '%s' not found, using TheSportsDB fallback",
            team_name,
        )
    except Exception:
        logger.exception(
            "API-Football team results failed, using TheSportsDB fallback"
        )

    try:
        team = search_thesportsdb_team(team_name)

        if not team:
            context.user_data["waiting_results"] = True
            await update.message.reply_text(build_team_not_found_retry_message())
            return

        team_id = team["idTeam"]

        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/eventslast.php",
            params={"id": team_id},
            timeout=20,
        )

        response.raise_for_status()

        events = response.json().get("results") or []

        if not events:
            await update.message.reply_text(
                "Последние матчи не найдены."
            )
            context.user_data["waiting_results"] = False
            return

        message = f"📊 {team['strTeam']}\n\n"

        for event in events[:5]:
            home = event.get("strHomeTeam", "")
            away = event.get("strAwayTeam", "")
            home_score = event.get("intHomeScore", "-")
            away_score = event.get("intAwayScore", "-")

            message += (
                f"⚽ {home} {home_score}-{away_score} {away}\n"
            )

        await update.message.reply_text(message)
        context.user_data["waiting_results"] = False

    except Exception:
        logger.exception("Team results failed")

        await update.message.reply_text(
            "Ошибка при получении результатов."
        )   

async def favorite_team(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    if update.message.text == "⭐ Моя команда":
        return

    if update.message.text == FAVORITE_MANUAL_INPUT_BUTTON:
        return

    if not context.user_data.get("waiting_favorite_team"):
        return

    team_name = normalize_team_name(update.message.text)

    try:
        team = search_api_football_team(team_name)
        favorite_team_name = team["name"] if team else None
    except Exception:
        logger.exception(
            "API-Football favorite team search failed, using TheSportsDB fallback"
        )
        favorite_team_name = None

    if favorite_team_name is None:
        try:
            team = search_thesportsdb_team(team_name)
            favorite_team_name = team["strTeam"] if team else None
        except Exception:
            logger.exception("Favorite team search failed")

    if favorite_team_name is None:
        context.user_data["waiting_favorite_team"] = True
        await update.message.reply_text(build_team_not_found_retry_message())
        return

    try:
        context.user_data["favorite_team"] = favorite_team_name
        if update.effective_user:
            save_favorite_team_to_db(update.effective_user.id, favorite_team_name)
        context.user_data["waiting_favorite_team"] = False
        context.user_data["favorite_select_mode"] = False
        context.user_data["favorite_selected_league"] = None
    except Exception:
        logger.exception("Failed to save favorite team")
        context.user_data["waiting_favorite_team"] = True
        await update.message.reply_text(build_team_not_found_retry_message())
        return

    await update.message.reply_text(
        f"⭐ Любимая команда сохранена:\n"
        f"{favorite_team_name}\n\n"
        f"Открывайте ⭐ Моя команда → 📋 Открыть профиль "
        f"для просмотра матчей команды.",
        reply_markup=build_main_menu_markup(),
    )


def build_favorite_team_missing_message() -> str:
    return (
        "⭐ Моя команда\n\n"
        "Любимая команда не выбрана.\n"
        "Нажмите “⚽ Команда”, чтобы выбрать команду."
    )


async def show_subscription_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user:
        await update.message.reply_text(
            "📋 Профиль временно недоступен.",
            reply_markup=build_main_menu_markup(),
        )
        return

    await update.message.reply_text(
        "📋 Профиль\n\n"
        f"{build_subscription_profile_block(update.effective_user.id)}",
        reply_markup=build_main_menu_markup(),
    )


async def show_favorite_team_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    favorite_team = get_current_favorite_team(update, context)

    if not favorite_team:
        await update.message.reply_text(
            build_favorite_team_missing_message(),
            reply_markup=build_main_menu_markup(),
        )
        return

    api_key = os.getenv("THESPORTSDB_API_KEY")

    try:
        message = build_api_football_profile_message(favorite_team)
        if message:
            await update.message.reply_text(message)
            return

        logger.info(
            "API-Football team '%s' not found, using TheSportsDB fallback",
            favorite_team,
        )
    except Exception:
        logger.exception(
            "API-Football profile failed, using TheSportsDB fallback"
        )

    try:
        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/searchteams.php",
            params={"t": favorite_team},
            timeout=20,
        )

        response.raise_for_status()

        teams = response.json().get("teams")

        if not teams:
            await update.message.reply_text(
                "Команда не найдена."
            )
            return

        team_id = teams[0]["idTeam"]

        # будущие матчи
        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/eventsnext.php",
            params={"id": team_id},
            timeout=20,
        )

        response.raise_for_status()

        next_events = response.json().get("events") or []

        # последние результаты
        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/eventslast.php",
            params={"id": team_id},
            timeout=20,
        )

        response.raise_for_status()

        last_events = response.json().get("results") or []

        message = (
            "📋 Профиль\n\n"
            f"⭐ Любимая команда: {favorite_team}\n\n"
        )

        # Ближайшие матчи
        if next_events:
            message += "📅 Ближайшие матчи\n\n"

            for event in next_events[:3]:
                message += format_thesportsdb_event(event)
                message += "\n"

        # Последние результаты
        if last_events:
            message += "\n📊 Последние 5 матчей\n\n"

            wins = 0
            draws = 0
            losses = 0

            form = []

            for event in last_events[:5]:

                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")

                hs = int(event.get("intHomeScore") or 0)
                aw = int(event.get("intAwayScore") or 0)

                league = event.get("strLeague", "")

                message += (
                    f"⚽ {home} {hs}-{aw} {away}\n"
                    f"🏆 {league}\n\n"
                )

                is_home = (
                    home.lower() ==
                    favorite_team.lower()
                )

                if hs == aw:
                    draws += 1
                    form.append("➖")

                elif (
                    (is_home and hs > aw)
                    or
                    (not is_home and aw > hs)
                ):
                    wins += 1
                    form.append("✅")

                else:
                    losses += 1
                    form.append("❌")

            message += (
                "🔥 Форма команды\n\n"
                f"{''.join(form)}\n\n"
                f"🏆 Побед: {wins}\n"
                f"🤝 Ничьих: {draws}\n"
                f"😔 Поражений: {losses}"
            )

        await update.message.reply_text(message)

    except Exception:
        logger.exception("Profile failed")

        await update.message.reply_text(
            "Ошибка при загрузке профиля."
        )


async def show_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    await show_favorite_team_profile(update, context)


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    track_user_action(update, "top_clicked")
    context.user_data["analysis_match_options"] = []
    context.user_data["analysis_match_source"] = None
    context.user_data["waiting_match_number_for_analysis"] = False
    context.user_data["last_match_for_ai"] = None

    try:
        now_almaty = datetime.now(ALMATY_TZ)
        window_end = now_almaty + timedelta(hours=72)
        api_matches = get_api_football_matches_between(
            now_almaty,
            window_end,
            only_top=True,
            allowed_only=True,
        )
        if not api_matches:
            await update.message.reply_text(
                "🔥 Топ матчи на ближайшие 72 часа не найдены."
            )
            return

        await show_numbered_analysis_matches(
            update,
            context,
            "🔥 Топ матчи",
            api_matches[:MAX_TOP_MATCHES],
            "top",
            MAX_TOP_MATCHES,
        )
        return
    except Exception:
        logger.exception("API-Football top matches failed, using TheSportsDB fallback")

    api_key = os.getenv("THESPORTSDB_API_KEY")

    if not api_key:
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        now_almaty = datetime.now(ALMATY_TZ)
        window_end = now_almaty + timedelta(hours=72)
        matches = get_thesportsdb_football_matches_between(
            api_key,
            now_almaty,
            window_end,
        )
    except Exception:
        logger.exception("Failed to process top matches")
        await update.message.reply_text("Не удалось обработать список топ матчей.")
        return

    LEAGUE_RATINGS = {
        "FIFA World Cup": 100,
        "UEFA Champions League": 95,
        "UEFA Europa League": 90,
        "Premier League": 90,
        "La Liga": 90,
        "Serie A": 90,
        "Bundesliga": 90,
        "Ligue 1": 85,
        "Eredivisie": 80,
        "Swiss Super League": 75,
        "Allsvenskan": 75,
        "Eliteserien": 75,
        "Czech Liga": 75,
        "Serbian Super Liga": 70,
        "A Lyga": 65,
        "Virsliga": 65,
        "Azerbaijan Premier League": 65,
        "Kazakhstan Premier League": 65,
        "CONCACAF Gold Cup": 90,
        "Copa America": 95,
        "Brazil Serie A": 85,
        "Argentine Primera Division": 80,
        "MLS": 75,
        "J1 League": 70,
        "K League 1": 70,
        "World Cup": 100,
        "Champions League": 95,
        "Europa League": 90,
        "Premier Division": 70,
        "National League": 60,
        "Eliteserien": 75,
        "Allsvenskan": 75,
        "Veikkausliiga": 70,
        "Super League": 75,
        "Superliga": 75,
        "Premier Liga": 70,
        "Norwegian Eliteserien": 80,
        "Allsvenskan": 80,
        "Danish Superliga": 80,
        "Swiss Super League": 80,
        "Belgian Pro League": 85,
        "Scottish Premiership": 80,
        "Austrian Bundesliga": 80,
        "MLS": 75,
        "J1 League": 75,
        "K League 1": 75,
        "Brasileiro Serie A": 90,
        "Argentine Primera Division": 85,
    }

    filtered = []

    for match in matches:
        league_name = match.get("strLeague") or ""
        logger.info("League: %s", league_name)
        rating = 0

        for league_key, league_rating in LEAGUE_RATINGS.items():
            if league_key.lower() in league_name.lower():
                rating = league_rating
                break

        if rating > 0:
            filtered.append((rating, match))

    filtered.sort(key=lambda x: x[0], reverse=True)

    final_matches = [m for _, m in filtered]

    if not final_matches:
        await update.message.reply_text("Топ матчей не найдено.")
        return

    message = "🔥 Топ матчи\n\n"

    for match in final_matches[:10]:
        message += format_thesportsdb_event(match) + "\n\n"

    await update.message.reply_text(message)


async def testdb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api_key = os.getenv("THESPORTSDB_API_KEY")
    if not api_key:
        logger.error("THESPORTSDB_API_KEY is not configured")
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        matches = get_thesportsdb_next_football_matches(api_key)
        logger.info(
            "TheSportsDB returned %s matches",
            len(matches),
        )
    except requests.RequestException:
        logger.exception("Failed to request events from TheSportsDB")
        await update.message.reply_text("Не удалось получить матчи из TheSportsDB.")
        return
    except Exception:
        logger.exception("Failed to process events from TheSportsDB")
        await update.message.reply_text("Не удалось обработать матчи из TheSportsDB.")
        return

    if not matches:
        await update.message.reply_text("Матчи TheSportsDB не найдены.")
        return

    message = "\n\n".join(format_thesportsdb_event(match) for match in matches)
    await update.message.reply_text(message)


def validate_telegram_webapp_init_data(init_data: str) -> dict | None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token or not init_data:
        return None

    try:
        init_data_values = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = init_data_values.pop("hash", "")
        if not received_hash:
            logger.debug("Telegram WebApp initData does not contain a hash")
            return None

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(init_data_values.items())
        )
        secret_key = hmac.new(
            b"WebAppData",
            telegram_token.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Telegram WebApp initData hash validation failed")
            return None

        user_data = json.loads(init_data_values.get("user", ""))
        if not isinstance(user_data, dict) or not user_data.get("id"):
            logger.debug("Telegram WebApp initData does not contain a valid user")
            return None

        user_data["_auth_mode"] = "init_data"
        return user_data
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse Telegram WebApp initData")
        return None
    except Exception:
        logger.warning(
            "Unexpected Telegram WebApp initData validation error",
            exc_info=True,
        )
        return None


def get_api_telegram_user(request) -> dict | None:
    init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
    if init_data:
        telegram_user = validate_telegram_webapp_init_data(init_data)
        if telegram_user:
            return telegram_user

    # TODO: Remove this query fallback before the public Mini App launch.
    if not ENABLE_MINIAPP_API:
        return None

    telegram_user_id = request.args.get("telegram_user_id", "").strip()
    if not telegram_user_id:
        request_data = request.get_json(silent=True)
        if isinstance(request_data, dict):
            telegram_user_id = str(
                request_data.get("telegram_user_id") or ""
            ).strip()
    if not telegram_user_id:
        telegram_user_id = request.form.get(
            "telegram_user_id",
            "",
        ).strip()

    if not telegram_user_id.isdigit():
        return None

    user_id = int(telegram_user_id)
    if user_id <= 0:
        return None

    return {
        "id": user_id,
        "_auth_mode": "query_fallback",
    }


def serialize_api_datetime(value) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def format_miniapp_fixture_item(fixture_item: dict) -> dict | None:
    fixture = fixture_item.get("fixture") or {}
    teams = fixture_item.get("teams") or {}
    league = fixture_item.get("league") or {}
    home_team = teams.get("home") or {}
    away_team = teams.get("away") or {}
    fixture_id = fixture.get("id")
    timestamp = fixture.get("timestamp")

    if fixture_id is None:
        return None

    kickoff = None
    if timestamp is not None:
        kickoff = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).astimezone(ALMATY_TZ).isoformat()

    return {
        "id": str(fixture_id),
        "home": home_team.get("name") or "",
        "away": away_team.get("name") or "",
        "home_logo": home_team.get("logo") or None,
        "away_logo": away_team.get("logo") or None,
        "league": league.get("name") or "",
        "league_logo": league.get("logo") or None,
        "country": league.get("country") or "",
        "kickoff": kickoff,
        "source": "api_football",
    }


def get_miniapp_matches(match_type: str) -> list[dict]:
    now_almaty = datetime.now(ALMATY_TZ)

    if match_type == "today":
        start_almaty = now_almaty
        end_almaty = datetime.combine(
            now_almaty.date(),
            datetime.max.time(),
            tzinfo=ALMATY_TZ,
        )
        only_top = False
    elif match_type == "tomorrow":
        tomorrow_date = (now_almaty + timedelta(days=1)).date()
        start_almaty = datetime.combine(
            tomorrow_date,
            datetime.min.time(),
            tzinfo=ALMATY_TZ,
        )
        end_almaty = datetime.combine(
            tomorrow_date,
            datetime.max.time(),
            tzinfo=ALMATY_TZ,
        )
        only_top = False
    elif match_type == "top":
        start_almaty = now_almaty
        end_almaty = now_almaty + timedelta(hours=72)
        only_top = True
    else:
        raise ValueError(f"Unsupported Mini App match type: {match_type}")

    fixtures = get_api_football_matches_between(
        start_almaty,
        end_almaty,
        only_top=only_top,
        allowed_only=True,
    )
    items = []
    for fixture_item in fixtures[:MAX_TOP_MATCHES]:
        formatted_item = format_miniapp_fixture_item(fixture_item)
        if formatted_item and formatted_item.get("id"):
            items.append(formatted_item)
    return items


def find_miniapp_match(match_id: str) -> dict | None:
    normalized_match_id = str(match_id).strip()
    if not normalized_match_id:
        return None

    for match_type in ("top", "today", "tomorrow"):
        try:
            matches = get_miniapp_matches(match_type)
        except Exception:
            logger.warning(
                "Mini App match lookup failed for list: %s",
                match_type,
                exc_info=True,
            )
            continue

        for match in matches:
            if str(match.get("id") or "") == normalized_match_id:
                return match

    return None


def format_miniapp_context_fixture(fixture_item: dict) -> dict | None:
    fixture = fixture_item.get("fixture") or {}
    teams = fixture_item.get("teams") or {}
    league = fixture_item.get("league") or {}
    goals = fixture_item.get("goals") or {}
    fixture_id = fixture.get("id")
    timestamp = fixture.get("timestamp")

    if fixture_id is None:
        return None

    date = None
    if timestamp is not None:
        date = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).astimezone(ALMATY_TZ).isoformat()
    elif fixture.get("date"):
        date = str(fixture["date"])

    return {
        "id": str(fixture_id),
        "date": date,
        "league": league.get("name") or "",
        "home": (teams.get("home") or {}).get("name") or "",
        "away": (teams.get("away") or {}).get("name") or "",
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "status": (fixture.get("status") or {}).get("short") or "",
    }


def format_miniapp_standing_row(row: dict) -> dict | None:
    team = row.get("team") or {}
    all_stats = row.get("all") or {}
    goals = all_stats.get("goals") or {}
    team_name = team.get("name") or ""
    rank = row.get("rank")

    if not team_name or rank is None:
        return None

    goals_for = goals.get("for")
    goals_against = goals.get("against")
    goal_diff = row.get("goalsDiff")
    if (
        goal_diff is None
        and isinstance(goals_for, (int, float))
        and isinstance(goals_against, (int, float))
    ):
        goal_diff = goals_for - goals_against

    return {
        "rank": rank,
        "team": team_name,
        "played": all_stats.get("played"),
        "wins": all_stats.get("win"),
        "draws": all_stats.get("draw"),
        "losses": all_stats.get("lose"),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goal_diff,
        "points": row.get("points"),
    }


def get_miniapp_match_context(match: dict) -> dict:
    match_id = str(match.get("id") or "")
    fixture_item = {}

    try:
        fixture_response = request_api_football(
            "/fixtures",
            {
                "id": match_id,
                "timezone": "UTC",
            },
        )
        if fixture_response:
            fixture_item = fixture_response[0]
    except Exception:
        logger.warning(
            "Mini App fixture context lookup failed: match_id=%s",
            match_id,
            exc_info=True,
        )

    teams = fixture_item.get("teams") or {}
    league = fixture_item.get("league") or {}
    home_team = teams.get("home") or {}
    away_team = teams.get("away") or {}
    home_team_id = home_team.get("id")
    away_team_id = away_team.get("id")

    standings = []
    for row in get_fixture_league_standings(
        league.get("id"),
        league.get("season"),
    ):
        formatted_row = format_miniapp_standing_row(row)
        if formatted_row:
            standings.append(formatted_row)

    h2h_fixtures = []
    if home_team_id and away_team_id:
        try:
            h2h_fixtures = get_head_to_head_fixtures(
                home_team_id,
                away_team_id,
            )
        except Exception:
            logger.warning(
                "Mini App head-to-head lookup failed: match_id=%s",
                match_id,
                exc_info=True,
            )

    recent_fixtures = {}
    upcoming_fixtures = {}
    for side, team_id in (
        ("home", home_team_id),
        ("away", away_team_id),
    ):
        if not team_id:
            recent_fixtures[side] = []
            upcoming_fixtures[side] = []
            continue

        try:
            recent_fixtures[side] = get_api_football_finished_fixtures(
                team_id
            )
        except Exception:
            logger.warning(
                "Mini App recent fixtures lookup failed: "
                "match_id=%s side=%s",
                match_id,
                side,
                exc_info=True,
            )
            recent_fixtures[side] = []

        try:
            upcoming_fixtures[side] = get_api_football_next_fixtures(team_id)
        except Exception:
            logger.warning(
                "Mini App upcoming fixtures lookup failed: "
                "match_id=%s side=%s",
                match_id,
                side,
                exc_info=True,
            )
            upcoming_fixtures[side] = []

    def format_fixture_list(fixtures: list[dict]) -> list[dict]:
        formatted_fixtures = []
        for item in fixtures:
            formatted_item = format_miniapp_context_fixture(item)
            if formatted_item:
                formatted_fixtures.append(formatted_item)
        return formatted_fixtures

    upcoming_by_id = {}
    for item in (
        upcoming_fixtures.get("home", [])
        + upcoming_fixtures.get("away", [])
    ):
        formatted_item = format_miniapp_context_fixture(item)
        if not formatted_item or formatted_item["id"] == match_id:
            continue
        upcoming_by_id[formatted_item["id"]] = formatted_item

    upcoming = sorted(
        upcoming_by_id.values(),
        key=lambda item: item.get("date") or "",
    )[:8]

    return {
        "ok": True,
        "match_id": match_id,
        "home": match.get("home") or home_team.get("name") or "",
        "away": match.get("away") or away_team.get("name") or "",
        "league": match.get("league") or league.get("name") or "",
        "country": match.get("country") or league.get("country") or "",
        "kickoff": match.get("kickoff"),
        "standings": standings,
        "h2h": format_fixture_list(h2h_fixtures),
        "home_recent": format_fixture_list(
            recent_fixtures.get("home", [])
        ),
        "away_recent": format_fixture_list(
            recent_fixtures.get("away", [])
        ),
        "upcoming": upcoming,
    }


def build_miniapp_ai_match_data(match: dict) -> dict:
    fixture_id_text = str(match.get("id") or "")
    fixture_id = int(fixture_id_text) if fixture_id_text.isdigit() else None
    match_context = {
        "league_name": match.get("league"),
        "league_country": match.get("country"),
        "kickoff": match.get("kickoff"),
    }
    analysis_data = build_match_analysis_data(
        match.get("home") or "",
        match.get("away") or "",
        fixture_id,
        match_context,
    )
    if analysis_data.get("error"):
        raise RuntimeError("Mini App match analysis data is unavailable")

    match_data = {
        "home": match.get("home") or "",
        "away": match.get("away") or "",
        "fixture_id": fixture_id,
        "league_name": match.get("league"),
        "league_country": match.get("country"),
        "kickoff": match.get("kickoff"),
        "numeric_basis_block": analysis_data.get("numeric_basis_block"),
        "analysis_text": analysis_data.get("full_analysis_text") or "",
    }
    match_data["tournament_context_text"] = build_tournament_context_for_ai(
        match_data
    )
    return match_data


def notify_admins_about_miniapp_receipt(
    telegram_user_id: int,
    package_code: str,
    package: dict,
    receipt_path: Path,
) -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token or not ADMIN_TELEGRAM_IDS:
        return

    caption = (
        "🧾 Получен PDF-чек из Mini App\n\n"
        f"Telegram ID: {telegram_user_id}\n"
        f"Пакет: {package.get('title', package_code)}\n"
        f"Сумма: {format_kzt(package['amount_kzt'])} ₸\n"
        f"Время: {datetime.now(ALMATY_TZ).strftime('%d.%m %H:%M')}\n\n"
        "Проверь оплату и активируй доступ:\n"
        f"{get_admin_activation_command(telegram_user_id, package_code)}"
    )
    send_document_url = (
        f"https://api.telegram.org/bot{telegram_token}/sendDocument"
    )
    if package_code == "ai_30":
        button_text = "✅ Активировать 30 AI"
    elif package_code == "premium_90":
        button_text = "✅ Активировать 3 месяца"
    else:
        button_text = "✅ Активировать 1 месяц"
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": button_text,
                    "callback_data": (
                        "admin_pay_confirm:"
                        f"{telegram_user_id}:{package_code}"
                    ),
                }
            ]
        ]
    }

    for admin_id in ADMIN_TELEGRAM_IDS:
        try:
            with receipt_path.open("rb") as receipt_file:
                response = requests.post(
                    send_document_url,
                    data={
                        "chat_id": admin_id,
                        "caption": caption,
                        "reply_markup": json.dumps(reply_markup),
                    },
                    files={
                        "document": (
                            receipt_path.name,
                            receipt_file,
                            "application/pdf",
                        )
                    },
                    timeout=30,
                )
                response.raise_for_status()
        except Exception:
            logger.error(
                "Failed to notify admin %s about Mini App receipt",
                admin_id,
                exc_info=True,
            )


def activate_payment_package(
    telegram_user_id: int,
    package_code: str,
) -> bool:
    if package_code == "ai_30":
        before_subscription = get_or_create_subscription(telegram_user_id)
        before_credits = int(
            before_subscription.get("extra_ai_credits") or 0
        )
        subscription = add_ai_limit(
            telegram_user_id,
            AI_PACK_30_LIMIT,
        )
        return int(
            subscription.get("extra_ai_credits") or 0
        ) >= before_credits + AI_PACK_30_LIMIT

    if package_code == "premium_90":
        days = PREMIUM_90_DAYS
        ai_limit = PREMIUM_90_AI_LIMIT
    elif package_code == "premium_30":
        days = PREMIUM_30_DAYS
        ai_limit = PREMIUM_30_AI_LIMIT
    else:
        return False

    subscription = grant_premium(
        telegram_user_id,
        days,
        ai_limit,
    )
    return (
        is_premium_active(subscription)
        and int(subscription.get("ai_limit_monthly") or 0) == ai_limit
    )


def build_activated_payment_user_message(package_code: str) -> str:
    if package_code == "ai_30":
        return (
            "✅ Доступ активирован!\n\n"
            "Ваш пакет: ⚡ 30 AI-разборов\n"
            "Теперь можно снова пользоваться AI-разборами в MatchLab.\n\n"
            "Откройте Mini App и проверьте профиль."
        )

    if package_code == "premium_90":
        tariff_text = "🏆 3 месяца"
    else:
        tariff_text = "💎 1 месяц"

    return (
        "✅ Подписка активирована!\n\n"
        f"Ваш тариф: {tariff_text}\n"
        "AI-разборы доступны в MatchLab.\n\n"
        "Откройте Mini App и проверьте профиль."
    )


async def admin_payment_confirm_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.answer("Недоступно", show_alert=True)
        return

    callback_data = query.data or ""
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "admin_pay_confirm":
        await query.answer("Не удалось активировать", show_alert=True)
        return

    try:
        telegram_user_id = int(parts[1])
    except ValueError:
        await query.answer("Не удалось активировать", show_alert=True)
        return

    package_code = parts[2]
    if package_code not in PAYMENT_PACKAGES:
        await query.answer("Не удалось активировать", show_alert=True)
        return

    payment_request = claim_payment_request_for_activation(
        telegram_user_id,
        package_code,
    )
    if not payment_request:
        await query.answer("Уже обработано", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug(
                "Failed to remove processed payment button",
                exc_info=True,
            )
        return

    payment_request_id = int(payment_request["id"])
    try:
        if not activate_payment_package(telegram_user_id, package_code):
            raise RuntimeError("Payment package activation failed")
    except Exception:
        update_payment_request_status(
            payment_request_id,
            "receipt_received",
        )
        logger.exception(
            "Admin payment activation failed: user_id=%s package=%s",
            telegram_user_id,
            package_code,
        )
        await query.answer(
            "Не удалось активировать",
            show_alert=True,
        )
        return

    update_payment_request_status(payment_request_id, "approved")
    log_user_event(
        telegram_user_id,
        "payment_approved",
        {
            "package_code": package_code,
            "admin_id": admin_id,
            "source": "miniapp_callback",
        },
    )

    user_notified = False
    try:
        await context.bot.send_message(
            chat_id=telegram_user_id,
            text=build_activated_payment_user_message(package_code),
            reply_markup=build_miniapp_inline_keyboard("profile"),
        )
        user_notified = True
    except Exception:
        logger.warning(
            "Failed to notify user about activated payment",
            exc_info=True,
        )

    activated_at = datetime.now(ALMATY_TZ).strftime("%d.%m %H:%M")
    current_caption = query.message.caption if query.message else ""
    notification_status = (
        "📩 Пользователь уведомлён"
        if user_notified
        else "📩 Пользователь не уведомлён"
    )
    activated_caption = (
        f"{current_caption}\n\n"
        "✅ Доступ активирован\n"
        f"Админ: {admin_id}\n"
        f"Время: {activated_at}\n"
        f"{notification_status}"
    ).strip()

    await query.answer("Доступ активирован")
    try:
        await query.edit_message_caption(
            caption=activated_caption,
            reply_markup=None,
        )
    except Exception:
        logger.error(
            "Failed to update activated payment message",
            exc_info=True,
        )


@miniapp_api.get("/api/health")
def miniapp_health():
    return jsonify(
        {
            "ok": True,
            "service": "matchlab",
            "version": "miniapp-api-v1",
        }
    )


@miniapp_api.get("/api/config")
def miniapp_config():
    packages = []
    for package_code, package in PAYMENT_PACKAGES.items():
        package_data = {
            "code": package_code,
            "title": package["title"],
            "price_kzt": package["amount_kzt"],
        }
        for field_name in ("ai_credits", "days", "ai_limit"):
            if field_name in package:
                package_data[field_name] = package[field_name]
        packages.append(package_data)

    return jsonify(
        {
            "bot_username": "Match_Stat_bot",
            "free_ai_limit": FREE_AI_LIMIT_MONTHLY,
            "packages": packages,
        }
    )


@miniapp_api.get("/api/subscription")
def miniapp_subscription():
    telegram_user = get_api_telegram_user(flask_request)
    if not telegram_user:
        return jsonify(
            {
                "ok": False,
                "error": "telegram_user_id_required",
            }
        ), 400

    telegram_user_id = int(telegram_user["id"])
    auth_mode = telegram_user.get("_auth_mode", "init_data")
    subscription = get_or_create_subscription(telegram_user_id)
    is_admin = is_admin_user(telegram_user_id)

    if is_admin:
        plan = "admin"
    elif is_premium_active(subscription):
        plan = "premium"
    else:
        plan = "free"

    response_data = {
        "ok": True,
        "telegram_user_id": telegram_user_id,
        "plan": plan,
        "premium_until": serialize_api_datetime(
            subscription.get("premium_until")
        ),
        "ai_used_monthly": int(subscription.get("ai_used_monthly") or 0),
        "ai_limit_monthly": int(subscription.get("ai_limit_monthly") or 0),
        "extra_ai_credits": int(subscription.get("extra_ai_credits") or 0),
        "usage_period": (
            subscription.get("usage_period") or get_current_usage_period()
        ),
        "is_admin": is_admin,
        "auth_mode": auth_mode,
    }
    if is_admin:
        response_data["ai_text"] = "без лимита"

    return jsonify(response_data)


def build_miniapp_matches_response(match_type: str):
    try:
        return jsonify(
            {
                "ok": True,
                "items": get_miniapp_matches(match_type),
            }
        )
    except Exception:
        logger.exception("Mini App %s matches request failed", match_type)
        return jsonify(
            {
                "ok": False,
                "items": [],
                "error": "matches_unavailable",
            }
        ), 503


@miniapp_api.get("/api/matches/today")
def miniapp_matches_today():
    return build_miniapp_matches_response("today")


@miniapp_api.get("/api/matches/tomorrow")
def miniapp_matches_tomorrow():
    return build_miniapp_matches_response("tomorrow")


@miniapp_api.get("/api/matches/top")
def miniapp_matches_top():
    return build_miniapp_matches_response("top")


@miniapp_api.route(
    "/api/matches/<match_id>/context",
    methods=["GET", "OPTIONS"],
)
def miniapp_match_context(match_id: str):
    if flask_request.method == "OPTIONS":
        return "", 204

    match = find_miniapp_match(match_id)
    if not match:
        return jsonify(
            {
                "ok": False,
                "error": "match_not_found",
                "message": "Матч не найден или уже недоступен.",
            }
        ), 404

    try:
        return jsonify(get_miniapp_match_context(match))
    except Exception:
        logger.exception(
            "Mini App match context request failed: match_id=%s",
            match_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "match_context_unavailable",
                "message": "Данные матча временно недоступны.",
            }
        ), 503


@miniapp_api.route(
    "/api/matches/<match_id>/ai",
    methods=["POST", "OPTIONS"],
)
def miniapp_match_ai_analysis(match_id: str):
    if flask_request.method == "OPTIONS":
        return "", 204

    telegram_user = get_api_telegram_user(flask_request)
    if not telegram_user:
        return jsonify(
            {
                "ok": False,
                "error": "telegram_user_id_required",
                "message": "Не удалось определить пользователя Telegram.",
            }
        ), 400

    telegram_user_id = int(telegram_user["id"])
    is_admin = is_admin_user(telegram_user_id)
    logger.info(
        "Mini App AI analysis requested: match_id=%s user_id=%s",
        match_id,
        telegram_user_id,
    )

    match = find_miniapp_match(match_id)
    if not match:
        return jsonify(
            {
                "ok": False,
                "error": "match_not_found",
                "message": "Матч не найден или уже недоступен.",
            }
        ), 404

    if is_admin:
        allowed = True
        subscription = {}
    else:
        allowed, _, subscription = can_use_ai_analysis(telegram_user_id)

    if not allowed:
        return jsonify(
            {
                "ok": False,
                "error": "ai_limit_exceeded",
                "message": (
                    "AI-лимит закончился. Оформите подписку "
                    "или докупите AI-разборы."
                ),
            }
        ), 402

    try:
        match_data = build_miniapp_ai_match_data(match)
        analysis = get_openai_ai_analysis(match_data)
    except Exception:
        logger.exception(
            "Mini App AI analysis failed: match_id=%s user_id=%s",
            match_id,
            telegram_user_id,
        )
        analysis = "AI-разбор временно недоступен."

    if analysis in {
        "AI-разбор пока не подключён.",
        "AI-разбор временно недоступен.",
    }:
        return jsonify(
            {
                "ok": False,
                "error": "ai_analysis_unavailable",
                "message": "AI-разбор временно недоступен.",
            }
        ), 503

    limit_charged = False
    remaining_ai = None
    if not is_admin:
        available_before = get_ai_available_count(subscription)
        updated_subscription = increment_ai_usage(telegram_user_id)
        remaining_ai = get_ai_available_count(updated_subscription)
        limit_charged = remaining_ai < available_before

    return jsonify(
        {
            "ok": True,
            "match_id": str(match.get("id") or match_id),
            "home": match.get("home") or "",
            "away": match.get("away") or "",
            "analysis": analysis,
            "limit_charged": limit_charged,
            "remaining_ai": remaining_ai,
            "is_admin": is_admin,
        }
    )


@miniapp_api.route(
    "/api/payments/request",
    methods=["POST", "OPTIONS"],
)
def miniapp_payment_request():
    if flask_request.method == "OPTIONS":
        return "", 204

    telegram_user = get_api_telegram_user(flask_request)
    if not telegram_user:
        return jsonify(
            {
                "ok": False,
                "error": "telegram_user_id_required",
                "message": "Не удалось определить пользователя Telegram.",
            }
        ), 400

    requested_package_code = flask_request.form.get(
        "package_code",
        "",
    ).strip()
    package_code = MINIAPP_PAYMENT_PACKAGE_CODES.get(
        requested_package_code
    )
    if not package_code:
        return jsonify(
            {
                "ok": False,
                "error": "invalid_package",
                "message": "Неизвестный пакет.",
            }
        ), 400

    receipt_file = flask_request.files.get("receipt_file")
    receipt_file_name = (
        receipt_file.filename.strip()
        if receipt_file and receipt_file.filename
        else ""
    )
    if not receipt_file or not receipt_file_name.lower().endswith(".pdf"):
        return jsonify(
            {
                "ok": False,
                "error": "invalid_receipt",
                "message": "Загрузите PDF-чек.",
            }
        ), 400

    telegram_user_id = int(telegram_user["id"])
    package = PAYMENT_PACKAGES[package_code]
    payment_request = create_payment_request(
        telegram_user_id,
        package_code,
        package["amount_kzt"],
    )
    if not payment_request:
        return jsonify(
            {
                "ok": False,
                "error": "payment_request_unavailable",
                "message": "Не удалось отправить чек. Попробуйте позже.",
            }
        ), 503

    receipts_directory = (
        Path(tempfile.gettempdir()) / "matchlab_receipts"
    )
    receipts_directory.mkdir(parents=True, exist_ok=True)
    safe_receipt_name = (
        f"receipt_{telegram_user_id}_{payment_request['id']}.pdf"
    )
    receipt_path = receipts_directory / safe_receipt_name

    try:
        receipt_file.save(receipt_path)
        updated_request = update_latest_payment_request_with_receipt(
            telegram_user_id,
            str(receipt_path),
            safe_receipt_name,
        )
        if not updated_request:
            raise RuntimeError("Failed to save Mini App payment receipt")

        notify_admins_about_miniapp_receipt(
            telegram_user_id,
            package_code,
            package,
            receipt_path,
        )
    except Exception:
        logger.exception(
            "Mini App payment receipt processing failed: user_id=%s",
            telegram_user_id,
        )
        receipt_path.unlink(missing_ok=True)
        return jsonify(
            {
                "ok": False,
                "error": "receipt_processing_failed",
                "message": "Не удалось отправить чек. Попробуйте позже.",
            }
        ), 503

    return jsonify(
        {
            "ok": True,
            "message": (
                "Чек отправлен на проверку. "
                "После проверки доступ будет активирован."
            ),
            "package_title": package["title"],
            "amount": package["amount_kzt"],
        }
    )


def run_miniapp_api_server() -> None:
    miniapp_api.run(
        host=MINIAPP_API_HOST,
        port=MINIAPP_API_PORT,
        use_reloader=False,
        threaded=True,
    )


def main() -> None:
    init_db()
    if WEBAPP_URL:
        logger.info("Mini App WEBAPP_URL configured: %s", WEBAPP_URL)

    if not RUN_TELEGRAM_BOT:
        logger.info("🤖 Telegram bot polling disabled")
        if ENABLE_MINIAPP_API:
            logger.info(
                "🌐 Mini App API enabled on %s:%s",
                MINIAPP_API_HOST,
                MINIAPP_API_PORT,
            )
            logger.info("🌐 Mini App API running as main web service")
            run_miniapp_api_server()
        else:
            logger.info("🌐 Mini App API disabled")
            logger.warning(
                "RUN_TELEGRAM_BOT and ENABLE_MINIAPP_API are both disabled"
            )
        return

    logger.info("🤖 Telegram bot polling enabled")
    telegram_token = get_required_env("TELEGRAM_BOT_TOKEN")
    #football_api_key = os.getenv("FOOTBALL_API_KEY", "")

    application = Application.builder().token(telegram_token).build()
    #application.bot_data["football_api_key"] = football_api_key

    from telegram import BotCommand

    application.bot.set_my_commands([
        BotCommand("today", "Матчи сегодня"),
        BotCommand("tomorrow", "Матчи завтра"),
        BotCommand("top", "Топ матчи"),
    ])

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("tomorrow", tomorrow))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("testdb", testdb))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("user", user_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("grant_premium", grant_premium_command))
    application.add_handler(CommandHandler("revoke_premium", revoke_premium_command))
    application.add_handler(CommandHandler("add_ai_limit", add_ai_limit_command))
    application.add_handler(CommandHandler("subscription", subscription_command))
    application.add_handler(
        CallbackQueryHandler(
            admin_payment_confirm_callback,
            pattern=r"^admin_pay_confirm:\d+:(ai_30|premium_30|premium_90)$",
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^📅 Сегодня$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^📆 Завтра$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^🔥 Топ матчи$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^⚽ Команда$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^📋 Профиль$"),
            button_handler
        )
    )
    
    application.add_handler(
        MessageHandler(
            filters.Regex("^📊 Результаты$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^⭐ Моя команда$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^🏆 Таблица$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^⬅️ Назад$"),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex(
                "^(" + "|".join(
                    re.escape(key)
                    for key in STANDINGS_LEAGUES.keys()
                ) + ")$"
            ),
            button_handler
        )
    )

    favorite_team_buttons = set(FAVORITE_TEAM_LEAGUES.keys())
    favorite_team_buttons.add(FAVORITE_MANUAL_INPUT_BUTTON)
    favorite_team_buttons.add(FAVORITE_BACK_TO_LEAGUES_BUTTON)
    favorite_team_buttons.add(FAVORITE_OPEN_PROFILE_BUTTON)
    favorite_team_buttons.add(FAVORITE_CHANGE_TEAM_BUTTON)
    favorite_team_buttons.add(MATCH_AI_ANALYSIS_BUTTON)
    favorite_team_buttons.add(PREMIUM_BUTTON)
    favorite_team_buttons.update(PAYMENT_PACKAGE_BUTTONS)
    for teams in FAVORITE_TEAM_LEAGUES.values():
        favorite_team_buttons.update(teams)

    application.add_handler(
        MessageHandler(
            filters.Regex(
                "^(" + "|".join(
                    re.escape(button)
                    for button in favorite_team_buttons
                ) + ")$"
            ),
            button_handler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            payment_receipt_document
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            match_number_analysis
        ),
        group=1
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            team_search
        ),
        group=2
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            team_results
        ),
        group=3
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            favorite_team
        ),
        group=4
    )

    if ENABLE_MINIAPP_API:
        logger.info(
            "🌐 Mini App API enabled on %s:%s",
            MINIAPP_API_HOST,
            MINIAPP_API_PORT,
        )
        threading.Thread(
            target=run_miniapp_api_server,
            daemon=True,
            name="matchlab-miniapp-api",
        ).start()
    else:
        logger.info("🌐 Mini App API disabled")

    application.run_polling(
    drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
