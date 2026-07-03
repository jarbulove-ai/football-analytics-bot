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
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Flask, jsonify, request as flask_request
from openai import OpenAI
import psycopg2
import requests
from psycopg2.extras import Json, RealDictCursor
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
OPENAI_AI_MODEL_DEFAULT = os.getenv(
    "OPENAI_AI_MODEL_DEFAULT",
    OPENAI_MODEL,
)
OPENAI_AI_MODEL_PREMIUM = os.getenv(
    "OPENAI_AI_MODEL_PREMIUM",
    OPENAI_AI_MODEL_DEFAULT,
)
OPENAI_AI_REASONING_EFFORT_DEFAULT = os.getenv(
    "OPENAI_AI_REASONING_EFFORT_DEFAULT",
    "medium",
).strip()
OPENAI_AI_REASONING_EFFORT_PREMIUM = os.getenv(
    "OPENAI_AI_REASONING_EFFORT_PREMIUM",
    "high",
).strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
MATCHLAB_CHANNEL_ID = os.getenv("MATCHLAB_CHANNEL_ID", "").strip()
MATCHDAY_COVER_TEMPLATE_PATH = os.getenv(
    "MATCHDAY_COVER_TEMPLATE_PATH",
    "assets/matchday_cover_bg.png",
)
MATCHLAB_LOGO_PATH = os.getenv(
    "MATCHLAB_LOGO_PATH",
    "assets/matchlab_logo.png",
)
MATCHLAB_LOGO_MARK_PATH = os.getenv(
    "MATCHLAB_LOGO_MARK_PATH",
    "assets/matchlab_logo_mark.png",
)
MATCHLAB_FONT_PATH = os.getenv(
    "MATCHLAB_FONT_PATH",
    "assets/fonts/matchlab_title.ttf",
)
MATCHLAB_CONDENSED_FONT_PATH = os.getenv(
    "MATCHLAB_CONDENSED_FONT_PATH",
    "assets/fonts/matchlab_condensed.ttf",
)
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
MINIAPP_AI_FREE_REFRESH_TOTAL = 2
AI_PACK_30_PRICE_KZT = int(os.getenv("AI_PACK_30_PRICE_KZT", "499"))
AI_PACK_30_LIMIT = int(os.getenv("AI_PACK_30_LIMIT", "30"))
PREMIUM_30_PRICE_KZT = int(os.getenv("PREMIUM_30_PRICE_KZT", "990"))
PREMIUM_30_DAYS = int(os.getenv("PREMIUM_30_DAYS", "30"))
PREMIUM_30_AI_LIMIT = 100
PREMIUM_90_PRICE_KZT = int(os.getenv("PREMIUM_90_PRICE_KZT", "2490"))
PREMIUM_90_DAYS = int(os.getenv("PREMIUM_90_DAYS", "90"))
PREMIUM_90_AI_LIMIT = 350
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
MINIAPP_LIVE_CACHE = {}
MINIAPP_LIVE_CACHE_LOCK = threading.Lock()
CHANNEL_PLAN_CANDIDATES_TTL_SECONDS = 900
CHANNEL_PLAN_DRAFTS_TTL_SECONDS = 1800
MINIAPP_LIVE_STATUSES = {
    "1H",
    "HT",
    "2H",
    "ET",
    "BT",
    "P",
    "LIVE",
    "INT",
}
MINIAPP_FINISHED_STATUSES = {"FT", "AET", "PEN"}
MINIAPP_NOT_STARTED_STATUSES = {"NS", "TBD"}


@miniapp_api.after_request
def add_miniapp_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers[
        "Access-Control-Allow-Headers"
    ] = "Content-Type, X-Telegram-Init-Data"
    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, DELETE, OPTIONS"
    )
    return response


def normalize_team_name(team_name: str) -> str:
    stripped_team_name = team_name.strip()
    normalized_team_name = stripped_team_name.lower().replace("ё", "е")
    normalized_team_name = re.sub(r"\s+", " ", normalized_team_name)

    return TEAM_ALIASES.get(normalized_team_name, stripped_team_name)


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def get_database_url_fingerprint(database_url: str | None = None) -> str:
    database_url = database_url or get_database_url()
    if not database_url:
        return ""

    try:
        parsed_url = urlsplit(database_url)
        host = parsed_url.hostname or "unknown-host"
        port = f":{parsed_url.port}" if parsed_url.port else ""
        database_name = parsed_url.path.lstrip("/") or "unknown-db"
        url_hash = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:12]
        return f"{host}{port}/{database_name}#{url_hash}"
    except Exception:
        url_hash = hashlib.sha256(str(database_url).encode("utf-8")).hexdigest()[:12]
        return f"unparsed#{url_hash}"


MINIAPP_REFERRAL_REWARD_TYPE = "invite_3_premium_ai_25"
MINIAPP_REFERRAL_TARGET_COUNT = 3
MINIAPP_REFERRAL_REWARD_AI_LIMIT = 25


def ensure_miniapp_referrals_table() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_telegram_user_id BIGINT NOT NULL,
                    referred_telegram_user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    reward_granted_at TIMESTAMPTZ,
                    UNIQUE (referred_telegram_user_id)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_miniapp_referrals_referrer
                ON miniapp_referrals (referrer_telegram_user_id);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_miniapp_referrals_referred
                ON miniapp_referrals (referred_telegram_user_id);
                """
            )
        connection.commit()
        return True
    except Exception:
        logger.exception("Failed to ensure Mini App referrals table")
        return False
    finally:
        if connection is not None:
            connection.close()


def ensure_miniapp_referral_rewards_table() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_referral_rewards (
                    id SERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    reward_type TEXT NOT NULL,
                    reward_value INTEGER NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (telegram_user_id, reward_type)
                );
                """
            )
        connection.commit()
        return True
    except Exception:
        logger.exception("Failed to ensure Mini App referral rewards table")
        return False
    finally:
        if connection is not None:
            connection.close()


def ensure_miniapp_ai_credit_grants_table() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_ai_credit_grants (
                    id SERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    credits_total INTEGER NOT NULL,
                    credits_used INTEGER NOT NULL DEFAULT 0,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (telegram_user_id, source_type, source_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_miniapp_ai_credit_grants_user
                ON miniapp_ai_credit_grants (telegram_user_id);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_miniapp_ai_credit_grants_expires
                ON miniapp_ai_credit_grants (expires_at);
                """
            )
        connection.commit()
        return True
    except Exception:
        logger.exception("Failed to ensure Mini App AI credit grants table")
        return False
    finally:
        if connection is not None:
            connection.close()


def init_db() -> None:
    database_url = get_database_url()
    logger.info(
        "database_url_present %s database_url_fingerprint=%s",
        bool(database_url),
        get_database_url_fingerprint(database_url),
    )
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_favorite_teams (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    team_id BIGINT NOT NULL,
                    team_name TEXT NOT NULL,
                    team_logo TEXT,
                    team_country TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_user_id, team_id)
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_match_reminders (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    match_id TEXT NOT NULL,
                    home_team TEXT,
                    away_team TEXT,
                    league TEXT,
                    kickoff TIMESTAMPTZ NOT NULL,
                    notify_at TIMESTAMPTZ NOT NULL,
                    is_sent BOOLEAN DEFAULT FALSE,
                    lineups_notified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_user_id, match_id)
                );
                """
            )
            cursor.execute(
                """
                ALTER TABLE miniapp_match_reminders
                ADD COLUMN IF NOT EXISTS lineups_notified
                BOOLEAN DEFAULT FALSE;
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_match_event_notifications (
                    id SERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    match_id TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time INTEGER,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_user_id, match_id, event_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_match_ai_analyses (
                    id SERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL,
                    match_id TEXT NOT NULL,
                    analysis TEXT NOT NULL,
                    structured JSONB,
                    analysis_mode TEXT NOT NULL DEFAULT 'default',
                    refresh_count INTEGER DEFAULT 0,
                    home_team TEXT,
                    away_team TEXT,
                    league TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_user_id, match_id)
                );
                """
            )
            cursor.execute(
                """
                ALTER TABLE miniapp_match_ai_analyses
                ADD COLUMN IF NOT EXISTS refresh_count
                INTEGER DEFAULT 0;
                """
            )
            cursor.execute(
                """
                ALTER TABLE miniapp_match_ai_analyses
                DROP CONSTRAINT IF EXISTS
                miniapp_match_ai_analyses_telegram_user_id_match_id_key;
                """
            )
            cursor.execute(
                """
                DO $$
                DECLARE
                    constraint_row RECORD;
                BEGIN
                    FOR constraint_row IN
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid = 'miniapp_match_ai_analyses'::regclass
                        AND contype = 'u'
                        AND (
                            SELECT array_agg(
                                att.attname::text ORDER BY ord.ordinality
                            )
                            FROM unnest(conkey) WITH ORDINALITY
                            AS ord(attnum, ordinality)
                            JOIN pg_attribute att
                            ON att.attrelid = conrelid
                            AND att.attnum = ord.attnum
                        ) = ARRAY['telegram_user_id', 'match_id']::text[]
                    LOOP
                        EXECUTE format(
                            'ALTER TABLE miniapp_match_ai_analyses '
                            'DROP CONSTRAINT %I',
                            constraint_row.conname
                        );
                    END LOOP;
                END $$;
                """
            )
            cursor.execute(
                """
                DO $$
                DECLARE
                    index_row RECORD;
                BEGIN
                    FOR index_row IN
                        SELECT idx.indexrelid::regclass AS index_name
                        FROM pg_index idx
                        WHERE idx.indrelid =
                            'miniapp_match_ai_analyses'::regclass
                        AND idx.indisunique
                        AND NOT idx.indisprimary
                        AND (
                            SELECT array_agg(
                                att.attname::text ORDER BY ord.ordinality
                            )
                            FROM unnest(idx.indkey) WITH ORDINALITY
                            AS ord(attnum, ordinality)
                            JOIN pg_attribute att
                            ON att.attrelid = idx.indrelid
                            AND att.attnum = ord.attnum
                        ) = ARRAY['telegram_user_id', 'match_id']::text[]
                    LOOP
                        EXECUTE format(
                            'DROP INDEX IF EXISTS %s',
                            index_row.index_name
                        );
                    END LOOP;
                END $$;
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                miniapp_match_ai_analyses_user_match_mode_uidx
                ON miniapp_match_ai_analyses (
                    telegram_user_id,
                    match_id,
                    analysis_mode
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_match_ai_global_analyses (
                    id SERIAL PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL DEFAULT 'default',
                    analysis TEXT NOT NULL,
                    structured JSONB,
                    home_team TEXT,
                    away_team TEXT,
                    league TEXT,
                    context_hash TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (match_id, analysis_mode)
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_agent_matchdays (
                    id BIGSERIAL PRIMARY KEY,
                    agent_key TEXT NOT NULL DEFAULT 'default',
                    match_id TEXT NOT NULL,
                    match_json JSONB NOT NULL,
                    status TEXT NOT NULL,
                    agent_score INTEGER,
                    agent_reasons JSONB,
                    selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    pre_match_published_at TIMESTAMPTZ,
                    pre_match_message_id BIGINT,
                    post_match_draft_created_at TIMESTAMPTZ,
                    post_match_published_at TIMESTAMPTZ,
                    post_match_message_id BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (agent_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_agent_matchdays_match_id
                ON channel_agent_matchdays (match_id);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_agent_matchdays_status
                ON channel_agent_matchdays (status);
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_auto_posts (
                    id BIGSERIAL PRIMARY KEY,
                    content_type TEXT NOT NULL,
                    date_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    draft TEXT,
                    published_at TIMESTAMPTZ,
                    published_message_id BIGINT,
                    error_text TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (content_type, date_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_content_type
                ON channel_auto_posts (content_type);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_date_key
                ON channel_auto_posts (date_key);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_status
                ON channel_auto_posts (status);
                """
            )
        connection.commit()
        ensure_miniapp_referrals_table()
        ensure_miniapp_referral_rewards_table()
        ensure_miniapp_ai_credit_grants_table()
    except Exception:
        logger.exception("Failed to initialize database")
    finally:
        if connection is not None:
            connection.close()


def ensure_channel_agent_matchdays_table() -> bool:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; channel agent DB memory disabled"
        )
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_agent_matchdays (
                    id BIGSERIAL PRIMARY KEY,
                    agent_key TEXT NOT NULL DEFAULT 'default',
                    match_id TEXT NOT NULL,
                    match_json JSONB NOT NULL,
                    status TEXT NOT NULL,
                    agent_score INTEGER,
                    agent_reasons JSONB,
                    selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    pre_match_published_at TIMESTAMPTZ,
                    pre_match_message_id BIGINT,
                    post_match_draft_created_at TIMESTAMPTZ,
                    post_match_published_at TIMESTAMPTZ,
                    post_match_message_id BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (agent_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_agent_matchdays_match_id
                ON channel_agent_matchdays (match_id);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_agent_matchdays_status
                ON channel_agent_matchdays (status);
                """
            )
        connection.commit()
        logger.info("channel_agent db table ensured")
        return True
    except Exception:
        logger.exception("channel_agent db table ensure failed")
        return False
    finally:
        if connection is not None:
            connection.close()


def ensure_channel_auto_posts_table() -> bool:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; channel auto posts DB disabled"
        )
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_auto_posts (
                    id BIGSERIAL PRIMARY KEY,
                    content_type TEXT NOT NULL,
                    date_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    draft TEXT,
                    published_at TIMESTAMPTZ,
                    published_message_id BIGINT,
                    error_text TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (content_type, date_key)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_content_type
                ON channel_auto_posts (content_type);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_date_key
                ON channel_auto_posts (date_key);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_auto_posts_status
                ON channel_auto_posts (status);
                """
            )
        connection.commit()
        logger.info("channel_auto_posts db table ensured")
        return True
    except Exception:
        logger.exception("channel_auto_posts db table ensure failed")
        return False
    finally:
        if connection is not None:
            connection.close()


def ensure_miniapp_ai_global_cache_table() -> bool:
    database_url = get_database_url()
    logger.info(
        "database_url_present %s database_url_fingerprint=%s "
        "source=ensure_miniapp_ai_global_cache_table",
        bool(database_url),
        get_database_url_fingerprint(database_url),
    )
    if not database_url:
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE miniapp_match_ai_analyses
                ADD COLUMN IF NOT EXISTS refresh_count
                INTEGER DEFAULT 0;
                """
            )
            cursor.execute(
                """
                ALTER TABLE miniapp_match_ai_analyses
                DROP CONSTRAINT IF EXISTS
                miniapp_match_ai_analyses_telegram_user_id_match_id_key;
                """
            )
            cursor.execute(
                """
                DO $$
                DECLARE
                    constraint_row RECORD;
                BEGIN
                    FOR constraint_row IN
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid = 'miniapp_match_ai_analyses'::regclass
                        AND contype = 'u'
                        AND (
                            SELECT array_agg(
                                att.attname::text ORDER BY ord.ordinality
                            )
                            FROM unnest(conkey) WITH ORDINALITY
                            AS ord(attnum, ordinality)
                            JOIN pg_attribute att
                            ON att.attrelid = conrelid
                            AND att.attnum = ord.attnum
                        ) = ARRAY['telegram_user_id', 'match_id']::text[]
                    LOOP
                        EXECUTE format(
                            'ALTER TABLE miniapp_match_ai_analyses '
                            'DROP CONSTRAINT %I',
                            constraint_row.conname
                        );
                    END LOOP;
                END $$;
                """
            )
            cursor.execute(
                """
                DO $$
                DECLARE
                    index_row RECORD;
                BEGIN
                    FOR index_row IN
                        SELECT idx.indexrelid::regclass AS index_name
                        FROM pg_index idx
                        WHERE idx.indrelid =
                            'miniapp_match_ai_analyses'::regclass
                        AND idx.indisunique
                        AND NOT idx.indisprimary
                        AND (
                            SELECT array_agg(
                                att.attname::text ORDER BY ord.ordinality
                            )
                            FROM unnest(idx.indkey) WITH ORDINALITY
                            AS ord(attnum, ordinality)
                            JOIN pg_attribute att
                            ON att.attrelid = idx.indrelid
                            AND att.attnum = ord.attnum
                        ) = ARRAY['telegram_user_id', 'match_id']::text[]
                    LOOP
                        EXECUTE format(
                            'DROP INDEX IF EXISTS %s',
                            index_row.index_name
                        );
                    END LOOP;
                END $$;
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                miniapp_match_ai_analyses_user_match_mode_uidx
                ON miniapp_match_ai_analyses (
                    telegram_user_id,
                    match_id,
                    analysis_mode
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS miniapp_match_ai_global_analyses (
                    id SERIAL PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL DEFAULT 'default',
                    analysis TEXT NOT NULL,
                    structured JSONB,
                    home_team TEXT,
                    away_team TEXT,
                    league TEXT,
                    context_hash TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (match_id, analysis_mode)
                );
                """
            )
        connection.commit()
        return True
    except Exception:
        logger.warning(
            "Failed to ensure Mini App AI global cache table",
            exc_info=True,
        )
        return False
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


MINIAPP_EVENT_TYPES = {
    "miniapp_opened",
    "daily_focus_opened",
    "daily_focus_match_selected",
    "miniapp_match_selected",
    "miniapp_ai_clicked",
    "miniapp_ai_success",
    "miniapp_ai_limit_reached",
    "miniapp_premium_upsell_clicked",
    "scenarios_teaser_clicked",
    "subscription_opened",
    "payment_plan_selected",
    "payment_started",
}


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
    miniapp_event_types = {
        "miniapp_opened": "Открыли miniapp",
        "daily_focus_opened": "Открыли Матчи дня",
        "daily_focus_match_selected": "Матч из фокуса открыли",
        "miniapp_match_selected": "Обычный матч открыли",
        "miniapp_ai_clicked": "AI-разбор нажали",
        "miniapp_ai_success": "AI-разбор успешно",
        "miniapp_ai_limit_reached": "Лимит AI достигнут",
        "miniapp_premium_upsell_clicked": "Premium после AI",
        "scenarios_teaser_clicked": "Сценарии → Premium",
        "subscription_opened": "Подписку открыли",
        "payment_plan_selected": "Тариф выбрали",
        "payment_started": "К оплате перешли",
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

            miniapp_event_counts = {}
            for event_type in miniapp_event_types:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS value
                    FROM user_events
                    WHERE event_type = %s
                    AND created_at >= %s;
                    """,
                    (event_type, today_start),
                )
                miniapp_event_counts[event_type] = cursor.fetchone()["value"]
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
    lines.extend(["", "Mini App сегодня:"])
    lines.extend(
        f"• {label}: {miniapp_event_counts[event_type]}"
        for event_type, label in miniapp_event_types.items()
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


def get_total_ai_available_count(
    telegram_user_id: int,
    subscription: dict,
) -> int:
    return get_ai_available_count(subscription) + get_active_bonus_ai_credits(
        telegram_user_id
    )


def get_ai_usage_text(subscription: dict) -> str:
    used = int(subscription.get("ai_used_monthly") or 0)
    limit = int(subscription.get("ai_limit_monthly") or 0)
    lines = [f"AI-разборы: {used} / {limit}"]
    extra_ai_credits = int(subscription.get("extra_ai_credits") or 0)
    if extra_ai_credits > 0:
        lines.append(f"Доп. AI-разборы: {extra_ai_credits}")
    return "\n".join(lines)


def grant_bonus_ai_credits(
    telegram_user_id: int,
    source_type: str,
    source_key: str,
    credits: int,
    days_valid: int,
    cursor=None,
) -> dict:
    expires_at = datetime.now(timezone.utc) + timedelta(days=days_valid)

    def execute_grant(active_cursor):
        active_cursor.execute(
            """
            INSERT INTO miniapp_ai_credit_grants (
                telegram_user_id,
                source_type,
                source_key,
                credits_total,
                credits_used,
                expires_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, 0, %s, NOW())
            ON CONFLICT (telegram_user_id, source_type, source_key)
            DO NOTHING
            RETURNING *;
            """,
            (
                telegram_user_id,
                source_type,
                source_key,
                credits,
                expires_at,
            ),
        )
        row = active_cursor.fetchone()
        if row:
            return {
                "granted": True,
                "already_granted": False,
                "grant": dict(row),
            }
        return {
            "granted": False,
            "already_granted": True,
            "grant": None,
        }

    if cursor is not None:
        return execute_grant(cursor)

    database_url = get_database_url()
    if not database_url:
        return {"granted": False, "already_granted": False, "grant": None}

    ensure_miniapp_ai_credit_grants_table()
    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as active_cursor:
            result = execute_grant(active_cursor)
        connection.commit()
        return result
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception(
            "Failed to grant bonus AI credits: user_id=%s source_type=%s source_key=%s",
            telegram_user_id,
            source_type,
            source_key,
        )
        return {"granted": False, "already_granted": False, "grant": None}
    finally:
        if connection is not None:
            connection.close()


def get_active_bonus_ai_credit_info(
    telegram_user_id: int,
    cursor=None,
) -> dict:
    def execute_lookup(active_cursor):
        active_cursor.execute(
            """
            SELECT
                COALESCE(SUM(credits_total - credits_used), 0)
                    AS bonus_ai_remaining,
                MIN(expires_at) AS bonus_ai_expires_at
            FROM miniapp_ai_credit_grants
            WHERE telegram_user_id = %s
              AND expires_at > NOW()
              AND credits_used < credits_total;
            """,
            (telegram_user_id,),
        )
        row = active_cursor.fetchone() or {}
        return {
            "bonus_ai_remaining": int(row.get("bonus_ai_remaining") or 0),
            "bonus_ai_expires_at": row.get("bonus_ai_expires_at"),
        }

    if cursor is not None:
        return execute_lookup(cursor)

    database_url = get_database_url()
    if not database_url:
        return {"bonus_ai_remaining": 0, "bonus_ai_expires_at": None}

    ensure_miniapp_ai_credit_grants_table()
    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as active_cursor:
            return execute_lookup(active_cursor)
    except Exception:
        logger.exception(
            "Failed to get active bonus AI credits: user_id=%s",
            telegram_user_id,
        )
        return {"bonus_ai_remaining": 0, "bonus_ai_expires_at": None}
    finally:
        if connection is not None:
            connection.close()


def get_active_bonus_ai_credits(telegram_user_id: int, cursor=None) -> int:
    return int(
        get_active_bonus_ai_credit_info(
            telegram_user_id,
            cursor,
        ).get("bonus_ai_remaining")
        or 0
    )


def consume_bonus_ai_credit(telegram_user_id: int, cursor) -> bool:
    cursor.execute(
        """
        SELECT id
        FROM miniapp_ai_credit_grants
        WHERE telegram_user_id = %s
          AND expires_at > NOW()
          AND credits_used < credits_total
        ORDER BY expires_at ASC, created_at ASC
        LIMIT 1
        FOR UPDATE;
        """,
        (telegram_user_id,),
    )
    grant = cursor.fetchone()
    if not grant:
        return False

    cursor.execute(
        """
        UPDATE miniapp_ai_credit_grants
        SET credits_used = credits_used + 1,
            updated_at = NOW()
        WHERE id = %s
          AND credits_used < credits_total
        RETURNING id;
        """,
        (grant["id"],),
    )
    return bool(cursor.fetchone())


def can_use_ai_analysis(telegram_user_id: int) -> tuple[bool, str, dict]:
    subscription = get_or_create_subscription(telegram_user_id)
    if get_active_bonus_ai_credits(telegram_user_id) > 0:
        return True, "", subscription

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


def parse_miniapp_ref_param(value: str | None) -> int | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    if raw_value.startswith("ref_"):
        raw_value = raw_value[4:]

    if not raw_value.isdigit():
        return None

    referrer_id = int(raw_value)
    return referrer_id if referrer_id > 0 else None


def miniapp_user_exists(telegram_user_id: int) -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM user_events
                    WHERE telegram_user_id = %s
                      AND event_type = 'miniapp_opened'
                );
                """,
                (telegram_user_id,),
            )
            return bool(cursor.fetchone()[0])
    except Exception:
        logger.warning(
            "Mini App user existence check failed: user_id=%s",
            telegram_user_id,
            exc_info=True,
        )
        return False
    finally:
        if connection is not None:
            connection.close()


def extend_miniapp_premium_with_cursor(
    cursor,
    telegram_user_id: int,
    days: int,
) -> dict:
    usage_period = get_current_usage_period()
    now_utc = get_now_utc_naive()
    cursor.execute(
        """
        SELECT *
        FROM subscriptions
        WHERE telegram_user_id = %s
        FOR UPDATE;
        """,
        (telegram_user_id,),
    )
    current_subscription = normalize_subscription_row(
        cursor.fetchone(),
        telegram_user_id,
    )
    current_until = current_subscription.get("premium_until")
    if isinstance(current_until, datetime):
        if current_until.tzinfo is not None:
            current_until = current_until.astimezone(timezone.utc).replace(tzinfo=None)
        base_date = max(now_utc, current_until)
    else:
        base_date = now_utc

    premium_until = base_date + timedelta(days=days)
    ai_limit = max(
        int(current_subscription.get("ai_limit_monthly") or 0),
        PREMIUM_30_AI_LIMIT,
    )
    ai_used_monthly = (
        0
        if current_subscription.get("usage_period") != usage_period
        else int(current_subscription.get("ai_used_monthly") or 0)
    )
    extra_ai_credits = int(current_subscription.get("extra_ai_credits") or 0)

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
            ai_limit_monthly = GREATEST(
                subscriptions.ai_limit_monthly,
                EXCLUDED.ai_limit_monthly
            ),
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
            extra_ai_credits,
        ),
    )
    return normalize_subscription_row(cursor.fetchone(), telegram_user_id)


def extend_miniapp_premium(telegram_user_id: int, days: int) -> datetime | None:
    database_url = get_database_url()
    if not database_url:
        return None

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            subscription = extend_miniapp_premium_with_cursor(
                cursor,
                telegram_user_id,
                days,
            )
        connection.commit()
        return subscription.get("premium_until")
    except Exception:
        logger.exception(
            "Failed to extend Mini App premium: user_id=%s days=%s",
            telegram_user_id,
            days,
        )
        return None
    finally:
        if connection is not None:
            connection.close()


def record_miniapp_referral(
    referrer_id: int,
    referred_id: int,
    is_new_user: bool = True,
) -> dict:
    if referrer_id == referred_id:
        logger.info(
            "miniapp referral skipped: self_referral referrer_id=%s referred_id=%s",
            referrer_id,
            referred_id,
        )
        return {"ok": False, "status": "self_referral"}

    if not is_new_user:
        logger.info(
            "miniapp referral skipped: existing_user referrer_id=%s referred_id=%s",
            referrer_id,
            referred_id,
        )
        return {"ok": False, "status": "existing_user"}

    database_url = get_database_url()
    if not database_url:
        return {"ok": False, "status": "database_unavailable"}

    ensure_miniapp_referrals_table()
    ensure_miniapp_referral_rewards_table()
    ensure_miniapp_ai_credit_grants_table()
    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO miniapp_referrals (
                    referrer_telegram_user_id,
                    referred_telegram_user_id
                )
                VALUES (%s, %s)
                ON CONFLICT (referred_telegram_user_id) DO NOTHING
                RETURNING id;
                """,
                (referrer_id, referred_id),
            )
            inserted_referral = cursor.fetchone()
            if not inserted_referral:
                logger.info(
                    "miniapp referral skipped: already_referred "
                    "referrer_id=%s referred_id=%s",
                    referrer_id,
                    referred_id,
                )
                connection.commit()
                return {"ok": False, "status": "already_referred"}

            logger.info(
                "miniapp referral recorded referrer_id=%s referred_id=%s",
                referrer_id,
                referred_id,
            )
            cursor.execute(
                """
                SELECT COUNT(*) AS invited_count
                FROM miniapp_referrals
                WHERE referrer_telegram_user_id = %s;
                """,
                (referrer_id,),
            )
            invited_count = int((cursor.fetchone() or {}).get("invited_count") or 0)
            logger.info(
                "miniapp referral count updated referrer_id=%s invited_count=%s",
                referrer_id,
                invited_count,
            )

            result = {
                "ok": True,
                "status": "recorded",
                "invited_count": invited_count,
                "reward_granted": False,
            }
            if invited_count < MINIAPP_REFERRAL_TARGET_COUNT:
                connection.commit()
                return result

            cursor.execute(
                """
                INSERT INTO miniapp_referral_rewards (
                    telegram_user_id,
                    reward_type,
                    reward_value
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_user_id, reward_type) DO NOTHING
                RETURNING id;
                """,
                (
                    referrer_id,
                    MINIAPP_REFERRAL_REWARD_TYPE,
                    MINIAPP_REFERRAL_REWARD_AI_LIMIT,
                ),
            )
            inserted_reward = cursor.fetchone()
            if not inserted_reward:
                logger.info(
                    "miniapp referral reward already granted referrer_id=%s "
                    "reward_type=%s",
                    referrer_id,
                    MINIAPP_REFERRAL_REWARD_TYPE,
                )
                connection.commit()
                return {
                    **result,
                    "status": "reward_already_granted",
                }

            cursor.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE telegram_user_id = %s
                FOR UPDATE;
                """,
                (referrer_id,),
            )
            current_subscription = normalize_subscription_row(
                cursor.fetchone(),
                referrer_id,
            )
            credit_grant = grant_bonus_ai_credits(
                referrer_id,
                source_type="referral",
                source_key="invite_3_ai_25",
                credits=MINIAPP_REFERRAL_REWARD_AI_LIMIT,
                days_valid=30,
                cursor=cursor,
            )
            cursor.execute(
                """
                UPDATE miniapp_referrals
                SET reward_granted_at = NOW()
                WHERE referrer_telegram_user_id = %s
                  AND reward_granted_at IS NULL;
                """,
                (referrer_id,),
            )
            logger.info(
                "miniapp referral reward granted referrer_id=%s reward_type=%s",
                referrer_id,
                MINIAPP_REFERRAL_REWARD_TYPE,
            )
            connection.commit()
            return {
                **result,
                "status": "reward_granted",
                "reward_granted": True,
                "reward_value": MINIAPP_REFERRAL_REWARD_AI_LIMIT,
                "bonus_ai_granted": credit_grant.get("granted"),
                "bonus_ai_expires_at": (
                    (credit_grant.get("grant") or {}).get("expires_at")
                ),
                "premium_until": current_subscription.get("premium_until"),
            }
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception(
            "Mini App referral recording failed: referrer_id=%s referred_id=%s",
            referrer_id,
            referred_id,
        )
        return {"ok": False, "status": "failed"}
    finally:
        if connection is not None:
            connection.close()


def get_miniapp_referral_status(telegram_user_id: int) -> dict:
    ensure_miniapp_referrals_table()
    ensure_miniapp_referral_rewards_table()
    ensure_miniapp_ai_credit_grants_table()
    database_url = get_database_url()
    invited_count = 0
    reward_granted = False

    if database_url:
        connection = None
        try:
            connection = psycopg2.connect(database_url)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS invited_count
                    FROM miniapp_referrals
                    WHERE referrer_telegram_user_id = %s;
                    """,
                    (telegram_user_id,),
                )
                invited_count = int(
                    (cursor.fetchone() or {}).get("invited_count") or 0
                )
                cursor.execute(
                    """
                    SELECT 1
                    FROM miniapp_referral_rewards
                    WHERE telegram_user_id = %s
                      AND reward_type = %s
                    LIMIT 1;
                    """,
                    (telegram_user_id, MINIAPP_REFERRAL_REWARD_TYPE),
                )
                reward_granted = bool(cursor.fetchone())
        except Exception:
            logger.exception(
                "Mini App referral status failed: user_id=%s",
                telegram_user_id,
            )
        finally:
            if connection is not None:
                connection.close()

    subscription = get_or_create_subscription(telegram_user_id)
    bonus_info = get_active_bonus_ai_credit_info(telegram_user_id)
    return {
        "ok": True,
        "referral_code": f"ref_{telegram_user_id}",
        "referral_link": (
            "https://t.me/Match_Stat_bot/app"
            f"?startapp=ref_{telegram_user_id}"
        ),
        "invited_count": invited_count,
        "target_count": MINIAPP_REFERRAL_TARGET_COUNT,
        "reward_value": MINIAPP_REFERRAL_REWARD_AI_LIMIT,
        "reward_type": MINIAPP_REFERRAL_REWARD_TYPE,
        "reward_granted": reward_granted,
        "bonus_ai_remaining": bonus_info.get("bonus_ai_remaining") or 0,
        "bonus_ai_expires_at": serialize_api_datetime(
            bonus_info.get("bonus_ai_expires_at")
        ),
        "is_premium": is_premium_active(subscription),
        "premium_until": serialize_api_datetime(
            subscription.get("premium_until")
        ),
    }


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


def normalize_ai_analysis_match_id(match_id) -> str:
    normalized_match_id = str(match_id or "").strip()
    if ":" in normalized_match_id:
        source_name, source_match_id = normalized_match_id.rsplit(":", 1)
        if (
            source_match_id.strip()
            and source_name.strip().lower().replace("_", "-")
            in {"api-football", "apifootball"}
        ):
            normalized_match_id = source_match_id.strip()
    return normalized_match_id


def get_saved_miniapp_ai_analysis(
    telegram_user_id: int,
    match_id: str,
    analysis_mode: str = "default",
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
                SELECT *
                FROM miniapp_match_ai_analyses
                WHERE telegram_user_id = %s
                AND match_id = %s
                AND analysis_mode = %s;
                """,
                (telegram_user_id, match_id, analysis_mode),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        logger.exception(
            "Failed to load saved Mini App AI analysis: "
            "user_id=%s match_id=%s analysis_mode=%s",
            telegram_user_id,
            match_id,
            analysis_mode,
        )
        raise
    finally:
        if connection is not None:
            connection.close()


def verify_miniapp_ai_personal_save(
    telegram_user_id: int,
    match_id: str,
    analysis_mode: str,
) -> bool:
    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    try:
        found = bool(
            get_saved_miniapp_ai_analysis(
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
        )
    except Exception:
        logger.warning(
            "personal save verify failed: user_id=%s normalized_match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
            exc_info=True,
        )
        return False

    logger.info(
        "personal save verify: user_id=%s normalized_match_id=%s "
        "analysis_mode=%s found=%s",
        telegram_user_id,
        normalized_match_id,
        analysis_mode,
        found,
    )
    return found


def lookup_saved_miniapp_ai_analysis(
    telegram_user_id: int,
    raw_match_id: str,
    analysis_mode: str = "default",
) -> tuple[dict | None, str]:
    normalized_match_id = normalize_ai_analysis_match_id(raw_match_id)
    saved_analysis = get_saved_miniapp_ai_analysis(
        telegram_user_id,
        normalized_match_id,
        analysis_mode,
    )
    if saved_analysis or raw_match_id == normalized_match_id:
        logger.info(
            "personal AI lookup: user_id=%s raw_match_id=%s "
            "normalized_match_id=%s analysis_mode=%s found=%s",
            telegram_user_id,
            raw_match_id,
            normalized_match_id,
            analysis_mode,
            bool(saved_analysis),
        )
        return saved_analysis, normalized_match_id

    saved_analysis = get_saved_miniapp_ai_analysis(
        telegram_user_id,
        raw_match_id,
        analysis_mode,
    )
    logger.info(
        "personal AI fallback lookup: user_id=%s raw_match_id=%s "
        "normalized_match_id=%s analysis_mode=%s found=%s",
        telegram_user_id,
        raw_match_id,
        normalized_match_id,
        analysis_mode,
        bool(saved_analysis),
    )
    return saved_analysis, normalized_match_id


def get_global_miniapp_ai_analysis(
    match_id: str,
    analysis_mode: str = "default",
) -> dict | None:
    database_url = get_database_url()
    if not database_url:
        return None

    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    if not normalized_match_id:
        return None

    for attempt in range(2):
        connection = None
        try:
            connection = psycopg2.connect(database_url)
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM miniapp_match_ai_global_analyses
                    WHERE match_id = %s
                    AND analysis_mode = %s;
                    """,
                    (normalized_match_id, analysis_mode),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except psycopg2.errors.UndefinedTable:
            logger.warning(
                "Mini App AI global cache table missing during lookup: "
                "match_id=%s analysis_mode=%s attempt=%s",
                normalized_match_id,
                analysis_mode,
                attempt + 1,
            )
            if connection is not None:
                connection.rollback()
            if attempt == 0 and ensure_miniapp_ai_global_cache_table():
                continue
            return None
        except Exception:
            logger.warning(
                "Failed to load global Mini App AI analysis, skipping cache: "
                "match_id=%s analysis_mode=%s",
                normalized_match_id,
                analysis_mode,
                exc_info=True,
            )
            return None
        finally:
            if connection is not None:
                connection.close()
    return None


def save_global_miniapp_ai_analysis(
    match_id: str,
    analysis: str,
    structured: dict | None,
    analysis_mode: str,
    home_team: str,
    away_team: str,
    league: str,
) -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    if not normalized_match_id:
        logger.warning("Skipped global Mini App AI save with empty match_id")
        return False
    logger.info(
        "global AI save started: raw_match_id=%s normalized_match_id=%s "
        "analysis_mode=%s",
        match_id,
        normalized_match_id,
        analysis_mode,
    )

    for attempt in range(2):
        connection = None
        try:
            connection = psycopg2.connect(database_url)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO miniapp_match_ai_global_analyses (
                        match_id,
                        analysis_mode,
                        analysis,
                        structured,
                        home_team,
                        away_team,
                        league,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (match_id, analysis_mode)
                    DO UPDATE SET
                        analysis = EXCLUDED.analysis,
                        structured = EXCLUDED.structured,
                        home_team = EXCLUDED.home_team,
                        away_team = EXCLUDED.away_team,
                        league = EXCLUDED.league,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        normalized_match_id,
                        analysis_mode,
                        analysis,
                        Json(structured) if structured is not None else None,
                        home_team,
                        away_team,
                        league,
                    ),
                )
            connection.commit()
            return True
        except psycopg2.errors.UndefinedTable:
            logger.warning(
                "Mini App AI global cache table missing during save: "
                "match_id=%s analysis_mode=%s attempt=%s",
                normalized_match_id,
                analysis_mode,
                attempt + 1,
            )
            if connection is not None:
                connection.rollback()
            if attempt == 0 and ensure_miniapp_ai_global_cache_table():
                continue
            return False
        except Exception:
            logger.warning(
                "Failed to save global Mini App AI analysis: "
                "match_id=%s analysis_mode=%s",
                normalized_match_id,
                analysis_mode,
                exc_info=True,
            )
            return False
        finally:
            if connection is not None:
                connection.close()
    return False


def verify_miniapp_ai_global_save(match_id: str, analysis_mode: str) -> bool:
    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    found = bool(get_global_miniapp_ai_analysis(normalized_match_id, analysis_mode))
    logger.info(
        "global save verify: normalized_match_id=%s analysis_mode=%s found=%s",
        normalized_match_id,
        analysis_mode,
        found,
    )
    return found


def get_ai_free_refreshes_left(
    saved_analysis: dict | None,
    is_admin: bool = False,
) -> int | None:
    if is_admin:
        return None
    refresh_count = int((saved_analysis or {}).get("refresh_count") or 0)
    return max(0, MINIAPP_AI_FREE_REFRESH_TOTAL - refresh_count)


def build_miniapp_ai_saved_response(
    saved_analysis: dict,
    match_id: str,
    remaining_ai: int | None,
    is_admin: bool,
    *,
    limit_charged: bool = False,
    cached: bool = True,
    regenerated: bool = False,
    from_personal_cache: bool = False,
    from_global_cache: bool = False,
    source: str | None = None,
) -> dict:
    refresh_count = int(saved_analysis.get("refresh_count") or 0)
    free_refreshes_left = get_ai_free_refreshes_left(saved_analysis, is_admin)
    return {
        "ok": True,
        "match_id": match_id,
        "home": saved_analysis.get("home_team") or "",
        "away": saved_analysis.get("away_team") or "",
        "analysis": saved_analysis.get("analysis") or "",
        "structured": saved_analysis.get("structured"),
        "analysis_mode": saved_analysis.get("analysis_mode") or "default",
        "limit_charged": limit_charged,
        "charged": limit_charged,
        "unlocked": True,
        "source": source
        or (
            "global_cache"
            if from_global_cache
            else "user_unlock"
            if from_personal_cache
            else "openai"
            if regenerated
            else "user_unlock"
        ),
        "remaining_ai": remaining_ai,
        "is_admin": is_admin,
        "cached": cached,
        "regenerated": regenerated,
        "refresh_count": refresh_count,
        "free_refreshes_total": MINIAPP_AI_FREE_REFRESH_TOTAL,
        "free_refreshes_left": free_refreshes_left,
        "from_personal_cache": from_personal_cache,
        "from_global_cache": from_global_cache,
        "created_at": serialize_api_datetime(saved_analysis.get("created_at")),
        "updated_at": serialize_api_datetime(saved_analysis.get("updated_at")),
    }


def is_saveable_miniapp_ai_analysis(analysis: str, structured: dict | None) -> bool:
    normalized_analysis = str(analysis or "").strip()
    if not normalized_analysis:
        return False
    if normalized_analysis in {
        "AI-разбор пока не подключён.",
        "AI-разбор временно недоступен.",
    }:
        return False
    if normalized_analysis.startswith(
        "AI-разбор временно недоступен в красивом формате."
    ):
        return False
    return structured is not None or len(normalized_analysis) > 80


def save_miniapp_ai_analysis_with_cursor(
    cursor,
    telegram_user_id: int,
    match_id: str,
    analysis: str,
    structured: dict | None,
    analysis_mode: str,
    home_team: str,
    away_team: str,
    league: str,
    refresh_count: int = 0,
    increment_refresh_count: bool = False,
) -> None:
    cursor.execute(
        """
        INSERT INTO miniapp_match_ai_analyses (
            telegram_user_id,
            match_id,
            analysis,
            structured,
            analysis_mode,
            refresh_count,
            home_team,
            away_team,
            league,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (telegram_user_id, match_id, analysis_mode)
        DO UPDATE SET
            analysis = EXCLUDED.analysis,
            structured = EXCLUDED.structured,
            refresh_count = CASE
                WHEN %s THEN
                    miniapp_match_ai_analyses.refresh_count + 1
                ELSE EXCLUDED.refresh_count
            END,
            home_team = EXCLUDED.home_team,
            away_team = EXCLUDED.away_team,
            league = EXCLUDED.league,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (
            telegram_user_id,
            match_id,
            analysis,
            Json(structured) if structured is not None else None,
            analysis_mode,
            refresh_count,
            home_team,
            away_team,
            league,
            increment_refresh_count,
        ),
    )


def save_miniapp_ai_analysis(
    telegram_user_id: int,
    match_id: str,
    analysis: str,
    structured: dict | None,
    analysis_mode: str,
    home_team: str,
    away_team: str,
    league: str,
    refresh_count: int = 0,
    increment_refresh_count: bool = False,
) -> bool:
    database_url = get_database_url()
    if not database_url:
        return False

    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    if not normalized_match_id:
        logger.warning(
            "Skipped Mini App AI analysis save with empty match_id: user_id=%s",
            telegram_user_id,
        )
        return False
    logger.info(
        "personal AI save started: user_id=%s raw_match_id=%s "
        "normalized_match_id=%s analysis_mode=%s increment_refresh_count=%s",
        telegram_user_id,
        match_id,
        normalized_match_id,
        analysis_mode,
        increment_refresh_count,
    )

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            save_miniapp_ai_analysis_with_cursor(
                cursor,
                telegram_user_id,
                normalized_match_id,
                analysis,
                structured,
                analysis_mode,
                home_team,
                away_team,
                league,
                refresh_count,
                increment_refresh_count,
            )
        connection.commit()
        return True
    except Exception:
        logger.warning(
            "Failed to save Mini App AI analysis: user_id=%s match_id=%s",
            telegram_user_id,
            normalized_match_id,
            exc_info=True,
        )
        return False
    finally:
        if connection is not None:
            connection.close()


def save_miniapp_ai_analysis_and_charge(
    telegram_user_id: int,
    match_id: str,
    analysis: str,
    structured: dict | None,
    analysis_mode: str,
    home_team: str,
    away_team: str,
    league: str,
    source: str,
) -> tuple[bool, dict | None, bool, str]:
    database_url = get_database_url()
    if not database_url:
        return False, None, False, "database_unavailable"

    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    if not normalized_match_id:
        return False, None, False, "invalid_match_id"

    logger.info(
        "ai unlock atomic charge started: user_id=%s match_id=%s "
        "analysis_mode=%s source=%s",
        telegram_user_id,
        normalized_match_id,
        analysis_mode,
        source,
    )
    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0));",
                (
                    "miniapp_ai_unlock:"
                    f"{telegram_user_id}:{normalized_match_id}:{analysis_mode}",
                ),
            )
            cursor.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE telegram_user_id = %s
                FOR UPDATE;
                """,
                (telegram_user_id,),
            )
            subscription = normalize_subscription_row(
                cursor.fetchone(),
                telegram_user_id,
            )
            cursor.execute(
                """
                SELECT id
                FROM miniapp_match_ai_analyses
                WHERE telegram_user_id = %s
                  AND match_id = %s
                  AND analysis_mode = %s
                LIMIT 1;
                """,
                (telegram_user_id, normalized_match_id, analysis_mode),
            )
            if cursor.fetchone():
                connection.rollback()
                logger.info(
                    "ai unlock atomic charge skipped already_unlocked: "
                    "user_id=%s match_id=%s analysis_mode=%s source=%s",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                return True, subscription, False, "already_unlocked"

            bonus_remaining = get_active_bonus_ai_credits(
                telegram_user_id,
                cursor,
            )
            premium_active = is_premium_active(subscription)
            monthly_remaining = max(
                0,
                int(subscription.get("ai_limit_monthly") or 0)
                - int(subscription.get("ai_used_monthly") or 0),
            )
            extra_remaining = int(subscription.get("extra_ai_credits") or 0)
            if analysis_mode == "premium":
                available_before = bonus_remaining + (
                    monthly_remaining if premium_active else 0
                )
            else:
                available_before = monthly_remaining + extra_remaining
            if available_before <= 0:
                error_code = (
                    "premium_required"
                    if analysis_mode == "premium" and not premium_active
                    else "ai_limit_exceeded"
                )
                logger.info(
                    "ai unlock atomic charge %s: user_id=%s match_id=%s "
                    "analysis_mode=%s source=%s",
                    error_code,
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                connection.rollback()
                logger.info(
                    "ai unlock atomic charge rollback: user_id=%s match_id=%s "
                    "analysis_mode=%s source=%s reason=limit_exceeded",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                return False, subscription, False, error_code

            bonus_consumed = False
            if analysis_mode == "premium" and bonus_remaining > 0:
                bonus_consumed = consume_bonus_ai_credit(
                    telegram_user_id,
                    cursor,
                )
                if not bonus_consumed:
                    connection.rollback()
                    logger.info(
                        "ai unlock atomic charge rollback: user_id=%s match_id=%s "
                        "analysis_mode=%s source=%s reason=bonus_charge_failed",
                        telegram_user_id,
                        normalized_match_id,
                        analysis_mode,
                        source,
                    )
                    return False, subscription, False, "ai_limit_exceeded"
                updated_subscription = subscription
            elif analysis_mode == "premium" and not premium_active:
                logger.info(
                    "ai unlock atomic charge premium_required: user_id=%s "
                    "match_id=%s analysis_mode=%s source=%s",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                connection.rollback()
                logger.info(
                    "ai unlock atomic charge rollback: user_id=%s match_id=%s "
                    "analysis_mode=%s source=%s reason=premium_required",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                return False, subscription, False, "premium_required"
            elif analysis_mode == "default" and extra_remaining > 0:
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
                updated_subscription = normalize_subscription_row(
                    cursor.fetchone(),
                    telegram_user_id,
                )
            else:
                cursor.execute(
                    """
                    UPDATE subscriptions
                    SET ai_used_monthly = ai_used_monthly + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                      AND ai_used_monthly < ai_limit_monthly
                    RETURNING *;
                    """,
                    (telegram_user_id,),
                )
                updated_subscription = normalize_subscription_row(
                    cursor.fetchone(),
                    telegram_user_id,
                )

            bonus_after = get_active_bonus_ai_credits(telegram_user_id, cursor)
            if analysis_mode == "premium":
                monthly_after = max(
                    0,
                    int(updated_subscription.get("ai_limit_monthly") or 0)
                    - int(updated_subscription.get("ai_used_monthly") or 0),
                )
                available_after = bonus_after + (
                    monthly_after if premium_active else 0
                )
            else:
                available_after = get_ai_available_count(updated_subscription)
            if available_after >= available_before:
                logger.info(
                    "ai unlock atomic charge limit_exceeded: user_id=%s "
                    "match_id=%s analysis_mode=%s source=%s",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                connection.rollback()
                logger.info(
                    "ai unlock atomic charge rollback: user_id=%s match_id=%s "
                    "analysis_mode=%s source=%s reason=charge_failed",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    source,
                )
                return False, subscription, False, "ai_limit_exceeded"

            save_miniapp_ai_analysis_with_cursor(
                cursor,
                telegram_user_id,
                normalized_match_id,
                analysis,
                structured,
                analysis_mode,
                home_team,
                away_team,
                league,
                refresh_count=0,
            )
        connection.commit()
        logger.info(
            "ai unlock atomic charge success: user_id=%s match_id=%s "
            "analysis_mode=%s source=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
            source,
        )
        return True, updated_subscription, True, ""
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.warning(
            "ai unlock atomic charge save_failed: user_id=%s match_id=%s "
            "analysis_mode=%s source=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
            source,
            exc_info=True,
        )
        logger.info(
            "ai unlock atomic charge rollback: user_id=%s match_id=%s "
            "analysis_mode=%s source=%s reason=exception",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
            source,
        )
        return False, None, False, "save_failed"
    finally:
        if connection is not None:
            connection.close()


CHANNEL_FORBIDDEN_WORDS = (
    "ставка",
    "ставки",
    "поставить",
    "ставить",
    "ставь",
    "прогноз на ставку",
    "экспресс",
    "ординар",
    "купон",
    "коэффициент",
    "кэф",
    "БК",
    "букмекер",
    "букмекерская",
    "беттинг",
    "betting",
    "валуй",
    "value bet",
    "проходимость",
    "железно",
    "жб",
    "гарантия",
    "100%",
    "точный прогноз",
    "верняк",
    "банк",
    "флет",
    "догон",
    "выигрыш",
    "заработок",
    "доход",
    "поднять денег",
    "фрибет",
    "депозит",
    "вывод",
    "казино",
    "тб",
    "тм",
    "оз",
    "обз",
    "итб",
    "итм",
    "фора",
    "тотал",
    "тотал больше",
    "тотал меньше",
)


CHANNEL_FORBIDDEN_REPLACEMENTS = {
    "ставка": "AI-разбор",
    "ставки": "AI-разборы",
    "поставить": "выбрать направление",
    "ставить": "смотреть данные",
    "ставь": "смотри данные",
    "прогноз на ставку": "AI-оценка",
    "экспресс": "сценарий",
    "ординар": "сценарий",
    "купон": "сценарий",
    "коэффициент": "вероятность",
    "кэф": "вероятность",
    "БК": "аналитика",
    "букмекер": "аналитика",
    "букмекерская": "аналитическая",
    "беттинг": "аналитика",
    "betting": "football analytics",
    "валуй": "статистический сигнал",
    "value bet": "статистический сигнал",
    "проходимость": "устойчивость сценария",
    "железно": "сильный сигнал",
    "жб": "сильный сигнал",
    "гарантия": "оценка",
    "100%": "высокая вероятность",
    "точный прогноз": "AI-оценка",
    "верняк": "сильный сценарий",
    "банк": "профиль",
    "флет": "ровный подход",
    "догон": "повторная оценка",
    "выигрыш": "результат",
    "заработок": "результат",
    "доход": "результат",
    "поднять денег": "получить результат",
    "фрибет": "дополнительный материал",
    "депозит": "доступ",
    "вывод": "итог",
    "казино": "игра",
    "тотал больше": "сценарий с голами",
    "тотал меньше": "сдержанный темп",
    "тотал": "сценарий по голам",
    "фора": "игровое преимущество",
    "ТБ": "результативный сценарий",
    "ТМ": "осторожный сценарий",
    "ОБЗ": "голы с обеих сторон",
    "ОЗ": "обе команды могут забить",
    "ИТБ": "высокая индивидуальная активность команды",
    "ИТМ": "сдержанная индивидуальная активность команды",
}


CHANNEL_STANDALONE_FORBIDDEN_TERMS = (
    "тб",
    "тм",
    "оз",
    "обз",
    "итб",
    "итм",
)


def build_channel_forbidden_pattern(term: str) -> re.Pattern:
    escaped_term = re.escape(str(term or ""))
    if term.casefold() in CHANNEL_STANDALONE_FORBIDDEN_TERMS:
        return re.compile(rf"(?<!\w){escaped_term}(?!\w)", re.IGNORECASE)
    return re.compile(escaped_term, re.IGNORECASE)


def sanitize_channel_post_text(text: str) -> str:
    sanitized = str(text or "")
    for forbidden, replacement in CHANNEL_FORBIDDEN_REPLACEMENTS.items():
        pattern = build_channel_forbidden_pattern(forbidden)
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized.strip()


def channel_text_has_forbidden_words(text: str) -> bool:
    checked_text = str(text or "")
    return any(
        build_channel_forbidden_pattern(word).search(checked_text)
        for word in CHANNEL_FORBIDDEN_WORDS
    )


TEAM_NAME_RU_OVERRIDES = {
    "South Africa": "ЮАР",
    "Canada": "Канада",
    "Brazil": "Бразилия",
    "Japan": "Япония",
    "Germany": "Германия",
    "Paraguay": "Парагвай",
    "Netherlands": "Нидерланды",
    "Morocco": "Марокко",
    "Ivory Coast": "Кот-д'Ивуар",
    "Norway": "Норвегия",
    "France": "Франция",
    "Sweden": "Швеция",
    "Mexico": "Мексика",
    "Ecuador": "Эквадор",
    "England": "Англия",
    "DR Congo": "ДР Конго",
    "Belgium": "Бельгия",
    "Senegal": "Сенегал",
    "United States": "США",
    "USA": "США",
    "Bosnia and Herzegovina": "Босния и Герцеговина",
    "Spain": "Испания",
    "Austria": "Австрия",
    "Portugal": "Португалия",
    "Croatia": "Хорватия",
    "Switzerland": "Швейцария",
    "Algeria": "Алжир",
    "Australia": "Австралия",
    "Egypt": "Египет",
    "Argentina": "Аргентина",
    "Cape Verde": "Кабо-Верде",
    "Colombia": "Колумбия",
    "Ghana": "Гана",
    "RSA": "ЮАР",
    "CAN": "Канада",
    "BRA": "Бразилия",
    "JPN": "Япония",
    "GER": "Германия",
    "PAR": "Парагвай",
    "NED": "Нидерланды",
    "MAR": "Марокко",
    "CIV": "Кот-д'Ивуар",
    "NOR": "Норвегия",
    "FRA": "Франция",
    "SWE": "Швеция",
    "MEX": "Мексика",
    "ECU": "Эквадор",
    "ENG": "Англия",
    "COD": "ДР Конго",
    "BEL": "Бельгия",
    "SEN": "Сенегал",
    "BIH": "Босния и Герцеговина",
    "ESP": "Испания",
    "AUT": "Австрия",
    "POR": "Португалия",
    "CRO": "Хорватия",
    "SUI": "Швейцария",
    "DZA": "Алжир",
    "AUS": "Австралия",
    "EGY": "Египет",
    "ARG": "Аргентина",
    "CPV": "Кабо-Верде",
    "COL": "Колумбия",
    "GHA": "Гана",
}


TEAM_NAME_RU_OVERRIDES_CASEFOLD = {
    key.casefold(): value for key, value in TEAM_NAME_RU_OVERRIDES.items()
}


def translate_team_name_ru(name: str | None) -> str:
    team_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not team_name:
        return ""
    if team_name in TEAM_NAME_RU_OVERRIDES:
        return TEAM_NAME_RU_OVERRIDES[team_name]
    return TEAM_NAME_RU_OVERRIDES_CASEFOLD.get(team_name.casefold(), team_name)


def parse_match_kickoff_datetime(match: dict) -> datetime | None:
    kickoff = match.get("kickoff")
    if not kickoff:
        return None
    try:
        parsed = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def format_channel_match_time(match: dict) -> str:
    kickoff = parse_match_kickoff_datetime(match)
    if not kickoff:
        return "время не указано"
    return kickoff.strftime("%d.%m %H:%M")


def is_channel_match_not_started(match: dict) -> bool:
    status = str(match.get("status") or "").strip().upper()
    if status in MINIAPP_FINISHED_STATUSES or status in MINIAPP_LIVE_STATUSES:
        return False
    kickoff = parse_match_kickoff_datetime(match)
    return kickoff is None or kickoff > datetime.now(ALMATY_TZ)


def is_channel_match_finished(match: dict) -> bool:
    status = str(match.get("status") or "").strip().upper()
    return status in MINIAPP_FINISHED_STATUSES


def format_channel_match_score(match: dict) -> str:
    score = match.get("score") or {}
    home_score = score.get("home")
    away_score = score.get("away")
    if home_score is None or away_score is None:
        return "счёт не указан"
    return f"{home_score}:{away_score}"


def get_channel_match_priority(match: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    league_id = match.get("league_id")
    league_name = str(match.get("league") or "")
    country = str(match.get("country") or "")
    kickoff = parse_match_kickoff_datetime(match)

    if is_channel_match_not_started(match):
        score += 30
        reasons.append("матч ещё не начался")
    if kickoff:
        days_until = (kickoff.date() - datetime.now(ALMATY_TZ).date()).days
        if days_until in (0, 1):
            score += 25
            reasons.append("подходит по времени: сегодня/завтра")
    if league_id in TOP_LEAGUE_IDS:
        score += 24
        reasons.append("топ-турнир MatchLab")
    if any(
        keyword in f"{league_name} {country}".lower()
        for keyword in (
            "world cup",
            "champions",
            "europa",
            "conference",
            "nations",
            "international",
            "world",
            "euro",
            "cup",
        )
    ):
        score += 18
        reasons.append("международный или кубковый контекст")
    if league_name:
        score += 8
        reasons.append("есть турнир и контекст")
    if match.get("home_id") and match.get("away_id"):
        score += 8
        reasons.append("есть данные команд для AI-разбора")
    if match.get("home_logo") and match.get("away_logo"):
        score += 4
    if not reasons:
        reasons.append("матч может быть интересен для контента")

    return score, reasons[:3]


def get_channel_recap_match_priority(match: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    league_id = match.get("league_id")
    league_name = str(match.get("league") or "")
    match_score = match.get("score") or {}

    if league_id in TOP_LEAGUE_IDS:
        score += 24
        reasons.append("топ-турнир MatchLab")
    if match_score.get("home") is not None and match_score.get("away") is not None:
        score += 18
        reasons.append("есть итоговый счёт")
    if match.get("home") and match.get("away") and league_name:
        score += 12
        reasons.append("есть команды и турнир")
    if match.get("_channel_cache_available"):
        score += 35
        reasons.append("есть сохранённый AI-разбор до игры")
    if not reasons:
        reasons.append("завершённый матч подходит для итогов")
    return score, reasons[:3]


def get_channel_plan_candidates(limit: int = 3) -> list[dict]:
    candidates_by_id = {}
    for match_type in ("top", "today", "tomorrow"):
        try:
            for match in get_miniapp_matches(match_type):
                match_id = str(match.get("id") or "").strip()
                if match_id and match_id not in candidates_by_id:
                    candidates_by_id[match_id] = match
        except Exception:
            logger.warning(
                "channel_plan match list failed: match_type=%s",
                match_type,
                exc_info=True,
            )

    ranked = []
    for match in candidates_by_id.values():
        if not is_channel_match_not_started(match):
            continue
        score, reasons = get_channel_match_priority(match)
        ranked.append((score, parse_match_kickoff_datetime(match) or datetime.max.replace(tzinfo=ALMATY_TZ), reasons, match))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    candidates = []
    for _, _, reasons, match in ranked[:limit]:
        enriched_match = dict(match)
        enriched_match["_channel_reasons"] = reasons
        candidates.append(enriched_match)
    return candidates


def is_known_channel_team(name: str | None) -> bool:
    team_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not team_name:
        return False
    return (
        team_name in TEAM_NAME_RU_OVERRIDES
        or team_name.casefold() in TEAM_NAME_RU_OVERRIDES_CASEFOLD
        or team_name in TEAM_FLAG_EMOJI_OVERRIDES
        or team_name.casefold() in TEAM_FLAG_EMOJI_OVERRIDES_CASEFOLD
        or team_name in TEAM_COLOR_OVERRIDES
        or team_name.casefold() in TEAM_COLOR_OVERRIDES_CASEFOLD
    )


def is_important_channel_league(match: dict) -> bool:
    league_id = match.get("league_id")
    league_name = str(match.get("league") or "")
    country = str(match.get("country") or "")
    league_context = f"{league_name} {country}".casefold()
    important_keywords = (
        "world cup",
        "uefa",
        "champions league",
        "europa league",
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "copa",
        "euro",
        "nations league",
        "world cup qualification",
        "international",
    )
    return league_id in TOP_LEAGUE_IDS or any(
        keyword in league_context for keyword in important_keywords
    )


def score_channel_matchday_candidate(match: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    home = str(match.get("home") or "").strip()
    away = str(match.get("away") or "").strip()
    league_name = str(match.get("league") or "").strip()
    country = str(match.get("country") or "").strip()
    kickoff = parse_match_kickoff_datetime(match)
    now_almaty = datetime.now(ALMATY_TZ)

    home_known = is_known_channel_team(home)
    away_known = is_known_channel_team(away)
    if home_known and away_known:
        score += 25
        reasons.append("известные команды")
    elif home_known or away_known:
        score += 12
        reasons.append("есть узнаваемая команда")

    if is_important_channel_league(match):
        score += 20
        reasons.append("важный турнир")
    elif league_name:
        score += 8
        reasons.append("есть турнирный контекст")

    if kickoff:
        hours_until = (kickoff - now_almaty).total_seconds() / 3600
        if 6 <= hours_until <= 18:
            score += 15
            reasons.append("удобное время для публикации")
        elif 18 < hours_until <= 36:
            score += 10
            reasons.append("подходит по времени")
    else:
        score -= 20
        reasons.append("время начала не указано")

    if home and away and (match.get("home_id") or match.get("away_id")) and league_name:
        score += 15
        reasons.append("есть данные для AI-разбора")
    elif home and away:
        score += 7
        reasons.append("есть базовые данные матча")

    league_context = f"{league_name} {country}".casefold()
    if any(
        keyword in league_context
        for keyword in ("international", "world cup", "euro", "nations")
    ) or (home_known and away_known and country):
        score += 10
        reasons.append("понятный инфоповод")

    if (
        translate_team_name_ru(home) != home
        or translate_team_name_ru(away) != away
        or home_known
        or away_known
    ):
        score += 5

    if "friendly" in league_context or "товарищ" in league_context:
        score -= 30
        reasons.append("товарищеский формат")
    if not home or not away:
        score -= 20
        reasons.append("команды указаны неполно")
    if not league_name:
        score -= 20
        reasons.append("турнир не указан")

    if not reasons:
        reasons.append("выбран как лучший из доступных кандидатов")

    safe_score = max(0, min(100, score))
    return safe_score, reasons[:5]


def select_best_channel_matchday_candidate(
    candidates: list[dict],
) -> tuple[dict | None, list[dict]]:
    ranked = []
    for match in candidates:
        score, reasons = score_channel_matchday_candidate(match)
        enriched_match = dict(match)
        enriched_match["agent_score"] = score
        enriched_match["agent_reasons"] = reasons
        kickoff = parse_match_kickoff_datetime(enriched_match) or datetime.max.replace(
            tzinfo=ALMATY_TZ
        )
        ranked.append((score, kickoff, enriched_match))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    top_matches = [item[2] for item in ranked[:3]]
    best_match = top_matches[0] if top_matches else None
    return best_match, top_matches


def build_channel_agent_selection_message(
    best_match: dict,
    top_matches: list[dict],
) -> str:
    home = translate_team_name_ru(best_match.get("home")) or "Команда 1"
    away = translate_team_name_ru(best_match.get("away")) or "Команда 2"
    score = int(best_match.get("agent_score") or 0)
    reasons = best_match.get("agent_reasons") or [
        "выбран как лучший из доступных кандидатов"
    ]
    lines = [
        "🤖 MatchLab Agent выбрал Матч дня",
        "",
        "Главный выбор:",
        f"{home} — {away}",
        f"Рейтинг: {score}/100",
        "",
        "Почему этот матч:",
    ]
    lines.extend(f"— {reason}" for reason in reasons)
    lines.extend(["", "Топ кандидатов:"])
    for index, match in enumerate(top_matches, start=1):
        match_home = translate_team_name_ru(match.get("home")) or "Команда 1"
        match_away = translate_team_name_ru(match.get("away")) or "Команда 2"
        match_score = int(match.get("agent_score") or 0)
        lines.append(f"{index}. {match_home} — {match_away} — {match_score}/100")
    lines.extend(["", "Ниже готовый Telegram-пост."])
    return "\n".join(lines)


def build_channel_agent_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔎 Показать кандидатов вручную",
                    callback_data="channel_admin_plan_manual",
                )
            ]
        ]
    )


def get_channel_digest_reason(match: dict, index: int) -> str:
    reasons = [
        str(reason).strip()
        for reason in (match.get("agent_reasons") or match.get("_channel_reasons") or [])
        if str(reason).strip()
    ]
    fallback_reasons = [
        "важный турнирный контекст",
        "интересный инфоповод",
        "матч может быть интересен аудитории",
        "удобное время для просмотра",
        "контраст команд и игровых стилей",
    ]
    reason = reasons[0] if reasons else fallback_reasons[index % len(fallback_reasons)]
    reason = sanitize_channel_post_text(reason)
    if channel_text_has_forbidden_words(reason):
        return fallback_reasons[index % len(fallback_reasons)]
    return reason.rstrip(".") + "."


def get_channel_morning_digest_matches(limit: int = 5) -> list[dict]:
    try:
        candidates = get_channel_plan_candidates(10)
    except Exception:
        logger.exception("channel_morning_digest candidate fetch failed")
        return []

    ranked = []
    for match in candidates:
        score, reasons = score_channel_matchday_candidate(match)
        enriched_match = dict(match)
        enriched_match["agent_score"] = score
        enriched_match["agent_reasons"] = reasons
        kickoff = parse_match_kickoff_datetime(enriched_match) or datetime.max.replace(
            tzinfo=ALMATY_TZ
        )
        ranked.append((score, kickoff, enriched_match))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def get_channel_morning_recap_window() -> tuple[datetime, datetime]:
    yesterday = (datetime.now(ALMATY_TZ) - timedelta(days=1)).date()
    return (
        datetime.combine(yesterday, datetime.min.time(), tzinfo=ALMATY_TZ),
        datetime.combine(yesterday, datetime.max.time(), tzinfo=ALMATY_TZ),
    )


def score_channel_morning_recap_match(match: dict) -> int:
    score = 0
    league_context = (
        f"{match.get('league') or ''} {match.get('country') or ''} "
        f"{match.get('round') or ''}"
    ).casefold()
    home = str(match.get("home") or "")
    away = str(match.get("away") or "")
    if any(
        keyword in league_context
        for keyword in ("world cup", "champions league", "euro", "nations", "cup")
    ):
        score += 35
    if any(
        keyword in league_context
        for keyword in ("final", "semi", "quarter", "round", "playoff", "knockout")
    ):
        score += 20
    if translate_team_name_ru(home) != home or translate_team_name_ru(away) != away:
        score += 12
    if home.casefold() == "england" or away.casefold() == "england":
        score += 18
    score_data = match.get("score") or {}
    home_score = score_data.get("home")
    away_score = score_data.get("away")
    if isinstance(home_score, int) and isinstance(away_score, int):
        score += 10 + min(abs(home_score - away_score), 3) * 3
    kickoff = parse_match_kickoff_datetime(match)
    if kickoff:
        score += max(0, 10 - abs((datetime.now(ALMATY_TZ) - kickoff).total_seconds()) // 7200)
    return int(score)


def get_channel_morning_recap_matches(limit: int = 6) -> list[dict]:
    logger.info("channel_morning_recap matches fetch started")
    start_almaty, end_almaty = get_channel_morning_recap_window()

    def load_finished_between(start_value: datetime, end_value: datetime) -> list[dict]:
        fixtures = get_api_football_matches_between(
            start_value,
            end_value,
            only_top=False,
            allowed_only=True,
        )
        loaded_matches = []
        for fixture_item in fixtures:
            formatted_item = format_miniapp_fixture_item(fixture_item)
            if not formatted_item or not is_channel_match_finished(formatted_item):
                continue
            score = formatted_item.get("score") or {}
            if score.get("home") is None or score.get("away") is None:
                continue
            loaded_matches.append(formatted_item)
        return loaded_matches

    matches = load_finished_between(start_almaty, end_almaty)
    if not matches:
        now_almaty = datetime.now(ALMATY_TZ)
        matches = load_finished_between(now_almaty - timedelta(hours=36), now_almaty)

    ranked = []
    for match in matches:
        kickoff = parse_match_kickoff_datetime(match) or datetime.min.replace(
            tzinfo=ALMATY_TZ
        )
        ranked.append((score_channel_morning_recap_match(match), kickoff, match))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    result = [item[2] for item in ranked[:limit]]
    logger.info("channel_morning_recap matches found: %s", len(result))
    return result


def format_channel_recap_date_label() -> str:
    start_almaty, _ = get_channel_morning_recap_window()
    month_names = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }
    return f"{start_almaty.day} {month_names.get(start_almaty.month, '')}".strip()


def get_channel_morning_match_short_note(match: dict) -> str:
    score = match.get("score") or {}
    home_score = score.get("home")
    away_score = score.get("away")
    home = translate_team_name_ru(match.get("home")) or "Команда 1"
    away = translate_team_name_ru(match.get("away")) or "Команда 2"
    if not isinstance(home_score, int) or not isinstance(away_score, int):
        return "матч завершён, но подробный счёт в источнике не указан."
    if home_score == away_score:
        return "команды завершили матч вничью."
    winner = home if home_score > away_score else away
    diff = abs(home_score - away_score)
    if diff >= 3:
        return f"{winner} одержала крупную победу по счёту."
    if diff == 2:
        return f"{winner} выиграла уверенно, с разницей в два мяча."
    return f"{winner} выиграла минимально, матч остался близким по счёту."


def is_channel_knockout_context(match: dict) -> bool:
    context = f"{match.get('league') or ''} {match.get('round') or ''}".casefold()
    return any(
        keyword in context
        for keyword in ("final", "semi", "quarter", "round", "playoff", "knockout")
    )


def build_channel_morning_recap_draft(
    matches: list[dict],
    upcoming_matches: list[dict] | None = None,
) -> str:
    selected_matches = matches[:6]
    upcoming_matches = upcoming_matches or []
    lines = [
        f"🇰🇿 ЧМ-2026 — итоги игрового дня ({format_channel_recap_date_label()}, время Алматы)",
        "",
        "⚽ Результаты дня",
        "",
    ]
    for index, match in enumerate(selected_matches, start=1):
        home = translate_team_name_ru(match.get("home")) or "Команда 1"
        away = translate_team_name_ru(match.get("away")) or "Команда 2"
        score = format_channel_match_score(match)
        lines.extend(
            [
                f"{index}. {home} {score} {away}",
                f"   Коротко: {get_channel_morning_match_short_note(match)}",
            ]
        )

    moments = []
    for match in selected_matches:
        home = translate_team_name_ru(match.get("home")) or "Команда 1"
        away = translate_team_name_ru(match.get("away")) or "Команда 2"
        score = match.get("score") or {}
        home_score = score.get("home")
        away_score = score.get("away")
        if isinstance(home_score, int) and isinstance(away_score, int):
            diff = abs(home_score - away_score)
            if diff >= 2:
                winner = home if home_score > away_score else away
                moments.append(f"{winner} выиграла с заметным преимуществом по счёту.")
            elif diff == 1:
                moments.append(f"{home} — {away}: близкий матч с минимальной разницей.")
            elif home_score == away_score:
                moments.append(f"{home} — {away}: равный счёт после основного времени.")
    moments = moments[:4] or [
        "Подробных событий матча в источнике нет, поэтому фиксируем только результаты."
    ]
    lines.extend(["", "🌟 Главные моменты"])
    lines.extend(f"— {moment}" for moment in moments)

    tournament_notes = []
    for match in selected_matches:
        if not is_channel_knockout_context(match):
            continue
        score = match.get("score") or {}
        home_score = score.get("home")
        away_score = score.get("away")
        if not isinstance(home_score, int) or not isinstance(away_score, int):
            continue
        if home_score == away_score:
            continue
        winner = (
            translate_team_name_ru(match.get("home"))
            if home_score > away_score
            else translate_team_name_ru(match.get("away"))
        ) or "Победитель"
        stage = str(match.get("round") or "").strip()
        tournament_notes.append(
            f"{winner} выиграла матч стадии {stage}." if stage else f"{winner} выиграла матч плей-офф."
        )
    if tournament_notes:
        lines.extend(["", "📈 Влияние на турнир"])
        lines.extend(f"— {note}" for note in tournament_notes[:3])

    england_matches = [
        match
        for match in selected_matches
        if str(match.get("home") or "").casefold() == "england"
        or str(match.get("away") or "").casefold() == "england"
    ]
    upcoming_england = [
        match
        for match in upcoming_matches
        if str(match.get("home") or "").casefold() == "england"
        or str(match.get("away") or "").casefold() == "england"
    ]
    if england_matches:
        lines.extend(["", "🔴 Англия"])
        match = england_matches[0]
        home = translate_team_name_ru(match.get("home")) or "Англия"
        away = translate_team_name_ru(match.get("away")) or "соперник"
        lines.append(
            f"— Англия играла: {home} {format_channel_match_score(match)} {away}."
        )
    elif upcoming_england:
        lines.extend(["", "🔴 Англия"])
        match = upcoming_england[0]
        home = translate_team_name_ru(match.get("home")) or "Англия"
        away = translate_team_name_ru(match.get("away")) or "соперник"
        lines.append(f"— Матч Англии впереди: {home} — {away}.")

    lines.extend(["", "👀 Что смотреть дальше"])
    if upcoming_matches:
        for match in upcoming_matches[:3]:
            home = translate_team_name_ru(match.get("home")) or "Команда 1"
            away = translate_team_name_ru(match.get("away")) or "Команда 2"
            marker = " 🔴" if "england" in f"{match.get('home')} {match.get('away')}".casefold() else ""
            lines.append(f"— {home} — {away}, {format_channel_match_time(match)}{marker}")
    else:
        lines.append("— Ближайшие важные матчи в источнике не найдены.")

    lines.extend(
        [
            "",
            "Полный AI-разбор: @Match_Stat_bot",
            "Канал MatchLab: https://t.me/matchlab_ai",
            "",
            CHANNEL_DRAFT_DISCLAIMER,
        ]
    )
    draft = sanitize_channel_post_text("\n".join(lines))
    return limit_channel_text_preserving_disclaimer(draft, 1400)


def build_channel_morning_digest_draft(matches: list[dict]) -> str:
    return build_channel_morning_recap_draft(matches)


def build_channel_daily_radar_draft(matches: list[dict]) -> str:
    selected_matches = matches[:5]
    lines = [
        "🛰 Футбольный радар MatchLab",
        "",
        "Коротко о матчах, которые сегодня держим в фокусе.",
        "",
        "🔥 Фокус дня",
        "",
    ]
    if selected_matches:
        for index, match in enumerate(selected_matches, start=1):
            home = translate_team_name_ru(match.get("home")) or "Команда 1"
            away = translate_team_name_ru(match.get("away")) or "Команда 2"
            context_lines = []
            league = str(match.get("league") or "").strip()
            stage = str(match.get("round") or "").strip()
            venue = str(match.get("venue") or match.get("stadium") or "").strip()
            city = str(match.get("city") or "").strip()
            if league:
                context_lines.append(f"Турнир: {league}.")
            if stage:
                context_lines.append(f"Этап: {stage}.")
            if parse_match_kickoff_datetime(match):
                context_lines.append(f"Время Алматы: {format_channel_match_time(match)}.")
            if venue and city:
                context_lines.append(f"Место: {venue}, {city}.")
            elif venue:
                context_lines.append(f"Место: {venue}.")
            elif city:
                context_lines.append(f"Город: {city}.")

            reason = get_channel_digest_reason(match, index - 1)
            motivation = ""
            if stage:
                motivation = f"Мотивация: пройти сильнее через этап {stage}."
            lines.extend([f"{index}. {home} — {away}", *context_lines])
            if motivation:
                lines.append(motivation)
            if reason:
                lines.append(f"Почему смотреть: {reason}")
            lines.append("")
    else:
        lines.extend(
            [
                "Сегодня в фокусе общая картина футбольного дня: форма команд, "
                "темп матчей и неожиданные игровые сценарии.",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "Полный AI-разбор: @Match_Stat_bot",
            "Канал MatchLab: https://t.me/matchlab_ai",
            "",
            CHANNEL_DRAFT_DISCLAIMER,
        ]
    )
    draft = sanitize_channel_post_text("\n".join(lines))
    return limit_channel_text_preserving_disclaimer(draft, 1200)


CHANNEL_FOOTBALL_NEWS_SOURCES = (
    ("BBC Sport Football", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("Sky Sports Football", "https://www.skysports.com/rss/12040"),
    ("The Guardian Football", "https://www.theguardian.com/football/rss"),
    ("ESPN Soccer", "https://www.espn.com/espn/rss/soccer/news"),
)


def strip_html_tags(text: str | None) -> str:
    compact_text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", compact_text).strip()


def parse_channel_news_datetime(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return text


def get_rss_child_text(item, names: tuple[str, ...]) -> str:
    for child in list(item):
        child_name = child.tag.rsplit("}", 1)[-1].lower()
        if child_name in names:
            return str(child.text or "").strip()
    return ""


def fetch_channel_football_news_items() -> list[dict]:
    items = []
    seen_urls = set()
    headers = {"User-Agent": "MatchLabBot/1.0"}
    for source_name, source_url in CHANNEL_FOOTBALL_NEWS_SOURCES:
        try:
            response = requests.get(
                source_url,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception:
            logger.warning(
                "channel_news_radar source fetch failed: source=%s",
                source_name,
                exc_info=True,
            )
            continue

        for rss_item in root.findall(".//item")[:12]:
            title = strip_html_tags(get_rss_child_text(rss_item, ("title",)))
            url = get_rss_child_text(rss_item, ("link",))
            summary = strip_html_tags(
                get_rss_child_text(rss_item, ("description", "summary"))
            )
            published_at = parse_channel_news_datetime(
                get_rss_child_text(rss_item, ("pubdate", "published", "updated"))
            )
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "source": source_name,
                    "published_at": published_at,
                    "summary": summary,
                }
            )
    return items


def score_channel_news_item(item: dict) -> int:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "summary", "source")
    ).casefold()
    score = 10
    positive_keywords = {
        "liverpool": 14,
        "england": 12,
        "world cup": 16,
        "champions league": 16,
        "premier league": 14,
        "real madrid": 14,
        "barcelona": 14,
        "man city": 13,
        "manchester city": 13,
        "arsenal": 12,
        "chelsea": 12,
        "man united": 12,
        "manchester united": 12,
        "bayern": 12,
        "psg": 12,
        "transfer": 10,
        "injury": 8,
        "interview": 7,
        "press conference": 7,
        "coach": 7,
        "manager": 7,
        "quote": 7,
        "young player": 7,
        "record": 8,
        "official": 9,
        "agreement": 8,
        "talks": 7,
        "interest": 6,
        "considering": 6,
        "bid": 8,
        "medical": 8,
    }
    negative_keywords = {
        "betting": 35,
        "odds": 35,
        "casino": 35,
        "fantasy": 25,
        "quiz": 20,
        "gossip": 10,
        "cricket": 25,
        "tennis": 25,
        "rugby": 25,
        "nba": 25,
        "nfl": 25,
        "formula 1": 25,
    }
    for keyword, points in positive_keywords.items():
        if keyword in text:
            score += points
    for keyword, points in negative_keywords.items():
        if keyword in text:
            score -= points
    return max(0, min(100, score))


def build_channel_news_item_fallback_ru(item: dict) -> dict:
    title = sanitize_channel_post_text(strip_html_tags(item.get("title")))
    source = sanitize_channel_post_text(str(item.get("source") or "Источник"))
    url = str(item.get("url") or "").strip()
    headline = f"Инфоповод: {title}" if title else "Футбольный инфоповод"
    return {
        "headline": headline,
        "summary": (
            "Источник сообщает футбольный инфоповод. Подробности лучше "
            "проверить по ссылке."
        ),
        "importance": [
            "сохраняем конкретику из заголовка источника",
            "детали стоит сверять с первоисточником",
        ],
        "source": source,
        "url": url,
    }


def normalize_channel_news_item_ru_payload(payload: dict, item: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None

    headline = get_channel_short_text(
        sanitize_channel_post_text(str(payload.get("headline") or "").strip()),
        120,
    )
    summary = get_channel_short_text(
        sanitize_channel_post_text(str(payload.get("summary") or "").strip()),
        350,
    )
    importance = [
        get_channel_short_text(sanitize_channel_post_text(str(reason).strip()), 120)
        for reason in payload.get("importance") or []
        if str(reason).strip()
    ]
    if not headline or not summary:
        return None

    fallback = build_channel_news_item_fallback_ru(item)
    return {
        "headline": headline,
        "summary": summary,
        "importance": importance[:2] or fallback["importance"],
        "source": fallback["source"],
        "url": fallback["url"],
    }


def build_channel_news_item_ru_with_openai(item: dict) -> dict | None:
    if not OPENAI_API_KEY:
        return None

    title = strip_html_tags(item.get("title"))
    summary = strip_html_tags(item.get("summary"))
    source = str(item.get("source") or "Источник").strip()
    prompt = (
        "Ты редактор футбольного Telegram-канала MatchLab. Сделай короткий "
        "русский пересказ новости строго по данным ниже.\n"
        "Требования:\n"
        "- ответ строго на русском;\n"
        "- сохрани имена игроков, клубов, тренеров и турниров как в источнике;\n"
        "- не добавляй факты сверх title, summary и source;\n"
        "- не используй betting/gambling-лексику и коммерческие обещания результата;\n"
        "- если это слух, интерес, переговоры, запрос, medical, bid или agreement, "
        "пиши осторожно: по данным источника, сообщается, ситуация развивается, "
        "официального подтверждения в тексте нет;\n"
        "- верни только JSON без markdown.\n\n"
        "Формат JSON:\n"
        "{\n"
        '  "headline": "короткий русский заголовок до 90 символов",\n'
        '  "summary": "1-2 предложения русского пересказа"\n'
        "}\n\n"
        f"title: {title}\n"
        f"summary: {summary}\n"
        f"source: {source}"
    )
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        try:
            completion = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратно переводишь и пересказываешь футбольные "
                            "новости для MatchLab без домыслов."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_completion_tokens=500,
            )
        except TypeError:
            completion = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратно переводишь и пересказываешь футбольные "
                            "новости для MatchLab без домыслов."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=500,
            )
        content = completion.choices[0].message.content or ""
        payload = parse_ai_analysis_json(content)
        normalized = normalize_channel_news_item_ru_payload(payload or {}, item)
        if normalized:
            combined_text = "\n".join(
                [
                    normalized.get("headline", ""),
                    normalized.get("summary", ""),
                    "\n".join(normalized.get("importance") or []),
                ]
            )
            if not channel_text_has_forbidden_words(combined_text):
                return normalized
            logger.warning(
                "channel_news_radar OpenAI summary blocked by forbidden filter: "
                "source=%s",
                source,
            )
    except Exception:
        logger.warning(
            "channel_news_radar OpenAI summary failed: source=%s",
            source,
            exc_info=True,
        )
    return None


def build_channel_news_item_ru(item: dict) -> dict:
    return build_channel_news_item_ru_with_openai(
        item
    ) or build_channel_news_item_fallback_ru(item)


def render_channel_news_radar_draft(selected_items: list[dict]) -> str:
    lines = [
        "📰 Футбольный радар MatchLab",
        "",
    ]
    for index, item in enumerate(selected_items, start=1):
        news_item = build_channel_news_item_ru(item)
        lines.append(f"{index}. {news_item['headline']}")
        lines.append("")
        lines.append(news_item["summary"])
        lines.append("")
        lines.append(f"Источник: {news_item['source']}")
        if news_item["url"]:
            lines.append(f"Подробнее: {news_item['url']}")
        lines.append("")

    lines.extend(
        [
            "Полный AI-разбор: @Match_Stat_bot",
            "Канал MatchLab: https://t.me/matchlab_ai",
            "",
            CHANNEL_DRAFT_DISCLAIMER,
        ]
    )
    return sanitize_channel_post_text("\n".join(lines))


def build_channel_news_radar_draft(items: list[dict]) -> str:
    ranked_items = sorted(
        items,
        key=lambda item: int(item.get("score") or score_channel_news_item(item)),
        reverse=True,
    )
    selected_items = ranked_items[:3]
    for item_count in range(len(selected_items), 0, -1):
        draft = render_channel_news_radar_draft(selected_items[:item_count])
        if len(draft) <= 1400 or item_count == 1:
            return limit_channel_text_preserving_disclaimer(draft, 1400)
    return limit_channel_text_preserving_disclaimer(
        render_channel_news_radar_draft(selected_items[:1]),
        1400,
    )


def build_channel_news_draft_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Опубликовать новостной радар",
                    callback_data=f"channel_news_publish:{draft_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Пропустить",
                    callback_data=f"channel_news_skip:{draft_id}",
                )
            ],
        ]
    )


async def publish_channel_morning_digest(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict:
    content_type = "morning_digest"
    date_key = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d")
    logger.info("channel_morning_digest started: date_key=%s", date_key)

    local_key = f"{content_type}:{date_key}:published"
    if context.bot_data.get(local_key):
        logger.info("channel_morning_digest already published: date_key=%s", date_key)
        return {
            "ok": False,
            "status": "already_published",
            "message": (
                "ℹ️ Утренний обзор сегодня уже был опубликован. Если ты удалил "
                "пост из канала, в памяти бота он всё равно считается опубликованным."
            ),
        }

    if not MATCHLAB_CHANNEL_ID:
        logger.warning("channel_morning_digest skipped: reason=no_channel_id")
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            error_text="MATCHLAB_CHANNEL_ID is not configured",
        )
        return {
            "ok": False,
            "status": "no_channel_id",
            "message": (
                "❌ Утренний обзор не опубликован: MATCHLAB_CHANNEL_ID не настроен."
            ),
        }

    if has_channel_auto_post_been_published(content_type, date_key):
        context.bot_data[local_key] = True
        logger.info("channel_morning_digest already published: date_key=%s", date_key)
        return {
            "ok": False,
            "status": "already_published",
            "message": (
                "ℹ️ Утренний обзор сегодня уже был опубликован. Если ты удалил "
                "пост из канала, в БД он всё равно считается опубликованным."
            ),
        }

    try:
        matches = await asyncio.to_thread(get_channel_morning_recap_matches, 6)
    except Exception:
        logger.exception("channel_morning_digest failed: matches_fetch")
        return {
            "ok": False,
            "status": "failed",
            "message": (
                "❌ Утренний обзор не опубликован: ошибка при подборе завершённых матчей."
            ),
        }
    logger.info("channel_morning_recap matches found: %s", len(matches))
    if not matches:
        save_channel_auto_post_status(
            content_type,
            date_key,
            "skipped",
            error_text="no_matches",
        )
        logger.info("channel_morning_digest no finished matches")
        return {
            "ok": False,
            "status": "no_matches",
            "message": (
                "⚠️ Утренний обзор не опубликован: завершённые матчи за прошедший игровой день не найдены."
            ),
        }

    try:
        upcoming_matches = await asyncio.to_thread(get_channel_morning_digest_matches, 3)
    except Exception:
        logger.warning(
            "channel_morning_recap upcoming fetch failed",
            exc_info=True,
        )
        upcoming_matches = []
    logger.info("channel_morning_recap upcoming found: %s", len(upcoming_matches))

    draft = build_channel_morning_recap_draft(matches, upcoming_matches)
    draft = sanitize_channel_post_text(draft)
    logger.info("channel_morning_digest draft generated: length=%s", len(draft))
    forbidden_left = channel_text_has_forbidden_words(draft)
    logger.info("channel_morning_digest forbidden_left=%s", forbidden_left)
    if forbidden_left:
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            draft=draft,
            error_text="forbidden_words_left",
        )
        logger.warning("channel_morning_digest failed: forbidden_words_left")
        return {
            "ok": False,
            "status": "forbidden_words",
            "message": (
                "❌ Утренний обзор не опубликован: текст заблокирован фильтром безопасности."
            ),
        }

    save_channel_auto_post_status(content_type, date_key, "draft_created", draft=draft)
    try:
        sent_message = await context.bot.send_message(
            chat_id=MATCHLAB_CHANNEL_ID,
            text=draft,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("channel_morning_digest failed: send_message")
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            draft=draft,
            error_text="send_message_failed",
        )
        return {
            "ok": False,
            "status": "send_failed",
            "message": (
                "❌ Не удалось отправить утренний обзор в канал. Проверь права бота и логи."
            ),
        }

    context.bot_data[local_key] = True
    save_channel_auto_post_status(
        content_type,
        date_key,
        "published",
        draft=draft,
        published_message_id=sent_message.message_id,
    )
    logger.info(
        "channel_morning_digest published: date_key=%s message_id=%s",
        date_key,
        sent_message.message_id,
    )
    return {
        "ok": True,
        "status": "published",
        "message": (
            "✅ Утренний обзор опубликован в канал. "
            f"message_id={sent_message.message_id}"
        ),
        "message_id": sent_message.message_id,
    }


async def publish_channel_daily_football_radar(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict:
    content_type = "daily_football_radar"
    date_key = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d")
    logger.info("channel_daily_football_radar publish started: date_key=%s", date_key)

    local_key = f"{content_type}:{date_key}:published"
    if context.bot_data.get(local_key):
        logger.info(
            "channel_daily_football_radar already published: date_key=%s",
            date_key,
        )
        return {
            "ok": False,
            "status": "already_published",
            "message": (
                "ℹ️ Дневной радар сегодня уже был опубликован. Если ты удалил "
                "пост из канала, в памяти бота он всё равно считается опубликованным."
            ),
        }

    if not MATCHLAB_CHANNEL_ID:
        logger.warning("channel_daily_football_radar failed: no_channel_id")
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            error_text="MATCHLAB_CHANNEL_ID is not configured",
        )
        return {
            "ok": False,
            "status": "no_channel_id",
            "message": (
                "❌ Дневной радар не опубликован: MATCHLAB_CHANNEL_ID не настроен."
            ),
        }

    if has_channel_auto_post_been_published(content_type, date_key):
        context.bot_data[local_key] = True
        logger.info(
            "channel_daily_football_radar already published: date_key=%s",
            date_key,
        )
        return {
            "ok": False,
            "status": "already_published",
            "message": (
                "ℹ️ Дневной радар сегодня уже был опубликован. Если ты удалил "
                "пост из канала, в БД он всё равно считается опубликованным."
            ),
        }

    try:
        matches = await asyncio.to_thread(get_channel_morning_digest_matches, 5)
    except Exception:
        logger.exception("channel_daily_football_radar failed: matches_fetch")
        return {
            "ok": False,
            "status": "failed",
            "message": "❌ Дневной радар не опубликован: ошибка при подборе матчей.",
        }
    draft = build_channel_daily_radar_draft(matches)
    draft = sanitize_channel_post_text(draft)
    forbidden_left = channel_text_has_forbidden_words(draft)
    if forbidden_left:
        logger.warning("channel_daily_football_radar failed: forbidden_words_left")
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            draft=draft,
            error_text="forbidden_words_left",
        )
        return {
            "ok": False,
            "status": "forbidden_words",
            "message": (
                "❌ Дневной радар не опубликован: текст заблокирован фильтром безопасности."
            ),
        }

    save_channel_auto_post_status(content_type, date_key, "draft_created", draft=draft)
    try:
        sent_message = await context.bot.send_message(
            chat_id=MATCHLAB_CHANNEL_ID,
            text=draft,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("channel_daily_football_radar failed: send_message")
        save_channel_auto_post_status(
            content_type,
            date_key,
            "failed",
            draft=draft,
            error_text="send_message_failed",
        )
        return {
            "ok": False,
            "status": "send_failed",
            "message": (
                "❌ Не удалось отправить дневной радар в канал. Проверь права бота и логи."
            ),
        }

    context.bot_data[local_key] = True
    save_channel_auto_post_status(
        content_type,
        date_key,
        "published",
        draft=draft,
        published_message_id=sent_message.message_id,
    )
    logger.info(
        "channel_daily_football_radar published: date_key=%s message_id=%s",
        date_key,
        sent_message.message_id,
    )
    return {
        "ok": True,
        "status": "published",
        "message": (
            "✅ Дневной радар опубликован в канал. "
            f"message_id={sent_message.message_id}"
        ),
        "message_id": sent_message.message_id,
    }


def build_channel_agent_recap_manual_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔎 Показать завершённые матчи вручную",
                    callback_data="channel_admin_recap_manual",
                )
            ]
        ]
    )


def channel_agent_timestamp_to_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def channel_agent_datetime_to_timestamp(value) -> float | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def save_channel_agent_last_matchday_to_db(last_matchday: dict) -> None:
    database_url = get_database_url()
    if not database_url:
        return
    if not ensure_channel_agent_matchdays_table():
        logger.warning("channel_agent last_matchday db save failed")
        return

    match_id = str((last_matchday or {}).get("match_id") or "").strip()
    match = (last_matchday or {}).get("match")
    if not match_id or not isinstance(match, dict):
        return

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO channel_agent_matchdays (
                    agent_key,
                    match_id,
                    match_json,
                    status,
                    agent_score,
                    agent_reasons,
                    selected_at,
                    pre_match_published_at,
                    pre_match_message_id,
                    post_match_draft_created_at,
                    post_match_published_at,
                    post_match_message_id,
                    updated_at
                )
                VALUES (
                    'default',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    COALESCE(%s, now()),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    now()
                )
                ON CONFLICT (agent_key)
                DO UPDATE SET
                    match_id = EXCLUDED.match_id,
                    match_json = EXCLUDED.match_json,
                    status = EXCLUDED.status,
                    agent_score = EXCLUDED.agent_score,
                    agent_reasons = EXCLUDED.agent_reasons,
                    selected_at = EXCLUDED.selected_at,
                    pre_match_published_at = EXCLUDED.pre_match_published_at,
                    pre_match_message_id = EXCLUDED.pre_match_message_id,
                    post_match_draft_created_at =
                        EXCLUDED.post_match_draft_created_at,
                    post_match_published_at =
                        EXCLUDED.post_match_published_at,
                    post_match_message_id = EXCLUDED.post_match_message_id,
                    updated_at = now();
                """,
                (
                    match_id,
                    Json(make_json_safe(match) or {}),
                    str(last_matchday.get("status") or "unknown"),
                    last_matchday.get("agent_score"),
                    Json(last_matchday.get("agent_reasons") or []),
                    channel_agent_timestamp_to_datetime(
                        last_matchday.get("selected_at")
                    ),
                    channel_agent_timestamp_to_datetime(
                        last_matchday.get("pre_match_published_at")
                    ),
                    last_matchday.get("pre_match_message_id"),
                    channel_agent_timestamp_to_datetime(
                        last_matchday.get("post_match_draft_created_at")
                    ),
                    channel_agent_timestamp_to_datetime(
                        last_matchday.get("post_match_published_at")
                    ),
                    last_matchday.get("post_match_message_id"),
                ),
            )
        connection.commit()
        logger.info(
            "channel_agent last_matchday saved to db: match_id=%s status=%s",
            match_id,
            last_matchday.get("status"),
        )
    except Exception:
        logger.exception("channel_agent last_matchday db save failed")
    finally:
        if connection is not None:
            connection.close()


def load_channel_agent_last_matchday_from_db() -> dict | None:
    database_url = get_database_url()
    if not database_url:
        return None
    if not ensure_channel_agent_matchdays_table():
        logger.warning("channel_agent last_matchday db load failed")
        return None

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    match_id,
                    match_json,
                    status,
                    agent_score,
                    agent_reasons,
                    selected_at,
                    pre_match_published_at,
                    pre_match_message_id,
                    post_match_draft_created_at,
                    post_match_published_at,
                    post_match_message_id
                FROM channel_agent_matchdays
                WHERE agent_key = 'default'
                LIMIT 1;
                """
            )
            row = cursor.fetchone()
        if not row:
            return None

        last_matchday = {
            "match_id": row.get("match_id"),
            "match": row.get("match_json") or {},
            "selected_at": channel_agent_datetime_to_timestamp(
                row.get("selected_at")
            ),
            "status": row.get("status"),
            "agent_score": row.get("agent_score"),
            "agent_reasons": row.get("agent_reasons") or [],
            "pre_match_published_at": channel_agent_datetime_to_timestamp(
                row.get("pre_match_published_at")
            ),
            "pre_match_message_id": row.get("pre_match_message_id"),
            "post_match_draft_created_at": channel_agent_datetime_to_timestamp(
                row.get("post_match_draft_created_at")
            ),
            "post_match_published_at": channel_agent_datetime_to_timestamp(
                row.get("post_match_published_at")
            ),
            "post_match_message_id": row.get("post_match_message_id"),
            "_source": "db",
        }
        logger.info(
            "channel_agent last_matchday loaded from db: match_id=%s",
            last_matchday.get("match_id"),
        )
        return last_matchday
    except Exception:
        logger.exception("channel_agent last_matchday db load failed")
        return None
    finally:
        if connection is not None:
            connection.close()


def has_channel_auto_post_been_published(
    content_type: str,
    date_key: str,
) -> bool:
    database_url = get_database_url()
    if not database_url:
        logger.warning("channel_auto_posts publish lookup skipped: no DATABASE_URL")
        return False
    if not ensure_channel_auto_posts_table():
        return False

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM channel_auto_posts
                WHERE content_type = %s
                AND date_key = %s
                AND status = 'published'
                LIMIT 1;
                """,
                (content_type, date_key),
            )
            return cursor.fetchone() is not None
    except Exception:
        logger.exception("channel_auto_posts publish lookup failed")
        return False
    finally:
        if connection is not None:
            connection.close()


def save_channel_auto_post_status(
    content_type: str,
    date_key: str,
    status: str,
    draft: str | None = None,
    published_message_id: int | None = None,
    error_text: str | None = None,
) -> None:
    database_url = get_database_url()
    if not database_url:
        logger.warning("channel_auto_posts status save skipped: no DATABASE_URL")
        return
    if not ensure_channel_auto_posts_table():
        logger.warning("channel_auto_posts status save failed: ensure_failed")
        return

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO channel_auto_posts (
                    content_type,
                    date_key,
                    status,
                    draft,
                    published_at,
                    published_message_id,
                    error_text,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    CASE WHEN %s = 'published' THEN now() ELSE NULL END,
                    %s,
                    %s,
                    now()
                )
                ON CONFLICT (content_type, date_key)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    draft = COALESCE(EXCLUDED.draft, channel_auto_posts.draft),
                    published_at = CASE
                        WHEN EXCLUDED.status = 'published'
                        THEN COALESCE(EXCLUDED.published_at, now())
                        ELSE channel_auto_posts.published_at
                    END,
                    published_message_id = COALESCE(
                        EXCLUDED.published_message_id,
                        channel_auto_posts.published_message_id
                    ),
                    error_text = EXCLUDED.error_text,
                    updated_at = now();
                """,
                (
                    content_type,
                    date_key,
                    status,
                    draft,
                    status,
                    published_message_id,
                    error_text,
                ),
            )
        connection.commit()
    except Exception:
        logger.exception(
            "channel_auto_posts status save failed: content_type=%s date_key=%s",
            content_type,
            date_key,
        )
    finally:
        if connection is not None:
            connection.close()


def get_channel_agent_last_matchday(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict | None:
    last_matchday = context.bot_data.get("channel_agent_last_matchday")
    if (
        isinstance(last_matchday, dict)
        and last_matchday.get("match_id")
        and last_matchday.get("match")
    ):
        last_matchday.setdefault("_source", "memory")
        return last_matchday

    loaded_matchday = load_channel_agent_last_matchday_from_db()
    if loaded_matchday and loaded_matchday.get("match_id") and loaded_matchday.get("match"):
        context.bot_data["channel_agent_last_matchday"] = loaded_matchday
        return loaded_matchday
    return None


def find_recap_candidate_for_last_matchday(
    last_matchday: dict,
    recap_candidates: list[dict],
) -> dict | None:
    match_id = str(last_matchday.get("match_id") or "").strip()
    if not match_id:
        return None

    for candidate in recap_candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        if candidate_id == match_id:
            return candidate

    stored_match = last_matchday.get("match")
    if isinstance(stored_match, dict) and is_channel_match_finished(stored_match):
        return stored_match
    return None


def get_channel_recap_cached_analysis(
    admin_id: int,
    match_id: str,
) -> tuple[dict | None, str | None]:
    normalized_match_id = normalize_ai_analysis_match_id(match_id)
    for lookup_mode in ("premium", "default"):
        logger.info(
            "channel_recap cache lookup mode=%s match_id=%s",
            lookup_mode,
            normalized_match_id,
        )
        saved_analysis = None
        try:
            saved_analysis, normalized_match_id = lookup_saved_miniapp_ai_analysis(
                admin_id,
                normalized_match_id,
                lookup_mode,
            )
        except Exception:
            logger.warning(
                "channel_recap personal AI lookup failed: match_id=%s "
                "analysis_mode=%s",
                normalized_match_id,
                lookup_mode,
                exc_info=True,
            )
        logger.info(
            "channel_recap personal saved found %s: match_id=%s mode=%s",
            bool(saved_analysis),
            normalized_match_id,
            lookup_mode,
        )
        if saved_analysis:
            source_name = f"personal_cache_{lookup_mode}"
            logger.info(
                "channel_recap AI source selected %s: match_id=%s",
                source_name,
                normalized_match_id,
            )
            return saved_analysis, source_name

        global_analysis = get_global_miniapp_ai_analysis(
            normalized_match_id,
            lookup_mode,
        )
        logger.info(
            "channel_recap global cache found %s: match_id=%s mode=%s",
            bool(global_analysis),
            normalized_match_id,
            lookup_mode,
        )
        if global_analysis:
            source_name = f"global_cache_{lookup_mode}"
            logger.info(
                "channel_recap AI source selected %s: match_id=%s",
                source_name,
                normalized_match_id,
            )
            return global_analysis, source_name

    return None, None


def get_channel_recent_finished_matches() -> list[dict]:
    now_almaty = datetime.now(ALMATY_TZ)
    fixtures = get_api_football_matches_between(
        now_almaty - timedelta(hours=48),
        now_almaty,
        only_top=False,
        allowed_only=True,
    )
    items = []
    for fixture_item in fixtures:
        formatted_item = format_miniapp_fixture_item(fixture_item)
        if formatted_item and is_channel_match_finished(formatted_item):
            items.append(formatted_item)
    return items


def get_channel_recap_candidates(
    admin_id: int | None = None,
    limit: int = 3,
) -> list[dict]:
    candidates_by_id = {}
    for match_type in ("top", "today", "yesterday"):
        try:
            for match in get_miniapp_matches(match_type):
                match_id = str(match.get("id") or "").strip()
                if match_id and match_id not in candidates_by_id:
                    candidates_by_id[match_id] = match
        except Exception:
            logger.warning(
                "channel_recap match list failed: match_type=%s",
                match_type,
                exc_info=True,
            )
    try:
        for match in get_channel_recent_finished_matches():
            match_id = str(match.get("id") or "").strip()
            if match_id and match_id not in candidates_by_id:
                candidates_by_id[match_id] = match
    except Exception:
        logger.warning("channel_recap recent finished fetch failed", exc_info=True)

    now_almaty = datetime.now(ALMATY_TZ)
    ranked = []
    for match in candidates_by_id.values():
        if not is_channel_match_finished(match):
            continue
        kickoff = parse_match_kickoff_datetime(match)
        if kickoff and not (
            now_almaty - timedelta(hours=48) <= kickoff <= now_almaty
        ):
            continue

        match_id = str(match.get("id") or "")
        cache_available = False
        for lookup_mode in ("premium", "default"):
            personal_cached = False
            if admin_id is not None:
                try:
                    personal_cached = bool(
                        get_saved_miniapp_ai_analysis(
                            admin_id,
                            normalize_ai_analysis_match_id(match_id),
                            lookup_mode,
                        )
                    )
                except Exception:
                    logger.warning(
                        "channel_recap candidate personal cache lookup failed: "
                        "match_id=%s mode=%s",
                        match_id,
                        lookup_mode,
                        exc_info=True,
                    )
            if personal_cached or get_global_miniapp_ai_analysis(match_id, lookup_mode):
                cache_available = True
                break
        enriched_match = dict(match)
        enriched_match["_channel_cache_available"] = cache_available
        score, reasons = get_channel_recap_match_priority(enriched_match)
        ranked.append((score, kickoff or datetime.min.replace(tzinfo=ALMATY_TZ), reasons, enriched_match))

    ranked.sort(key=lambda item: (-item[0], item[1]), reverse=False)
    candidates = []
    for _, _, reasons, match in ranked[:limit]:
        enriched_match = dict(match)
        enriched_match["_channel_reasons"] = reasons
        candidates.append(enriched_match)
    return candidates


def build_channel_plan_message(candidates: list[dict]) -> str:
    lines = ["🤖 Кандидаты на матч дня:", ""]
    for index, match in enumerate(candidates, start=1):
        home = format_channel_team_display(match.get("home")) or "Команда 1"
        away = format_channel_team_display(match.get("away")) or "Команда 2"
        lines.extend(
            [
                f"{index}. {home} — {away}",
                f"   Время: {format_channel_match_time(match)}",
                f"   Турнир: {match.get('league') or 'не указан'}",
                "   Почему подходит: "
                + "; ".join(match.get("_channel_reasons") or ["интересен для контента"]),
                "",
            ]
        )
    lines.append("Выбери матч для черновика:")
    return "\n".join(lines)


def build_channel_recap_message(candidates: list[dict]) -> str:
    lines = ["✅ Кандидаты для итогов матча дня:", ""]
    for index, match in enumerate(candidates, start=1):
        home = translate_team_name_ru(match.get("home")) or "Команда 1"
        away = translate_team_name_ru(match.get("away")) or "Команда 2"
        lines.extend(
            [
                f"{index}. {home} {format_channel_match_score(match)} {away}",
                f"   Время: {format_channel_match_time(match)}",
                f"   Турнир: {match.get('league') or 'не указан'}",
                "   Почему подходит: "
                + "; ".join(match.get("_channel_reasons") or ["подходит для итогов"]),
                "",
            ]
        )
    lines.append("Выбери матч для черновика итогов:")
    return "\n".join(lines)


def build_channel_plan_keyboard(candidates: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for index, match in enumerate(candidates, start=1):
        home = format_channel_team_display(match.get("home")) or "Команда 1"
        away = format_channel_team_display(match.get("away")) or "Команда 2"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{index}. {home} — {away}"[:64],
                    callback_data=f"channel_pick:{match.get('id')}",
                )
            ]
        )
    return InlineKeyboardMarkup(keyboard)


def build_channel_recap_keyboard(candidates: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for index, match in enumerate(candidates, start=1):
        home = translate_team_name_ru(match.get("home")) or "Команда 1"
        away = translate_team_name_ru(match.get("away")) or "Команда 2"
        score = format_channel_match_score(match)
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{index}. {home} {score} {away}"[:64],
                    callback_data=f"channel_recap_pick:{match.get('id')}",
                )
            ]
        )
    return InlineKeyboardMarkup(keyboard)


def cleanup_channel_bot_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    candidates = context.bot_data.get("channel_plan_candidates") or {}
    context.bot_data["channel_plan_candidates"] = {
        key: value
        for key, value in candidates.items()
        if now_ts - float(value.get("created_at") or 0)
        < CHANNEL_PLAN_CANDIDATES_TTL_SECONDS
    }
    drafts = context.bot_data.get("channel_plan_drafts") or {}
    context.bot_data["channel_plan_drafts"] = {
        key: value
        for key, value in drafts.items()
        if now_ts - float(value.get("created_at") or 0)
        < CHANNEL_PLAN_DRAFTS_TTL_SECONDS
    }


def store_channel_candidates(
    context: ContextTypes.DEFAULT_TYPE,
    candidates: list[dict],
) -> None:
    cleanup_channel_bot_data(context)
    storage = context.bot_data.setdefault("channel_plan_candidates", {})
    now_ts = datetime.now(timezone.utc).timestamp()
    for match in candidates:
        match_id = str(match.get("id") or "").strip()
        if match_id:
            storage[match_id] = {"match": match, "created_at": now_ts}


def get_stored_channel_match(
    context: ContextTypes.DEFAULT_TYPE,
    match_id: str,
) -> dict | None:
    cleanup_channel_bot_data(context)
    item = (context.bot_data.get("channel_plan_candidates") or {}).get(match_id)
    if item and item.get("match"):
        return item["match"]
    return find_miniapp_match(match_id)


def extract_signal_lines(structured: dict | None, limit: int = 3) -> list[str]:
    signals = (structured or {}).get("signals") or []
    lines = []
    for signal in signals:
        if isinstance(signal, dict):
            label = str(signal.get("label") or "Сигнал").strip()
            value = str(signal.get("value") or "").strip()
            reason = str(signal.get("reason") or "").strip()
            text = f"{label}: {value}".strip(": ")
            if reason:
                text = f"{text} — {reason}"
        elif isinstance(signal, str):
            text = signal.strip()
        else:
            text = str(signal).strip()

        if text:
            lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def extract_risk_lines(structured: dict | None, limit: int = 3) -> list[str]:
    risks = (structured or {}).get("risks") or []
    return [str(risk).strip() for risk in risks[:limit] if str(risk).strip()]


CHANNEL_DRAFT_DISCLAIMER = "Это аналитика на основе данных, а не обещание результата."
CHANNEL_RECAP_DRAFT_MAX_CHARS = 1400
SAFE_SOCIAL_HASHTAGS = [
    "#футбол",
    "#футбольнаяаналитика",
    "#аналитикафутбола",
    "#matchlab",
    "#football",
    "#footballanalytics",
    "#soccer",
    "#socceranalysis",
    "#матчдня",
    "#спорт",
]

SAFE_RECAP_SOCIAL_HASHTAGS = [
    "#футбол",
    "#футбольнаяаналитика",
    "#аналитикафутбола",
    "#matchlab",
    "#football",
    "#footballanalytics",
    "#soccer",
    "#socceranalysis",
    "#итогиматча",
    "#спорт",
]


TEAM_COLOR_OVERRIDES = {
    "Brazil": ("#0f7a34", "#f6d54a"),
    "Japan": ("#c91f37", "#f8fafc"),
    "South Africa": ("#0b6b3a", "#f3c623"),
    "Canada": ("#d71920", "#f8fafc"),
    "France": ("#1d4ed8", "#dc2626"),
    "Germany": ("#111827", "#dc2626"),
    "England": ("#f8fafc", "#dc2626"),
    "Spain": ("#c60b1e", "#ffc400"),
    "Portugal": ("#c8102e", "#006b3f"),
    "Argentina": ("#75aadb", "#f8fafc"),
    "Netherlands": ("#f97316", "#f8fafc"),
    "Morocco": ("#c1272d", "#006233"),
    "Mexico": ("#006847", "#ce1126"),
}

TEAM_COLOR_OVERRIDES_CASEFOLD = {
    key.casefold(): value for key, value in TEAM_COLOR_OVERRIDES.items()
}


TEAM_FLAG_EMOJI_OVERRIDES = {
    "Brazil": "🇧🇷",
    "Japan": "🇯🇵",
    "South Africa": "🇿🇦",
    "Canada": "🇨🇦",
    "Germany": "🇩🇪",
    "France": "🇫🇷",
    "England": "🏴",
    "Spain": "🇪🇸",
    "Portugal": "🇵🇹",
    "Argentina": "🇦🇷",
    "Netherlands": "🇳🇱",
    "Morocco": "🇲🇦",
    "Mexico": "🇲🇽",
    "USA": "🇺🇸",
    "United States": "🇺🇸",
    "Belgium": "🇧🇪",
    "Senegal": "🇸🇳",
    "Croatia": "🇭🇷",
    "Switzerland": "🇨🇭",
    "Australia": "🇦🇺",
    "Egypt": "🇪🇬",
    "Ghana": "🇬🇭",
    "Colombia": "🇨🇴",
}


TEAM_FLAG_EMOJI_OVERRIDES_CASEFOLD = {
    key.casefold(): value for key, value in TEAM_FLAG_EMOJI_OVERRIDES.items()
}


def get_team_flag_emoji(name: str | None) -> str:
    team_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not team_name:
        return ""
    if team_name in TEAM_FLAG_EMOJI_OVERRIDES:
        return TEAM_FLAG_EMOJI_OVERRIDES[team_name]
    return TEAM_FLAG_EMOJI_OVERRIDES_CASEFOLD.get(team_name.casefold(), "")


def format_channel_team_display(name: str | None) -> str:
    raw_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not raw_name:
        return ""
    translated_name = translate_team_name_ru(raw_name) or raw_name
    flag = get_team_flag_emoji(raw_name)
    if flag:
        return f"{flag} {translated_name}"
    return translated_name


def trim_to_complete_sentence(text: str, limit: int) -> str:
    compact_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact_text) <= limit:
        return compact_text

    cut = compact_text[:limit].rstrip()
    sentence_end_positions = [
        match.end()
        for match in re.finditer(r"[.!?…](?:\s|$)", cut)
        if match.end() >= max(40, int(limit * 0.45))
    ]
    if sentence_end_positions:
        candidate = cut[: sentence_end_positions[-1]].strip()
    else:
        newline_position = cut.rfind("\n")
        if newline_position >= max(40, int(limit * 0.45)):
            candidate = cut[:newline_position].strip()
        else:
            space_position = cut.rfind(" ")
            candidate = cut[:space_position].strip() if space_position > 0 else cut

    candidate = candidate.rstrip(" ,;:-")
    dangling_words = {
        "за",
        "через",
        "потому",
        "потому что",
        "так как",
        "и",
        "но",
        "а",
        "а также",
        "при этом",
        "который",
        "которая",
        "которые",
        "с учётом",
        "с учетом",
        "на фоне",
    }
    while candidate:
        lowered = candidate.casefold()
        removed = False
        for word in sorted(dangling_words, key=len, reverse=True):
            suffix = f" {word}"
            if lowered == word or lowered.endswith(suffix):
                candidate = candidate[: -len(word)].rstrip(" ,;:-")
                removed = True
                break
        if not removed:
            break
    if not candidate:
        candidate = compact_text[:limit].rstrip(" ,;:-")
    if candidate and not re.search(r"[.!?…]$", candidate):
        candidate = candidate.rstrip(" ,;:-") + "…"
    return candidate


def get_channel_short_text(text: str, max_chars: int = 140) -> str:
    compact_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact_text) <= max_chars:
        return compact_text
    return trim_to_complete_sentence(compact_text, max_chars)


def get_channel_short_sentences(text: str, limit: int = 2, max_chars: int = 220) -> str:
    compact_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact_text:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", compact_text)
    selected = " ".join(sentence for sentence in sentences[:limit] if sentence)
    return get_channel_short_text(selected or compact_text, max_chars)


def limit_channel_text_preserving_disclaimer(text: str, max_chars: int) -> str:
    sanitized = sanitize_channel_post_text(text)
    if len(sanitized) <= max_chars:
        return sanitized

    disclaimer = CHANNEL_DRAFT_DISCLAIMER
    body = sanitized.replace(disclaimer, "").rstrip()
    max_body_chars = max(120, max_chars - len(disclaimer) - 3)
    trimmed_body = trim_to_complete_sentence(body, max_body_chars)
    return sanitize_channel_post_text(f"{trimmed_body}\n\n{disclaimer}")


def format_channel_probability(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}%"

    probability_text = str(value).strip()
    if not probability_text:
        return "—"
    if "%" in probability_text:
        return probability_text
    return f"{probability_text}%"


def build_channel_post_draft(match: dict, analysis_result: dict) -> str:
    structured = analysis_result.get("structured") or {}
    probabilities = structured.get("outcome_probabilities") or {}
    home_raw = match.get("home") or analysis_result.get("home_team") or ""
    away_raw = match.get("away") or analysis_result.get("away_team") or ""
    home = format_channel_team_display(home_raw) or "Команда 1"
    away = format_channel_team_display(away_raw) or "Команда 2"
    logger.info(
        "channel_draft display teams: home_raw=%s home_display=%s "
        "away_raw=%s away_display=%s",
        home_raw,
        home,
        away_raw,
        away,
    )
    summary = structured.get("summary") or "AI-оценка MatchLab видит матч с несколькими рабочими сценариями."
    scenario = structured.get("scenario") or structured.get("tactical_notes") or summary
    summary_text = get_channel_short_sentences(summary, limit=2, max_chars=210)
    if scenario and scenario != summary:
        scenario_text = get_channel_short_sentences(scenario, limit=1, max_chars=160)
        intro_text = f"{summary_text} {scenario_text}".strip()
    else:
        intro_text = summary_text
    intro_text = get_channel_short_text(intro_text, 260)
    signals = [
        get_channel_short_text(signal, 105)
        for signal in extract_signal_lines(structured, limit=2)
    ]
    risks = [
        get_channel_short_text(risk, 105)
        for risk in extract_risk_lines(structured, limit=2)
    ]

    lines = [
        f"🔥 Матч дня: {home} — {away}",
        "",
        "AI-оценка MatchLab:",
        intro_text,
        "",
        "📊 Вероятности:",
        f"• {home} — {format_channel_probability(probabilities.get('home_win'))}",
        f"• Ничья — {format_channel_probability(probabilities.get('draw'))}",
        f"• {away} — {format_channel_probability(probabilities.get('away_win'))}",
        "",
        "📈 Сигналы:",
    ]
    lines.extend(f"• {signal}" for signal in (signals or ["Есть умеренный аналитический сигнал."]))
    lines.extend(["", "⚠️ Главные риски:"])
    lines.extend(f"• {risk}" for risk in (risks or ["Часть данных может обновиться ближе к началу матча."]))
    lines.extend(
        [
            "",
            "Полный AI-разбор: @Match_Stat_bot",
            "",
            CHANNEL_DRAFT_DISCLAIMER,
        ]
    )
    draft = limit_channel_text_preserving_disclaimer("\n".join(lines), 900)
    logger.info(
        "channel_draft length chars=%s forbidden_left=%s",
        len(draft),
        channel_text_has_forbidden_words(draft),
    )
    return draft


def shorten_channel_post_draft(text: str) -> str:
    lines = [line for line in str(text or "").splitlines()]
    shortened = []
    skip_markers = {"📈 Статистические сигналы:", "⚠️ Главные риски:"}
    skipped_bullets = {marker: 0 for marker in skip_markers}
    current_section = ""
    for line in lines:
        if line in skip_markers:
            current_section = line
            shortened.append(line)
            continue
        if line.startswith("• ") and current_section in skip_markers:
            skipped_bullets[current_section] += 1
            if skipped_bullets[current_section] > 2:
                continue
        if len(line) > 220:
            line = trim_to_complete_sentence(line, 220)
        shortened.append(line)
    shortened_text = limit_channel_text_preserving_disclaimer(
        "\n".join(shortened),
        750,
    )
    logger.info(
        "channel_draft length chars=%s forbidden_left=%s",
        len(shortened_text),
        channel_text_has_forbidden_words(shortened_text),
    )
    return shortened_text


def build_social_caption_for_draft(
    match: dict,
    content_type: str,
    draft: str,
) -> str:
    home = format_channel_team_display(match.get("home")) or "Команда 1"
    away = format_channel_team_display(match.get("away")) or "Команда 2"
    score = format_channel_match_score(match)

    if content_type == "post_match":
        title = (
            f"{home} — {away} {score}"
            if score != "счёт не указан"
            else f"{home} — {away}"
        )
        hashtags = " ".join(SAFE_RECAP_SOCIAL_HASHTAGS)
        body = (
            "Проверяем AI-оценку MatchLab после матча: что подтвердилось, "
            "какие цифры оказались ключевыми и где игра получилась ближе, "
            "чем ожидалось."
        )
    else:
        title = f"{home} — {away}"
        hashtags = " ".join(SAFE_SOCIAL_HASHTAGS)
        body = (
            "Матч дня в MatchLab. AI-оценка показывает ключевые вероятности, "
            "статистические сигналы и риски перед игрой."
        )

    caption = "\n\n".join(
        [
            title,
            body,
            "Полный AI-разбор: @Match_Stat_bot\n"
            "Канал MatchLab: https://t.me/matchlab_ai",
            CHANNEL_DRAFT_DISCLAIMER,
            hashtags,
        ]
    )
    caption = limit_channel_text_preserving_disclaimer(caption, 900)
    caption = sanitize_channel_post_text(caption)
    return caption


def get_matchday_prompt_team_names(match: dict) -> tuple[str, str]:
    home_raw = match.get("home") or ""
    away_raw = match.get("away") or ""
    home = translate_team_name_ru(home_raw) or str(home_raw or "Команда 1")
    away = translate_team_name_ru(away_raw) or str(away_raw or "Команда 2")
    return home, away


def build_matchday_tg_cover_prompt(match: dict, draft: str | None = None) -> str:
    home, away = get_matchday_prompt_team_names(match)
    return f"""Сделай Telegram-обложку для MatchLab "Матч дня".

Формат:

* горизонтальная картинка 16:9
* размер 1280x720
* стиль: премиальная футбольная аналитика, спортивная ТВ-графика, тёмный кинематографичный стадион

Бренд:

* название: MATCHLAB
* подпись: ФУТБОЛЬНАЯ АНАЛИТИКА
* основной акцент: лаймово-зелёный
* стиль: современный спортивный, тёмный, контрастный
* если я прикрепил референс логотипа MatchLab, используй его стиль
* не придумывай другое название бренда

Матч:

* {home} — {away}

Текст на обложке:
MATCHLAB
ФУТБОЛЬНАЯ АНАЛИТИКА
МАТЧ ДНЯ
{home.upper()} — {away.upper()}
AI-РАЗБОР ДО МАТЧА

Композиция:

* фон: ночной футбольный стадион, прожекторы, дым, футбольное поле внизу
* логотип/название MatchLab сверху по центру
* крупный заголовок "МАТЧ ДНЯ" по центру
* ниже названия команд
* внизу "AI-РАЗБОР ДО МАТЧА"
* слева визуальная зона первой команды
* справа визуальная зона второй команды
* можно использовать цвета/флаги команд как вдохновение, но не использовать официальные эмблемы федераций
* текст должен быть крупным и читаемым

Важно:

* не добавлять другие слова
* не добавлять betting/gambling-лексику, betting-сокращения и коммерческие обещания результата
* не добавлять водяные знаки
* не добавлять людей
* не искажать MATCHLAB
* не искажать названия команд"""


def build_channel_full_ai_source_text(match: dict, analysis_result: dict) -> str:
    structured = analysis_result.get("structured")
    if isinstance(structured, dict) and structured:
        try:
            formatted = format_ai_analysis_text(structured)
        except Exception:
            formatted = ""
        if formatted:
            return formatted

    parts = [
        str(analysis_result.get("analysis") or "").strip(),
        json.dumps(
            {
                "match": {
                    "home": match.get("home"),
                    "away": match.get("away"),
                    "league": match.get("league"),
                    "round": match.get("round"),
                    "kickoff": match.get("kickoff"),
                },
                "structured": structured,
            },
            ensure_ascii=False,
            default=str,
        ),
    ]
    return "\n\n".join(part for part in parts if part)


def build_matchday_social_cards_prompt(match: dict, draft: str | None = None) -> str:
    home, away = get_matchday_prompt_team_names(match)
    source_text = str(draft or "").strip() or "Источник смысла пока не указан."
    return f"""Сделай 7 вертикальных карточек для TikTok/Instagram в стиле MatchLab.

Формат:

* 1080x1920
* вертикальные карточки
* каждая карточка отдельная
* стиль: тёмный футбольный стадион, лаймово-зелёные акценты, спортивная аналитика, крупная типографика
* логотип/название MATCHLAB должно быть на каждой карточке одинаковым по стилю
* если я прикрепил референс MatchLab, используй его как стиль бренда

Матч:
{home} — {away}

Карточка 1/7 — Обложка:
MATCHLAB
МАТЧ ДНЯ
{home.upper()} — {away.upper()}
AI-РАЗБОР ДО МАТЧА

Карточка 2/7 — AI-вероятности:
AI-ВЕРОЯТНОСТИ
Используй вероятности из источника смысла ниже.
Если вероятностей нет, не выдумывай проценты и сделай карточку без чисел.

Карточка 3/7 — Почему одна команда выше:
ПОЧЕМУ ОДНА КОМАНДА ВЫШЕ
3 коротких причины только из полного AI-разбора и входных данных.

Карточка 4/7 — Статистические сигналы:
СТАТИСТИЧЕСКИЕ СИГНАЛЫ
3 коротких пункта только из полного AI-разбора:

* атака / xG
* оборона / риски
* форма / темп / моменты

Карточка 5/7 — Осторожные сигналы:
ОСТОРОЖНЫЕ СИГНАЛЫ
2–3 коротких риска только из полного AI-разбора.

Карточка 6/7 — Риски матча:
РИСКИ МАТЧА
2–3 фактора, которые могут изменить сценарий, только если они есть в источнике.

Карточка 7/7 — Итоговый сценарий:
ИТОГОВЫЙ СЦЕНАРИЙ
1 короткий вывод.
Полный AI-разбор: @Match_Stat_bot
Это аналитика на основе данных, а не обещание результата.

Важно:

* карточки должны строиться только на полном AI-разборе и входных данных ниже
* не додумывать факты, травмы, составы, инсайды и турнирные детали
* если данных для пункта нет, не писать этот пункт
* каждая карточка должна быть законченным самостоятельным текстом
* не использовать запрещённую betting/gambling-лексику, betting-сокращения, коммерческие обещания результата и денежные формулировки
* не добавлять лишний текст
* если текст не помещается, сокращать, но не менять смысл
* не добавлять водяные знаки
* не искажать MATCHLAB
* не искажать названия команд

Полный AI-разбор и входные данные:
{source_text}"""


def get_recap_prompt_match_info(match: dict) -> dict:
    home_raw = match.get("home") or ""
    away_raw = match.get("away") or ""
    home = translate_team_name_ru(home_raw) or str(home_raw or "Команда 1")
    away = translate_team_name_ru(away_raw) or str(away_raw or "Команда 2")
    score = match.get("score") or {}
    home_score = score.get("home")
    away_score = score.get("away")
    score_available = home_score is not None and away_score is not None
    score_text = f"{home_score}:{away_score}" if score_available else "счёт не указан"
    return {
        "home": home,
        "away": away,
        "home_upper": home.upper(),
        "away_upper": away.upper(),
        "home_score": home_score,
        "away_score": away_score,
        "score_text": score_text,
        "score_available": score_available,
    }


def build_recap_tg_cover_prompt(match: dict, draft: str | None = None) -> str:
    info = get_recap_prompt_match_info(match)
    score_line = f"{info['score_text']}\n" if info["score_available"] else ""
    score_bullet = f"* счёт: {info['score_text']}" if info["score_available"] else "* счёт: не указывать, если его нет в источнике"
    return f"""Сделай Telegram-обложку для MatchLab "Итоги матча дня".

Формат:

* горизонтальная картинка 16:9
* размер 1280x720
* стиль: премиальная футбольная аналитика, спортивная ТВ-графика, тёмный кинематографичный стадион

Бренд:

* название: MATCHLAB
* подпись: ФУТБОЛЬНАЯ АНАЛИТИКА
* основной акцент: лаймово-зелёный
* стиль: современный спортивный, тёмный, контрастный
* если я прикрепил референс логотипа MatchLab, используй его стиль
* не придумывай другое название бренда

Матч:

* {info['home']} — {info['away']}
{score_bullet}

Текст на обложке:
MATCHLAB
ФУТБОЛЬНАЯ АНАЛИТИКА
ИТОГИ МАТЧА ДНЯ
{info['home_upper']} — {info['away_upper']}
{score_line}ПРОВЕРКА AI-РАЗБОРА

Композиция:

* фон: ночной футбольный стадион после матча, прожекторы, дым, атмосфера финального свистка
* логотип/название MatchLab сверху по центру
* крупный заголовок "ИТОГИ МАТЧА ДНЯ" по центру
* ниже названия команд
* ниже крупный счёт, только если он указан в источнике
* внизу "ПРОВЕРКА AI-РАЗБОРА"
* слева визуальная зона первой команды
* справа визуальная зона второй команды
* можно использовать цвета/флаги команд как вдохновение, но не использовать официальные эмблемы федераций
* текст должен быть крупным и читаемым

Важно:

* не добавлять другие слова
* не добавлять betting/gambling-лексику, betting-сокращения и коммерческие обещания результата
* не добавлять водяные знаки
* не добавлять людей
* не искажать MATCHLAB
* не искажать названия команд
* не искажать счёт"""


def build_recap_social_cards_prompt(match: dict, draft: str | None = None) -> str:
    info = get_recap_prompt_match_info(match)
    source_text = str(draft or "").strip() or "Источник смысла пока не указан."
    score_line = f"{info['score_text']}\n" if info["score_available"] else ""
    score_context = (
        f"Счёт: {info['score_text']}"
        if info["score_available"]
        else "Счёт: не указывать, если его нет в источнике"
    )
    return f"""Сделай 7 вертикальных карточек для TikTok/Instagram в стиле MatchLab.

Тема:
Итоги матча дня и проверка AI-разбора после игры.

Формат:

* 1080x1920
* вертикальные карточки
* каждая карточка отдельная
* стиль: тёмный футбольный стадион, лаймово-зелёные акценты, спортивная аналитика, крупная типографика
* логотип/название MATCHLAB должно быть на каждой карточке одинаковым по стилю
* если я прикрепил референс MatchLab, используй его как стиль бренда

Матч:
{info['home']} — {info['away']}
{score_context}

Карточка 1/7 — Обложка:
MATCHLAB
ИТОГИ МАТЧА ДНЯ
{info['home_upper']} — {info['away_upper']}
{score_line}ПРОВЕРКА AI-РАЗБОРА

Карточка 2/7 — AI-оценка до матча:
AI-ОЦЕНКА ДО МАТЧА
Используй вероятности из источника смысла ниже.
Если вероятностей нет, не выдумывай проценты и сделай карточку без чисел.

Карточка 3/7 — Что подтвердилось:
ЧТО ПОДТВЕРДИЛОСЬ
2–3 пункта, которые совпали с AI-разбором.

Карточка 4/7 — Главные цифры матча:
ГЛАВНЫЕ ЦИФРЫ
2–4 статистики из источника смысла:

* владение
* xG
* удары
* удары в створ
* угловые
Если статистики нет, не выдумывай числа.

Карточка 5/7 — Что не полностью совпало:
ЧТО НЕ СОВПАЛО ПОЛНОСТЬЮ
1–3 осторожных пункта.

Карточка 6/7 — Почему победитель был лучше:
ПОЧЕМУ ПОБЕДИТЕЛЬ БЫЛ ЛУЧШЕ
2–3 причины из источника смысла.
Если победителя нет, замени заголовок на "ПОЧЕМУ ИГРА БЫЛА РАВНОЙ".

Карточка 7/7 — Главный вывод:
ГЛАВНЫЙ ВЫВОД
1 короткий вывод.
Полный AI-разбор: @Match_Stat_bot
Это аналитика на основе данных, а не обещание результата.

Важно:

* не использовать betting/gambling-лексику, betting-сокращения, коммерческие обещания результата и денежные формулировки
* не добавлять лишний текст
* если текст не помещается, сокращать, но не менять смысл
* не добавлять водяные знаки
* не искажать MATCHLAB
* не искажать названия команд
* не искажать счёт
* не выдумывать статистику, если её нет в источнике

Источник смысла:
{source_text}"""


def get_channel_team_colors(name: str | None) -> tuple[str, str]:
    team_name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not team_name:
        return "#0f3f2f", "#0f2f4f"
    if team_name in TEAM_COLOR_OVERRIDES:
        return TEAM_COLOR_OVERRIDES[team_name]
    return TEAM_COLOR_OVERRIDES_CASEFOLD.get(team_name.casefold(), ("#0f3f2f", "#0f2f4f"))


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = str(color or "").strip().lstrip("#")
    if len(normalized) != 6:
        return (22, 163, 74)
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))


def mix_rgb(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    bounded_ratio = max(0.0, min(1.0, ratio))
    return tuple(
        int(first[index] * (1 - bounded_ratio) + second[index] * bounded_ratio)
        for index in range(3)
    )


def get_channel_cover_font(size: int, bold: bool = False):
    from PIL import ImageFont

    custom_candidates = []
    if bold:
        custom_candidates.append(MATCHLAB_CONDENSED_FONT_PATH)
    custom_candidates.append(MATCHLAB_FONT_PATH)
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    preferred = (
        *custom_candidates,
        *(candidates if bold else (candidates[1], candidates[0], *candidates[2:])),
    )
    for font_path in preferred:
        if not font_path or not Path(font_path).exists():
            continue
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            logger.debug(
                "channel_cover font load failed: path=%s",
                font_path,
                exc_info=True,
            )
            continue
    return ImageFont.load_default()


def load_cover_image(path: str, target_width: int, target_height: int):
    from PIL import Image

    image_path = Path(str(path or ""))
    if not image_path.exists():
        return None
    try:
        image = Image.open(image_path).convert("RGBA")
        source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            return None

        scale = max(target_width / source_width, target_height / source_height)
        resized_width = max(target_width, int(source_width * scale))
        resized_height = max(target_height, int(source_height * scale))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((resized_width, resized_height), resampling)

        left = max((resized_width - target_width) // 2, 0)
        top = max((resized_height - target_height) // 2, 0)
        return image.crop((left, top, left + target_width, top + target_height))
    except Exception:
        logger.debug(
            "channel_cover template load failed: path=%s",
            path,
            exc_info=True,
        )
        return None


def load_cover_logo(path: str, max_width: int, max_height: int):
    from PIL import Image

    logo_path = Path(str(path or ""))
    if not logo_path.exists():
        return None
    try:
        logo = Image.open(logo_path).convert("RGBA")
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        logo.thumbnail((max_width, max_height), resampling)
        return logo
    except Exception:
        logger.debug(
            "channel_cover logo load failed: path=%s",
            path,
            exc_info=True,
        )
        return None


def get_text_size(draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_channel_cover_font(
    draw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int = 34,
    bold: bool = True,
):
    for size in range(start_size, min_size - 1, -2):
        font = get_channel_cover_font(size, bold=bold)
        width, _ = get_text_size(draw, text, font)
        if width <= max_width:
            return font
    return get_channel_cover_font(min_size, bold=bold)


def draw_centered_text(
    draw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int] | str,
) -> None:
    width, height = get_text_size(draw, text, font)
    draw.text((xy[0] - width / 2, xy[1] - height / 2), text, font=font, fill=fill)


def draw_text_with_shadow(
    draw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int] | str,
    anchor: str = "mm",
    shadow_fill: tuple[int, int, int, int] | str = (0, 0, 0, 180),
    shadow_offset: int = 3,
) -> None:
    try:
        for x_offset, y_offset in (
            (-shadow_offset, 0),
            (shadow_offset, 0),
            (0, -shadow_offset),
            (0, shadow_offset),
            (shadow_offset, shadow_offset),
        ):
            draw.text(
                (xy[0] + x_offset, xy[1] + y_offset),
                text,
                font=font,
                fill=shadow_fill,
                anchor=anchor,
            )
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
    except Exception:
        if anchor == "mm":
            draw_centered_text(draw, xy, text, font, fill)
        else:
            draw.text(xy, text, font=font, fill=fill)


def generate_channel_matchday_cover(match: dict) -> str:
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1280, 720
    home_raw = match.get("home") or ""
    away_raw = match.get("away") or ""
    home_name = translate_team_name_ru(home_raw) or str(home_raw or "Команда 1")
    away_name = translate_team_name_ru(away_raw) or str(away_raw or "Команда 2")
    match_title = f"{home_name} — {away_name}"

    home_primary, home_secondary = get_channel_team_colors(home_raw)
    away_primary, away_secondary = get_channel_team_colors(away_raw)
    left_color = hex_to_rgb(home_primary)
    right_color = hex_to_rgb(away_primary)
    left_secondary = hex_to_rgb(home_secondary)
    right_secondary = hex_to_rgb(away_secondary)
    dark_base = (5, 10, 18)
    matchlab_accent = (132, 204, 22)

    background = load_cover_image(MATCHDAY_COVER_TEMPLATE_PATH, width, height)
    if background:
        logger.info(
            "channel_cover template used: path=%s",
            MATCHDAY_COVER_TEMPLATE_PATH,
        )
        image = background
    else:
        logger.info(
            "channel_cover template missing, fallback generated: path=%s",
            MATCHDAY_COVER_TEMPLATE_PATH,
        )
        image = Image.new("RGB", (width, height), dark_base)
        pixels = image.load()
        for y in range(height):
            vertical_ratio = y / max(height - 1, 1)
            for x in range(width):
                horizontal_ratio = x / max(width - 1, 1)
                team_mix = mix_rgb(left_color, right_color, horizontal_ratio)
                shade = mix_rgb(team_mix, dark_base, 0.55 + vertical_ratio * 0.25)
                pixels[x, y] = shade
        image = image.convert("RGBA")

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 44))
    draw.rectangle((0, 0, width // 2, height), fill=(*left_color, 54))
    draw.rectangle((width // 2, 0, width, height), fill=(*right_color, 54))
    draw.polygon(
        [(0, height), (0, 0), (width * 0.34, 0), (width * 0.18, height)],
        fill=(*left_secondary, 42),
    )
    draw.polygon(
        [(width, 0), (width, height), (width * 0.66, height), (width * 0.82, 0)],
        fill=(*right_secondary, 42),
    )
    for y in range(height):
        edge_ratio = max(0, (160 - min(y, height - y)) / 160)
        if edge_ratio:
            alpha = int(120 * edge_ratio)
            draw.line((0, y, width, y), fill=(0, 0, 0, alpha))
    draw.rounded_rectangle((70, 62, 1210, 658), radius=42, fill=(3, 7, 18, 112))
    draw.rounded_rectangle(
        (90, 82, 1190, 638),
        radius=34,
        outline=(255, 255, 255, 42),
        width=2,
    )
    draw.line((width // 2, 120, width // 2, 600), fill=(255, 255, 255, 34), width=3)
    draw.ellipse(
        (width // 2 - 105, height // 2 - 105, width // 2 + 105, height // 2 + 105),
        outline=(255, 255, 255, 36),
        width=3,
    )
    draw.ellipse(
        (width // 2 - 11, height // 2 - 11, width // 2 + 11, height // 2 + 11),
        fill=(*matchlab_accent, 190),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=0.2))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)
    logo = load_cover_logo(MATCHLAB_LOGO_PATH, max_width=420, max_height=120)
    logger.info(
        "channel_cover logo_used %s path=%s",
        bool(logo),
        MATCHLAB_LOGO_PATH,
    )
    custom_font_configured = any(
        Path(path).exists()
        for path in (MATCHLAB_FONT_PATH, MATCHLAB_CONDENSED_FONT_PATH)
        if path
    )
    logger.info(
        "channel_cover custom_font_configured %s",
        custom_font_configured,
    )

    brand_font = get_channel_cover_font(38, bold=True)
    label_font = get_channel_cover_font(58, bold=True)
    subtitle_font = get_channel_cover_font(40, bold=False)
    handle_font = get_channel_cover_font(34, bold=True)
    title_font = fit_channel_cover_font(draw, match_title, 1040, 78, 42, bold=True)

    if logo:
        image.alpha_composite(logo, ((width - logo.width) // 2, 96))
    else:
        draw.text((118, 108), "MatchLab", font=brand_font, fill=(236, 253, 245))
        brand_width, _ = get_text_size(draw, "MatchLab", brand_font)
        draw.rounded_rectangle(
            (118 + brand_width + 20, 111, 118 + brand_width + 92, 146),
            radius=16,
            fill=(*matchlab_accent, 220),
        )
        draw.text(
            (118 + brand_width + 38, 113),
            "AI",
            font=get_channel_cover_font(24, bold=True),
            fill=(5, 10, 18),
        )
    draw_text_with_shadow(
        draw,
        (width // 2, 230),
        "МАТЧ ДНЯ",
        label_font,
        (190, 242, 100),
        shadow_offset=4,
    )
    draw_text_with_shadow(
        draw,
        (width // 2, 352),
        match_title,
        title_font,
        (248, 250, 252),
        shadow_offset=5,
    )
    draw_text_with_shadow(
        draw,
        (width // 2, 454),
        "AI-РАЗБОР ДО МАТЧА",
        subtitle_font,
        (203, 213, 225),
        shadow_offset=3,
    )
    draw.rounded_rectangle(
        (width // 2 - 190, 545, width // 2 + 190, 600),
        radius=22,
        fill=(15, 23, 42, 210),
        outline=(*matchlab_accent, 190),
        width=2,
    )
    draw_text_with_shadow(
        draw,
        (width // 2, 572),
        "@Match_Stat_bot",
        handle_font,
        (236, 253, 245),
        shadow_offset=2,
    )

    cover_file = tempfile.NamedTemporaryFile(
        prefix="matchlab_matchday_",
        suffix=".png",
        delete=False,
    )
    cover_path = cover_file.name
    cover_file.close()
    image.convert("RGB").save(cover_path, "PNG", optimize=True)
    return cover_path


def get_channel_draft_keyboard(
    match_id: str,
    content_type: str = "pre_match",
) -> InlineKeyboardMarkup:
    choose_callback = (
        "channel_recap_again"
        if content_type == "post_match"
        else "channel_plan_again"
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎬 Описание TikTok/Instagram",
                    callback_data=f"channel_social_caption:{match_id}",
                )
            ],
            *(
                [
                    [
                        InlineKeyboardButton(
                            (
                                "🖼 Промпт TG-обложки итогов"
                                if content_type == "post_match"
                                else "🖼 Промпт TG-обложки"
                            ),
                            callback_data=f"channel_tg_cover_prompt:{match_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            (
                                "📱 Промпт 7 карточек итогов"
                                if content_type == "post_match"
                                else "📱 Промпт 7 карточек"
                            ),
                            callback_data=f"channel_social_cards_prompt:{match_id}",
                        )
                    ],
                ]
                if content_type in ("pre_match", "post_match")
                else []
            ),
            *(
                [
                    [
                        InlineKeyboardButton(
                            "📤 Опубликовать в канал",
                            callback_data=f"channel_publish:{match_id}",
                        )
                    ]
                ]
                if content_type == "pre_match"
                else []
            ),
            *(
                [
                    [
                        InlineKeyboardButton(
                            "📤 Опубликовать в канал",
                            callback_data=f"channel_publish:{match_id}",
                        )
                    ]
                ]
                if content_type == "post_match"
                else []
            ),
            [
                InlineKeyboardButton(
                    "Выбрать другой матч",
                    callback_data=choose_callback,
                )
            ],
        ]
    )


def get_channel_actual_result(match: dict) -> str:
    score = match.get("score") or {}
    home_score = score.get("home")
    away_score = score.get("away")
    if home_score is None or away_score is None:
        return "unknown"
    if home_score > away_score:
        return "home_win"
    if away_score > home_score:
        return "away_win"
    return "draw"


def get_channel_top_probability_key(structured: dict) -> str:
    probabilities = structured.get("outcome_probabilities") or {}
    values = {}
    for key in ("home_win", "draw", "away_win"):
        value = probabilities.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[key] = float(value)
            continue
        value_text = str(value or "").replace("%", "").strip()
        try:
            values[key] = float(value_text)
        except ValueError:
            continue
    if not values:
        return "unknown"
    return max(values.items(), key=lambda item: item[1])[0]


def get_channel_match_actual_stats(match: dict) -> dict:
    match_id = normalize_ai_analysis_match_id(match.get("id"))
    if not match_id:
        return {}
    logger.info("channel_recap actual stats fetch started: match_id=%s", match_id)

    try:
        statistics = format_miniapp_match_statistics(
            get_fixture_statistics(match_id),
            match.get("home_id"),
            match.get("away_id"),
        )
        if not statistics.get("available"):
            return {}

        stats_by_type = {
            item.get("type"): item
            for item in statistics.get("items") or []
            if item.get("type")
        }

        def get_pair(statistic_type: str) -> tuple[str | None, str | None]:
            item = stats_by_type.get(statistic_type) or {}
            return item.get("home"), item.get("away")

        actual_stats = {}
        mapping = {
            "Ball Possession": ("home_possession", "away_possession"),
            "Expected Goals": ("home_xg", "away_xg"),
            "Big Chances": ("home_big_chances", "away_big_chances"),
            "Total Shots": ("home_shots", "away_shots"),
            "Shots on Goal": ("home_shots_on_target", "away_shots_on_target"),
            "Corner Kicks": ("home_corners", "away_corners"),
        }
        for statistic_type, (home_key, away_key) in mapping.items():
            home_value, away_value = get_pair(statistic_type)
            if home_value is not None and away_value is not None:
                actual_stats[home_key] = home_value
                actual_stats[away_key] = away_value
        return actual_stats
    except Exception:
        logger.warning(
            "channel_recap actual stats load failed: match_id=%s",
            match_id,
            exc_info=True,
        )
        return {}


def get_channel_match_actual_events(match: dict) -> dict:
    match_id = normalize_ai_analysis_match_id(match.get("id"))
    if not match_id:
        return {}
    home_id = match.get("home_id")
    away_id = match.get("away_id")
    home = translate_team_name_ru(match.get("home")) or str(match.get("home") or "")
    away = translate_team_name_ru(match.get("away")) or str(match.get("away") or "")
    try:
        raw_events = get_fixture_events(match_id)
    except Exception:
        logger.warning(
            "channel_recap events load failed: match_id=%s",
            match_id,
            exc_info=True,
        )
        return {}

    home_score = 0
    away_score = 0
    goals = []
    red_cards = []
    penalties = []
    leaders = []
    late_decisive_goal = False

    for event in raw_events:
        if not isinstance(event, dict):
            continue
        formatted = format_miniapp_live_event(event)
        if not formatted:
            continue
        minute = formatted.get("time")
        extra = formatted.get("extra")
        minute_value = int(minute or 0)
        minute_label = f"{minute}'" if minute else "минута не указана"
        if extra:
            minute_label = f"{minute}+{extra}'" if minute else f"+{extra}'"
            minute_value += int(extra or 0)
        event_type = str(formatted.get("type") or "").casefold()
        detail = str(formatted.get("detail") or "").strip()
        detail_lower = detail.casefold()
        team_id = formatted.get("team_id")
        team_name = (
            home
            if team_id == home_id
            else away
            if team_id == away_id
            else translate_team_name_ru(formatted.get("team_name"))
            or formatted.get("team_name")
            or "Команда"
        )
        player = formatted.get("player") or team_name

        if event_type == "goal" and "missed" not in detail_lower:
            if team_id == home_id:
                home_score += 1
            elif team_id == away_id:
                away_score += 1
            score_after = f"{home_score}:{away_score}"
            goals.append(
                {
                    "minute": minute_label,
                    "minute_value": minute_value,
                    "team": team_name,
                    "player": player,
                    "detail": detail,
                    "score_after": score_after,
                }
            )
            if home_score > away_score:
                leaders.append("home")
            elif away_score > home_score:
                leaders.append("away")
            else:
                leaders.append("draw")
            if minute_value >= 85:
                late_decisive_goal = True
            if "penalty" in detail_lower:
                penalties.append(f"{minute_label} {team_name}: пенальти, счёт {score_after}")
        elif event_type == "card" and (
            "red" in detail_lower or "second yellow" in detail_lower
        ):
            red_cards.append(f"{minute_label} {team_name}: {player}")
        elif "penalty" in detail_lower:
            penalties.append(f"{minute_label} {team_name}: {detail}")

    score = match.get("score") or {}
    final_home = score.get("home")
    final_away = score.get("away")
    actual_result = get_channel_actual_result(match)
    expected_leader = None
    if goals:
        first_non_draw = next((leader for leader in leaders if leader != "draw"), None)
        expected_leader = first_non_draw
    comeback = bool(
        expected_leader
        and actual_result in {"home_win", "away_win"}
        and expected_leader != actual_result.replace("_win", "")
    )
    max_away_lead = 0
    max_home_lead = 0
    running_home = 0
    running_away = 0
    for goal in goals:
        score_after = goal.get("score_after") or "0:0"
        try:
            running_home, running_away = [int(part) for part in score_after.split(":", 1)]
        except Exception:
            continue
        max_home_lead = max(max_home_lead, running_home - running_away)
        max_away_lead = max(max_away_lead, running_away - running_home)

    status = str(match.get("status") or "").upper()
    extra_time = status == "AET" or any((goal.get("minute_value") or 0) > 90 for goal in goals)
    shootout = status == "PEN"
    return {
        "goals": goals,
        "red_cards": red_cards,
        "penalties": penalties,
        "extra_time": extra_time,
        "shootout": shootout,
        "comeback": comeback,
        "late_decisive_goal": late_decisive_goal,
        "max_home_lead": max_home_lead,
        "max_away_lead": max_away_lead,
        "final_score": f"{final_home}:{final_away}" if final_home is not None and final_away is not None else "",
    }


def get_channel_recap_event_lines(actual_events: dict, home: str, away: str) -> list[str]:
    lines = []
    for goal in (actual_events.get("goals") or [])[:8]:
        detail = f" ({goal.get('detail')})" if goal.get("detail") else ""
        lines.append(
            f"— {goal.get('minute')} {goal.get('team')}: {goal.get('player')}{detail}, счёт {goal.get('score_after')}"
        )
    for card in (actual_events.get("red_cards") or [])[:3]:
        lines.append(f"— Красная карточка: {card}")
    for penalty in (actual_events.get("penalties") or [])[:3]:
        lines.append(f"— Пенальти: {penalty}")
    if actual_events.get("extra_time"):
        lines.append("— Матч затронул овертайм.")
    if actual_events.get("shootout"):
        lines.append("— Победитель определился в серии пенальти.")
    return lines[:10]


def get_channel_recap_probability_line(
    label: str,
    value,
) -> str:
    return f"{label} — {format_channel_probability(value)}"


def get_channel_recap_expected_label(
    expected_result: str,
    home: str,
    away: str,
) -> str:
    if expected_result == "home_win":
        return home
    if expected_result == "away_win":
        return away
    if expected_result == "draw":
        return "ничью / близкий матч"
    return "несколько сценариев"


def get_channel_recap_result_text(
    actual_result: str,
    home: str,
    away: str,
) -> str:
    if actual_result == "home_win":
        return f"победа команды {home}"
    if actual_result == "away_win":
        return f"победа команды {away}"
    if actual_result == "draw":
        return "ничья"
    return "итоговый результат"


def is_channel_recap_minimal_margin(match: dict) -> bool:
    score = match.get("score") or {}
    home_score = score.get("home")
    away_score = score.get("away")
    if home_score is None or away_score is None:
        return False
    return abs(home_score - away_score) == 1


def get_channel_recap_stat_lines(actual_stats: dict) -> list[str]:
    stat_specs = [
        ("Владение", "home_possession", "away_possession"),
        ("xG", "home_xg", "away_xg"),
        ("Большие моменты", "home_big_chances", "away_big_chances"),
        ("Удары", "home_shots", "away_shots"),
        ("В створ", "home_shots_on_target", "away_shots_on_target"),
        ("Угловые", "home_corners", "away_corners"),
    ]
    lines = []
    for label, home_key, away_key in stat_specs:
        home_value = actual_stats.get(home_key)
        away_value = actual_stats.get(away_key)
        if home_value is None or away_value is None:
            continue
        lines.append(f"{label}: {home_value} — {away_value}")
    return lines[:6]


def build_channel_recap_post_draft(
    match: dict,
    analysis_result: dict,
    actual_stats: dict | None = None,
    actual_events: dict | None = None,
) -> str:
    structured = analysis_result.get("structured") or {}
    home_raw = match.get("home") or analysis_result.get("home_team") or ""
    away_raw = match.get("away") or analysis_result.get("away_team") or ""
    home = translate_team_name_ru(home_raw) or "Команда 1"
    away = translate_team_name_ru(away_raw) or "Команда 2"
    score = format_channel_match_score(match)
    home_flag = get_team_flag_emoji(home_raw)
    away_flag = get_team_flag_emoji(away_raw)
    header_parts = [
        f"{home_flag} {home}".strip(),
        "—",
        away,
        score,
        away_flag,
    ]
    header = " ".join(part for part in header_parts if part).strip()
    probabilities = structured.get("outcome_probabilities") or {}
    actual_stats = actual_stats or {}
    actual_events = actual_events or {}
    stat_lines = get_channel_recap_stat_lines(actual_stats)
    event_lines = get_channel_recap_event_lines(actual_events, home, away)
    actual_result = get_channel_actual_result(match)
    expected_result = get_channel_top_probability_key(structured)
    expected_label = get_channel_recap_expected_label(expected_result, home, away)
    actual_text = get_channel_recap_result_text(actual_result, home, away)
    favorite_probability = None
    if expected_result in probabilities:
        probability_value = probabilities.get(expected_result)
        if isinstance(probability_value, (int, float)) and not isinstance(
            probability_value,
            bool,
        ):
            favorite_probability = float(probability_value)
        else:
            try:
                favorite_probability = float(
                    str(probability_value or "").replace("%", "").strip()
                )
            except ValueError:
                favorite_probability = None
    can_say_same_direction = (
        actual_result == expected_result
        and actual_result != "unknown"
        and favorite_probability is not None
        and favorite_probability >= 45
    )
    logger.info(
        "channel_recap probabilities: home=%s draw=%s away=%s expected=%s",
        probabilities.get("home_win"),
        probabilities.get("draw"),
        probabilities.get("away_win"),
        expected_result,
    )
    logger.info(
        "channel_recap comparison result: actual_result=%s expected_result=%s",
        actual_result,
        expected_result,
    )

    difficult_same_direction = bool(
        can_say_same_direction
        and (
            actual_events.get("comeback")
            or actual_events.get("late_decisive_goal")
            or actual_events.get("extra_time")
            or actual_events.get("shootout")
            or actual_events.get("penalties")
        )
    )
    near_upset = bool(
        actual_result == "home_win"
        and (actual_events.get("max_away_lead") or 0) >= 2
    ) or bool(
        actual_result == "away_win"
        and (actual_events.get("max_home_lead") or 0) >= 2
    )

    if difficult_same_direction:
        winner = home if actual_result == "home_win" else away
        post_match_text = (
            f"Итог совпал с направлением AI-оценки: {winner} выиграла {score}. "
            "Но сценарий был намного сложнее, чем показывает финальный счёт."
        )
        if near_upset:
            opponent = away if actual_result == "home_win" else home
            post_match_text += (
                f" {opponent} вела с разницей в два мяча и была близка к сенсации."
            )
    elif actual_result == expected_result and actual_result == "draw":
        post_match_text = (
            f"После матча сценарий близкой игры подтвердился: команды "
            f"завершили встречу вничью {score}."
        )
    elif can_say_same_direction:
        winner = home if actual_result == "home_win" else away
        post_match_text = f"После матча направление AI-оценки совпало: {winner} выиграла {score}."
    elif actual_result == expected_result and actual_result != "unknown":
        winner = home if actual_result == "home_win" else away
        post_match_text = (
            f"Победитель совпал с верхним направлением AI-оценки: {winner} "
            f"выиграла {score}. Но до матча перевес не выглядел большим."
        )
    elif actual_result != "unknown" and expected_result != "unknown":
        post_match_text = (
            "После матча итоговый результат разошёлся с главным направлением "
            f"AI-оценки: {actual_text}."
        )
    else:
        post_match_text = (
            "После матча можно сравнить сохранённую AI-оценку с итогом, "
            "но расширенных данных пока мало."
        )

    if difficult_same_direction:
        matched_text = (
            "Направление по победителю совпало, но ход матча был напряжённее: "
            "важными стали поздние эпизоды, пенальти, овертайм или камбэк."
        )
    elif actual_result == expected_result == "draw":
        matched_text = (
            "AI-оценка заранее показывала близкий матч, и итоговый счёт это подтвердил."
        )
    elif can_say_same_direction and stat_lines:
        winner = home if actual_result == "home_win" else away
        matched_text = (
            f"{winner} контролировала ключевые фазы, создала больше моментов "
            "и чаще доводила атаки до ударов."
        )
    elif can_say_same_direction:
        matched_text = "Главное направление AI-оценки совпало с итоговым результатом."
    elif actual_result == expected_result and actual_result != "unknown":
        matched_text = (
            "Победитель совпал с верхним направлением AI-оценки, но перевес "
            "до игры был умеренным."
        )
    else:
        matched_text = (
            "Часть контекста до игры помогла увидеть риски и возможный темп матча."
        )

    if actual_result != expected_result and expected_result != "unknown":
        caution_title = "⚠️ Что не совпало:"
        caution_text = (
            "Итоговый результат разошёлся с главным направлением AI-оценки. "
            "Футбол оставил пространство для риска."
        )
        conclusion = (
            "Главный вывод: AI-оценка дала полезный контекст, но итоговый "
            "результат оказался другим."
        )
    elif difficult_same_direction:
        caution_title = "⚠️ Что было сложнее по сценарию:"
        caution_text = (
            "Победитель совпал с главным направлением AI-оценки, но матч был "
            "намного тяжелее: сценарий решали поздние эпизоды, камбэк, пенальти "
            "или дополнительное время."
        )
        if near_upset:
            opponent = away if actual_result == "home_win" else home
            caution_text += f" {opponent} была близка к сенсации."
        conclusion = (
            "Главный вывод: направление AI-оценки совпало по победителю, "
            "но ход матча был намного ближе и сложнее."
        )
    elif is_channel_recap_minimal_margin(match):
        caution_title = "⚠️ Что было ближе по табло:"
        loser = away if actual_result == "home_win" else home
        caution_text = (
            f"{loser} сохранила интригу до конца. Поэтому счёт {score} "
            "выглядит ближе, чем сама картина матча."
        )
        winner = home if actual_result == "home_win" else away
        conclusion = (
            f"Главный вывод: AI-оценка верно уловила перевес {winner}, "
            "но итоговый счёт получился напряжённее, чем статистика."
        )
    else:
        caution_title = "⚠️ Что не совпало:"
        caution_text = "Для точной оценки нужны расширенные события матча."
        conclusion = (
            "Главный вывод: AI-оценка верно уловила направление матча, "
            "но для глубокой проверки нужны расширенные данные."
        )

    lines = [
        header,
        "Итоги матча дня от MatchLab",
        "",
        f"До игры AI-оценка выделяла {expected_label}:",
        "",
        get_channel_recap_probability_line(home, probabilities.get("home_win")),
        get_channel_recap_probability_line("Ничья", probabilities.get("draw")),
        get_channel_recap_probability_line(away, probabilities.get("away_win")),
        "",
        post_match_text,
    ]
    lines.extend(["", "📊 Главные цифры:"])
    if stat_lines:
        lines.extend(["", *stat_lines])
    else:
        lines.append("Расширенная статистика по матчу ограничена.")
    if event_lines:
        lines.extend(["", "🎞 События матча:", *event_lines])
    lines.extend(
        [
            "",
            "✅ Что совпало:",
            matched_text,
            "",
            caution_title,
            caution_text,
            "",
            conclusion,
            "",
            "Полный AI-разбор: @Match_Stat_bot",
            "",
            CHANNEL_DRAFT_DISCLAIMER,
        ]
    )
    draft = limit_channel_text_preserving_disclaimer(
        "\n".join(lines),
        CHANNEL_RECAP_DRAFT_MAX_CHARS,
    )
    logger.info(
        "channel_recap_draft length chars=%s forbidden_left=%s",
        len(draft),
        channel_text_has_forbidden_words(draft),
    )
    return draft


def get_or_create_channel_match_ai_analysis(
    admin_id: int,
    match: dict,
) -> tuple[dict | None, bool, bool]:
    raw_match_id = str(match.get("id") or "").strip()
    match_id = normalize_ai_analysis_match_id(raw_match_id)
    generated = False
    logger.info(
        "channel_draft AI source lookup started: admin_id=%s raw_match_id=%s "
        "normalized_match_id=%s source=channel_agent",
        admin_id,
        raw_match_id,
        match_id,
    )

    for lookup_mode in ("premium", "default"):
        logger.info(
            "channel_draft cache lookup mode=%s match_id=%s",
            lookup_mode,
            match_id,
        )
        saved_analysis = None
        try:
            saved_analysis, match_id = lookup_saved_miniapp_ai_analysis(
                admin_id,
                match_id,
                lookup_mode,
            )
        except Exception:
            logger.warning(
                "channel_draft personal AI lookup failed: raw_match_id=%s "
                "normalized_match_id=%s analysis_mode=%s",
                raw_match_id,
                match_id,
                lookup_mode,
                exc_info=True,
            )
        logger.info(
            "channel_draft personal saved found %s: admin_id=%s "
            "raw_match_id=%s normalized_match_id=%s saved_match_id=%s "
            "mode=%s",
            bool(saved_analysis),
            admin_id,
            raw_match_id,
            match_id,
            match_id,
            lookup_mode,
        )
        if saved_analysis:
            source_name = f"personal_cache_{lookup_mode}"
            logger.info(
                "channel_draft AI source selected %s: admin_id=%s "
                "saved_match_id=%s analysis_mode=%s",
                source_name,
                admin_id,
                match_id,
                lookup_mode,
            )
            return saved_analysis, True, generated

        global_analysis = get_global_miniapp_ai_analysis(match_id, lookup_mode)
        logger.info(
            "channel_draft global cache found %s: match_id=%s mode=%s",
            bool(global_analysis),
            match_id,
            lookup_mode,
        )
        if global_analysis:
            personal_saved = save_miniapp_ai_analysis(
                admin_id,
                match_id,
                global_analysis.get("analysis") or "",
                global_analysis.get("structured"),
                lookup_mode,
                global_analysis.get("home_team") or "",
                global_analysis.get("away_team") or "",
                global_analysis.get("league") or "",
            )
            logger.info(
                "channel_draft personal analysis saved %s: admin_id=%s "
                "match_id=%s analysis_mode=%s",
                personal_saved,
                admin_id,
                match_id,
                lookup_mode,
            )
            verify_miniapp_ai_personal_save(admin_id, match_id, lookup_mode)
            source_name = f"global_cache_{lookup_mode}"
            logger.info(
                "channel_draft AI source selected %s: match_id=%s "
                "analysis_mode=%s",
                source_name,
                match_id,
                lookup_mode,
            )
            return global_analysis, True, generated

    logger.info("channel_draft saved/global AI found false")
    analysis_mode = "premium"
    logger.info(
        "channel_draft OpenAI generation required true: match_id=%s analysis_mode=%s",
        match_id,
        analysis_mode,
    )
    match_data = build_miniapp_ai_match_data(match)
    analysis_result = get_openai_ai_analysis_result(match_data, analysis_mode)
    analysis = analysis_result.get("analysis") or ""
    structured = analysis_result.get("structured")
    if not is_saveable_miniapp_ai_analysis(analysis, structured):
        logger.info("channel_draft AI generated false")
        return None, False, generated

    generated = True
    logger.info("channel_draft AI generated true")
    global_saved = save_global_miniapp_ai_analysis(
        match_id,
        analysis,
        structured,
        analysis_mode,
        match.get("home") or "",
        match.get("away") or "",
        match.get("league") or "",
    )
    logger.info(
        "channel_draft global cache saved %s: match_id=%s analysis_mode=%s",
        global_saved,
        match_id,
        analysis_mode,
    )
    verify_miniapp_ai_global_save(match_id, analysis_mode)
    personal_saved = save_miniapp_ai_analysis(
        admin_id,
        match_id,
        analysis,
        structured,
        analysis_mode,
        match.get("home") or "",
        match.get("away") or "",
        match.get("league") or "",
    )
    logger.info(
        "channel_draft personal analysis saved %s: admin_id=%s match_id=%s analysis_mode=%s",
        personal_saved,
        admin_id,
        match_id,
        analysis_mode,
    )
    verify_miniapp_ai_personal_save(admin_id, match_id, analysis_mode)
    logger.info(
        "channel_draft AI source selected openai_generated_premium: "
        "match_id=%s analysis_mode=%s",
        match_id,
        analysis_mode,
    )
    return {
        "analysis": analysis,
        "structured": structured,
        "analysis_mode": analysis_mode,
        "home_team": match.get("home") or "",
        "away_team": match.get("away") or "",
        "league": match.get("league") or "",
    }, False, generated


def is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


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


def get_miniapp_favorite_teams(telegram_user_id: int) -> list[dict]:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    team_id,
                    team_name,
                    team_logo,
                    team_country,
                    created_at
                FROM miniapp_favorite_teams
                WHERE telegram_user_id = %s
                ORDER BY created_at DESC, team_name ASC;
                """,
                (telegram_user_id,),
            )
            rows = cursor.fetchall()
    finally:
        if connection is not None:
            connection.close()

    return [
        {
            "team_id": int(row["team_id"]),
            "team_name": row["team_name"],
            "team_logo": row.get("team_logo"),
            "team_country": row.get("team_country") or "",
            "created_at": serialize_api_datetime(row.get("created_at")),
        }
        for row in rows
    ]


def add_miniapp_favorite_team(
    telegram_user_id: int,
    team: dict,
) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO miniapp_favorite_teams (
                    telegram_user_id,
                    team_id,
                    team_name,
                    team_logo,
                    team_country
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (telegram_user_id, team_id)
                DO UPDATE SET
                    team_name = EXCLUDED.team_name,
                    team_logo = EXCLUDED.team_logo,
                    team_country = EXCLUDED.team_country;
                """,
                (
                    telegram_user_id,
                    team["id"],
                    team["name"],
                    team.get("logo"),
                    team.get("country") or "",
                ),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def remove_miniapp_favorite_team(
    telegram_user_id: int,
    team_id: int,
) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM miniapp_favorite_teams
                WHERE telegram_user_id = %s AND team_id = %s;
                """,
                (telegram_user_id, team_id),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def get_miniapp_match_reminders(telegram_user_id: int) -> list[dict]:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    match_id,
                    home_team,
                    away_team,
                    league,
                    kickoff,
                    notify_at,
                    is_sent
                FROM miniapp_match_reminders
                WHERE telegram_user_id = %s
                  AND kickoff >= CURRENT_TIMESTAMP - INTERVAL '4 hours'
                ORDER BY kickoff ASC;
                """,
                (telegram_user_id,),
            )
            rows = cursor.fetchall()
    finally:
        if connection is not None:
            connection.close()

    return [
        {
            "match_id": row["match_id"],
            "home_team": row.get("home_team") or "",
            "away_team": row.get("away_team") or "",
            "league": row.get("league") or "",
            "kickoff": serialize_api_datetime(row.get("kickoff")),
            "notify_at": serialize_api_datetime(row.get("notify_at")),
            "is_sent": bool(row.get("is_sent")),
        }
        for row in rows
    ]


def add_miniapp_match_reminder(
    telegram_user_id: int,
    match: dict,
) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO miniapp_match_reminders (
                    telegram_user_id,
                    match_id,
                    home_team,
                    away_team,
                    league,
                    kickoff,
                    notify_at,
                    is_sent
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s::timestamptz,
                    %s::timestamptz - INTERVAL '1 hour',
                    FALSE
                )
                ON CONFLICT (telegram_user_id, match_id)
                DO UPDATE SET
                    home_team = EXCLUDED.home_team,
                    away_team = EXCLUDED.away_team,
                    league = EXCLUDED.league,
                    kickoff = EXCLUDED.kickoff,
                    notify_at = EXCLUDED.notify_at,
                    is_sent = FALSE;
                """,
                (
                    telegram_user_id,
                    match["id"],
                    match.get("home") or "",
                    match.get("away") or "",
                    match.get("league") or "",
                    match["kickoff"],
                    match["kickoff"],
                ),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def remove_miniapp_match_reminder(
    telegram_user_id: int,
    match_id: str,
) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM miniapp_match_reminders
                WHERE telegram_user_id = %s AND match_id = %s;
                """,
                (telegram_user_id, match_id),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def get_pending_miniapp_match_reminders(limit: int = 20) -> list[dict]:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; match reminders were not checked"
        )
        return []

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    telegram_user_id,
                    match_id,
                    home_team,
                    away_team,
                    league,
                    kickoff
                FROM miniapp_match_reminders
                WHERE is_sent = FALSE
                  AND notify_at <= CURRENT_TIMESTAMP
                  AND kickoff > CURRENT_TIMESTAMP
                ORDER BY notify_at ASC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
    finally:
        if connection is not None:
            connection.close()

    return [dict(row) for row in rows]


def mark_miniapp_match_reminder_sent(reminder_id: int) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE miniapp_match_reminders
                SET is_sent = TRUE
                WHERE id = %s AND is_sent = FALSE;
                """,
                (reminder_id,),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def get_pending_lineup_notification_reminders(
    limit: int = 20,
) -> list[dict]:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; lineup reminders were not checked"
        )
        return []

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    telegram_user_id,
                    match_id,
                    home_team,
                    away_team,
                    league,
                    kickoff
                FROM miniapp_match_reminders
                WHERE lineups_notified = FALSE
                  AND kickoff > CURRENT_TIMESTAMP
                  AND kickoff <= CURRENT_TIMESTAMP + INTERVAL '3 hours'
                ORDER BY kickoff ASC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
    finally:
        if connection is not None:
            connection.close()

    return [dict(row) for row in rows]


def mark_miniapp_lineups_notified(reminder_id: int) -> None:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE miniapp_match_reminders
                SET lineups_notified = TRUE
                WHERE id = %s AND lineups_notified = FALSE;
                """,
                (reminder_id,),
            )
        connection.commit()
    finally:
        if connection is not None:
            connection.close()


def get_active_event_notification_reminders(
    limit: int = 30,
) -> list[dict]:
    database_url = get_database_url()
    if not database_url:
        logger.warning(
            "DATABASE_URL is not configured; event reminders were not checked"
        )
        return []

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    telegram_user_id,
                    match_id,
                    home_team,
                    away_team,
                    league,
                    kickoff
                FROM miniapp_match_reminders
                WHERE kickoff <= CURRENT_TIMESTAMP + INTERVAL '10 minutes'
                  AND kickoff >= CURRENT_TIMESTAMP - INTERVAL '3 hours'
                ORDER BY kickoff ASC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
    finally:
        if connection is not None:
            connection.close()

    return [dict(row) for row in rows]


def was_miniapp_event_notification_sent(
    telegram_user_id: int,
    match_id: str,
    event_key: str,
) -> bool:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM miniapp_match_event_notifications
                WHERE telegram_user_id = %s
                  AND match_id = %s
                  AND event_key = %s
                LIMIT 1;
                """,
                (telegram_user_id, match_id, event_key),
            )
            return cursor.fetchone() is not None
    finally:
        if connection is not None:
            connection.close()


def save_miniapp_event_notification(
    telegram_user_id: int,
    match_id: str,
    event_key: str,
    event_type: str,
    event_time,
) -> bool:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    normalized_event_time = (
        int(event_time)
        if isinstance(event_time, (int, float)) and not isinstance(event_time, bool)
        else None
    )
    connection = None
    try:
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO miniapp_match_event_notifications (
                    telegram_user_id,
                    match_id,
                    event_key,
                    event_type,
                    event_time
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (telegram_user_id, match_id, event_key)
                DO NOTHING;
                """,
                (
                    telegram_user_id,
                    match_id,
                    event_key,
                    event_type,
                    normalized_event_time,
                ),
            )
            inserted = cursor.rowcount == 1
        connection.commit()
        return inserted
    finally:
        if connection is not None:
            connection.close()


def format_match_reminder_kickoff(kickoff) -> str:
    if not isinstance(kickoff, datetime):
        return "время уточняется"

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    kickoff_almaty = kickoff.astimezone(ALMATY_TZ)
    month_names = (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    return (
        f"{kickoff_almaty.day} "
        f"{month_names[kickoff_almaty.month - 1]}, "
        f"{kickoff_almaty.strftime('%H:%M')}"
    )


def build_miniapp_match_reminder_message(reminder: dict) -> str:
    home_team = reminder.get("home_team") or "Хозяева"
    away_team = reminder.get("away_team") or "Гости"
    league = reminder.get("league") or "Турнир не указан"
    kickoff_text = format_match_reminder_kickoff(reminder.get("kickoff"))
    return (
        "🔔 Напоминание MatchLab\n\n"
        "Через 1 час матч:\n"
        f"{home_team} — {away_team}\n\n"
        f"Турнир: {league}\n"
        f"Начало: {kickoff_text}\n\n"
        "Открыть MatchLab 👇"
    )


def build_miniapp_lineups_available_message(reminder: dict) -> str:
    home_team = reminder.get("home_team") or "Хозяева"
    away_team = reminder.get("away_team") or "Гости"
    return (
        "📋 Составы доступны\n\n"
        f"{home_team} — {away_team}\n\n"
        "Стартовые составы опубликованы.\n"
        "Откройте MatchLab, чтобы посмотреть игроков и запасных."
    )


def format_miniapp_event_minute(event_time, event_extra=None) -> str:
    if not isinstance(event_time, (int, float)) or isinstance(event_time, bool):
        return "Минута не указана"

    minute = str(int(event_time))
    if (
        isinstance(event_extra, (int, float))
        and not isinstance(event_extra, bool)
        and event_extra > 0
    ):
        minute += f"+{int(event_extra)}"
    return f"{minute}’"


def build_miniapp_event_notification_message(
    reminder: dict,
    event_type: str,
    event: dict | None,
    home_score,
    away_score,
) -> str:
    home_team = reminder.get("home_team") or "Хозяева"
    away_team = reminder.get("away_team") or "Гости"
    score_text = (
        f"{home_score}:{away_score}"
        if home_score is not None and away_score is not None
        else "не указан"
    )

    if event_type == "match_finished":
        return (
            "✅ Матч завершён\n\n"
            f"{home_team} — {away_team}\n"
            f"Итоговый счёт: {score_text}"
        )

    event = event or {}
    event_time = event.get("time") or {}
    minute_text = format_miniapp_event_minute(
        event_time.get("elapsed"),
        event_time.get("extra"),
    )
    player = event.get("player")
    if not isinstance(player, dict):
        player = {}
    team = event.get("team")
    if not isinstance(team, dict):
        team = {}
    assist = event.get("assist")
    if not isinstance(assist, dict):
        assist = {}

    player_name = str(player.get("name") or "").strip()
    team_name = str(team.get("name") or "").strip()
    participant_name = player_name or team_name or "Игрок не указан"
    assist_name = str(assist.get("name") or "").strip()
    detail = str(event.get("detail") or "").strip()
    comments = str(event.get("comments") or "").strip()
    titles = {
        "goal": "⚽ Гол!",
        "red_card": "🟥 Красная карточка",
        "penalty": "🥅 Пенальти",
    }
    participant_line = (
        f"{minute_text} — {participant_name}"
        if minute_text == "Минута не указана"
        else f"{minute_text} {participant_name}"
    )
    lines = [
        titles.get(event_type, "📝 Событие матча"),
        "",
        f"{home_team} — {away_team}",
        participant_line,
    ]
    if event_type == "goal":
        lines.extend(["", f"Счёт: {score_text}"])
        if assist_name:
            lines.append(f"Ассист: {assist_name}")
    elif event_type == "penalty":
        penalty_detail = comments or detail
        if penalty_detail:
            lines.append(penalty_detail)
    return "\n".join(lines)


def classify_miniapp_push_event(event: dict) -> str | None:
    if not isinstance(event, dict):
        return None

    event_type = str(event.get("type") or "").strip().lower()
    detail = str(event.get("detail") or "").strip().lower()
    comments = str(event.get("comments") or "").strip().lower()
    event_text = f"{detail} {comments}"

    if "penalty" in event_text:
        return "penalty"

    if event_type == "card" and (
        "red" in detail or "second yellow" in detail
    ):
        return "red_card"

    if event_type == "var" and "red" in event_text:
        return "red_card"

    if event_type == "goal":
        return "goal"

    if (
        event_type == "var"
        and "goal" in event_text
        and "cancel" not in event_text
        and "disallow" not in event_text
    ):
        return "goal"

    return None


def build_miniapp_event_key(match_id: str, event: dict) -> str:
    event_time = event.get("time")
    if not isinstance(event_time, dict):
        event_time = {}
    team = event.get("team")
    if not isinstance(team, dict):
        team = {}
    player = event.get("player")
    if not isinstance(player, dict):
        player = {}

    player_key = player.get("id") or player.get("name") or ""
    key_parts = (
        match_id,
        event_time.get("elapsed"),
        event_time.get("extra"),
        team.get("id"),
        event.get("type"),
        event.get("detail"),
        player_key,
    )
    return ":".join(str(part or "").strip() for part in key_parts)


async def check_and_send_miniapp_match_reminders(bot) -> None:
    try:
        reminders = get_pending_miniapp_match_reminders(limit=20)
    except Exception:
        logger.exception("Failed to load pending Mini App match reminders")
        return

    logger.info("Pending Mini App match reminders found: %s", len(reminders))

    for reminder in reminders:
        telegram_user_id = int(reminder["telegram_user_id"])
        match_id = str(reminder["match_id"])
        try:
            await bot.send_message(
                chat_id=telegram_user_id,
                text=build_miniapp_match_reminder_message(reminder),
                reply_markup=build_miniapp_inline_keyboard(
                    params={"match_id": match_id}
                ),
            )
        except Exception:
            logger.warning(
                "Failed to send Mini App match reminder: "
                "user_id=%s match_id=%s",
                telegram_user_id,
                match_id,
                exc_info=True,
            )
            continue

        try:
            mark_miniapp_match_reminder_sent(int(reminder["id"]))
        except Exception:
            logger.exception(
                "Failed to mark Mini App match reminder as sent: "
                "user_id=%s match_id=%s",
                telegram_user_id,
                match_id,
            )
            continue

        logger.info(
            "Mini App match reminder sent: user_id=%s match_id=%s",
            telegram_user_id,
            match_id,
        )


async def check_and_send_miniapp_lineup_notifications(bot) -> None:
    try:
        reminders = get_pending_lineup_notification_reminders(limit=20)
    except Exception:
        logger.exception(
            "Failed to load pending Mini App lineup notifications"
        )
        return

    logger.info(
        "Pending Mini App lineup notifications found: %s",
        len(reminders),
    )

    for reminder in reminders:
        telegram_user_id = int(reminder["telegram_user_id"])
        match_id = str(reminder["match_id"])
        lineups = get_fixture_lineups(match_id)
        if not lineups:
            logger.debug(
                "Mini App lineups not available yet: "
                "user_id=%s match_id=%s",
                telegram_user_id,
                match_id,
            )
            continue

        try:
            await bot.send_message(
                chat_id=telegram_user_id,
                text=build_miniapp_lineups_available_message(reminder),
                reply_markup=build_miniapp_inline_keyboard(
                    params={"match_id": match_id}
                ),
            )
        except Exception:
            logger.warning(
                "Failed to send Mini App lineup notification: "
                "user_id=%s match_id=%s",
                telegram_user_id,
                match_id,
                exc_info=True,
            )
            continue

        try:
            mark_miniapp_lineups_notified(int(reminder["id"]))
        except Exception:
            logger.exception(
                "Failed to mark Mini App lineups as notified: "
                "user_id=%s match_id=%s",
                telegram_user_id,
                match_id,
            )
            continue

        logger.info(
            "Mini App lineup notification sent: user_id=%s match_id=%s",
            telegram_user_id,
            match_id,
        )


async def check_and_send_miniapp_event_notifications(bot) -> None:
    try:
        reminders = get_active_event_notification_reminders(limit=30)
    except Exception:
        logger.exception(
            "Failed to load active Mini App event notification reminders"
        )
        return

    reminders_by_match = {}
    for reminder in reminders:
        match_id = str(reminder.get("match_id") or "").strip()
        if match_id:
            reminders_by_match.setdefault(match_id, []).append(reminder)

    logger.info(
        "Active Mini App event reminders found: %s; unique matches: %s",
        len(reminders),
        len(reminders_by_match),
    )

    sent_count = 0
    for match_id, match_reminders in reminders_by_match.items():
        fixture_item = get_fixture_by_id(match_id)
        if not fixture_item:
            continue

        fixture = fixture_item.get("fixture") or {}
        status = fixture.get("status") or {}
        status_short = str(status.get("short") or "").strip().upper()
        goals = fixture_item.get("goals") or {}
        home_score = format_miniapp_score_value(goals.get("home"))
        away_score = format_miniapp_score_value(goals.get("away"))
        logger.info(
            "Mini App event match check: match_id=%s status=%s",
            match_id,
            status_short or "unknown",
        )

        notification_items = []
        if is_miniapp_fixture_live_status(status_short):
            raw_events = get_fixture_events(match_id)
            for event in raw_events:
                event_type = classify_miniapp_push_event(event)
                if not event_type:
                    continue
                event_time = event.get("time") or {}
                notification_items.append(
                    {
                        "event_key": build_miniapp_event_key(match_id, event),
                        "event_type": event_type,
                        "event_time": event_time.get("elapsed"),
                        "event": event,
                    }
                )
        elif is_miniapp_fixture_finished_status(status_short):
            notification_items.append(
                {
                    "event_key": f"{match_id}:match_finished",
                    "event_type": "match_finished",
                    "event_time": status.get("elapsed"),
                    "event": None,
                }
            )
        else:
            continue

        logger.info(
            "Important Mini App match events found: match_id=%s events=%s",
            match_id,
            len(notification_items),
        )

        for reminder in match_reminders:
            telegram_user_id = int(reminder["telegram_user_id"])
            for notification in notification_items:
                try:
                    inserted = save_miniapp_event_notification(
                        telegram_user_id,
                        match_id,
                        notification["event_key"],
                        notification["event_type"],
                        notification["event_time"],
                    )
                except Exception:
                    logger.exception(
                        "Failed to reserve Mini App event notification: "
                        "user_id=%s match_id=%s event_key=%s event_type=%s",
                        telegram_user_id,
                        match_id,
                        notification["event_key"],
                        notification["event_type"],
                    )
                    continue

                if not inserted:
                    continue

                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=build_miniapp_event_notification_message(
                            reminder,
                            notification["event_type"],
                            notification["event"],
                            home_score,
                            away_score,
                        ),
                        reply_markup=build_miniapp_inline_keyboard(
                            params={"match_id": match_id}
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Failed to send Mini App event notification: "
                        "user_id=%s match_id=%s event_key=%s event_type=%s",
                        telegram_user_id,
                        match_id,
                        notification["event_key"],
                        notification["event_type"],
                        exc_info=True,
                    )
                    continue

                sent_count += 1
                logger.info(
                    "Mini App event notification sent: "
                    "user_id=%s match_id=%s event_type=%s",
                    telegram_user_id,
                    match_id,
                    notification["event_type"],
                )

    logger.info(
        "Mini App event notifications sent in cycle: %s",
        sent_count,
    )


async def miniapp_match_reminders_loop(bot) -> None:
    try:
        await asyncio.sleep(10)
        while True:
            await check_and_send_miniapp_match_reminders(bot)
            await check_and_send_miniapp_lineup_notifications(bot)
            await check_and_send_miniapp_event_notifications(bot)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Mini App match reminders background loop stopped")
        raise


async def start_miniapp_match_reminders_loop(application: Application) -> None:
    try:
        await application.bot.set_my_commands(
            [BotCommand("start", "Открыть MatchLab")]
        )
    except Exception:
        logger.warning("Failed to update Telegram bot commands", exc_info=True)

    application.bot_data["miniapp_match_reminders_task"] = (
        asyncio.create_task(
            miniapp_match_reminders_loop(application.bot),
            name="miniapp-match-reminders",
        )
    )
    logger.info("Mini App match reminders background loop started")


async def stop_miniapp_match_reminders_loop(application: Application) -> None:
    task = application.bot_data.pop("miniapp_match_reminders_task", None)
    if not task:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def schedule_channel_morning_digest(application: Application) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning(
            "channel_morning_digest schedule skipped: JobQueue is not available"
        )
        return

    if job_queue.get_jobs_by_name("channel_morning_digest"):
        logger.info("channel_morning_digest schedule already exists")
        return

    job_queue.run_daily(
        publish_channel_morning_digest,
        time=time(hour=9, minute=0, tzinfo=ALMATY_TZ),
        name="channel_morning_digest",
    )
    logger.info("channel_morning_digest scheduled for 09:00 Asia/Almaty")


def schedule_channel_daily_football_radar(application: Application) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning(
            "channel_daily_football_radar schedule skipped: JobQueue is not available"
        )
        return

    if job_queue.get_jobs_by_name("channel_daily_football_radar"):
        logger.info("channel_daily_football_radar schedule already exists")
        return

    job_queue.run_daily(
        publish_channel_daily_football_radar,
        time=time(hour=14, minute=0, tzinfo=ALMATY_TZ),
        name="channel_daily_football_radar",
    )
    logger.info("channel_daily_football_radar scheduled for 14:00 Asia/Almaty")


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


def build_main_menu_markup() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def build_miniapp_url(params: dict | None = None) -> str:
    if not WEBAPP_URL:
        return ""

    if not params:
        return WEBAPP_URL

    url_parts = urlsplit(WEBAPP_URL)
    query_params = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    query_params.update(
        {
            str(key): str(value)
            for key, value in params.items()
            if value is not None and str(value).strip()
        }
    )
    return urlunsplit(
        (
            url_parts.scheme,
            url_parts.netloc,
            url_parts.path,
            urlencode(query_params),
            url_parts.fragment,
        )
    )


def build_miniapp_inline_keyboard(
    screen: str | None = None,
    params: dict | None = None,
) -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL:
        return None

    button_params = dict(params or {})
    button_text = "Открыть MatchLab"
    if screen:
        button_params["screen"] = screen
        if screen == "profile":
            button_text = "👤 Открыть профиль"

    button_url = build_miniapp_url(button_params)
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
    message = update.effective_message
    if not message:
        return

    if message.text and message.text.startswith("/start"):
        track_user_action(update, "start")

    sent_message = await message.reply_text(
        "👋 Добро пожаловать в MatchLab\n\n"
        "Вся аналитика, матчи, турниры, команды, избранное, "
        "уведомления и AI-разбор теперь в Mini App.\n\n"
        "Открой MatchLab 👇",
        reply_markup=build_main_menu_markup(),
    )
    miniapp_markup = build_miniapp_inline_keyboard()
    if miniapp_markup:
        try:
            await sent_message.edit_reply_markup(reply_markup=miniapp_markup)
        except Exception:
            logger.warning(
                "Failed to attach Mini App button to start message",
                exc_info=True,
            )
            await message.reply_text(
                "Открыть MatchLab 👇",
                reply_markup=miniapp_markup,
            )


async def open_miniapp_redirect(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if not message:
        return

    sent_message = await message.reply_text(
        "Открой MatchLab — теперь всё внутри Mini App 👇",
        reply_markup=build_main_menu_markup(),
    )
    miniapp_markup = build_miniapp_inline_keyboard()
    if miniapp_markup:
        try:
            await sent_message.edit_reply_markup(reply_markup=miniapp_markup)
        except Exception:
            logger.warning(
                "Failed to attach Mini App button to redirect message",
                exc_info=True,
            )
            await message.reply_text(
                "Открыть MatchLab 👇",
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


def get_fixture_statistics(fixture_id: int | str) -> list[dict]:
    try:
        statistics = request_api_football(
            "/fixtures/statistics",
            {"fixture": fixture_id},
        )
        logger.debug(
            "Fixture statistics loaded: fixture_id=%s teams=%s",
            fixture_id,
            len(statistics),
        )
        return statistics
    except Exception:
        logger.warning(
            "Failed to get fixture statistics for fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
        return []


def get_fixture_by_id(fixture_id: int | str) -> dict | None:
    try:
        fixtures = request_api_football(
            "/fixtures",
            {
                "id": fixture_id,
                "timezone": "UTC",
            },
        )
        if fixtures and isinstance(fixtures[0], dict):
            return fixtures[0]
    except Exception:
        logger.warning(
            "Failed to get fixture by id: fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
    return None


def get_fixture_events(fixture_id: int | str) -> list[dict]:
    try:
        events = request_api_football(
            "/fixtures/events",
            {"fixture": fixture_id},
        )
        return events if isinstance(events, list) else []
    except Exception:
        logger.warning(
            "Failed to get fixture events: fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
        return []


def is_miniapp_fixture_live_status(status_short) -> bool:
    return str(status_short or "").strip().upper() in MINIAPP_LIVE_STATUSES


def is_miniapp_fixture_finished_status(status_short) -> bool:
    return (
        str(status_short or "").strip().upper()
        in MINIAPP_FINISHED_STATUSES
    )


def get_fixture_lineups(fixture_id: int | str) -> list[dict]:
    try:
        lineups = request_api_football(
            "/fixtures/lineups",
            {"fixture": fixture_id},
        )
        logger.debug(
            "Fixture lineups loaded: fixture_id=%s teams=%s",
            fixture_id,
            len(lineups),
        )
        return lineups
    except Exception:
        logger.warning(
            "Failed to get fixture lineups for fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
        return []


def get_fixture_injuries(fixture_id: int | str) -> list[dict]:
    try:
        injuries = request_api_football(
            "/injuries",
            {"fixture": fixture_id},
        )
        logger.debug(
            "Fixture injuries loaded: fixture_id=%s items=%s",
            fixture_id,
            len(injuries),
        )
        return injuries if isinstance(injuries, list) else []
    except Exception:
        logger.warning(
            "Failed to get fixture injuries for fixture_id=%s",
            fixture_id,
            exc_info=True,
        )
        return []


def format_miniapp_lineup_player(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    player = item.get("player")
    if not isinstance(player, dict):
        player = item

    player_name = str(player.get("name") or "").strip()
    if not player_name:
        return None

    return {
        "id": player.get("id"),
        "name": player_name,
        "number": player.get("number"),
        "pos": str(player.get("pos") or "").strip(),
        "grid": player.get("grid") or None,
    }


def format_miniapp_match_lineups(raw_lineups) -> dict:
    if not isinstance(raw_lineups, list):
        return {
            "available": False,
            "teams": [],
        }

    teams = []
    for lineup in raw_lineups:
        if not isinstance(lineup, dict):
            continue

        team = lineup.get("team")
        if not isinstance(team, dict):
            team = {}

        coach_data = lineup.get("coach")
        coach = None
        if isinstance(coach_data, dict):
            coach_name = str(coach_data.get("name") or "").strip()
            if coach_name or coach_data.get("id") is not None:
                coach = {
                    "id": coach_data.get("id"),
                    "name": coach_name,
                    "photo": coach_data.get("photo") or None,
                }

        raw_start_xi = lineup.get("startXI")
        if raw_start_xi is None:
            raw_start_xi = lineup.get("start_xi")
        if not isinstance(raw_start_xi, list):
            raw_start_xi = []

        raw_substitutes = lineup.get("substitutes")
        if not isinstance(raw_substitutes, list):
            raw_substitutes = []

        start_xi = [
            player
            for item in raw_start_xi
            if (player := format_miniapp_lineup_player(item))
        ]
        substitutes = [
            player
            for item in raw_substitutes
            if (player := format_miniapp_lineup_player(item))
        ]

        team_name = str(team.get("name") or "").strip()
        if (
            not team_name
            and team.get("id") is None
            and not start_xi
            and not substitutes
            and coach is None
        ):
            continue

        teams.append(
            {
                "team_id": team.get("id"),
                "team_name": team_name,
                "team_logo": team.get("logo") or None,
                "formation": str(lineup.get("formation") or "").strip(),
                "coach": coach,
                "start_xi": start_xi,
                "substitutes": substitutes,
            }
        )

    return {
        "available": bool(teams),
        "teams": teams,
    }


def format_miniapp_match_absences(raw_injuries) -> dict:
    if not isinstance(raw_injuries, list):
        return {
            "available": False,
            "teams": [],
        }

    teams_by_id = {}
    fallback_index = 0

    for injury in raw_injuries:
        if not isinstance(injury, dict):
            continue

        player = injury.get("player")
        if not isinstance(player, dict):
            player = {}

        team = injury.get("team")
        if not isinstance(team, dict):
            team = {}

        player_name = str(player.get("name") or "").strip()
        if not player_name:
            continue

        team_id = team.get("id")
        team_name = str(team.get("name") or "").strip()
        if team_id is None and not team_name:
            fallback_index += 1
            team_key = f"unknown-{fallback_index}"
        else:
            team_key = str(team_id if team_id is not None else team_name)

        if team_key not in teams_by_id:
            teams_by_id[team_key] = {
                "team_id": team_id,
                "team_name": team_name,
                "team_logo": team.get("logo") or None,
                "players": [],
            }

        teams_by_id[team_key]["players"].append(
            {
                "id": player.get("id"),
                "name": player_name,
                "photo": player.get("photo") or None,
                "type": str(player.get("type") or "").strip(),
                "reason": str(player.get("reason") or "").strip(),
            }
        )

    teams = [
        team
        for team in teams_by_id.values()
        if team.get("players")
    ]

    return {
        "available": bool(teams),
        "teams": teams,
    }


MINIAPP_STATISTIC_LABELS = {
    "Ball Possession": "Владение мячом",
    "Expected Goals": "Ожидаемые голы (xG)",
    "Total Shots": "Удары",
    "Shots on Goal": "Удары в створ",
    "Shots off Goal": "Удары мимо",
    "Blocked Shots": "Заблокированные удары",
    "Corner Kicks": "Угловые",
    "Fouls": "Фолы",
    "Offsides": "Офсайды",
    "Yellow Cards": "Жёлтые карточки",
    "Red Cards": "Красные карточки",
    "Goalkeeper Saves": "Сейвы",
    "Total passes": "Пасы",
    "Passes accurate": "Точные пасы",
    "Passes %": "Точность пасов",
}

MINIAPP_STATISTIC_ORDER = {
    statistic_type: index
    for index, statistic_type in enumerate(MINIAPP_STATISTIC_LABELS)
}


def format_miniapp_statistic_display_value(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    text = str(value).strip()
    if not text or text == "-":
        return None

    return text


def format_miniapp_match_statistics(
    raw_statistics: list[dict],
    home_team_id: int | None = None,
    away_team_id: int | None = None,
) -> dict:
    empty_result = {
        "available": False,
        "home": None,
        "away": None,
        "items": [],
    }
    if not raw_statistics:
        return empty_result

    entries_by_id = {
        (entry.get("team") or {}).get("id"): entry
        for entry in raw_statistics
        if (entry.get("team") or {}).get("id") is not None
    }
    home_entry = entries_by_id.get(home_team_id)
    away_entry = entries_by_id.get(away_team_id)

    if home_entry is None and raw_statistics:
        home_entry = raw_statistics[0]
    if away_entry is None:
        away_entry = next(
            (entry for entry in raw_statistics if entry is not home_entry),
            None,
        )
    if home_entry is None or away_entry is None:
        return empty_result

    def format_team(entry: dict) -> dict:
        team = entry.get("team") or {}
        return {
            "team_id": team.get("id"),
            "team_name": team.get("name") or "",
            "team_logo": team.get("logo") or None,
        }

    def statistics_by_type(entry: dict) -> dict:
        result = {}
        for statistic in entry.get("statistics") or []:
            statistic_type = str(statistic.get("type") or "").strip()
            if statistic_type:
                result[statistic_type] = statistic.get("value")
        return result

    home_statistics = statistics_by_type(home_entry)
    away_statistics = statistics_by_type(away_entry)
    statistic_types = list(
        dict.fromkeys([*home_statistics.keys(), *away_statistics.keys()])
    )
    statistic_types.sort(
        key=lambda statistic_type: (
            MINIAPP_STATISTIC_ORDER.get(
                statistic_type,
                len(MINIAPP_STATISTIC_ORDER),
            ),
            statistic_type.lower(),
        )
    )

    items = []
    for statistic_type in statistic_types:
        raw_home_value = home_statistics.get(statistic_type)
        raw_away_value = away_statistics.get(statistic_type)
        home_display = format_miniapp_statistic_display_value(raw_home_value)
        away_display = format_miniapp_statistic_display_value(raw_away_value)
        if home_display is None and away_display is None:
            continue

        items.append(
            {
                "type": statistic_type,
                "label": MINIAPP_STATISTIC_LABELS.get(
                    statistic_type,
                    statistic_type,
                ),
                "home": home_display,
                "away": away_display,
                "home_value": parse_stat_number(raw_home_value),
                "away_value": parse_stat_number(raw_away_value),
            }
        )

    return {
        "available": bool(items),
        "home": format_team(home_entry),
        "away": format_team(away_entry),
        "items": items,
    }


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


def get_ai_analysis_mode(is_admin: bool, subscription: dict | None) -> str:
    if is_admin or is_premium_active(subscription or {}):
        return "premium"
    return "default"


def get_ai_model_settings(analysis_mode: str) -> tuple[str, str]:
    if analysis_mode == "premium":
        return (
            OPENAI_AI_MODEL_PREMIUM,
            OPENAI_AI_REASONING_EFFORT_PREMIUM,
        )
    return (
        OPENAI_AI_MODEL_DEFAULT,
        OPENAI_AI_REASONING_EFFORT_DEFAULT,
    )


def build_ai_prompt(match_data: dict, analysis_mode: str = "default") -> str:
    if analysis_mode == "premium":
        detail_instruction = (
            "Это Premium deep analysis. Дай углублённое объяснение связей "
            "между формой, таблицей, составами, потерями, статистическими "
            "сигналами и стилем игры. Полноценно раскрой все поля JSON. "
            "В каждом важном блоке сначала сформулируй главный вывод, затем "
            "отдельным предложением назови основной риск или ограничение "
            "данных.\n"
            "Ограничения Premium: summary — максимум 3-4 предложения; context "
            "— 4-5; form — 5-6; lineups_and_absences — 4-5; tactical_notes — "
            "5-6; scenario — 4-5 предложений. Дай 6-8 signals, если данные "
            "позволяют; каждый signal.reason — максимум 2-3 предложения; "
            "risks — максимум 4-5 коротких пунктов."
        )
        signal_instruction = (
            "Для signals обязательно оцени: Тотал больше 1.5, Тотал больше "
            "2.5, Обе команды забьют, Жёлтые карточки, Угловые. Если данные "
            "позволяют, добавь ещё 1-3 полезных статистических сигнала по "
            "голам команды, ударам, первому тайму или темпу матча. Не добавляй "
            "сигнал без числовой опоры."
        )
    else:
        detail_instruction = (
            "Это обычный короткий AI-разбор для Free и разового AI-пакета. "
            "Сфокусируйся на кратком выводе, вероятностях исхода, 3-5 главных "
            "статистических сигналах, коротком контексте, основных рисках и "
            "итоговом сценарии. Не углубляйся в длинную тактику, подробный "
            "разбор составов и потерь или многочисленные альтернативные "
            "сценарии.\n"
            "Ограничения обычного разбора: summary — максимум 2-3 предложения; "
            "context — 2-3; form — 2-3; lineups_and_absences — 1-2 предложения "
            "и только о действительно важных данных; tactical_notes — 2-3; "
            "scenario — 3-4 предложения. Дай максимум 5 signals; каждый "
            "signal.reason — максимум 1-2 предложения; risks — максимум 2-3 "
            "коротких пункта. Если расширенный блок не нужен или данных мало, "
            "заполни его коротко: 'Ключевых данных недостаточно для "
            "расширенного вывода.'"
        )
        signal_instruction = (
            "Для signals выбери 3-5 наиболее полезных пунктов из списка: "
            "Тотал больше 1.5, Тотал больше 2.5, Обе команды забьют, Жёлтые "
            "карточки, Угловые. Не добавляй второстепенные сигналы."
        )
    compact_context = match_data.get("compact_context") or match_data
    numeric_basis_block = (
        match_data.get("numeric_basis_block")
        or "Недостаточно данных для сводки числовой базы."
    )
    analysis_text = (
        match_data.get("analysis_text")
        or "Расширенные внутренние данные недоступны."
    )
    tournament_context_text = (
        match_data.get("tournament_context_text")
        or "Турнирный контекст недоступен."
    )

    return (
        "Ты футбольный аналитик MatchLab. Пиши для пользователя мобильного "
        "приложения: ясно, живо и по делу, короткими абзацами и простыми "
        "предложениями. Текст вокруг названий команд должен быть полностью "
        "на русском; названия команд из данных можно оставить как есть.\n"
        "Подготовь независимую AI-оценку матча только по переданным данным.\n"
        f"{detail_instruction}\n"
        "Не используй в ответе служебные заголовки или формулировки "
        "'Сильный вывод' и 'Контраргумент'. Не повторяй один вывод разными "
        "словами и избегай канцелярита.\n"
        "Приоритет источников: numeric_basis_block является основной базой "
        "для выводов по голам, тоталам, обеим забившим командам, карточкам и "
        "угловым. compact_context используй для составов, потерь, положения "
        "в таблице, последних матчей, H2H и ближайшего календаря. Турнирный "
        "контекст используй для стадии, группы и мотивации команд.\n"
        "Не выдумывай xG или xGA: используй их только если они явно есть в "
        "numeric_basis_block или statistics внутри compact_context.\n"
        "Не выдумывай статистику, проценты, составы, потери или события. "
        "Если данных для метрики недостаточно, прямо укажи "
        "'Недостаточно данных'. Вероятности исхода оцени осторожно на основе "
        "доступного контекста; три значения должны быть целыми числами от 0 "
        "до 100 и в сумме давать 100.\n"
        "Если home_win или away_win выше 55, в summary и scenario прямо назови "
        "соответствующую команду главным фаворитом по AI-оценке. Объясни её "
        "преимущество конкретными данными и обязательно назови главный риск, "
        "но не обещай победу. Используй естественные формулировки: "
        "'выглядит сильнее', 'имеет преимущество', 'базовый сценарий на её "
        "стороне'. Не своди такой вывод автоматически к формулировке "
        "'не проиграет'. Если вероятности команд близки, честно напиши, что "
        "матч выглядит равным и решающими могут стать отдельные эпизоды.\n"
        "Не используй слова: ставка, ставить, экспресс, купон, железно, "
        "гарантия, 100%. Не обещай результат, не давай финансовых советов и "
        "не называй оценку точным прогнозом. Используй формулировки: "
        "AI-оценка, вероятностный сценарий, статистический сигнал, риск, "
        "осторожная оценка.\n"
        f"{signal_instruction}\n"
        "Для signal.value "
        "используй одну из понятных оценок: 'Хорошо поддержан данными', "
        "'Умеренно вероятно', 'Слабая поддержка', 'Лучше осторожно', "
        "'Недостаточно данных'. Не пиши просто 'Поддержан статистикой' без "
        "степени уверенности. Если данных нет, confidence должно быть 'low', "
        "а reason должен кратко объяснять нехватку данных.\n"
        "В scenario последовательно и коротко объясни: кто вероятнее будет "
        "контролировать игру; откуда могут прийти моменты; какой ожидается "
        "темп; что является главным риском этого сценария. Не объединяй всё "
        "в одно длинное сложное предложение.\n"
        "Верни только валидный JSON без markdown и без текста до или после JSON "
        "строго по схеме:\n"
        "{\n"
        '  "summary": "краткий вывод",\n'
        '  "outcome_probabilities": {\n'
        '    "home_win": 0,\n'
        '    "draw": 0,\n'
        '    "away_win": 0\n'
        "  },\n"
        '  "signals": [\n'
        "    {\n"
        '      "label": "название метрики",\n'
        '      "value": "оценка или Недостаточно данных",\n'
        '      "confidence": "low|medium|high",\n'
        '      "reason": "обоснование"\n'
        "    }\n"
        "  ],\n"
        '  "context": "контекст матча и положение в турнире",\n'
        '  "form": "форма обеих команд",\n'
        '  "lineups_and_absences": "составы и потери",\n'
        '  "tactical_notes": "тактические и статистические заметки",\n'
        '  "risks": ["риск 1", "риск 2"],\n'
        '  "scenario": "итоговый вероятностный сценарий",\n'
        '  "disclaimer": "Информационная AI-оценка, не является советом '
        'или рекомендацией."\n'
        "}\n\n"
        "Сводка числовой базы MatchLab:\n"
        f"{numeric_basis_block}\n\n"
        "Расширенные внутренние данные MatchLab:\n"
        f"{analysis_text}\n\n"
        "Турнирный контекст:\n"
        f"{tournament_context_text}\n\n"
        "Компактный контекст матча:\n"
        f"{json.dumps(compact_context, ensure_ascii=False, default=str)}"
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
        r"\bрынок\b": "метрика",
        r"\bрынка\b": "метрики",
        r"\bрынку\b": "метрике",
        r"\bрынком\b": "метрикой",
        r"\bрынке\b": "метрике",
        r"\bрынки\b": "метрики",
        r"\bрынков\b": "метрик",
        r"\bрынкам\b": "метрикам",
        r"\bрынками\b": "метриками",
        r"\bрынках\b": "метриках",
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


def is_unsupported_structured_output_error(error: Exception) -> bool:
    message = str(error).lower()
    structured_terms = (
        "json_schema",
        "json schema",
        "response_format",
        "response format",
        "structured output",
        "structured outputs",
        "text.format",
        "parameter: text",
        "parameter 'text'",
        "parameter \"text\"",
        "invalid schema",
    )
    unsupported_terms = (
        "unsupported",
        "not supported",
        "unknown parameter",
        "unexpected keyword",
        "invalid parameter",
        "invalid schema",
    )
    return (
        any(term in message for term in structured_terms)
        and any(term in message for term in unsupported_terms)
    )


def build_ai_analysis_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "outcome_probabilities": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "home_win": {"type": "integer"},
                    "draw": {"type": "integer"},
                    "away_win": {"type": "integer"},
                },
                "required": ["home_win", "draw", "away_win"],
            },
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "label",
                        "value",
                        "confidence",
                        "reason",
                    ],
                },
            },
            "context": {"type": "string"},
            "form": {"type": "string"},
            "lineups_and_absences": {"type": "string"},
            "tactical_notes": {"type": "string"},
            "risks": {
                "type": "array",
                "items": {"type": "string"},
            },
            "scenario": {"type": "string"},
            "disclaimer": {"type": "string"},
        },
        "required": [
            "summary",
            "outcome_probabilities",
            "signals",
            "context",
            "form",
            "lineups_and_absences",
            "tactical_notes",
            "risks",
            "scenario",
            "disclaimer",
        ],
    }


def build_responses_ai_text_format() -> dict:
    return {
        "format": {
            "type": "json_schema",
            "name": "matchlab_ai_analysis",
            "schema": build_ai_analysis_json_schema(),
            "strict": True,
        }
    }


def build_chat_ai_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "matchlab_ai_analysis",
            "schema": build_ai_analysis_json_schema(),
            "strict": True,
        },
    }


def get_ai_max_output_tokens(
    analysis_mode: str,
    retry: bool = False,
) -> int:
    if analysis_mode == "premium":
        return 8000 if retry else 6500
    return 5000 if retry else 4000


def parse_ai_analysis_json(content: str) -> dict | None:
    text = str(content or "").strip()
    if not text:
        return None

    text = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```\s*$", "", text).strip()
    candidates = [("full", text)]

    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start >= 0 and json_end > json_start:
        fragment = text[json_start : json_end + 1].strip()
        if fragment != text:
            candidates.append(("fragment", fragment))

    last_error = None
    for source, candidate in candidates:
        result = candidate
        for decode_attempt in range(2):
            if not isinstance(result, str):
                break
            try:
                result = json.loads(result.strip())
            except (TypeError, json.JSONDecodeError) as error:
                last_error = (source, decode_attempt + 1, error)
                break

        if isinstance(result, dict):
            return result

    if last_error:
        source, decode_attempt, error = last_error
        logger.warning(
            "OpenAI AI analysis JSON parse failed: source=%s attempt=%s "
            "position=%s response_length=%s reason=%s",
            source,
            decode_attempt,
            getattr(error, "pos", None),
            len(text),
            getattr(error, "msg", type(error).__name__),
        )
    else:
        logger.warning(
            "OpenAI AI analysis JSON parse failed: "
            "response_length=%s result_type=non_object",
            len(text),
        )
    return None


def looks_like_ai_analysis_json(content: str) -> bool:
    text = str(content or "").strip()
    text = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).lstrip()
    return (
        text.startswith("{")
        or '"outcome_probabilities"' in text
        or '"summary"' in text and '"signals"' in text
    )


def clean_ai_analysis_text(content: str) -> str:
    if looks_like_ai_analysis_json(content):
        return (
            "AI-разбор временно недоступен в красивом формате. "
            "Попробуйте повторить запрос."
        )
    return sanitize_ai_analysis_text(content)


def sanitize_ai_analysis_value(value):
    if isinstance(value, str):
        return sanitize_ai_analysis_text(value)
    if isinstance(value, list):
        return [sanitize_ai_analysis_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_ai_analysis_value(item)
            for key, item in value.items()
        }
    return value


def normalize_ai_probability(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def normalize_ai_analysis_payload(payload: dict) -> dict:
    probabilities = payload.get("outcome_probabilities")
    if not isinstance(probabilities, dict):
        probabilities = {}

    normalized_probabilities = {
        "home_win": normalize_ai_probability(probabilities.get("home_win")),
        "draw": normalize_ai_probability(probabilities.get("draw")),
        "away_win": normalize_ai_probability(probabilities.get("away_win")),
    }
    probability_total = sum(normalized_probabilities.values())
    if probability_total and probability_total != 100:
        keys = ("home_win", "draw", "away_win")
        scaled = {
            key: round(normalized_probabilities[key] * 100 / probability_total)
            for key in keys
        }
        scaled["away_win"] += 100 - sum(scaled.values())
        normalized_probabilities = scaled

    signals = []
    for item in payload.get("signals") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        confidence = str(item.get("confidence") or "low").strip().lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        signals.append(
            {
                "label": label,
                "value": str(
                    item.get("value") or "Недостаточно данных"
                ).strip(),
                "confidence": confidence,
                "reason": str(item.get("reason") or "").strip(),
            }
        )

    risks = [
        str(item).strip()
        for item in payload.get("risks") or []
        if str(item).strip()
    ]
    normalized = {
        "summary": str(payload.get("summary") or "").strip(),
        "outcome_probabilities": normalized_probabilities,
        "signals": signals[:8],
        "context": str(payload.get("context") or "").strip(),
        "form": str(payload.get("form") or "").strip(),
        "lineups_and_absences": str(
            payload.get("lineups_and_absences") or ""
        ).strip(),
        "tactical_notes": str(payload.get("tactical_notes") or "").strip(),
        "risks": risks[:6],
        "scenario": str(payload.get("scenario") or "").strip(),
        "disclaimer": str(
            payload.get("disclaimer")
            or (
                "Информационная AI-оценка, не является советом "
                "или рекомендацией."
            )
        ).strip(),
    }
    return sanitize_ai_analysis_value(normalized)


def format_ai_analysis_text(payload: dict) -> str:
    probabilities = payload.get("outcome_probabilities") or {}
    lines = [
        "🤖 AI-разбор MatchLab",
        "",
        "1. Краткий вывод",
        payload.get("summary") or "Недостаточно данных.",
        "",
        "2. Вероятности исхода",
        f"Победа команды 1: {probabilities.get('home_win', 0)}%",
        f"Ничья: {probabilities.get('draw', 0)}%",
        f"Победа команды 2: {probabilities.get('away_win', 0)}%",
        "",
        "3. Статистические сигналы",
    ]
    signals = payload.get("signals") or []
    if signals:
        for signal in signals:
            lines.append(
                f"• {signal['label']}: {signal['value']} — "
                f"{signal['reason'] or 'Недостаточно данных.'}"
            )
    else:
        lines.append("Недостаточно данных.")

    sections = (
        ("4. Контекст матча", "context"),
        ("5. Форма команд", "form"),
        ("6. Составы и потери", "lineups_and_absences"),
        ("7. Тактические и статистические заметки", "tactical_notes"),
    )
    for title, key in sections:
        lines.extend(["", title, payload.get(key) or "Недостаточно данных."])

    lines.extend(["", "8. Риски оценки"])
    risks = payload.get("risks") or []
    lines.extend(
        [f"• {risk}" for risk in risks]
        or ["• Недостаточно данных для полной оценки рисков."]
    )
    lines.extend(
        [
            "",
            "9. Итоговый сценарий",
            payload.get("scenario") or "Недостаточно данных.",
            "",
            "10. Информационный дисклеймер",
            payload.get("disclaimer")
            or (
                "Информационная AI-оценка, не является советом "
                "или рекомендацией."
            ),
        ]
    )
    return "\n".join(lines)


def create_openai_responses_analysis(
    client: OpenAI,
    response_kwargs: dict,
    selected_model: str,
    analysis_mode: str,
):
    request_kwargs = dict(response_kwargs)
    while True:
        try:
            return client.responses.create(**request_kwargs)
        except Exception as error:
            if (
                "text" in request_kwargs
                and is_unsupported_structured_output_error(error)
            ):
                request_kwargs.pop("text", None)
                logger.warning(
                    "OpenAI structured output unsupported; retrying without "
                    "schema: api=responses model=%s analysis_mode=%s "
                    "structured_output_enabled=False",
                    selected_model,
                    analysis_mode,
                )
                continue
            if (
                "reasoning" in request_kwargs
                and is_unsupported_reasoning_error(error)
            ):
                request_kwargs.pop("reasoning", None)
                logger.warning(
                    "OpenAI reasoning effort unsupported; retrying without it: "
                    "api=responses model=%s analysis_mode=%s",
                    selected_model,
                    analysis_mode,
                )
                continue
            raise


def create_openai_chat_analysis(
    client: OpenAI,
    completion_kwargs: dict,
    selected_model: str,
    analysis_mode: str,
):
    request_kwargs = dict(completion_kwargs)
    while True:
        try:
            return client.chat.completions.create(**request_kwargs)
        except Exception as error:
            if (
                "response_format" in request_kwargs
                and is_unsupported_structured_output_error(error)
            ):
                request_kwargs.pop("response_format", None)
                logger.warning(
                    "OpenAI structured output unsupported; retrying without "
                    "schema: api=chat_completions model=%s analysis_mode=%s "
                    "structured_output_enabled=False",
                    selected_model,
                    analysis_mode,
                )
                continue
            if (
                "reasoning_effort" in request_kwargs
                and is_unsupported_reasoning_error(error)
            ):
                request_kwargs.pop("reasoning_effort", None)
                logger.warning(
                    "OpenAI reasoning effort unsupported; retrying without it: "
                    "api=chat_completions model=%s analysis_mode=%s",
                    selected_model,
                    analysis_mode,
                )
                continue
            raise


def log_openai_ai_analysis_response(
    response,
    content: str,
    selected_model: str,
    analysis_mode: str,
    api_name: str,
    retry: bool = False,
) -> None:
    status = get_openai_response_field(response, "status")
    incomplete_details = get_openai_response_field(
        response,
        "incomplete_details",
    )
    finish_reason = None
    choices = get_openai_response_field(response, "choices") or []
    if choices:
        finish_reason = get_openai_response_field(
            choices[0],
            "finish_reason",
        )

    incomplete_text = str(incomplete_details or "")
    if len(incomplete_text) > 300:
        incomplete_text = trim_to_complete_sentence(incomplete_text, 300)

    logger.info(
        "OpenAI AI analysis response received: model=%s mode=%s api=%s "
        "retry=%s response_length=%s status=%s incomplete=%s "
        "finish_reason=%s structured_output_enabled=True",
        selected_model,
        analysis_mode,
        api_name,
        retry,
        len(content or ""),
        status,
        incomplete_text or None,
        finish_reason,
    )


def get_openai_ai_analysis_result(
    match_data: dict,
    analysis_mode: str = "default",
) -> dict:
    if not OPENAI_API_KEY:
        return {
            "analysis": "AI-разбор пока не подключён.",
            "structured": None,
            "analysis_mode": analysis_mode,
        }

    response = None
    content = ""
    api_name = "responses"
    response_kwargs = None
    completion_kwargs = None
    selected_model, reasoning_effort = get_ai_model_settings(analysis_mode)
    logger.info(
        "OpenAI AI analysis selected: model=%s analysis_mode=%s "
        "structured_output_enabled=True",
        selected_model,
        analysis_mode,
    )
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response_kwargs = {
            "model": selected_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Ты аккуратный футбольный аналитик. "
                        "Отвечай только валидным JSON на русском языке."
                    ),
                },
                {
                    "role": "user",
                    "content": build_ai_prompt(match_data, analysis_mode),
                },
            ],
            "max_output_tokens": get_ai_max_output_tokens(analysis_mode),
            "text": build_responses_ai_text_format(),
        }
        if reasoning_effort:
            response_kwargs["reasoning"] = {"effort": reasoning_effort}
        use_chat_completions = not hasattr(client, "responses")
        if hasattr(client, "responses"):
            try:
                response = create_openai_responses_analysis(
                    client,
                    response_kwargs,
                    selected_model,
                    analysis_mode,
                )
                content = extract_openai_response_text(response)
            except AttributeError:
                logger.warning(
                    "OpenAI Responses API unavailable; using Chat "
                    "Completions: model=%s analysis_mode=%s",
                    selected_model,
                    analysis_mode,
                )
                use_chat_completions = True

        if use_chat_completions:
            api_name = "chat_completions"
            completion_kwargs = {
                "model": selected_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты аккуратный футбольный аналитик. "
                            "Отвечай только валидным JSON на русском языке."
                        ),
                    },
                    {
                        "role": "user",
                        "content": build_ai_prompt(match_data, analysis_mode),
                    },
                ],
                "max_completion_tokens": get_ai_max_output_tokens(
                    analysis_mode
                ),
                "response_format": build_chat_ai_response_format(),
            }
            if reasoning_effort:
                completion_kwargs["reasoning_effort"] = reasoning_effort
            response = create_openai_chat_analysis(
                client,
                completion_kwargs,
                selected_model,
                analysis_mode,
            )
            content = response.choices[0].message.content or ""
    except Exception as e:
        logger.exception("OpenAI match analysis failed: %s", e)
        return {
            "analysis": "AI-разбор временно недоступен.",
            "structured": None,
            "analysis_mode": analysis_mode,
        }

    log_openai_ai_analysis_response(
        response,
        content,
        selected_model,
        analysis_mode,
        api_name,
    )

    if not content.strip():
        logger.error("OpenAI returned empty AI analysis response")
        logger.error("OpenAI empty response: %s", response)
        return {
            "analysis": "AI-разбор временно недоступен.",
            "structured": None,
            "analysis_mode": analysis_mode,
        }

    parsed_payload = parse_ai_analysis_json(content)
    if parsed_payload is None and looks_like_ai_analysis_json(content):
        logger.warning(
            "OpenAI AI analysis appears incomplete; retrying once: "
            "model=%s analysis_mode=%s api=%s response_length=%s "
            "max_output_tokens=%s",
            selected_model,
            analysis_mode,
            api_name,
            len(content),
            get_ai_max_output_tokens(analysis_mode, retry=True),
        )
        try:
            if api_name == "responses" and response_kwargs is not None:
                retry_kwargs = dict(response_kwargs)
                retry_kwargs["max_output_tokens"] = get_ai_max_output_tokens(
                    analysis_mode,
                    retry=True,
                )
                if "reasoning" in retry_kwargs:
                    retry_kwargs["reasoning"] = {"effort": "medium"}
                retry_response = create_openai_responses_analysis(
                    client,
                    retry_kwargs,
                    selected_model,
                    analysis_mode,
                )
                retry_content = extract_openai_response_text(retry_response)
            elif completion_kwargs is not None:
                retry_kwargs = dict(completion_kwargs)
                retry_kwargs["max_completion_tokens"] = (
                    get_ai_max_output_tokens(
                        analysis_mode,
                        retry=True,
                    )
                )
                if "reasoning_effort" in retry_kwargs:
                    retry_kwargs["reasoning_effort"] = "medium"
                retry_response = create_openai_chat_analysis(
                    client,
                    retry_kwargs,
                    selected_model,
                    analysis_mode,
                )
                retry_content = (
                    retry_response.choices[0].message.content or ""
                )
            else:
                retry_response = None
                retry_content = ""

            if retry_response is not None:
                log_openai_ai_analysis_response(
                    retry_response,
                    retry_content,
                    selected_model,
                    analysis_mode,
                    api_name,
                    retry=True,
                )
                retry_payload = parse_ai_analysis_json(retry_content)
                if retry_payload is not None:
                    parsed_payload = retry_payload
                    content = retry_content
                elif retry_content:
                    content = retry_content
        except Exception:
            logger.warning(
                "OpenAI AI analysis incomplete-response retry failed: "
                "model=%s analysis_mode=%s api=%s",
                selected_model,
                analysis_mode,
                api_name,
                exc_info=True,
            )

    if parsed_payload is not None:
        structured = normalize_ai_analysis_payload(parsed_payload)
        return {
            "analysis": format_ai_analysis_text(structured),
            "structured": structured,
            "analysis_mode": analysis_mode,
        }

    content = clean_ai_analysis_text(content)
    if content.startswith("🤖 AI-разбор MatchLab"):
        analysis = content
    else:
        analysis = f"🤖 AI-разбор MatchLab\n\n{content}"

    return {
        "analysis": analysis,
        "structured": None,
        "analysis_mode": analysis_mode,
    }


def get_openai_ai_analysis(
    match_data: dict,
    analysis_mode: str = "default",
) -> str:
    return get_openai_ai_analysis_result(
        match_data,
        analysis_mode,
    )["analysis"]


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
        analysis_mode = get_ai_analysis_mode(is_admin, subscription)
        message = await asyncio.to_thread(
            get_openai_ai_analysis,
            match_data,
            analysis_mode,
        )
        ai_event_data = {
            "home": match_data.get("home"),
            "away": match_data.get("away"),
            "fixture_id": match_data.get("fixture_id"),
            "league_name": match_data.get("league_name"),
            "is_admin": is_admin,
            "analysis_mode": analysis_mode,
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


def format_miniapp_score_value(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def format_miniapp_fixture_item(fixture_item: dict) -> dict | None:
    fixture = fixture_item.get("fixture") or {}
    teams = fixture_item.get("teams") or {}
    league = fixture_item.get("league") or {}
    goals = fixture_item.get("goals") or {}
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
    elif fixture.get("date"):
        try:
            fixture_date = datetime.fromisoformat(
                str(fixture["date"]).replace("Z", "+00:00")
            )
            if fixture_date.tzinfo is None:
                fixture_date = fixture_date.replace(tzinfo=timezone.utc)
            kickoff = fixture_date.astimezone(ALMATY_TZ).isoformat()
        except (TypeError, ValueError):
            kickoff = str(fixture["date"])

    return {
        "id": str(fixture_id),
        "home_id": home_team.get("id"),
        "away_id": away_team.get("id"),
        "home": home_team.get("name") or "",
        "away": away_team.get("name") or "",
        "home_logo": home_team.get("logo") or None,
        "away_logo": away_team.get("logo") or None,
        "league": league.get("name") or "",
        "league_id": league.get("id"),
        "league_logo": league.get("logo") or None,
        "country": league.get("country") or "",
        "season": league.get("season"),
        "round": league.get("round") or "",
        "kickoff": kickoff,
        "status": (fixture.get("status") or {}).get("short") or "",
        "score": {
            "home": format_miniapp_score_value(goals.get("home")),
            "away": format_miniapp_score_value(goals.get("away")),
        },
        "source": "api_football",
    }


def format_miniapp_team_item(team_item: dict) -> dict | None:
    team = team_item.get("team") or {}
    venue = team_item.get("venue") or {}
    team_id = team.get("id")

    if team_id is None:
        return None

    return {
        "id": int(team_id),
        "name": team.get("name") or "",
        "country": team.get("country") or "",
        "logo": team.get("logo") or None,
        "founded": team.get("founded"),
        "national": bool(team.get("national")),
        "venue_name": venue.get("name") or "",
        "venue_city": venue.get("city") or "",
        "venue_capacity": venue.get("capacity"),
    }


def get_miniapp_matches(match_type: str) -> list[dict]:
    if match_type == "live":
        fixtures = request_api_football(
            "/fixtures",
            {
                "live": "all",
                "timezone": "UTC",
            },
        )
        items = []
        for fixture_item in fixtures[:50]:
            formatted_item = format_miniapp_fixture_item(fixture_item)
            if formatted_item and formatted_item.get("id"):
                items.append(formatted_item)
        return items

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

    if normalized_match_id.isdigit():
        try:
            fixture_response = request_api_football(
                "/fixtures",
                {
                    "id": normalized_match_id,
                    "timezone": "UTC",
                },
            )
            if fixture_response:
                return format_miniapp_fixture_item(fixture_response[0])
        except Exception:
            logger.warning(
                "Mini App direct fixture lookup failed: match_id=%s",
                normalized_match_id,
                exc_info=True,
            )

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


def get_miniapp_live_cache_ttl(status_short: str) -> int:
    normalized_status = str(status_short or "").strip().upper()
    if normalized_status in MINIAPP_LIVE_STATUSES:
        return 45
    if normalized_status in MINIAPP_FINISHED_STATUSES:
        return 600
    if normalized_status in MINIAPP_NOT_STARTED_STATUSES:
        return 180
    return 180


def get_cached_miniapp_live_payload(match_id: str) -> dict | None:
    now_timestamp = datetime.now(timezone.utc).timestamp()
    with MINIAPP_LIVE_CACHE_LOCK:
        cached = MINIAPP_LIVE_CACHE.get(match_id)
        if not cached:
            return None
        if float(cached.get("expires_at") or 0) <= now_timestamp:
            MINIAPP_LIVE_CACHE.pop(match_id, None)
            return None
        return cached.get("payload")


def cache_miniapp_live_payload(
    match_id: str,
    payload: dict,
    ttl_seconds: int,
) -> None:
    expires_at = (
        datetime.now(timezone.utc).timestamp() + max(ttl_seconds, 1)
    )
    with MINIAPP_LIVE_CACHE_LOCK:
        MINIAPP_LIVE_CACHE[match_id] = {
            "expires_at": expires_at,
            "payload": payload,
        }


def format_miniapp_live_event(event: dict) -> dict | None:
    if not isinstance(event, dict):
        return None

    event_time = event.get("time")
    if not isinstance(event_time, dict):
        event_time = {}
    team = event.get("team")
    if not isinstance(team, dict):
        team = {}
    player = event.get("player")
    if not isinstance(player, dict):
        player = {}
    assist = event.get("assist")
    if not isinstance(assist, dict):
        assist = {}

    return {
        "time": event_time.get("elapsed"),
        "extra": event_time.get("extra"),
        "team_id": team.get("id"),
        "team_name": str(team.get("name") or "").strip(),
        "player": str(player.get("name") or "").strip(),
        "assist": str(assist.get("name") or "").strip(),
        "type": str(event.get("type") or "").strip(),
        "detail": str(event.get("detail") or "").strip(),
        "comments": event.get("comments") or None,
    }


def build_miniapp_match_live_payload(
    match_id: str,
    fixture_item: dict,
    raw_events,
) -> dict:
    fixture = fixture_item.get("fixture") or {}
    status = fixture.get("status") or {}
    teams = fixture_item.get("teams") or {}
    league = fixture_item.get("league") or {}
    formatted_fixture = format_miniapp_fixture_item(fixture_item)
    if not formatted_fixture:
        raise ValueError("Fixture data is incomplete")

    events = []
    if isinstance(raw_events, list):
        for event in raw_events:
            formatted_event = format_miniapp_live_event(event)
            if formatted_event:
                events.append(formatted_event)

    return {
        "ok": True,
        "match_id": match_id,
        "status": {
            "short": str(status.get("short") or "").strip(),
            "long": str(status.get("long") or "").strip(),
            "elapsed": status.get("elapsed"),
        },
        "score": formatted_fixture["score"],
        "fixture": {
            "home": (teams.get("home") or {}).get("name") or "",
            "away": (teams.get("away") or {}).get("name") or "",
            "home_logo": (teams.get("home") or {}).get("logo") or None,
            "away_logo": (teams.get("away") or {}).get("logo") or None,
            "kickoff": formatted_fixture["kickoff"],
            "league": league.get("name") or "",
        },
        "events": events,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


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
        "home_score": format_miniapp_score_value(goals.get("home")),
        "away_score": format_miniapp_score_value(goals.get("away")),
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
        "team_id": team.get("id"),
        "team": team_name,
        "group": row.get("group") or "",
        "played": all_stats.get("played"),
        "wins": all_stats.get("win"),
        "draws": all_stats.get("draw"),
        "losses": all_stats.get("lose"),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goal_diff,
        "points": row.get("points"),
        "description": row.get("description") or "",
        "status": row.get("status") or "",
    }


def get_miniapp_team_standings_data(team_id: int) -> dict | None:
    fixtures = []
    for fixture_loader, label in (
        (get_api_football_next_fixtures, "upcoming"),
        (get_api_football_finished_fixtures, "recent"),
    ):
        try:
            fixtures.extend(fixture_loader(team_id))
        except Exception:
            logger.warning(
                "Mini App team standings fixture lookup failed: "
                "team_id=%s source=%s",
                team_id,
                label,
                exc_info=True,
            )

    candidates = []
    seen_candidates = set()
    for fixture_item in fixtures:
        league = fixture_item.get("league") or {}
        league_id = league.get("id")
        season = league.get("season")
        candidate_key = (league_id, season)
        if not league_id or not season or candidate_key in seen_candidates:
            continue

        seen_candidates.add(candidate_key)
        candidates.append(
            {
                "id": league_id,
                "name": league.get("name") or "",
                "country": league.get("country") or "",
                "logo": league.get("logo") or None,
                "season": season,
                "type": league.get("type") or "",
            }
        )

    for candidate in candidates[:6]:
        if candidate["type"]:
            continue
        try:
            league_response = request_api_football(
                "/leagues",
                {
                    "id": candidate["id"],
                    "season": candidate["season"],
                },
            )
            if league_response:
                league_details = league_response[0].get("league") or {}
                candidate["type"] = league_details.get("type") or ""
        except Exception:
            logger.warning(
                "Mini App team league type lookup failed: "
                "team_id=%s league_id=%s season=%s",
                team_id,
                candidate["id"],
                candidate["season"],
                exc_info=True,
            )

    candidates.sort(
        key=lambda candidate: (
            str(candidate.get("type") or "").lower() != "league",
        )
    )

    for candidate in candidates:
        raw_standings = get_fixture_league_standings(
            candidate["id"],
            candidate["season"],
        )
        if not raw_standings:
            continue

        selected_row = next(
            (
                row
                for row in raw_standings
                if (row.get("team") or {}).get("id") == team_id
            ),
            None,
        )
        if not selected_row:
            continue

        standings = []
        for row in raw_standings:
            formatted_row = format_miniapp_standing_row(row)
            if formatted_row:
                standings.append(formatted_row)

        if not standings:
            continue

        return {
            "league": {
                "id": candidate["id"],
                "name": candidate["name"],
                "country": candidate["country"],
                "logo": candidate["logo"],
                "season": candidate["season"],
            },
            "team_id": team_id,
            "team_name": (
                (selected_row.get("team") or {}).get("name") or ""
            ),
            "standings": standings,
        }

    return None


def get_miniapp_match_group(
    standings: list[dict],
    home_team_name: str,
    away_team_name: str,
    league_round: str | None,
) -> str:
    home_row = find_standings_row(standings, home_team_name)
    away_row = find_standings_row(standings, away_team_name)
    home_group = str((home_row or {}).get("group") or "").strip()
    away_group = str((away_row or {}).get("group") or "").strip()

    if (
        home_group
        and away_group
        and normalize_standings_team_name(home_group)
        == normalize_standings_team_name(away_group)
    ):
        return home_group

    round_match = re.search(
        r"\bgroup\s+[a-z0-9]+\b",
        str(league_round or ""),
        flags=re.IGNORECASE,
    )
    if not round_match:
        return ""

    round_group = round_match.group(0)
    normalized_round_group = normalize_standings_team_name(round_group)
    for row in standings:
        group_name = str(row.get("group") or "").strip()
        if (
            group_name
            and normalize_standings_team_name(group_name)
            == normalized_round_group
        ):
            return group_name

    return round_group


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
    statistics = format_miniapp_match_statistics(
        get_fixture_statistics(match_id),
        home_team_id,
        away_team_id,
    )
    logger.debug(
        "Mini App match statistics formatted: fixture_id=%s items=%s",
        match_id,
        len(statistics.get("items") or []),
    )
    lineups = format_miniapp_match_lineups(
        get_fixture_lineups(match_id)
    )
    absences = format_miniapp_match_absences(
        get_fixture_injuries(match_id)
    )

    raw_standings = get_fixture_league_standings(
        league.get("id"),
        league.get("season"),
    )
    standings = []
    for row in raw_standings:
        formatted_row = format_miniapp_standing_row(row)
        if formatted_row:
            standings.append(formatted_row)

    home_team_name = match.get("home") or home_team.get("name") or ""
    away_team_name = match.get("away") or away_team.get("name") or ""
    match_group = get_miniapp_match_group(
        raw_standings,
        home_team_name,
        away_team_name,
        league.get("round"),
    )

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
        "home": home_team_name,
        "away": away_team_name,
        "league": match.get("league") or league.get("name") or "",
        "country": match.get("country") or league.get("country") or "",
        "kickoff": match.get("kickoff"),
        "match_group": match_group,
        "statistics": statistics,
        "lineups": lineups,
        "absences": absences,
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
    context = get_miniapp_match_context(match)
    fixture_id_text = str(match.get("id") or "")
    fixture_id = int(fixture_id_text) if fixture_id_text.isdigit() else None
    match_context = {
        "league_name": match.get("league"),
        "league_country": match.get("country"),
        "kickoff": match.get("kickoff"),
    }
    analysis_data = {}
    try:
        analysis_data = build_match_analysis_data(
            match.get("home") or "",
            match.get("away") or "",
            fixture_id,
            match_context,
        )
        if analysis_data.get("error"):
            logger.warning(
                "Mini App legacy AI analysis data is incomplete: "
                "match_id=%s error=%s",
                fixture_id_text,
                analysis_data.get("error"),
            )
    except Exception:
        logger.warning(
            "Mini App legacy AI analysis data failed: match_id=%s",
            fixture_id_text,
            exc_info=True,
        )
        analysis_data = {}

    def compact_matches(items: list[dict], limit: int = 5) -> list[dict]:
        return [
            {
                "date": item.get("date"),
                "league": item.get("league"),
                "home": item.get("home"),
                "away": item.get("away"),
                "home_score": item.get("home_score"),
                "away_score": item.get("away_score"),
                "status": item.get("status"),
            }
            for item in (items or [])[:limit]
        ]

    compact_statistics = [
        {
            "label": item.get("label"),
            "home": item.get("home"),
            "away": item.get("away"),
        }
        for item in (context.get("statistics") or {}).get("items", [])[:16]
    ]
    compact_lineups = []
    for team in (context.get("lineups") or {}).get("teams", [])[:2]:
        compact_lineups.append(
            {
                "team": team.get("team_name"),
                "formation": team.get("formation"),
                "coach": (team.get("coach") or {}).get("name"),
                "start_xi": [
                    {
                        "name": player.get("name"),
                        "position": player.get("pos"),
                    }
                    for player in (team.get("start_xi") or [])[:11]
                ],
                "substitutes": [
                    {
                        "name": player.get("name"),
                        "position": player.get("pos"),
                    }
                    for player in (team.get("substitutes") or [])[:8]
                ],
            }
        )

    compact_absences = []
    for team in (context.get("absences") or {}).get("teams", [])[:2]:
        compact_absences.append(
            {
                "team": team.get("team_name"),
                "players": [
                    {
                        "name": player.get("name"),
                        "type": player.get("type"),
                        "reason": player.get("reason"),
                    }
                    for player in (team.get("players") or [])[:10]
                ],
            }
        )

    match_group = context.get("match_group") or ""
    standings = context.get("standings") or []
    if match_group:
        relevant_standings = [
            row for row in standings if row.get("group") == match_group
        ]
    else:
        relevant_standings = standings
    compact_standings = [
        {
            "rank": row.get("rank"),
            "team": row.get("team"),
            "group": row.get("group"),
            "played": row.get("played"),
            "wins": row.get("wins"),
            "draws": row.get("draws"),
            "losses": row.get("losses"),
            "goal_diff": row.get("goal_diff"),
            "points": row.get("points"),
        }
        for row in relevant_standings[:12]
    ]

    compact_context = {
        "match": {
            "id": str(match.get("id") or ""),
            "home": match.get("home") or "",
            "away": match.get("away") or "",
            "league": match.get("league") or "",
            "country": match.get("country") or "",
            "round": match.get("round") or "",
            "kickoff": match.get("kickoff"),
            "status": match.get("status") or "",
            "score": match.get("score") or {},
            "match_group": match_group,
        },
        "standings": compact_standings,
        "home_recent": compact_matches(context.get("home_recent") or []),
        "away_recent": compact_matches(context.get("away_recent") or []),
        "h2h": compact_matches(context.get("h2h") or []),
        "statistics": compact_statistics,
        "lineups": compact_lineups,
        "absences": compact_absences,
        "upcoming": compact_matches(context.get("upcoming") or []),
    }
    logger.info(
        "Mini App AI context prepared: match_id=%s recent=%s/%s h2h=%s "
        "statistics=%s lineups=%s absences=%s numeric_basis=%s "
        "analysis_text=%s",
        match.get("id"),
        len(compact_context["home_recent"]),
        len(compact_context["away_recent"]),
        len(compact_context["h2h"]),
        len(compact_statistics),
        len(compact_lineups),
        sum(len(team["players"]) for team in compact_absences),
        bool(analysis_data.get("numeric_basis_block")),
        bool(analysis_data.get("full_analysis_text")),
    )
    match_data = {
        "home": match.get("home") or "",
        "away": match.get("away") or "",
        "fixture_id": fixture_id,
        "league_name": match.get("league"),
        "league_country": match.get("country"),
        "league_id": match.get("league_id"),
        "league_season": match.get("season"),
        "league_round": match.get("round"),
        "kickoff": match.get("kickoff"),
        "numeric_basis_block": (
            analysis_data.get("numeric_basis_block") or ""
        ),
        "analysis_text": analysis_data.get("full_analysis_text") or "",
        "compact_context": compact_context,
    }
    try:
        match_data["tournament_context_text"] = (
            build_tournament_context_for_ai(match_data)
        )
    except Exception:
        logger.warning(
            "Mini App tournament AI context failed: match_id=%s",
            fixture_id_text,
            exc_info=True,
        )
        match_data["tournament_context_text"] = ""

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


def build_channel_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🧠 Подготовить Матч дня",
                    callback_data="channel_admin_plan",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏁 Подготовить Итоги матча дня",
                    callback_data="channel_admin_recap",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Статус агента",
                    callback_data="channel_admin_status",
                )
            ],
        ]
    )


def build_channel_admin_status_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    draft_count = len(context.bot_data.get("channel_plan_drafts") or {})
    last_matchday = get_channel_agent_last_matchday(context)
    morning_date_key = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d")
    morning_published = has_channel_auto_post_been_published(
        "morning_digest",
        morning_date_key,
    ) or bool(context.bot_data.get(f"morning_digest:{morning_date_key}:published"))
    radar_date_key = morning_date_key
    radar_published = has_channel_auto_post_been_published(
        "daily_football_radar",
        radar_date_key,
    ) or bool(
        context.bot_data.get(f"daily_football_radar:{radar_date_key}:published")
    )
    lines = [
        "📊 Статус MatchLab Channel Agent",
        "",
        f"Канал: {'настроен' if MATCHLAB_CHANNEL_ID else 'не настроен'}",
        f"Mini App URL: {'настроен' if WEBAPP_URL else 'не настроен'}",
        f"OpenAI API: {'настроен' if OPENAI_API_KEY else 'не настроен'}",
        f"Черновиков в памяти: {draft_count}",
        "Утренний обзор: авто 09:00 Алматы, без approve",
        f"Сегодняшний обзор: {'опубликован' if morning_published else 'не опубликован'}",
        "Дневной радар: авто 14:00 Алматы, без approve",
        f"Сегодняшний радар: {'опубликован' if radar_published else 'не опубликован'}",
        "Режим: подготовка → approve → публикация",
        "",
    ]
    if last_matchday:
        match = last_matchday.get("match") or {}
        home = translate_team_name_ru(match.get("home")) or "Команда 1"
        away = translate_team_name_ru(match.get("away")) or "Команда 2"
        lines.extend(
            [
                f"Матч дня: {home} — {away}",
                f"match_id: {last_matchday.get('match_id')}",
                f"status: {last_matchday.get('status') or 'unknown'}",
                f"Память агента: {last_matchday.get('_source') or 'memory'}",
                f"selected_at: {last_matchday.get('selected_at') or 'не указано'}",
            ]
        )
        if last_matchday.get("agent_score") is not None:
            lines.append(f"agent_score: {last_matchday.get('agent_score')}")
    else:
        lines.append("Матч дня: не выбран")
        lines.append("Память агента: empty")

    lines.extend(
        [
            "",
            "Матч дня и Итоги сейчас готовятся по кнопке, публикация только после approve.",
        ]
    )
    return "\n".join(lines)


async def channel_admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_private_chat(update):
        if update.message:
            await update.message.reply_text(
                "Админ-панель доступна только в личке с ботом."
            )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        if update.message:
            await update.message.reply_text("Команда доступна только администратору.")
        return

    if not update.message:
        return

    await update.message.reply_text(
        "🤖 MatchLab Channel Agent\n\nВыбери действие:",
        reply_markup=build_channel_admin_keyboard(),
    )


async def channel_admin_plan_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    if not query.message:
        return
    await auto_prepare_channel_matchday(query.message, context, admin_id)


async def channel_admin_plan_manual_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    if not query.message:
        return
    await send_channel_plan_candidates(query.message, context)


async def channel_admin_recap_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    if not query.message:
        return
    await auto_prepare_channel_recap(query.message, context, admin_id)


async def channel_admin_recap_manual_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    if not query.message:
        return
    await send_channel_recap_candidates(query.message, context, admin_id)


async def channel_admin_status_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    await query.message.reply_text(build_channel_admin_status_text(context))


async def channel_admin_publish_morning_digest_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    result = await publish_channel_morning_digest(context)
    await query.message.reply_text(
        result.get("message") or "Публикация утреннего обзора завершена."
    )


async def channel_admin_publish_daily_radar_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    result = await publish_channel_daily_football_radar(context)
    await query.message.reply_text(
        result.get("message") or "Публикация дневного радара завершена."
    )


async def channel_admin_check_news_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    await query.message.reply_text("Проверяю футбольные новости из открытых источников…")
    items = await asyncio.to_thread(fetch_channel_football_news_items)
    if not items:
        await query.message.reply_text(
            "Свежих новостей из доступных источников не найдено."
        )
        return

    for item in items:
        item["score"] = score_channel_news_item(item)
    items = [item for item in items if int(item.get("score") or 0) > 0]
    if not items:
        await query.message.reply_text(
            "Свежих новостей из доступных источников не найдено."
        )
        return

    items = sorted(items, key=lambda item: int(item.get("score") or 0), reverse=True)
    items = items[:3]
    draft = await asyncio.to_thread(build_channel_news_radar_draft, items)
    draft = sanitize_channel_post_text(draft)
    if channel_text_has_forbidden_words(draft):
        await query.message.reply_text(
            "Черновик заблокирован фильтром безопасности."
        )
        return

    draft_id = f"news_{datetime.now(ALMATY_TZ).strftime('%Y%m%d_%H%M%S')}"
    cleanup_channel_bot_data(context)
    news_drafts = context.bot_data.setdefault("channel_news_drafts", {})
    news_drafts[draft_id] = {
        "draft": draft,
        "items": items,
        "created_at": datetime.now(ALMATY_TZ).isoformat(),
        "published": False,
    }
    await query.message.reply_text(
        draft,
        reply_markup=build_channel_news_draft_keyboard(draft_id),
    )


async def channel_news_publish_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    logger.info("channel_news_radar publish started")
    callback_data = query.data or ""
    draft_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    draft_item = (context.bot_data.get("channel_news_drafts") or {}).get(draft_id)
    if not draft_item:
        await query.message.reply_text("Черновик не найден или устарел.")
        return
    if draft_item.get("published"):
        await query.message.reply_text("Этот новостной радар уже опубликован.")
        return
    if not MATCHLAB_CHANNEL_ID:
        await query.message.reply_text(
            "Канал не настроен: добавьте MATCHLAB_CHANNEL_ID в Environment."
        )
        return

    draft = sanitize_channel_post_text(draft_item.get("draft") or "")
    if channel_text_has_forbidden_words(draft):
        await query.message.reply_text(
            "Пост содержит запрещённые слова. Нужна ручная проверка."
        )
        return

    try:
        sent_message = await context.bot.send_message(
            chat_id=MATCHLAB_CHANNEL_ID,
            text=draft,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("channel_news_radar failed")
        await query.message.reply_text(
            "Не удалось опубликовать новостной радар. Проверь канал и логи."
        )
        return

    draft_item["published"] = True
    draft_item["published_at"] = datetime.now(ALMATY_TZ).isoformat()
    draft_item["published_message_id"] = sent_message.message_id
    logger.info(
        "channel_news_radar published: draft_id=%s message_id=%s",
        draft_id,
        sent_message.message_id,
    )
    await query.message.reply_text("Новостной радар опубликован в канал.")


async def channel_news_skip_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if not is_private_chat(update):
        await query.message.reply_text(
            "Админ-панель доступна только в личке с ботом."
        )
        return

    admin_id = update.effective_user.id if update.effective_user else None
    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    draft_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    news_drafts = context.bot_data.get("channel_news_drafts") or {}
    if draft_id in news_drafts:
        news_drafts[draft_id]["skipped"] = True
        news_drafts[draft_id]["skipped_at"] = datetime.now(ALMATY_TZ).isoformat()
    await query.message.reply_text("Новостной радар пропущен.")


async def channel_plan_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.info(
        "channel_plan requested: user_id=%s",
        update.effective_user.id if update.effective_user else None,
    )
    if not is_private_chat(update):
        if update.message:
            await update.message.reply_text(
                "AI-агент канала работает только в личке с ботом."
            )
        return

    if not update.effective_user or not is_admin_user(update.effective_user.id):
        logger.info(
            "channel_plan denied non-admin: user_id=%s",
            update.effective_user.id if update.effective_user else None,
        )
        if update.message:
            await update.message.reply_text(
                "Команда доступна только администратору."
            )
        return

    if not update.message:
        return

    await send_channel_plan_candidates(update.message, context)


async def send_channel_plan_candidates(
    message,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await message.reply_text("Подбираю кандидатов на матч дня…")
    candidates = await asyncio.to_thread(get_channel_plan_candidates)
    logger.info("channel_plan candidates found: count=%s", len(candidates))
    if not candidates:
        await message.reply_text(
            "Не нашёл подходящие ближайшие матчи. Попробуйте позже."
        )
        return

    store_channel_candidates(context, candidates)
    await message.reply_text(
        build_channel_plan_message(candidates),
        reply_markup=build_channel_plan_keyboard(candidates),
    )


async def show_channel_plan_again(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not query.message:
        return
    await send_channel_plan_candidates(query.message, context)


async def create_and_store_channel_matchday_draft(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    match: dict,
    progress_text: bool = True,
) -> tuple[str | None, str | None]:
    match_id = str(match.get("id") or "").strip()
    if not match_id:
        await message.reply_text("У матча нет ID, черновик не готов.")
        return None, None

    home = format_channel_team_display(match.get("home")) or "Команда 1"
    away = format_channel_team_display(match.get("away")) or "Команда 2"
    if progress_text:
        await message.reply_text(
            f"Готовлю черновик поста для канала по матчу {home} — {away}…"
        )
    logger.info(
        "channel_draft started: user_id=%s match_id=%s",
        admin_id,
        match_id,
    )

    try:
        analysis_result, _, _ = await asyncio.to_thread(
            get_or_create_channel_match_ai_analysis,
            admin_id,
            match,
        )
    except Exception:
        logger.exception(
            "channel_draft failed: user_id=%s match_id=%s",
            admin_id,
            match_id,
        )
        await message.reply_text(
            "Не удалось подготовить AI-черновик. Попробуйте позже."
        )
        return None, None

    if not analysis_result:
        await message.reply_text(
            "AI-разбор временно недоступен, черновик не готов."
        )
        return None, None

    draft = build_channel_post_draft(match, analysis_result)
    logger.info("channel_draft generated: match_id=%s", match_id)
    draft = sanitize_channel_post_text(draft)
    logger.info(
        "channel_draft sanitized: match_id=%s forbidden_left=%s",
        match_id,
        channel_text_has_forbidden_words(draft),
    )
    if channel_text_has_forbidden_words(draft):
        await message.reply_text(
            "Черновик содержит запрещённые слова после фильтра. "
            "Нужна ручная проверка."
        )
        return None, None

    drafts = context.bot_data.setdefault("channel_plan_drafts", {})
    drafts[match_id] = {
        "draft": draft,
        "match": match,
        "full_ai_source": build_channel_full_ai_source_text(match, analysis_result),
        "content_type": "pre_match",
        "created_at": datetime.now(timezone.utc).timestamp(),
    }
    return match_id, draft


async def auto_prepare_channel_matchday(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
) -> None:
    logger.info(
        "channel_agent auto matchday started: user_id=%s",
        admin_id,
    )
    await message.reply_text("🤖 Подбираю лучший Матч дня…")
    try:
        candidates = await asyncio.to_thread(get_channel_plan_candidates, 8)
    except Exception:
        logger.exception(
            "channel_agent auto matchday failed: stage=candidates user_id=%s",
            admin_id,
        )
        await message.reply_text(
            "Не удалось подобрать Матч дня. Попробуйте позже."
        )
        return

    logger.info("channel_agent candidates found: count=%s", len(candidates))
    if not candidates:
        await message.reply_text(
            "Не нашёл подходящие ближайшие матчи. Попробуйте позже."
        )
        return

    best_match, top_matches = select_best_channel_matchday_candidate(candidates)
    if not best_match:
        await message.reply_text("Не удалось выбрать Матч дня из кандидатов.")
        return

    store_channel_candidates(context, top_matches or candidates)
    match_id = str(best_match.get("id") or "").strip()
    logger.info(
        "channel_agent selected match_id=%s score=%s",
        match_id,
        best_match.get("agent_score"),
    )
    logger.info(
        "channel_agent selected reasons=%s",
        best_match.get("agent_reasons") or [],
    )

    draft_match_id, draft = await create_and_store_channel_matchday_draft(
        message,
        context,
        admin_id,
        best_match,
        progress_text=False,
    )
    if not draft_match_id or not draft:
        logger.warning(
            "channel_agent auto matchday failed: stage=draft match_id=%s",
            match_id,
        )
        return

    logger.info(
        "channel_agent auto matchday draft created: match_id=%s",
        draft_match_id,
    )
    context.bot_data["channel_agent_last_matchday"] = {
        "match_id": draft_match_id,
        "match": best_match,
        "selected_at": datetime.now(timezone.utc).timestamp(),
        "status": "pre_match_draft_created",
        "agent_score": best_match.get("agent_score"),
        "agent_reasons": best_match.get("agent_reasons") or [],
        "_source": "memory",
    }
    save_channel_agent_last_matchday_to_db(
        context.bot_data["channel_agent_last_matchday"]
    )
    await message.reply_text(
        build_channel_agent_selection_message(best_match, top_matches),
        reply_markup=build_channel_agent_selection_keyboard(),
    )
    await message.reply_text(
        draft,
        reply_markup=get_channel_draft_keyboard(
            draft_match_id,
            content_type="pre_match",
        ),
    )


async def channel_recap_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.info(
        "channel_recap requested: user_id=%s",
        update.effective_user.id if update.effective_user else None,
    )
    if not is_private_chat(update):
        if update.message:
            await update.message.reply_text(
                "AI-агент канала работает только в личке с ботом."
            )
        return

    if not update.effective_user or not is_admin_user(update.effective_user.id):
        logger.info(
            "channel_recap denied non-admin: user_id=%s",
            update.effective_user.id if update.effective_user else None,
        )
        if update.message:
            await update.message.reply_text(
                "Команда доступна только администратору."
            )
        return

    if not update.message:
        return

    await send_channel_recap_candidates(
        update.message,
        context,
        update.effective_user.id,
    )


async def send_channel_recap_candidates(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int | None,
) -> None:
    await message.reply_text("Подбираю завершённые матчи для итогов…")
    candidates = await asyncio.to_thread(get_channel_recap_candidates, admin_id)
    logger.info("channel_recap candidates found: count=%s", len(candidates))
    if not candidates:
        await message.reply_text(
            "Не нашёл завершённые матчи для итогов. Попробуйте позже."
        )
        return

    store_channel_candidates(context, candidates)
    await message.reply_text(
        build_channel_recap_message(candidates),
        reply_markup=build_channel_recap_keyboard(candidates),
    )


async def show_channel_recap_again(
    query,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not query.message:
        return
    admin_id = query.from_user.id if query.from_user else None
    await send_channel_recap_candidates(query.message, context, admin_id)


async def create_and_store_channel_recap_draft(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    match: dict,
    progress_text: bool = True,
) -> tuple[str | None, str | None]:
    match_id = str(match.get("id") or "").strip()
    if not match_id:
        await message.reply_text("У матча нет ID, итоговый черновик не готов.")
        return None, None

    if progress_text:
        home = format_channel_team_display(match.get("home")) or "Команда 1"
        away = format_channel_team_display(match.get("away")) or "Команда 2"
        await message.reply_text(
            f"Готовлю итоги матча дня по матчу {home} — {away}…"
        )

    analysis_result, _ = await asyncio.to_thread(
        get_channel_recap_cached_analysis,
        admin_id,
        match_id,
    )
    if not analysis_result:
        await message.reply_text(
            "Для этого матча нет сохранённого AI-разбора до игры, "
            "поэтому корректные итоги подготовить нельзя."
        )
        return None, None

    actual_stats = await asyncio.to_thread(get_channel_match_actual_stats, match)
    actual_events = await asyncio.to_thread(get_channel_match_actual_events, match)
    logger.info(
        "channel_recap actual stats available %s: match_id=%s keys=%s",
        bool(actual_stats),
        match_id,
        sorted(actual_stats.keys()),
    )
    logger.info(
        "channel_recap actual events available %s: match_id=%s goals=%s reds=%s",
        bool(actual_events),
        match_id,
        len((actual_events or {}).get("goals") or []),
        len((actual_events or {}).get("red_cards") or []),
    )
    draft = build_channel_recap_post_draft(
        match,
        analysis_result,
        actual_stats,
        actual_events,
    )
    logger.info("channel_recap draft generated: match_id=%s", match_id)
    draft = sanitize_channel_post_text(draft)
    if channel_text_has_forbidden_words(draft):
        await message.reply_text(
            "Черновик содержит запрещённые слова после фильтра. "
            "Нужна ручная проверка."
        )
        return None, None

    drafts = context.bot_data.setdefault("channel_plan_drafts", {})
    drafts[match_id] = {
        "draft": draft,
        "match": match,
        "content_type": "post_match",
        "created_at": datetime.now(timezone.utc).timestamp(),
    }
    return match_id, draft


def build_channel_agent_recap_ready_message(match: dict) -> str:
    home = translate_team_name_ru(match.get("home")) or "Команда 1"
    away = translate_team_name_ru(match.get("away")) or "Команда 2"
    return "\n".join(
        [
            "🏁 MatchLab Agent подготовил Итоги матча дня",
            "",
            "Матч:",
            f"{home} — {away}",
            f"Счёт: {format_channel_match_score(match)}",
            "",
            "Ниже готовый итоговый Telegram-пост.",
        ]
    )


def build_channel_agent_recap_not_ready_message(last_matchday: dict) -> str:
    match = last_matchday.get("match") or {}
    home = translate_team_name_ru(match.get("home")) or "Команда 1"
    away = translate_team_name_ru(match.get("away")) or "Команда 2"
    return "\n".join(
        [
            "Матч дня пока не найден среди завершённых матчей.",
            "Возможно, он ещё не закончился или статистика ещё не обновилась.",
            "",
            f"Ждём матч: {home} — {away}",
            f"match_id: {last_matchday.get('match_id')}",
        ]
    )


async def auto_prepare_channel_recap(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
) -> None:
    logger.info("channel_agent recap started: user_id=%s", admin_id)
    await message.reply_text("🏁 Проверяю выбранный Матч дня для итогов…")
    last_matchday = get_channel_agent_last_matchday(context)
    if not last_matchday:
        logger.info("channel_agent last_matchday found: match_id=None status=None")
        await message.reply_text(
            "Пока нет выбранного агентом Матча дня. Сначала нажми "
            "🧠 Подготовить Матч дня или используй /channel_recap вручную.",
            reply_markup=build_channel_agent_recap_manual_keyboard(),
        )
        return

    match_id = str(last_matchday.get("match_id") or "").strip()
    logger.info(
        "channel_agent last_matchday found: match_id=%s status=%s",
        match_id,
        last_matchday.get("status"),
    )
    try:
        candidates = await asyncio.to_thread(get_channel_recap_candidates, admin_id)
    except Exception:
        logger.exception(
            "channel_agent recap failed: stage=candidates match_id=%s",
            match_id,
        )
        await message.reply_text(
            "Не удалось проверить завершённые матчи. Попробуйте позже.",
            reply_markup=build_channel_agent_recap_manual_keyboard(),
        )
        return

    logger.info("channel_agent recap candidates found: count=%s", len(candidates))
    recap_match = find_recap_candidate_for_last_matchday(last_matchday, candidates)
    if not recap_match:
        logger.info("channel_agent recap not ready: match_id=%s", match_id)
        await message.reply_text(
            build_channel_agent_recap_not_ready_message(last_matchday),
            reply_markup=build_channel_agent_recap_manual_keyboard(),
        )
        return

    logger.info("channel_agent recap matched: match_id=%s", match_id)
    draft_match_id, draft = await create_and_store_channel_recap_draft(
        message,
        context,
        admin_id,
        recap_match,
        progress_text=False,
    )
    if not draft_match_id or not draft:
        logger.warning("channel_agent recap failed: stage=draft match_id=%s", match_id)
        return

    last_matchday["status"] = "post_match_draft_created"
    last_matchday["post_match_draft_created_at"] = datetime.now(
        timezone.utc
    ).timestamp()
    last_matchday["match"] = recap_match
    last_matchday["_source"] = "memory"
    context.bot_data["channel_agent_last_matchday"] = last_matchday
    save_channel_agent_last_matchday_to_db(last_matchday)
    logger.info("channel_agent recap draft created: match_id=%s", draft_match_id)

    await message.reply_text(build_channel_agent_recap_ready_message(recap_match))
    await message.reply_text(
        draft,
        reply_markup=get_channel_draft_keyboard(
            draft_match_id,
            content_type="post_match",
        ),
    )


async def send_long_admin_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    title: str | None = None,
) -> None:
    message = update.callback_query.message if update.callback_query else update.effective_message
    if not message:
        return

    full_text = str(text or "")
    if title:
        full_text = f"{title}\n\n{full_text}".strip()

    max_chars = 3500
    if len(full_text) <= max_chars:
        await message.reply_text(full_text)
        return

    parts = []
    remaining = full_text
    while remaining:
        if len(remaining) <= max_chars:
            parts.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < int(max_chars * 0.6):
            split_at = max_chars
        parts.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    total_parts = len(parts)
    for index, part in enumerate(parts, start=1):
        await message.reply_text(f"Часть {index}/{total_parts}\n\n{part}")


async def channel_pick_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        logger.info("channel_plan denied non-admin: user_id=%s", admin_id)
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    logger.info(
        "channel_plan candidate selected: user_id=%s match_id=%s",
        admin_id,
        match_id,
    )
    match = await asyncio.to_thread(get_stored_channel_match, context, match_id)
    if not match:
        await query.message.reply_text(
            "Матч не найден или уже недоступен. Запустите /channel_plan ещё раз."
        )
        return

    draft_match_id, draft = await create_and_store_channel_matchday_draft(
        query.message,
        context,
        admin_id,
        match,
    )
    if not draft_match_id or not draft:
        return

    await query.message.reply_text(
        draft,
        reply_markup=get_channel_draft_keyboard(draft_match_id),
    )


async def channel_show_post_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Сначала выбери матч через /channel_plan."
        )
        return
    if (draft_item.get("content_type") or "pre_match") != "pre_match":
        await query.message.reply_text("Эта кнопка только для Матча дня.")
        return

    await send_long_admin_message(
        update,
        context,
        draft_item.get("draft") or "",
        title="📝 Пост для Telegram",
    )


async def channel_tg_cover_prompt_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_prompt tg_cover requested: match_id=%s content_type=%s",
        match_id,
        content_type,
    )
    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Сначала выбери матч через /channel_plan."
        )
        return
    if content_type == "post_match":
        prompt = build_recap_tg_cover_prompt(
            draft_item.get("match") or {},
            draft_item.get("draft") or "",
        )
        title = "🖼 Промпт TG-обложки итогов"
    elif content_type == "pre_match":
        prompt = build_matchday_tg_cover_prompt(
            draft_item.get("match") or {},
            draft_item.get("draft") or "",
        )
        title = "🖼 Промпт TG-обложки"
    else:
        await query.message.reply_text("Эта кнопка недоступна для этого черновика.")
        return

    logger.info("channel_prompt length=%s", len(prompt))
    try:
        await send_long_admin_message(
            update,
            context,
            prompt,
            title=title,
        )
    except Exception:
        logger.exception("channel_prompt send failed: match_id=%s", match_id)
        await query.message.reply_text("Не удалось отправить промпт. Попробуйте позже.")


async def channel_social_cards_prompt_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_prompt social_cards requested: match_id=%s content_type=%s",
        match_id,
        content_type,
    )
    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Сначала выбери матч через /channel_plan."
        )
        return
    if content_type == "post_match":
        prompt = build_recap_social_cards_prompt(
            draft_item.get("match") or {},
            draft_item.get("draft") or "",
        )
        title = "📱 Промпт 7 карточек итогов"
    elif content_type == "pre_match":
        prompt = build_matchday_social_cards_prompt(
            draft_item.get("match") or {},
            draft_item.get("full_ai_source") or draft_item.get("draft") or "",
        )
        title = "📱 Промпт 7 карточек"
    else:
        await query.message.reply_text("Эта кнопка недоступна для этого черновика.")
        return

    logger.info("channel_prompt length=%s", len(prompt))
    try:
        await send_long_admin_message(
            update,
            context,
            prompt,
            title=title,
        )
    except Exception:
        logger.exception("channel_prompt send failed: match_id=%s", match_id)
        await query.message.reply_text("Не удалось отправить промпт. Попробуйте позже.")


async def channel_recap_pick_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        logger.info("channel_recap denied non-admin: user_id=%s", admin_id)
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    logger.info(
        "channel_recap candidate selected: user_id=%s match_id=%s",
        admin_id,
        match_id,
    )
    match = await asyncio.to_thread(get_stored_channel_match, context, match_id)
    if not match:
        await query.message.reply_text(
            "Матч не найден или уже недоступен. Запустите /channel_recap ещё раз."
        )
        return

    draft_match_id, draft = await create_and_store_channel_recap_draft(
        query.message,
        context,
        admin_id,
        match,
    )
    if not draft_match_id or not draft:
        return

    await query.message.reply_text(
        draft,
        reply_markup=get_channel_draft_keyboard(draft_match_id, "post_match"),
    )


async def channel_publish_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_publish requested: user_id=%s match_id=%s content_type=%s",
        admin_id,
        match_id,
        content_type,
    )

    channel_configured = bool(MATCHLAB_CHANNEL_ID)
    logger.info(
        "channel_publish channel_configured %s: match_id=%s content_type=%s",
        channel_configured,
        match_id,
        content_type,
    )
    if not channel_configured:
        await query.message.reply_text(
            "Канал не настроен: добавьте MATCHLAB_CHANNEL_ID в Environment."
        )
        return

    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Выберите матч заново через /channel_plan."
        )
        return

    if draft_item.get("published_at"):
        logger.info(
            "channel_publish skipped already_published: match_id=%s "
            "content_type=%s",
            match_id,
            content_type,
        )
        await query.message.reply_text("Этот черновик уже опубликован.")
        return

    draft = draft_item.get("draft") or ""
    forbidden_left = channel_text_has_forbidden_words(draft)
    logger.info(
        "channel_publish forbidden_left %s: match_id=%s content_type=%s",
        forbidden_left,
        match_id,
        content_type,
    )
    if forbidden_left:
        await query.message.reply_text(
            "Пост содержит запрещённые слова. Нужна ручная проверка."
        )
        return

    try:
        sent_message = await context.bot.send_message(
            chat_id=MATCHLAB_CHANNEL_ID,
            text=draft,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception(
            "channel_publish failed: match_id=%s content_type=%s "
            "channel_id_configured=%s",
            match_id,
            content_type,
            True,
        )
        await query.message.reply_text(
            "Не удалось опубликовать пост в канал. Проверьте, что "
            "MATCHLAB_CHANNEL_ID указан правильно и бот добавлен админом "
            "канала."
        )
        return

    draft_item["published_at"] = datetime.now(timezone.utc).isoformat()
    draft_item["published_message_id"] = sent_message.message_id
    last_matchday = get_channel_agent_last_matchday(context)
    if (
        content_type == "pre_match"
        and last_matchday
        and str(last_matchday.get("match_id") or "").strip() == match_id
    ):
        last_matchday["status"] = "pre_match_published"
        last_matchday["pre_match_published_at"] = datetime.now(
            timezone.utc
        ).timestamp()
        last_matchday["pre_match_message_id"] = sent_message.message_id
        last_matchday["_source"] = "memory"
        context.bot_data["channel_agent_last_matchday"] = last_matchday
        save_channel_agent_last_matchday_to_db(last_matchday)
    elif (
        content_type == "post_match"
        and last_matchday
        and str(last_matchday.get("match_id") or "").strip() == match_id
    ):
        last_matchday["status"] = "post_match_published"
        last_matchday["post_match_published_at"] = datetime.now(
            timezone.utc
        ).timestamp()
        last_matchday["post_match_message_id"] = sent_message.message_id
        last_matchday["_source"] = "memory"
        context.bot_data["channel_agent_last_matchday"] = last_matchday
        save_channel_agent_last_matchday_to_db(last_matchday)
    logger.info(
        "channel_publish success: match_id=%s content_type=%s message_id=%s",
        match_id,
        content_type,
        sent_message.message_id,
    )
    await query.message.reply_text("Пост опубликован в канал.")


async def channel_publish_cover_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_publish_cover requested: user_id=%s match_id=%s "
        "content_type=%s",
        admin_id,
        match_id,
        content_type,
    )

    channel_configured = bool(MATCHLAB_CHANNEL_ID)
    logger.info(
        "channel_publish_cover channel_configured %s: match_id=%s",
        channel_configured,
        match_id,
    )
    if not channel_configured:
        await query.message.reply_text(
            "Канал не настроен: добавьте MATCHLAB_CHANNEL_ID в Environment."
        )
        return

    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Выберите матч заново через /channel_plan."
        )
        return

    if content_type != "pre_match":
        await query.message.reply_text(
            "Публикация с обложкой пока доступна только для Матча дня."
        )
        return

    if draft_item.get("cover_published_at"):
        logger.info(
            "channel_publish_cover skipped already_published: match_id=%s",
            match_id,
        )
        await query.message.reply_text(
            "Этот черновик уже опубликован с обложкой."
        )
        return

    draft = draft_item.get("draft") or ""
    draft_to_publish = (
        limit_channel_text_preserving_disclaimer(draft, 950)
        if len(draft) > 950
        else draft
    )
    draft_to_publish = sanitize_channel_post_text(draft_to_publish)
    logger.info(
        "channel_publish_cover caption_length chars=%s",
        len(draft_to_publish),
    )
    forbidden_left = channel_text_has_forbidden_words(draft_to_publish)
    logger.info(
        "channel_publish_cover forbidden_left %s: match_id=%s",
        forbidden_left,
        match_id,
    )
    if forbidden_left:
        await query.message.reply_text(
            "Пост содержит запрещённые слова. Нужна ручная проверка."
        )
        return

    cover_path = ""
    try:
        cover_path = await asyncio.to_thread(
            generate_channel_matchday_cover,
            draft_item.get("match") or {},
        )
    except Exception:
        logger.exception("channel_publish_cover cover generation failed: match_id=%s", match_id)
        await query.message.reply_text(
            "Не удалось подготовить обложку. Попробуйте позже."
        )
        return

    logger.info("channel_publish_cover generated cover: path=%s", cover_path)
    try:
        with open(cover_path, "rb") as cover_file:
            sent_message = await context.bot.send_photo(
                chat_id=MATCHLAB_CHANNEL_ID,
                photo=cover_file,
                caption=draft_to_publish,
            )
    except Exception:
        logger.exception("channel_publish_cover failed: match_id=%s", match_id)
        await query.message.reply_text(
            "Не удалось опубликовать пост с обложкой. Проверьте, что бот "
            "добавлен админом канала и MATCHLAB_CHANNEL_ID указан правильно."
        )
        return
    finally:
        if cover_path:
            try:
                Path(cover_path).unlink(missing_ok=True)
            except Exception:
                logger.debug(
                    "channel_publish_cover temp cleanup failed: path=%s",
                    cover_path,
                    exc_info=True,
                )

    draft_item["cover_published_at"] = datetime.now(timezone.utc).isoformat()
    draft_item["cover_published_message_id"] = sent_message.message_id
    logger.info(
        "channel_publish_cover success: match_id=%s message_id=%s",
        match_id,
        sent_message.message_id,
    )
    await query.message.reply_text("Пост с обложкой опубликован в канал.")


async def channel_shorten_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    logger.info(
        "channel_draft_shorten clicked: user_id=%s match_id=%s",
        admin_id,
        match_id,
    )
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    if not draft_item:
        await query.message.reply_text(
            "Черновик не найден. Выберите матч заново через /channel_plan."
        )
        return

    shortened = shorten_channel_post_draft(draft_item.get("draft") or "")
    draft_item["draft"] = shortened
    draft_item["created_at"] = datetime.now(timezone.utc).timestamp()
    await query.message.reply_text(
        shortened,
        reply_markup=get_channel_draft_keyboard(
            match_id,
            draft_item.get("content_type") or "pre_match",
        ),
    )


async def channel_social_caption_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_social_caption requested: user_id=%s match_id=%s "
        "content_type=%s",
        admin_id,
        match_id,
        content_type,
    )

    if not draft_item:
        await query.message.reply_text("Черновик не найден. Выберите матч заново.")
        return

    caption = build_social_caption_for_draft(
        draft_item.get("match") or {},
        content_type,
        draft_item.get("draft") or "",
    )
    forbidden_left = channel_text_has_forbidden_words(caption)
    logger.info(
        "channel_social_caption length chars=%s forbidden_left=%s",
        len(caption),
        forbidden_left,
    )
    if forbidden_left:
        await query.message.reply_text(
            "Описание содержит запрещённые слова. Нужна ручная проверка."
        )
        return

    await query.message.reply_text(caption)


async def channel_cover_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    callback_data = query.data or ""
    match_id = callback_data.split(":", 1)[1].strip() if ":" in callback_data else ""
    cleanup_channel_bot_data(context)
    draft_item = (context.bot_data.get("channel_plan_drafts") or {}).get(match_id)
    content_type = (draft_item or {}).get("content_type") or "pre_match"
    logger.info(
        "channel_cover requested: user_id=%s match_id=%s content_type=%s",
        admin_id,
        match_id,
        content_type,
    )

    if not draft_item:
        await query.message.reply_text("Черновик не найден. Выберите матч заново.")
        return

    if content_type != "pre_match":
        await query.message.reply_text("Обложка пока доступна только для Матча дня.")
        return

    cover_path = ""
    try:
        cover_path = await asyncio.to_thread(
            generate_channel_matchday_cover,
            draft_item.get("match") or {},
        )
        logger.info("channel_cover generated: match_id=%s path=%s", match_id, cover_path)
        with open(cover_path, "rb") as cover_file:
            await query.message.reply_photo(
                photo=cover_file,
                caption='Обложка "Матч дня" готова.',
            )
    except Exception:
        logger.exception("channel_cover failed: match_id=%s", match_id)
        await query.message.reply_text(
            "Не удалось подготовить обложку. Попробуйте позже."
        )
    finally:
        if cover_path:
            try:
                Path(cover_path).unlink(missing_ok=True)
            except Exception:
                logger.debug(
                    "channel_cover temp cleanup failed: path=%s",
                    cover_path,
                    exc_info=True,
                )


async def channel_plan_again_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    await show_channel_plan_again(query, context)


async def channel_recap_again_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_id = update.effective_user.id if update.effective_user else None
    if not is_private_chat(update):
        await query.message.reply_text(
            "AI-агент канала работает только в личке с ботом."
        )
        return

    if admin_id is None or not is_admin_user(admin_id):
        await query.message.reply_text("Команда доступна только администратору.")
        return

    await show_channel_recap_again(query, context)


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


@miniapp_api.post("/api/events")
def miniapp_events():
    telegram_user = get_api_telegram_user(flask_request)
    if not telegram_user:
        return jsonify(
            {
                "ok": False,
                "error": "telegram_user_id_required",
            }
        ), 400

    request_data = flask_request.get_json(silent=True) or {}
    event_type = str(request_data.get("event_type") or "").strip()
    event_data = request_data.get("event_data")
    if event_type not in MINIAPP_EVENT_TYPES:
        return jsonify(
            {
                "ok": False,
                "error": "event_type_not_allowed",
            }
        ), 400

    if not isinstance(event_data, dict):
        event_data = {}

    telegram_user_id = int(telegram_user["id"])
    start_param = str(request_data.get("start_param") or "").strip()
    is_new_miniapp_user = not miniapp_user_exists(telegram_user_id)
    logger.info(
        "miniapp referral user existence before upsert: "
        "user_id=%s is_new_user=%s",
        telegram_user_id,
        is_new_miniapp_user,
    )
    if start_param:
        logger.info(
            "miniapp referral start_param received user_id=%s start_param=%s",
            telegram_user_id,
            start_param,
        )
        parsed_referrer_id = parse_miniapp_ref_param(start_param)
        logger.info(
            "miniapp referral parsed referrer_id=%s referred_id=%s",
            parsed_referrer_id,
            telegram_user_id,
        )
    else:
        parsed_referrer_id = None

    try:
        upsert_bot_user(
            SimpleNamespace(
                id=telegram_user_id,
                username=telegram_user.get("username"),
                first_name=telegram_user.get("first_name"),
                last_name=telegram_user.get("last_name"),
                language_code=telegram_user.get("language_code"),
            )
        )
    except Exception:
        logger.debug(
            "Mini App analytics user upsert failed: user_id=%s",
            telegram_user_id,
            exc_info=True,
        )

    if event_type == "miniapp_opened" and parsed_referrer_id:
        if is_new_miniapp_user:
            record_miniapp_referral(
                parsed_referrer_id,
                telegram_user_id,
                is_new_user=True,
            )
        else:
            logger.info(
                "miniapp referral skipped: existing_user "
                "referrer_id=%s referred_id=%s",
                parsed_referrer_id,
                telegram_user_id,
            )

    try:
        log_user_event(telegram_user_id, event_type, event_data)
    except Exception:
        logger.warning(
            "Mini App analytics event failed: user_id=%s event_type=%s",
            telegram_user_id,
            event_type,
            exc_info=True,
        )

    return jsonify({"ok": True})


@miniapp_api.get("/api/referrals/status")
def miniapp_referrals_status():
    telegram_user = get_api_telegram_user(flask_request)
    if not telegram_user:
        return jsonify(
            {
                "ok": False,
                "error": "telegram_user_id_required",
            }
        ), 400

    telegram_user_id = int(telegram_user["id"])
    return jsonify(get_miniapp_referral_status(telegram_user_id))


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
    bonus_info = get_active_bonus_ai_credit_info(telegram_user_id)
    bonus_ai_remaining = int(bonus_info.get("bonus_ai_remaining") or 0)
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
        "bonus_ai_remaining": bonus_ai_remaining,
        "bonus_ai_expires_at": serialize_api_datetime(
            bonus_info.get("bonus_ai_expires_at")
        ),
        "ai_remaining_total": get_ai_available_count(subscription)
        + bonus_ai_remaining,
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


@miniapp_api.get("/api/matches/live")
def miniapp_matches_live():
    return build_miniapp_matches_response("live")


@miniapp_api.get("/api/matches/<match_id>")
def miniapp_match(match_id: str):
    try:
        match = find_miniapp_match(match_id)
        if not match:
            return jsonify(
                {
                    "ok": False,
                    "error": "match_not_found",
                    "message": "Матч не найден или уже недоступен.",
                }
            ), 404
        return jsonify({"ok": True, "match": match})
    except Exception:
        logger.exception(
            "Mini App match request failed: match_id=%s",
            match_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "match_unavailable",
                "message": "Данные матча временно недоступны.",
            }
        ), 503


@miniapp_api.route(
    "/api/matches/<match_id>/live",
    methods=["GET", "OPTIONS"],
)
def miniapp_match_live(match_id: str):
    if flask_request.method == "OPTIONS":
        return "", 204

    normalized_match_id = str(match_id).strip()
    cached_payload = get_cached_miniapp_live_payload(normalized_match_id)
    if cached_payload:
        return jsonify(cached_payload)

    try:
        fixture_response = request_api_football(
            "/fixtures",
            {
                "id": normalized_match_id,
                "timezone": "UTC",
            },
        )
    except Exception:
        logger.exception(
            "Mini App live fixture request failed: match_id=%s",
            normalized_match_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "live_unavailable",
            }
        ), 503

    if not fixture_response:
        return jsonify(
            {
                "ok": False,
                "error": "match_not_found",
            }
        ), 404

    raw_events = []
    try:
        raw_events = request_api_football(
            "/fixtures/events",
            {"fixture": normalized_match_id},
        )
    except Exception:
        logger.warning(
            "Mini App live events request failed: match_id=%s",
            normalized_match_id,
            exc_info=True,
        )

    try:
        payload = build_miniapp_match_live_payload(
            normalized_match_id,
            fixture_response[0],
            raw_events,
        )
    except Exception:
        logger.exception(
            "Mini App live payload formatting failed: match_id=%s",
            normalized_match_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "live_unavailable",
            }
        ), 503

    ttl_seconds = get_miniapp_live_cache_ttl(
        payload["status"]["short"]
    )
    cache_miniapp_live_payload(
        normalized_match_id,
        payload,
        ttl_seconds,
    )
    return jsonify(payload)


@miniapp_api.get("/api/teams/search")
def miniapp_teams_search():
    query = (flask_request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"ok": True, "items": []})

    try:
        normalized_query = normalize_team_name(query)
        response = request_api_football(
            "/teams",
            {"search": normalized_query},
        )
        items = []
        for team_item in response[:10]:
            formatted_team = format_miniapp_team_item(team_item)
            if formatted_team:
                items.append(formatted_team)
        return jsonify({"ok": True, "items": items})
    except Exception:
        logger.exception("Mini App team search failed: query=%s", query)
        return jsonify(
            {
                "ok": False,
                "items": [],
                "error": "team_search_unavailable",
            }
        ), 503


@miniapp_api.get("/api/teams/<int:team_id>")
def miniapp_team_profile(team_id: int):
    try:
        response = request_api_football("/teams", {"id": team_id})
        team = (
            format_miniapp_team_item(response[0])
            if response
            else None
        )
        if not team:
            return jsonify(
                {
                    "ok": False,
                    "error": "team_not_found",
                    "message": "Команда не найдена.",
                }
            ), 404
        return jsonify({"ok": True, "team": team})
    except Exception:
        logger.exception(
            "Mini App team profile request failed: team_id=%s",
            team_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "team_profile_unavailable",
                "message": "Профиль команды временно недоступен.",
            }
        ), 503


@miniapp_api.get("/api/teams/<int:team_id>/matches")
def miniapp_team_matches(team_id: int):
    recent_fixtures = []
    upcoming_fixtures = []

    try:
        recent_fixtures = get_api_football_finished_fixtures(team_id)
    except Exception:
        logger.warning(
            "Mini App recent team fixtures unavailable: team_id=%s",
            team_id,
            exc_info=True,
        )

    try:
        upcoming_fixtures = get_api_football_next_fixtures(team_id)
    except Exception:
        logger.warning(
            "Mini App upcoming team fixtures unavailable: team_id=%s",
            team_id,
            exc_info=True,
        )

    recent = [
        formatted
        for fixture_item in recent_fixtures[:5]
        if (formatted := format_miniapp_fixture_item(fixture_item))
    ]
    upcoming = [
        formatted
        for fixture_item in upcoming_fixtures[:5]
        if (formatted := format_miniapp_fixture_item(fixture_item))
    ]

    return jsonify(
        {
            "ok": True,
            "recent": recent,
            "upcoming": upcoming,
        }
    )


@miniapp_api.get("/api/teams/<int:team_id>/standings")
def miniapp_team_standings(team_id: int):
    try:
        standings_data = get_miniapp_team_standings_data(team_id)
        if standings_data:
            return jsonify({"ok": True, **standings_data})
    except Exception:
        logger.exception(
            "Mini App team standings request failed: team_id=%s",
            team_id,
        )

    return jsonify(
        {
            "ok": False,
            "error": "team_standings_unavailable",
            "message": "Турнирная таблица команды пока недоступна.",
        }
    ), 404


@miniapp_api.route(
    "/api/favorites/teams",
    methods=["GET", "POST", "OPTIONS"],
)
def miniapp_favorite_teams():
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

    try:
        if flask_request.method == "GET":
            return jsonify(
                {
                    "ok": True,
                    "items": get_miniapp_favorite_teams(telegram_user_id),
                }
            )

        request_data = flask_request.get_json(silent=True) or {}
        team = request_data.get("team")
        if not isinstance(team, dict):
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid_team",
                    "message": "Не удалось сохранить команду.",
                }
            ), 400

        team_id = team.get("id")
        team_name = str(team.get("name") or "").strip()
        try:
            team_id = int(team_id)
        except (TypeError, ValueError):
            team_id = 0

        if team_id <= 0 or not team_name:
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid_team",
                    "message": "Не удалось сохранить команду.",
                }
            ), 400

        add_miniapp_favorite_team(
            telegram_user_id,
            {
                "id": team_id,
                "name": team_name,
                "logo": team.get("logo"),
                "country": str(team.get("country") or "").strip(),
            },
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception(
            "Mini App favorite teams request failed: "
            "method=%s user_id=%s",
            flask_request.method,
            telegram_user_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "favorite_teams_unavailable",
                "message": "Избранные команды временно недоступны.",
            }
        ), 503


@miniapp_api.route(
    "/api/favorites/teams/<int:team_id>",
    methods=["DELETE", "OPTIONS"],
)
def miniapp_favorite_team_delete(team_id: int):
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
    try:
        remove_miniapp_favorite_team(telegram_user_id, team_id)
        return jsonify({"ok": True})
    except Exception:
        logger.exception(
            "Mini App favorite team delete failed: "
            "user_id=%s team_id=%s",
            telegram_user_id,
            team_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "favorite_teams_unavailable",
                "message": "Избранные команды временно недоступны.",
            }
        ), 503


@miniapp_api.route(
    "/api/reminders/matches",
    methods=["GET", "POST", "OPTIONS"],
)
def miniapp_match_reminders():
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

    try:
        if flask_request.method == "GET":
            return jsonify(
                {
                    "ok": True,
                    "items": get_miniapp_match_reminders(telegram_user_id),
                }
            )

        request_data = flask_request.get_json(silent=True) or {}
        match = request_data.get("match")
        if not isinstance(match, dict):
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid_match",
                    "message": "Не удалось сохранить напоминание.",
                }
            ), 400

        match_id = str(match.get("id") or "").strip()
        kickoff = str(match.get("kickoff") or "").strip()
        if not match_id or not kickoff:
            return jsonify(
                {
                    "ok": False,
                    "error": "match_kickoff_required",
                    "message": "Для матча не указано время начала.",
                }
            ), 400

        try:
            parsed_kickoff = datetime.fromisoformat(
                kickoff.replace("Z", "+00:00")
            )
        except ValueError:
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid_match_kickoff",
                    "message": "Не удалось определить время начала матча.",
                }
            ), 400

        if parsed_kickoff.tzinfo is None:
            return jsonify(
                {
                    "ok": False,
                    "error": "invalid_match_kickoff",
                    "message": "Не удалось определить часовой пояс матча.",
                }
            ), 400

        add_miniapp_match_reminder(
            telegram_user_id,
            {
                "id": match_id,
                "home": str(match.get("home") or "").strip(),
                "away": str(match.get("away") or "").strip(),
                "league": str(match.get("league") or "").strip(),
                "kickoff": parsed_kickoff.isoformat(),
            },
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception(
            "Mini App match reminders request failed: "
            "method=%s user_id=%s",
            flask_request.method,
            telegram_user_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "match_reminders_unavailable",
                "message": "Напоминания временно недоступны.",
            }
        ), 503


@miniapp_api.route(
    "/api/reminders/matches/<path:match_id>",
    methods=["DELETE", "OPTIONS"],
)
def miniapp_match_reminder_delete(match_id: str):
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
    try:
        remove_miniapp_match_reminder(
            telegram_user_id,
            match_id.strip(),
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception(
            "Mini App match reminder delete failed: "
            "user_id=%s match_id=%s",
            telegram_user_id,
            match_id,
        )
        return jsonify(
            {
                "ok": False,
                "error": "match_reminders_unavailable",
                "message": "Напоминания временно недоступны.",
            }
        ), 503


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
    methods=["GET", "POST", "OPTIONS"],
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
    raw_match_id = str(match_id or "").strip()
    normalized_match_id = normalize_ai_analysis_match_id(raw_match_id)
    is_admin = is_admin_user(telegram_user_id)
    subscription = (
        {} if is_admin else get_or_create_subscription(telegram_user_id)
    )
    bonus_ai_remaining = (
        0 if is_admin else get_active_bonus_ai_credits(telegram_user_id)
    )
    analysis_mode = (
        "premium"
        if is_admin or is_premium_active(subscription) or bonus_ai_remaining > 0
        else "default"
    )

    if flask_request.method == "GET":
        logger.info(
            "AI saved lookup started: user_id=%s raw_match_id=%s "
            "normalized_match_id=%s analysis_mode=%s source=miniapp_get",
            telegram_user_id,
            raw_match_id,
            normalized_match_id,
            analysis_mode,
        )
        try:
            saved_analysis, normalized_match_id = (
                lookup_saved_miniapp_ai_analysis(
                    telegram_user_id,
                    raw_match_id,
                    analysis_mode,
                )
            )
        except Exception:
            logger.error(
                "AI saved lookup failed: user_id=%s raw_match_id=%s "
                "normalized_match_id=%s analysis_mode=%s",
                telegram_user_id,
                raw_match_id,
                normalized_match_id,
                analysis_mode,
                exc_info=True,
            )
            return jsonify(
                {
                    "ok": False,
                    "error": "saved_analysis_unavailable",
                    "message": "AI-разбор временно недоступен.",
                }
            ), 503

        logger.info(
            "AI saved lookup completed: user_id=%s raw_match_id=%s "
            "normalized_match_id=%s saved_match_id=%s analysis_mode=%s "
            "found=%s source=miniapp_get",
            telegram_user_id,
            raw_match_id,
            normalized_match_id,
            normalized_match_id,
            analysis_mode,
            bool(saved_analysis),
        )
        if not saved_analysis:
            logger.info(
                "ai unlock auto_load needs_unlock: user_id=%s match_id=%s "
                "analysis_mode=%s",
                telegram_user_id,
                raw_match_id,
                analysis_mode,
            )
            return jsonify(
                {
                    "ok": False,
                    "status": "needs_unlock",
                    "error": "needs_unlock",
                    "message": "AI-разбор ещё не открыт для этого матча.",
                    "analysis_mode": analysis_mode,
                    "unlocked": False,
                    "charged": False,
                }
            )

        remaining_ai = (
            None if is_admin else get_total_ai_available_count(
                telegram_user_id,
                subscription,
            )
        )
        logger.info(
            "ai unlock existing user unlock: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        return jsonify(
            build_miniapp_ai_saved_response(
                saved_analysis,
                normalized_match_id,
                remaining_ai,
                is_admin,
                from_personal_cache=True,
                source="user_unlock",
            )
        )

    request_data = flask_request.get_json(silent=True) or {}
    force_refresh = request_data.get("force_refresh") is True
    unlock_requested = request_data.get("unlock") is True
    logger.info(
        "AI generation started: user_id=%s raw_match_id=%s "
        "normalized_match_id=%s analysis_mode=%s force_refresh=%s "
        "unlock=%s "
        "source=miniapp_post",
        telegram_user_id,
        raw_match_id,
        normalized_match_id,
        analysis_mode,
        force_refresh,
        unlock_requested,
    )

    remaining_ai = (
        None if is_admin else get_total_ai_available_count(
            telegram_user_id,
            subscription,
        )
    )
    try:
        saved_analysis, normalized_match_id = lookup_saved_miniapp_ai_analysis(
            telegram_user_id,
            raw_match_id,
            analysis_mode,
        )
    except Exception:
        logger.error(
            "AI saved lookup failed before generation: user_id=%s "
            "raw_match_id=%s normalized_match_id=%s analysis_mode=%s",
            telegram_user_id,
            raw_match_id,
            normalized_match_id,
            analysis_mode,
            exc_info=True,
        )
        return jsonify(
            {
                "ok": False,
                "error": "saved_analysis_unavailable",
                "message": "AI-разбор временно недоступен.",
            }
        ), 503
    logger.info(
        "AI generation cache state: user_id=%s normalized_match_id=%s "
        "analysis_mode=%s force_refresh=%s saved_before=%s",
        telegram_user_id,
        normalized_match_id,
        analysis_mode,
        force_refresh,
        bool(saved_analysis),
    )
    if saved_analysis and not force_refresh:
        logger.info(
            "personal saved AI found true: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        logger.info(
            "OpenAI generation required false: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        logger.info(
            "ai unlock skipped already_unlocked: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        return jsonify(
            build_miniapp_ai_saved_response(
                saved_analysis,
                normalized_match_id,
                remaining_ai,
                is_admin,
                from_personal_cache=True,
                source="user_unlock",
            )
        )

    if saved_analysis and force_refresh:
        current_refresh_count = int(saved_analysis.get("refresh_count") or 0)
        free_refresh_allowed = (
            is_admin or current_refresh_count < MINIAPP_AI_FREE_REFRESH_TOTAL
        )
        logger.info(
            "AI refresh requested: user_id=%s match_id=%s analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        logger.info(
            "AI refresh count current: user_id=%s match_id=%s "
            "analysis_mode=%s refresh_count=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
            current_refresh_count,
        )
        logger.info(
            "AI free refresh allowed %s: user_id=%s match_id=%s "
            "analysis_mode=%s",
            free_refresh_allowed,
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        if not free_refresh_allowed:
            logger.info(
                "AI refresh blocked because free refresh limit reached: "
                "user_id=%s match_id=%s analysis_mode=%s",
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
            return jsonify(
                {
                    "ok": False,
                    "error": "ai_refresh_limit_exceeded",
                    "message": (
                        "Бесплатные обновления для этого AI-разбора "
                        "закончились. Для одного матча доступно 2 "
                        "бесплатных обновления."
                    ),
                    "refresh_count": current_refresh_count,
                    "free_refreshes_total": MINIAPP_AI_FREE_REFRESH_TOTAL,
                    "free_refreshes_left": 0,
                }
            ), 429

    if not saved_analysis and not force_refresh and not unlock_requested:
        logger.info(
            "ai unlock auto_load needs_unlock: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        return jsonify(
            {
                "ok": False,
                "status": "needs_unlock",
                "error": "needs_unlock",
                "message": "AI-разбор ещё не открыт для этого матча.",
                "analysis_mode": analysis_mode,
                "unlocked": False,
                "charged": False,
            }
        )

    if (
        analysis_mode == "premium"
        and not saved_analysis
        and not is_admin
        and not is_premium_active(subscription)
        and bonus_ai_remaining <= 0
    ):
        logger.info(
            "ai unlock premium_required: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        return jsonify(
            {
                "ok": False,
                "status": "premium_required",
                "error": "premium_required",
                "message": "Premium AI-разбор доступен по подписке.",
                "analysis_mode": analysis_mode,
                "unlocked": False,
                "charged": False,
            }
        ), 402

    if not saved_analysis:
        logger.info(
            "personal saved AI found false: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        logger.info(
            "global AI cache lookup started: match_id=%s analysis_mode=%s",
            normalized_match_id,
            analysis_mode,
        )
        global_analysis = get_global_miniapp_ai_analysis(
            normalized_match_id,
            analysis_mode,
        )
        logger.info(
            "global AI cache found %s: match_id=%s analysis_mode=%s",
            bool(global_analysis),
            normalized_match_id,
            analysis_mode,
        )
        if global_analysis:
            logger.info(
                "OpenAI generation required false: user_id=%s match_id=%s "
                "analysis_mode=%s",
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
            if is_admin:
                analysis_saved = save_miniapp_ai_analysis(
                    telegram_user_id,
                    normalized_match_id,
                    global_analysis.get("analysis") or "",
                    global_analysis.get("structured"),
                    analysis_mode,
                    global_analysis.get("home_team") or "",
                    global_analysis.get("away_team") or "",
                    global_analysis.get("league") or "",
                    refresh_count=0,
                )
                limit_charged = False
                remaining_ai = None
                save_error = "" if analysis_saved else "save_failed"
            else:
                (
                    analysis_saved,
                    updated_subscription,
                    limit_charged,
                    save_error,
                ) = save_miniapp_ai_analysis_and_charge(
                    telegram_user_id,
                    normalized_match_id,
                    global_analysis.get("analysis") or "",
                    global_analysis.get("structured"),
                    analysis_mode,
                    global_analysis.get("home_team") or "",
                    global_analysis.get("away_team") or "",
                    global_analysis.get("league") or "",
                    source="global_cache",
                )
                if updated_subscription is not None:
                    remaining_ai = get_total_ai_available_count(
                        telegram_user_id,
                        updated_subscription,
                    )
            if not analysis_saved:
                if save_error == "premium_required":
                    logger.info(
                        "ai unlock premium_required: user_id=%s match_id=%s "
                        "analysis_mode=%s from_global_cache=true",
                        telegram_user_id,
                        normalized_match_id,
                        analysis_mode,
                    )
                    return jsonify(
                        {
                            "ok": False,
                            "status": "premium_required",
                            "error": "premium_required",
                            "message": "Premium AI-разбор доступен по подписке.",
                            "analysis_mode": analysis_mode,
                            "unlocked": False,
                            "charged": False,
                        }
                    ), 402
                if save_error == "ai_limit_exceeded":
                    logger.info(
                        "ai unlock limit_exceeded: user_id=%s match_id=%s "
                        "analysis_mode=%s from_global_cache=true",
                        telegram_user_id,
                        normalized_match_id,
                        analysis_mode,
                    )
                    return jsonify(
                        {
                            "ok": False,
                            "status": "ai_limit_exceeded",
                            "error": "ai_limit_exceeded",
                            "message": (
                                "AI-лимит закончился. Оформите подписку "
                                "или докупите AI-разборы."
                            ),
                        }
                    ), 402
                logger.warning(
                    "Global AI cache hit but personal save failed: "
                    "user_id=%s match_id=%s analysis_mode=%s",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                )
                return jsonify(
                    {
                        "ok": False,
                        "error": "saved_analysis_unavailable",
                        "message": "AI-разбор временно недоступен.",
                    }
                ), 503
            verify_miniapp_ai_personal_save(
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
            logger.info(
                "AI limit charged %s: user_id=%s match_id=%s "
                "analysis_mode=%s from_global_cache=true",
                limit_charged,
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
            logger.info(
                "ai unlock charged from global_cache: user_id=%s match_id=%s "
                "analysis_mode=%s charged=%s",
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
                limit_charged,
            )
            logger.info(
                "personal AI saved/linked: user_id=%s match_id=%s "
                "analysis_mode=%s saved=%s",
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
                analysis_saved,
            )
            saved_for_response = None
            try:
                saved_for_response = get_saved_miniapp_ai_analysis(
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                )
            except Exception:
                logger.warning(
                    "AI global cache link reload failed: user_id=%s "
                    "match_id=%s analysis_mode=%s",
                    telegram_user_id,
                    normalized_match_id,
                    analysis_mode,
                    exc_info=True,
                )
            return jsonify(
                build_miniapp_ai_saved_response(
                    saved_for_response or {
                        **global_analysis,
                        "refresh_count": 0,
                        "analysis_mode": analysis_mode,
                    },
                    normalized_match_id,
                    remaining_ai,
                    is_admin,
                    limit_charged=limit_charged,
                    from_global_cache=True,
                    source="global_cache",
                )
            )

    logger.info(
        "OpenAI generation required true: user_id=%s match_id=%s "
        "analysis_mode=%s force_refresh=%s",
        telegram_user_id,
        normalized_match_id,
        analysis_mode,
        force_refresh,
    )
    match = find_miniapp_match(normalized_match_id)
    if not match:
        return jsonify(
            {
                "ok": False,
                "error": "match_not_found",
                "message": "Матч не найден или уже недоступен.",
            }
        ), 404

    if force_refresh and saved_analysis:
        allowed = True
        logger.info(
            "AI limit already charged for this user/match/mode true: "
            "user_id=%s match_id=%s analysis_mode=%s",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
    elif is_admin:
        allowed = True
    elif analysis_mode == "premium":
        bonus_ai_remaining = get_active_bonus_ai_credits(telegram_user_id)
        monthly_remaining = max(
            0,
            int(subscription.get("ai_limit_monthly") or 0)
            - int(subscription.get("ai_used_monthly") or 0),
        )
        if bonus_ai_remaining > 0:
            allowed = True
        elif not is_premium_active(subscription):
            logger.info(
                "ai unlock premium_required: user_id=%s match_id=%s "
                "analysis_mode=%s from_openai_precheck=true",
                telegram_user_id,
                normalized_match_id,
                analysis_mode,
            )
            return jsonify(
                {
                    "ok": False,
                    "status": "premium_required",
                    "error": "premium_required",
                    "message": "Premium AI-разбор доступен по подписке.",
                    "analysis_mode": analysis_mode,
                    "unlocked": False,
                    "charged": False,
                }
            ), 402
        else:
            allowed = monthly_remaining > 0
    else:
        allowed, _, subscription = can_use_ai_analysis(telegram_user_id)

    if not allowed:
        logger.info(
            "ai unlock limit_exceeded: user_id=%s match_id=%s "
            "analysis_mode=%s from_openai=true",
            telegram_user_id,
            normalized_match_id,
            analysis_mode,
        )
        return jsonify(
            {
                "ok": False,
                "status": "ai_limit_exceeded",
                "error": "ai_limit_exceeded",
                "message": (
                    "AI-лимит закончился. Оформите подписку "
                    "или докупите AI-разборы."
                ),
            }
        ), 402

    analysis_result = None
    try:
        match_data = build_miniapp_ai_match_data(match)
        compact_context = match_data.get("compact_context") or {}
        lineups = (
            compact_context.get("lineups")
            if isinstance(compact_context, dict)
            else None
        )
        if isinstance(lineups, dict):
            lineups_included = bool(
                lineups.get("teams")
                or lineups.get("home")
                or lineups.get("away")
            )
        elif isinstance(lineups, list):
            lineups_included = bool(lineups)
        else:
            lineups_included = False
        if force_refresh and analysis_mode == "premium":
            logger.info(
                "premium refresh after lineups requested: user_id=%s "
                "match_id=%s lineups_included=%s",
                telegram_user_id,
                normalized_match_id,
                lineups_included,
            )
        analysis_result = get_openai_ai_analysis_result(
            match_data,
            analysis_mode,
        )
        analysis = analysis_result["analysis"]
        logger.info(
            "Mini App AI analysis mode: match_id=%s user_id=%s mode=%s "
            "is_premium=%s is_admin=%s",
            normalized_match_id,
            telegram_user_id,
            analysis_mode,
            is_premium_active(subscription),
            is_admin,
        )
    except Exception:
        logger.exception(
            "Mini App AI analysis failed: match_id=%s user_id=%s",
            normalized_match_id,
            telegram_user_id,
        )
        analysis = "AI-разбор временно недоступен."
        analysis_result = {
            "analysis": analysis,
            "structured": None,
            "analysis_mode": (
                analysis_mode if "analysis_mode" in locals() else "default"
            ),
        }

    structured = analysis_result.get("structured")
    if not is_saveable_miniapp_ai_analysis(analysis, structured):
        return jsonify(
            {
                "ok": False,
                "error": "ai_analysis_unavailable",
                "message": "AI-разбор временно недоступен.",
            }
        ), 503

    analysis_mode = analysis_result.get("analysis_mode") or "default"
    saved_match_id = normalize_ai_analysis_match_id(
        match.get("id") or normalized_match_id
    )
    logger.info(
        "AI save started after OpenAI: user_id=%s raw_match_id=%s "
        "normalized_match_id=%s saved_match_id=%s analysis_mode=%s "
        "source=miniapp_post",
        telegram_user_id,
        raw_match_id,
        normalized_match_id,
        saved_match_id,
        analysis_mode,
    )
    first_unlock_requires_charge = not is_admin and not (
        force_refresh and saved_analysis
    )
    if first_unlock_requires_charge:
        (
            analysis_saved,
            updated_subscription,
            limit_charged,
            save_error,
        ) = save_miniapp_ai_analysis_and_charge(
            telegram_user_id,
            saved_match_id,
            analysis,
            structured,
            analysis_mode,
            match.get("home") or "",
            match.get("away") or "",
            match.get("league") or "",
            source="openai",
        )
        if updated_subscription is not None:
            remaining_ai = get_total_ai_available_count(
                telegram_user_id,
                updated_subscription,
            )
    else:
        analysis_saved = save_miniapp_ai_analysis(
            telegram_user_id,
            saved_match_id,
            analysis,
            structured,
            analysis_mode,
            match.get("home") or "",
            match.get("away") or "",
            match.get("league") or "",
            refresh_count=int((saved_analysis or {}).get("refresh_count") or 0),
            increment_refresh_count=bool(
                force_refresh and saved_analysis and not is_admin
            ),
        )
        limit_charged = False
        save_error = "" if analysis_saved else "save_failed"
    personal_save_verified = verify_miniapp_ai_personal_save(
        telegram_user_id,
        saved_match_id,
        analysis_mode,
    )
    global_saved = save_global_miniapp_ai_analysis(
        saved_match_id,
        analysis,
        structured,
        analysis_mode,
        match.get("home") or "",
        match.get("away") or "",
        match.get("league") or "",
    )
    global_save_verified = verify_miniapp_ai_global_save(
        saved_match_id,
        analysis_mode,
    )
    logger.info(
        "global AI cache saved: match_id=%s analysis_mode=%s saved=%s "
        "verified=%s",
        saved_match_id,
        analysis_mode,
        global_saved,
        global_save_verified,
    )
    if not analysis_saved:
        if save_error == "premium_required":
            logger.info(
                "ai unlock premium_required: user_id=%s match_id=%s "
                "analysis_mode=%s from_openai=true",
                telegram_user_id,
                saved_match_id,
                analysis_mode,
            )
            return jsonify(
                {
                    "ok": False,
                    "status": "premium_required",
                    "error": "premium_required",
                    "message": "Premium AI-разбор доступен по подписке.",
                    "analysis_mode": analysis_mode,
                    "unlocked": False,
                    "charged": False,
                }
            ), 402
        if save_error == "ai_limit_exceeded":
            logger.info(
                "ai unlock limit_exceeded: user_id=%s match_id=%s "
                "analysis_mode=%s from_openai=true",
                telegram_user_id,
                saved_match_id,
                analysis_mode,
            )
            return jsonify(
                {
                    "ok": False,
                    "status": "ai_limit_exceeded",
                    "error": "ai_limit_exceeded",
                    "message": (
                        "AI-лимит закончился. Оформите подписку "
                        "или докупите AI-разборы."
                    ),
                }
            ), 402
        logger.warning(
            "AI analysis generated but personal save failed before charge: "
            "user_id=%s saved_match_id=%s analysis_mode=%s verified=%s",
            telegram_user_id,
            saved_match_id,
            analysis_mode,
            personal_save_verified,
        )
        return jsonify(
            {
                "ok": False,
                "error": "saved_analysis_unavailable",
                "message": "AI-разбор временно недоступен.",
            }
        ), 503

    if is_admin:
        remaining_ai = None
    logger.info(
        "AI limit charged %s: user_id=%s match_id=%s analysis_mode=%s",
        limit_charged,
        telegram_user_id,
        saved_match_id,
        analysis_mode,
    )
    if limit_charged:
        logger.info(
            "ai unlock charged from openai: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            saved_match_id,
            analysis_mode,
        )
    if force_refresh and analysis_saved and not is_admin:
        logger.info(
            "AI refresh count incremented: user_id=%s match_id=%s "
            "analysis_mode=%s",
            telegram_user_id,
            saved_match_id,
            analysis_mode,
        )
    if force_refresh and analysis_mode == "premium":
        logger.info(
            "premium global cache updated: match_id=%s updated=%s",
            saved_match_id,
            global_saved,
        )
    saved_analysis = None
    logger.info(
        "AI analysis saved: user_id=%s raw_match_id=%s "
        "normalized_match_id=%s analysis_length=%s structured=%s",
        telegram_user_id,
        raw_match_id,
        saved_match_id,
        len(analysis),
        structured is not None,
    )
    logger.info(
        "personal AI saved/linked: user_id=%s match_id=%s "
        "analysis_mode=%s saved=true verified=%s",
        telegram_user_id,
        saved_match_id,
        analysis_mode,
        personal_save_verified,
    )
    try:
        saved_analysis = get_saved_miniapp_ai_analysis(
            telegram_user_id,
            saved_match_id,
            analysis_mode,
        )
    except Exception:
        logger.warning(
            "AI analysis saved but timestamp reload failed: "
            "user_id=%s normalized_match_id=%s",
            telegram_user_id,
            saved_match_id,
            exc_info=True,
        )

    return jsonify(
        {
            "ok": True,
            "match_id": saved_match_id,
            "home": match.get("home") or "",
            "away": match.get("away") or "",
            "analysis": analysis,
            "limit_charged": limit_charged,
            "charged": limit_charged,
            "unlocked": True,
            "source": "openai",
            "remaining_ai": remaining_ai,
            "is_admin": is_admin,
            "analysis_mode": analysis_mode,
            "structured": structured,
            "cached": False,
            "regenerated": True,
            "refresh_count": int((saved_analysis or {}).get("refresh_count") or 0),
            "free_refreshes_total": MINIAPP_AI_FREE_REFRESH_TOTAL,
            "free_refreshes_left": get_ai_free_refreshes_left(
                saved_analysis,
                is_admin,
            ),
            "from_personal_cache": False,
            "from_global_cache": False,
            "created_at": serialize_api_datetime(
                (saved_analysis or {}).get("created_at")
            ),
            "updated_at": serialize_api_datetime(
                (saved_analysis or {}).get("updated_at")
            ),
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
    ensure_channel_agent_matchdays_table()
    ensure_channel_auto_posts_table()
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

    application = (
        Application.builder()
        .token(telegram_token)
        .post_init(start_miniapp_match_reminders_loop)
        .post_shutdown(stop_miniapp_match_reminders_loop)
        .build()
    )
    #application.bot_data["football_api_key"] = football_api_key

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CommandHandler(
            [
                "today",
                "tomorrow",
                "top",
                "testdb",
                "matches",
                "profile",
                "help",
            ],
            open_miniapp_redirect,
        )
    )
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("user", user_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("grant_premium", grant_premium_command))
    application.add_handler(CommandHandler("revoke_premium", revoke_premium_command))
    application.add_handler(CommandHandler("add_ai_limit", add_ai_limit_command))
    application.add_handler(CommandHandler("subscription", subscription_command))
    application.add_handler(CommandHandler("channel_admin", channel_admin_command))
    application.add_handler(CommandHandler("channel_plan", channel_plan_command))
    application.add_handler(CommandHandler("channel_recap", channel_recap_command))
    application.add_handler(
        CallbackQueryHandler(
            channel_admin_plan_callback,
            pattern=r"^channel_admin_plan$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_admin_plan_manual_callback,
            pattern=r"^channel_admin_plan_manual$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_admin_recap_callback,
            pattern=r"^channel_admin_recap$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_admin_recap_manual_callback,
            pattern=r"^channel_admin_recap_manual$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_admin_status_callback,
            pattern=r"^channel_admin_status$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_pick_callback,
            pattern=r"^channel_pick:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_tg_cover_prompt_callback,
            pattern=r"^channel_tg_cover_prompt:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_social_cards_prompt_callback,
            pattern=r"^channel_social_cards_prompt:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_recap_pick_callback,
            pattern=r"^channel_recap_pick:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_publish_callback,
            pattern=r"^channel_publish:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_shorten_callback,
            pattern=r"^channel_shorten:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_social_caption_callback,
            pattern=r"^channel_social_caption:.+$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_plan_again_callback,
            pattern=r"^channel_plan_again$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            channel_recap_again_callback,
            pattern=r"^channel_recap_again$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            admin_payment_confirm_callback,
            pattern=r"^admin_pay_confirm:\d+:(ai_30|premium_30|premium_90)$",
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
            open_miniapp_redirect
        )
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
