"""
Integrace AI služby (Anthropic Claude API) - generuje lidsky čitelné
shrnutí a doporučení z nasbíraných dat o počasí.

Ukazuje vzorec, který se v praxi používá k napojení LLM na vlastní data:
strukturovaná data -> sestavení promptu -> volání LLM API -> zpracování odpovědi.

Pro tak malé množství dat (pár desítek čísel z jednoho zdroje) se nevyplatí
stavět RAG s vektorovou databází - všechna potřebná data se vejdou přímo
do promptu. RAG by dával smysl až při práci s velkým množstvím textu
(např. vyhledávání v dokumentaci), ne u krátkého strukturovaného záznamu.
"""
import logging

import requests
from requests.exceptions import ConnectionError, HTTPError, Timeout

import config

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Haiku je zvolen vědomě: jde o jednoduchou shrnovací úlohu nad pár desítkami
# čísel, kde nejlevnější dostupný model bohatě stačí - není důvod platit za víc.
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
TIMEOUT_SECONDS = 20


class AIServiceError(Exception):
    """Vlastní výjimka pro chyby při komunikaci s AI API."""


def _build_prompt(current: dict, forecast: list[dict]) -> str:
    """Sestaví textový prompt z aktuálního počasí a předpovědi."""
    forecast_lines = "\n".join(
        f"- {f['forecast_datetime']}: {f['temperature']}°C, "
        f"šance na déšť {f['rain_probability'] * 100:.0f}%, {f['description']}"
        for f in forecast[:8]
    ) or "(předpověď není k dispozici)"

    return (
        f"Aktuální počasí v {current['city']}: {current['temperature']}°C "
        f"(pocitově {current['feels_like']}°C), vlhkost {current['humidity']}%, "
        f"{current['description']}, srážky za poslední hodinu "
        f"{current['rain_last_hour_mm']} mm.\n\n"
        f"Předpověď na nejbližší hodiny:\n{forecast_lines}\n\n"
        "Napiš stručné shrnutí (max. 3 věty) a jedno praktické doporučení "
        "pro chod chytré domácnosti (např. zda otevřít okna, spustit klimatizaci, "
        "nebo počkat s venkovními pracemi kvůli dešti). "
        "Odpověz česky, plynulým textem, bez nadpisů a odrážek."
    )


def generate_weather_summary(current: dict, forecast: list[dict]) -> str:
    """Pošle naměřená data do Claude API a vrátí krátké textové shrnutí."""
    if not config.ANTHROPIC_API_KEY:
        raise AIServiceError(
            "Chybí ANTHROPIC_API_KEY v .env - shrnutí nelze vygenerovat."
        )

    prompt = _build_prompt(current, forecast)
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            ANTHROPIC_API_URL, json=payload, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except Timeout as exc:
        logger.error("Časový limit při volání AI API vypršel.")
        raise AIServiceError("AI služba neodpověděla v časovém limitu.") from exc
    except ConnectionError as exc:
        logger.error("Nepodařilo se připojit k AI API.")
        raise AIServiceError("Nepodařilo se připojit k AI službě.") from exc

    if response.status_code == 401:
        logger.error("Neplatný ANTHROPIC_API_KEY.")
        raise AIServiceError("Neplatný ANTHROPIC_API_KEY - zkontroluj .env.")

    if response.status_code == 429:
        logger.warning("Rate limit AI API překročen.")
        raise AIServiceError("AI služba je momentálně přetížená (rate limit).")

    try:
        response.raise_for_status()
    except HTTPError as exc:
        logger.error("AI API vrátilo chybu %s: %s", response.status_code, exc)
        raise AIServiceError(f"AI služba vrátila chybu: {response.status_code}") from exc

    data = response.json()
    text_blocks = [
        block["text"] for block in data.get("content", []) if block.get("type") == "text"
    ]
    summary = "\n".join(text_blocks).strip()

    if not summary:
        raise AIServiceError("AI služba vrátila prázdnou odpověď.")

    logger.info("AI shrnutí vygenerováno (%d znaků).", len(summary))
    return summary
