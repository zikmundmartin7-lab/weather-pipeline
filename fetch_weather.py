"""
Volání OpenWeatherMap API - aktuální počasí a 5denní předpověď.

Řeší:
- autentizaci (API klíč jako parametr požadavku)
- timeouty a výpadky spojení
- rate limit (HTTP 429)
- neplatný klíč (HTTP 401)
"""
from __future__ import annotations  # kompatibilita typových anotací s Python < 3.10

import logging

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5"
TIMEOUT_SECONDS = 10


class WeatherAPIError(Exception):
    """Vlastní výjimka pro všechny chyby při komunikaci s API."""


def _make_request(endpoint: str, params: dict) -> dict:
    """Pomocná funkce - provede GET požadavek a ošetří běžné chybové stavy."""
    params = dict(params)
    params["appid"] = config.OPENWEATHER_API_KEY
    params["units"] = "metric"  # stupně Celsia, m/s
    params["lang"] = "cz"

    url = f"{BASE_URL}/{endpoint}"

    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    except Timeout as exc:
        logger.error("Časový limit požadavku vypršel (endpoint: %s)", endpoint)
        raise WeatherAPIError("API neodpovědělo v časovém limitu.") from exc
    except ConnectionError as exc:
        logger.error("Nepodařilo se připojit k API (endpoint: %s)", endpoint)
        raise WeatherAPIError("Nepodařilo se připojit k OpenWeatherMap API.") from exc

    if response.status_code == 401:
        logger.error("Neplatný API klíč.")
        raise WeatherAPIError(
            "Neplatný API klíč - zkontroluj OPENWEATHER_API_KEY v .env."
        )

    if response.status_code == 429:
        logger.warning("Rate limit překročen (429) na endpointu %s", endpoint)
        raise WeatherAPIError("Příliš mnoho požadavků (rate limit). Zkus to později.")

    try:
        response.raise_for_status()
    except HTTPError as exc:
        logger.error(
            "HTTP chyba %s na endpointu %s: %s", response.status_code, endpoint, exc
        )
        raise WeatherAPIError(f"API vrátilo chybu: {response.status_code}") from exc

    return response.json()


def get_current_weather(lat: float | None = None, lon: float | None = None) -> dict:
    """Vrátí aktuální počasí pro dané souřadnice (výchozí dle config.py)."""
    lat = config.LATITUDE if lat is None else lat
    lon = config.LONGITUDE if lon is None else lon

    data = _make_request("weather", {"lat": lat, "lon": lon})
    logger.info("Aktuální počasí staženo pro [%s, %s]", lat, lon)

    return {
        "city": data.get("name") or config.CITY_NAME,
        "temperature": data["main"]["temp"],
        "feels_like": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "wind_speed": data["wind"]["speed"],
        "description": data["weather"][0]["description"],
        "clouds_percent": data["clouds"]["all"],
        "rain_last_hour_mm": data.get("rain", {}).get("1h", 0.0),
    }


def get_forecast(lat: float | None = None, lon: float | None = None) -> list[dict]:
    """Vrátí 5denní předpověď (interval 3h) pro dané souřadnice."""
    lat = config.LATITUDE if lat is None else lat
    lon = config.LONGITUDE if lon is None else lon

    data = _make_request("forecast", {"lat": lat, "lon": lon})
    entries = data.get("list", [])
    logger.info("Předpověď stažena pro [%s, %s] (%d záznamů)", lat, lon, len(entries))

    forecast = []
    for entry in entries:
        forecast.append(
            {
                "datetime": entry["dt_txt"],
                "temperature": entry["main"]["temp"],
                "rain_probability": entry.get("pop", 0.0),  # 0.0-1.0
                "rain_volume_mm": entry.get("rain", {}).get("3h", 0.0),
                "description": entry["weather"][0]["description"],
            }
        )
    return forecast
