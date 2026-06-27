"""
Odesílání upozornění na mobil přes Telegram bota.

Princip: po každém stažení dat se porovná aktuální stav deště s posledním
uloženým stavem (v databázi, tabulka app_state). Notifikace se posílá jen
při ZMĚNĚ stavu (přestalo/začalo pršet), ne při každém běhu - jinak by
při hodinovém spouštění chodila zpráva "ještě stále prší" každou hodinu.

Samostatně se jednou denně posílá i upozornění na blížící se déšť podle
předpovědi, pokud je pravděpodobnost v nejbližších hodinách vysoká.
"""
from __future__ import annotations  # kompatibilita typových anotací s Python < 3.10

import logging
from datetime import datetime, timezone

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

import config
import database

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 10
FORECAST_RAIN_THRESHOLD = 0.5  # 50% pravděpodobnost - od kdy se to počítá za "pravděpodobně bude pršet"
FORECAST_LOOKAHEAD_ENTRIES = 4  # 4 × 3h = nejbližších ~12 hodin předpovědi


class NotificationError(Exception):
    """Vlastní výjimka pro chyby při odesílání notifikace."""


def send_telegram_message(text: str) -> None:
    """Pošle textovou zprávu na nakonfigurovaný Telegram chat."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram notifikace nejsou nakonfigurované (chybí token/chat_id) - přeskakuji.")
        return

    url = TELEGRAM_API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text}

    try:
        response = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)
    except Timeout as exc:
        logger.error("Telegram API neodpovědělo v časovém limitu.")
        raise NotificationError("Telegram notifikace - vypršel časový limit.") from exc
    except ConnectionError as exc:
        logger.error("Nepodařilo se připojit k Telegram API.")
        raise NotificationError("Telegram notifikace - chyba spojení.") from exc

    if response.status_code == 401 or response.status_code == 404:
        logger.error("Neplatný TELEGRAM_BOT_TOKEN.")
        raise NotificationError("Neplatný Telegram bot token.")

    try:
        response.raise_for_status()
    except HTTPError as exc:
        logger.error("Telegram API vrátilo chybu %s: %s", response.status_code, exc)
        raise NotificationError(f"Telegram notifikace selhala: {response.status_code}") from exc

    logger.info("Telegram notifikace odeslána.")


def check_and_notify(current: dict, forecast: list[dict]) -> None:
    """
    Porovná aktuální stav deště s posledním uloženým a při změně pošle
    notifikaci. Zvlášť jednou denně upozorní i na blížící se déšť z předpovědi.
    Volá se po každém stažení dat - žádná výjimka odtud neuniká ven
    (chyba notifikace nemá shodit celou pipeline).
    """
    _check_rain_state_change(current)
    _check_upcoming_rain(current, forecast)


def _check_rain_state_change(current: dict) -> None:
    is_wet_now = current["rain_last_hour_mm"] > 0
    current_state = "wet" if is_wet_now else "dry"
    previous_state = database.get_state("rain_state") or "dry"

    if current_state == previous_state:
        return

    if current_state == "wet":
        message = (
            f"🌧️ V {current['city']} začalo pršet "
            f"({current['rain_last_hour_mm']} mm za poslední hodinu)."
        )
    else:
        message = f"☀️ V {current['city']} přestalo pršet."

    try:
        send_telegram_message(message)
    except NotificationError as exc:
        logger.error("Nepodařilo se odeslat notifikaci o změně deště: %s", exc)
    else:
        database.set_state("rain_state", current_state)


def _check_upcoming_rain(current: dict, forecast: list[dict]) -> None:
    upcoming_rain = any(
        f["rain_probability"] >= FORECAST_RAIN_THRESHOLD
        for f in forecast[:FORECAST_LOOKAHEAD_ENTRIES]
    )
    if not upcoming_rain:
        return

    today = datetime.now(timezone.utc).date().isoformat()
    if database.get_state("forecast_alert_date") == today:
        return  # dnes už se upozornění na blížící se déšť poslalo

    message = (
        f"🌂 Podle předpovědi má v {current['city']} v nejbližších hodinách "
        "pravděpodobně pršet - vyplatí se s tím počítat."
    )
    try:
        send_telegram_message(message)
    except NotificationError as exc:
        logger.error("Nepodařilo se odeslat předpovědní notifikaci: %s", exc)
    else:
        database.set_state("forecast_alert_date", today)
