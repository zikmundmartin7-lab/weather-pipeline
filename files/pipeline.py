"""
Hlavní vstupní bod pipeline.

Stáhne aktuální počasí a předpověď, uloží do databáze, vše zaloguje.
Tohle je skript, který by se v praxi spouštěl pravidelně (cron / GitHub Actions).

Spuštění:
    python pipeline.py
"""
import logging
import sys

import config
import database
import fetch_weather
import notify


def setup_logging() -> None:
    """Nastaví logování zároveň do souboru i na konzoli."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run() -> bool:
    """Provede jeden běh pipeline. Vrací True při úspěchu, False při chybě."""
    logger = logging.getLogger(__name__)
    logger.info("=== Spouštím pipeline ===")

    try:
        config.validate_config()
        database.init_db()

        current = fetch_weather.get_current_weather()
        database.save_current_weather(current)
        logger.info(
            "Aktuální teplota: %.1f°C, %s",
            current["temperature"],
            current["description"],
        )

        forecast = fetch_weather.get_forecast()
        database.save_forecast(forecast)

        notify.check_and_notify(current, forecast)

        logger.info("=== Pipeline úspěšně dokončena ===")
        return True

    except fetch_weather.WeatherAPIError as exc:
        logger.error("Pipeline selhala - chyba API: %s", exc)
        return False
    except RuntimeError as exc:
        logger.error("Pipeline selhala - chyba konfigurace: %s", exc)
        return False
    except Exception:
        logger.exception("Pipeline selhala - neočekávaná chyba")
        return False


if __name__ == "__main__":
    setup_logging()
    success = run()
    sys.exit(0 if success else 1)
