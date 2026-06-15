import logging
import os
import re
from datetime import datetime, timedelta, timezone

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
) -> tuple[str, dict]:
    lines = [title, ""]
    options = {}

    for index, fixture_item in enumerate(fixtures, start=1):
        number = str(index)
        teams = fixture_item.get("teams", {})
        league = fixture_item.get("league", {})
        fixture = fixture_item.get("fixture", {})

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
            "🧠 Для анализа матча отправьте его номер.",
            "Например: 2",
        ]
    )

    return "\n".join(lines), options


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

    if len(lines) == 1:
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
        return ""

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
        return ""

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


def build_advanced_stats_block(
    home_team_name: str,
    away_team_name: str,
    home_advanced_stats: dict,
    away_advanced_stats: dict,
) -> str:
    rows = []

    stat_rows = [
        ("🚩 Угловые", "avg_corners", 1),
        ("🟨 Жёлтые карточки", "avg_yellow_cards", 1),
        ("🟥 Красные карточки", "avg_red_cards", 1),
        ("🥅 Удары в створ", "avg_shots_on_goal", 1),
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

    return "\n".join(["📎 Доп. статистика последних матчей:", *rows])


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


def build_match_analysis_message(
    home_team_name: str,
    away_team_name: str,
    fixture_id: int | None = None,
) -> str:
    home_team_name = normalize_team_name(home_team_name)
    away_team_name = normalize_team_name(away_team_name)
    home_team = search_api_football_team(home_team_name)
    away_team = search_api_football_team(away_team_name)

    if not home_team or not away_team:
        return "Команда не найдена 😕\nПопробуйте выбрать другой матч."

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
    injuries_block = ""
    if fixture_id is not None:
        prediction_block = build_prediction_block(get_fixture_prediction(fixture_id))
        injuries_block = build_injuries_block(
            get_fixture_injuries(fixture_id),
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

    home_matches_count = home_stats["matches_count"]
    away_matches_count = away_stats["matches_count"]
    h2h_matches_count = h2h_stats["h2h_matches_count"]

    lines = [
        "🧠 Анализ матча",
        "",
        f"{home_team['name']} - {away_team['name']}",
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

    for block in (
        home_away_block,
        prediction_block,
        injuries_block,
        advanced_stats_block,
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
            "Это не гарантия результата.",
        ]
    )

    return "\n".join(lines)


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
            await update.message.reply_text("📅 Матчи на сегодня не найдены.")
            return

        message = "📅 Матчи на сегодня\n\n"
        message += "\n\n".join(
            format_api_football_match_card(match)
            for match in api_matches[:MAX_MATCHES]
        )
        await update.message.reply_text(message)
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
        await update.message.reply_text("В ближайшие 24 часа матчей не найдено.")
        return

    message = "\n\n".join(
    format_thesportsdb_event(match)
    for match in matches[:MAX_MATCHES]
    )
    await update.message.reply_text(message)

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            await update.message.reply_text("📆 Матчи на завтра не найдены.")
            return

        message = "📆 Матчи на завтра\n\n"
        message += "\n\n".join(
            format_api_football_match_card(match)
            for match in api_matches[:MAX_MATCHES]
        )
        await update.message.reply_text(message)
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
        await update.message.reply_text("На завтра матчей не найдено.")
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
        context.user_data["analysis_match_options"] = {}
        await start(update, context)
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
    context.user_data["analysis_match_options"] = {}
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
    if not context.user_data.get("waiting_match_number_for_analysis"):
        return

    text = update.message.text.strip()
    options = context.user_data.get("analysis_match_options") or {}

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
        message = build_match_analysis_message(
            selected_match["home"],
            selected_match["away"],
            selected_match.get("fixture_id"),
        )
        message += (
            "\n\n"
            "Введите другой номер из списка для анализа\n"
            "или нажмите ⬅️ Назад"
        )
    except Exception:
        logger.exception("Match analysis failed")
        message = "🧠 Анализ временно недоступен"

    await update.message.reply_text(
        message,
        reply_markup=build_match_analysis_back_markup(),
    )


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
    context.user_data["analysis_match_options"] = {}
    context.user_data["waiting_match_number_for_analysis"] = False

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

        message, options = build_numbered_match_list_message(
            "🔥 Топ матчи",
            api_matches[:MAX_TOP_MATCHES],
        )
        context.user_data["analysis_match_options"] = options
        context.user_data["waiting_match_number_for_analysis"] = bool(options)
        await update.message.reply_text(message)
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
