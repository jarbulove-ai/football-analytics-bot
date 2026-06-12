import logging
import os
from datetime import datetime, timedelta, timezone

import requests
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        ["📅 Сегодня", "📆 Завтра"],
        ["🔥 Топ матчи"],
        ["⚽ Команда", "📊 Результаты"],
        ["⭐ Моя команда", "📋 Профиль"],
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        "⚽ MatchLab\n\n"
        "📅 Сегодня — матчи на сегодня\n"
        "📆 Завтра — матчи на завтра\n"
        "🔥 Топ матчи — самые интересные игры\n"
        "⚽ Команда — ближайшие матчи команды\n"
        "📊 Результаты — последние результаты команды\n"
        "⭐ Моя команда — выбрать или изменить любимую команду\n"
        "📋 Профиль — информация по любимой команде",
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
        if start_time <= kickoff <= end_time:
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


def format_thesportsdb_event(event: dict) -> str:
    home_team = event.get("strHomeTeam") or "Неизвестная команда"
    away_team = event.get("strAwayTeam") or "Неизвестная команда"
    tournament = event.get("strLeague") or "Неизвестный турнир"
    country = event.get("strCountry") or "Неизвестная страна"

    event_time = parse_thesportsdb_event_time(event)
    if event_time is None:
        kickoff_text = "Время неизвестно"
    else:
        almaty_tz = timezone(timedelta(hours=5))
        kickoff_text = event_time.astimezone(almaty_tz).strftime("%d.%m %H:%M")

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


def search_api_football_team(team_name: str) -> dict | None:
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


def get_api_football_finished_fixtures(team_id: int) -> list[dict]:
    fixtures = request_api_football(
        "/fixtures",
        {
            "team": team_id,
            "last": 20,
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
    wins = 0
    draws = 0
    losses = 0
    form = []

    for item in fixtures[:5]:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        home_id = teams.get("home", {}).get("id")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue

        is_home = home_id == team_id
        team_goals = home_goals if is_home else away_goals
        opponent_goals = away_goals if is_home else home_goals

        if team_goals > opponent_goals:
            wins += 1
            form.append("✅")
        elif team_goals == opponent_goals:
            draws += 1
            form.append("➖")
        else:
            losses += 1
            form.append("❌")

    return wins, draws, losses, form


def build_api_football_team_message(team_name: str) -> str | None:
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
        f"😔 Поражений: {losses}"
    )

    return message


def format_match(item: dict) -> str:
    teams = item.get("teams", {})
    league = item.get("league", {})
    fixture = item.get("fixture", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")
    country = league.get("country", "Неизвестная страна")

    almaty_tz = timezone(timedelta(hours=5))
    kickoff = datetime.fromtimestamp(
        fixture["timestamp"],
        tz=timezone.utc
    ).astimezone(almaty_tz)
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

    almaty_tz = timezone(timedelta(hours=5))
    kickoff = datetime.fromtimestamp(
        fixture["timestamp"],
        tz=timezone.utc
    ).astimezone(almaty_tz)
    kickoff_text = kickoff.strftime("%d.%m %H:%M")

    return (
        f"⚽ {home_team} - {away_team}\n"
        f"🏆 {tournament} ({country})\n"
        f"🕒 {kickoff_text}"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    api_key = os.getenv("THESPORTSDB_API_KEY")

    if not api_key:
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        matches = get_thesportsdb_next_football_matches(api_key)
    except Exception:
        logger.exception("Failed to process events from TheSportsDB")
        await update.message.reply_text("Не удалось получить матчи.")
        return

    almaty_tz = timezone(timedelta(hours=5))
    tomorrow_date = (
        datetime.now(almaty_tz) + timedelta(days=1)
    ).date()

    tomorrow_matches = []

    for match in matches:
        event_time = parse_thesportsdb_event_time(match)

        if not event_time:
            continue

        if event_time.astimezone(almaty_tz).date() == tomorrow_date:
            tomorrow_matches.append(match)

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
    context.user_data["waiting_team"] = False
    context.user_data["waiting_results"] = False
    context.user_data["waiting_favorite_team"] = False

    if text == "📅 Сегодня":
        await today(update, context)

    elif text == "📆 Завтра":
        await tomorrow(update, context)

    elif text == "🔥 Топ матчи":
        await top(update, context)

    elif text == "⚽ Команда":
        context.user_data["waiting_team"] = True

        await update.message.reply_text(
            "⚽ Введите название команды\n\n"
            "Например:\n"
            "Liverpool\n"
            "Real Madrid\n"
            "Barcelona\n"
            "Kairat"
        )

    elif text == "📋 Профиль":
        await show_profile(update, context)
        return
    
    elif text == "📊 Результаты":
        context.user_data["waiting_results"] = True

        await update.message.reply_text(
            "Введите название команды"
        )

    elif text == "⭐ Моя команда":

        favorite_team = context.user_data.get("favorite_team")

        if favorite_team:
            await update.message.reply_text(
                f"⭐ Текущая команда: {favorite_team}\n\n"
                f"Введите новую любимую команду:"
            )
        else:
            await update.message.reply_text(
                "Введите название любимой команды:"
            )

        context.user_data["waiting_favorite_team"] = True

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

    team_name = update.message.text
    api_key = os.getenv("THESPORTSDB_API_KEY")

    context.user_data["waiting_team"] = False

    try:
        message = build_api_football_team_message(team_name)
        if message:
            await update.message.reply_text(message)
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
        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/searchteams.php",
            params={"t": team_name},
            timeout=20,
        )

        response.raise_for_status()

        teams = response.json().get("teams")

        if not teams:
            await update.message.reply_text(
                f"Команда '{team_name}' не найдена."
            )
            return

        team_id = teams[0]["idTeam"]

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
            return

        message = f"⚽ {teams[0]['strTeam']}\n\n"

        for event in events[:5]:
            message += format_thesportsdb_event(event)
            message += "\n\n"

        await update.message.reply_text(message)

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

    context.user_data["waiting_results"] = False

    team_name = update.message.text
    api_key = os.getenv("THESPORTSDB_API_KEY")

    try:
        message = build_api_football_results_message(team_name)
        if message:
            await update.message.reply_text(message)
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
        response = requests.get(
            f"{THESPORTSDB_BASE_URL}/{api_key}/searchteams.php",
            params={"t": team_name},
            timeout=20,
        )

        response.raise_for_status()

        teams = response.json().get("teams")

        if not teams:
            await update.message.reply_text(
                f"Команда '{team_name}' не найдена."
            )
            return

        team_id = teams[0]["idTeam"]

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
            return

        message = f"📊 {teams[0]['strTeam']}\n\n"

        for event in events[:5]:
            home = event.get("strHomeTeam", "")
            away = event.get("strAwayTeam", "")
            home_score = event.get("intHomeScore", "-")
            away_score = event.get("intAwayScore", "-")

            message += (
                f"⚽ {home} {home_score}-{away_score} {away}\n"
            )

        await update.message.reply_text(message)

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

    if not context.user_data.get("waiting_favorite_team"):
        return

    context.user_data["waiting_favorite_team"] = False

    team_name = update.message.text

    context.user_data["favorite_team"] = team_name

    await update.message.reply_text(
        f"⭐ Любимая команда сохранена:\n"
        f"{team_name}\n\n"
        f"Открывайте 📋 Профиль для просмотра матчей команды."
    )


async def show_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    favorite_team = context.user_data.get("favorite_team")

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
    api_key = os.getenv("THESPORTSDB_API_KEY")

    if not api_key:
        await update.message.reply_text("TheSportsDB API key is not configured.")
        return

    try:
        matches = get_thesportsdb_next_football_matches(api_key)
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
            filters.TEXT & ~filters.COMMAND,
            team_search
        ),
        group=1
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            team_results
        ),
        group=2
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            favorite_team
        ),
        group=3
    )
    
    application.run_polling(
    drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
