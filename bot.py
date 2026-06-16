import logging
import os
import re
import asyncio
from datetime import datetime, timedelta, timezone

from openai import OpenAI
import psycopg2
import requests
from psycopg2.extras import RealDictCursor
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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
        connection.commit()
    except Exception:
        logger.exception("Failed to initialize database")
    finally:
        if connection is not None:
            connection.close()


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
        ["🏆 Таблица"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
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
    reply_markup = build_main_menu_markup()

    await update.message.reply_text(
        "⚽ MatchLab\n\n"
        "📅 Сегодня — матчи на сегодня\n"
        "📆 Завтра — матчи на завтра\n"
        "🔥 Топ матчи — самые интересные игры\n"
        "⚽ Команда — ближайшие матчи команды\n"
        "📊 Результаты — последние результаты команды\n"
        "⭐ Моя команда — выбрать или изменить любимую команду\n"
        "📋 Профиль — информация по любимой команде\n"
        "🏆 Таблица — турнирные таблицы лиг",
        reply_markup=reply_markup,
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
    }


def format_optional_average(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


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
    analysis_text = match_data.get("analysis_text") or ""

    return (
        "Ты футбольный аналитический помощник MatchLab.\n"
        "Пользователь видел только сокращённый анализ. Ниже переданы полные "
        "внутренние статистические данные MatchLab. Используй их для более "
        "глубокого вывода.\n"
        "Не пересказывай все цифры подряд.\n"
        "Делай профессиональный вывод на основе данных.\n"
        "Если по травмам/дисквалификациям данных нет — честно напиши, что "
        "данных пока нет.\n"
        "Не придумывай потери, составы или xG, если их нет в данных.\n"
        "Не используй слова: ставка, ставить, экспресс, купон, железно, "
        "гарантия, 100%.\n"
        "Не обещай результат.\n"
        "Не придумывай факты, которых нет в данных.\n"
        "Не упоминай API-Football.\n"
        "Ориентир по длине: 400-700 слов максимум.\n"
        "Учитывай формат турнира.\n"
        "Если матч проходит в нейтральном турнире или финале на нейтральном "
        "поле, не делай сильный вывод на основе дома/в гостях.\n"
        "Если это внутренний чемпионат, внутренний кубок не в финале, ЛЧ, ЛЕ, "
        "ЛК, квалификация или двухматчевый формат — home/away можно учитывать.\n"
        "Если есть таблица/группа: оцени мотивацию команд, кому важнее очки, "
        "кому может быть достаточно ничьей, кому может быть важна разница "
        "мячей. Если данных мало — не делай уверенных выводов. Если таблицы "
        "нет — не придумывай мотивацию.\n"
        "По угловым и карточкам используй только данные из внутреннего анализа. "
        "Если данных по угловым нет, не добавляй угловые в дополнительные "
        "направления. Если данных по карточкам или фолам нет, не добавляй "
        "карточки в дополнительные направления. Если данные есть только по "
        "одной команде или выборка мала, уровень должен быть не выше 🟡.\n"
        "Не противоречь самому себе. Если в блоке 🟨 Карточки и угловые выбрано "
        "Карточки: жёстко, дальше нельзя писать про спокойную игру по карточкам. "
        "Если выбрано Карточки: спокойно, дальше нельзя писать про жёсткий матч. "
        "Если выбрано Угловые: активно, дальше нельзя писать, что угловых мало. "
        "Если выбрано Угловые: осторожно, дальше нельзя писать про высокий тотал "
        "угловых.\n"
        "Не используй точные или примерные цифры по угловым/карточкам, если они "
        "не переданы явно в полных внутренних данных. Не пиши приблизительные "
        "значения вроде 3-4 угловых без таких данных. Если данных мало, пиши: "
        "По угловым/карточкам данных недостаточно. Не делай вывод по карточкам "
        "и угловым только по названию команд. Если данных по карточкам/угловым "
        "мало, не добавляй карточки/угловые как сильное направление. В блоке "
        "🚫 Что лучше пропустить можно писать: Угловые/карточки — данных "
        "недостаточно для сильного вывода.\n"
        "Дополнительные направления выбирай строго из списка: двойной шанс "
        "1X / X2 / 12; фора 0 / +0.5 / -0.5 / +1.0 / -1.0; командный гол; "
        "индивидуальный тотал ИТБ 0.5 / ИТБ 1.0 / ИТБ 1.5 / ИТМ 1.5; "
        "первый тайм; угловые; карточки; сухой матч.\n"
        "Выбери только 3-5 самых логичных направлений. Лучше 3 сильных "
        "направления, чем 8 слабых. Не добавляй направление только ради "
        "заполнения блока. Если данных недостаточно, пиши осторожно или "
        "пропусти направление.\n"
        "Первый тайм добавляй только при данных или форме, указывающих на "
        "быстрый старт; если данных по таймам нет, формулируй осторожно. "
        "Сухой матч добавляй только при слабом ОЗ, слабой атаке одной команды "
        "и сильной обороне другой. Фору используй аккуратно; если матч равный, "
        "фора должна быть осторожной или отсутствовать. Двойной шанс используй, "
        "если одна команда стабильнее, но чистый исход рискован. "
        "Индивидуальный тотал используй при явном перевесе атаки команды или "
        "слабости обороны соперника.\n"
        "В блоке ⭐ Главное направление выбери только 1-2 наиболее обоснованных "
        "варианта. Не выбирай рискованный вариант как главный, если есть более "
        "спокойный статистический сигнал. Лучше 1 сильный пункт, чем 2 слабых. "
        "Если данных мало, напиши: Явного главного направления нет, матч "
        "требует осторожности.\n"
        "В блоке 🚫 Что лучше пропустить покажи направления, которые пользователь "
        "может ошибочно переоценить: агрессивная фора, высокий тотал, сухой "
        "матч, точный счёт, угловые/карточки без данных, первый тайм без "
        "данных. Если нечего явно пропускать, напиши: Явно слабых направлений "
        "по данным нет, но агрессивные варианты лучше оценивать осторожно.\n"
        "Цель AI-разбора — не перечислить всё подряд, а помочь отделить сильные "
        "направления от слабых.\n"
        "Ответ дай строго в структуре:\n\n"
        "🤖 AI-разбор MatchLab\n\n"
        "🏆 Матч и турнир:\n"
        "Team A - Team B\n"
        "Турнир: …\n"
        "Раунд: …\n"
        "Стадион/город: …\n"
        "Контекст поля: домашний фактор / нейтральный или условный home/away\n\n"
        "📊 Турнирная мотивация:\n"
        "Если есть данные по таблице — коротко объясни. Если нет — напиши: "
        "По таблице/мотивации данных недостаточно.\n\n"
        "📊 Форма и контекст:\n"
        "2-4 предложения. Кто стабильнее, кто лучше по атаке/обороне. "
        "Учитывай home/away только если контекст strong_home_away.\n\n"
        "⚽ Голы и тоталы:\n"
        "• Общий тотал: осторожно / умеренно / активно\n"
        "• ТБ 1.5: есть ли статистический сигнал\n"
        "• ТБ 2.5: есть ли риск\n"
        "• Индивидуальный тотал Team A: осторожно / умеренно / интересно\n"
        "• Индивидуальный тотал Team B: осторожно / умеренно / интересно\n\n"
        "🎯 ОЗ:\n"
        "Осторожно / умеренно / вероятно. Коротко объясни почему.\n\n"
        "🟨 Карточки и угловые:\n"
        "• Угловые: осторожно / умеренно / активно\n"
        "• Карточки: спокойно / умеренно / жёстко\n"
        "• Короткий вывод: 1-2 предложения\n"
        "Если данных нет — напиши: По угловым/карточкам данных недостаточно.\n\n"
        "📌 Дополнительные направления:\n"
        "• 3-5 пунктов максимум\n"
        "• Только самые логичные направления\n"
        "• Формат: • 🟢 Team A забьёт — причина в 1 предложении\n"
        "Каждое направление должно иметь уровень 🟢 Осторожнее, "
        "🟡 Средний риск или 🔴 Рискованно.\n\n"
        "⭐ Главное направление:\n"
        "• максимум 2 пункта\n"
        "• выбери 1-2 самых логичных направления из всего разбора\n"
        "• это должны быть не самые рискованные варианты, а самые обоснованные "
        "по данным\n"
        "• формат: • 🟢 Team A забьёт — причина в 1 предложении\n"
        "Если данных мало — напиши: Явного главного направления нет, матч "
        "требует осторожности.\n\n"
        "🚫 Что лучше пропустить:\n"
        "• 1-3 пункта\n"
        "• укажи направления, которые выглядят рискованно или слабо подтверждены "
        "данными\n"
        "• примеры: чистый исход при равном матче, агрессивная фора, ТБ 3.5 без "
        "сверхрезультативности, сухой матч при умеренном или вероятном ОЗ, "
        "угловые/карточки без данных, первый тайм без данных, точный счёт\n"
        "• формат: • Фора -1.0 — слишком агрессивно при текущем балансе команд\n\n"
        "🚑 Потери и составы:\n"
        "Если есть потери — коротко объясни, насколько это может быть важно. "
        "Если данных нет — напиши: По потерям данных пока нет. Составы обычно "
        "появляются ближе к старту.\n\n"
        "🧭 Аналитические направления:\n"
        "🟢 Осторожнее:\n"
        "• 1-2 пункта\n\n"
        "🟡 Средний риск:\n"
        "• 1-2 пункта\n\n"
        "🔴 Рискованно:\n"
        "• 1-2 пункта\n\n"
        "💬 Итог:\n"
        "2-3 предложения: главное направление матча и главный риск.\n\n"
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
                f"Открывайте 📋 Профиль для просмотра матчей команды.",
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
        FAVORITE_OPEN_PROFILE_BUTTON,
        FAVORITE_CHANGE_TEAM_BUTTON,
        MATCH_AI_ANALYSIS_BUTTON,
    }

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
        await show_profile(update, context)
        return

    elif text == FAVORITE_OPEN_PROFILE_BUTTON:
        await show_profile(update, context)
        return

    elif text == FAVORITE_CHANGE_TEAM_BUTTON:
        await show_favorite_team_leagues(update, context)
        return
    
    elif text == "📊 Результаты":
        await show_team_select_leagues(update, context, "results")

    elif text == "⭐ Моя команда":
        if get_current_favorite_team(update, context):
            await show_favorite_team_actions(update, context)
        else:
            await show_favorite_team_leagues(update, context)


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
    if not OPENAI_API_KEY:
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

    match_data = context.user_data.get("last_match_for_ai")
    if not match_data:
        await update.message.reply_text(
            "Сначала выберите матч из списка и откройте обычный анализ.",
            reply_markup=build_match_analysis_ai_markup(),
        )
        return

    context.user_data["ai_analysis_in_progress"] = True
    try:
        await update.message.reply_text("⏳ Готовлю AI-разбор…")
        match_data["tournament_context_text"] = build_tournament_context_for_ai(
            match_data
        )
        message = await asyncio.to_thread(get_openai_ai_analysis, match_data)

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
        f"Открывайте 📋 Профиль для просмотра матчей команды.",
        reply_markup=build_main_menu_markup(),
    )


async def show_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    favorite_team = get_current_favorite_team(update, context)

    if not favorite_team:
        await update.message.reply_text(
            "⭐ Любимая команда не выбрана.\n\n"
            "Нажмите ⭐ Моя команда и введите название."
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


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


def main() -> None:
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

    init_db()

    application.run_polling(
    drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
