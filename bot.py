import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
MAX_MATCHES = 20


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
    await update.message.reply_text(
        "Привет! Используй /today для просмотра матчей ближайших 24 часов."
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


def format_match(item: dict) -> str:
    teams = item.get("teams", {})
    league = item.get("league", {})
    fixture = item.get("fixture", {})

    home_team = teams.get("home", {}).get("name", "Неизвестная команда")
    away_team = teams.get("away", {}).get("name", "Неизвестная команда")
    tournament = league.get("name", "Неизвестный турнир")

    almaty_tz = timezone(timedelta(hours=5))
    kickoff = datetime.fromtimestamp(
        fixture["timestamp"],
        tz=timezone.utc
    ).astimezone(almaty_tz)
    kickoff_text = kickoff.strftime("%d.%m %H:%M")

    return (
        f"{home_team} - {away_team}\n"
        f"Турнир: {tournament}\n"
        f"Начало: {kickoff_text}"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api_key = context.application.bot_data["football_api_key"]

    try:
        matches = get_matches_next_24_hours(api_key)
    except requests.RequestException:
        logger.exception("Failed to request fixtures from API-Football")
        await update.message.reply_text("Не удалось получить матчи. Попробуй позже.")
        return
    except Exception:
        logger.exception("Failed to process fixtures from API-Football")
        await update.message.reply_text("Не удалось обработать список матчей.")
        return

    if not matches:
        await update.message.reply_text("В ближайшие 24 часа матчей не найдено.")
        return

    message = "\n\n".join(format_match(match) for match in matches)
    await update.message.reply_text(message)


def main() -> None:
    telegram_token = get_required_env("TELEGRAM_BOT_TOKEN")
    football_api_key = get_required_env("FOOTBALL_API_KEY")

    application = Application.builder().token(telegram_token).build()
    application.bot_data["football_api_key"] = football_api_key

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("today", today))

    application.run_polling()


if __name__ == "__main__":
    main()
