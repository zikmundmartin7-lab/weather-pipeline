"""
Konfigurace projektu - načítání proměnných prostředí.

API klíč a další citlivé údaje se NIKDY nepíšou přímo do kódu,
ale do souboru .env, který je v .gitignore a tedy se necommituje do GitHubu.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Načti proměnné z .env souboru (hledá se v aktuálním adresáři projektu)
load_dotenv()

# --- API ---
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Autorizace REST API (api_server.py) ---
# Dva typy klíčů s různými oprávněními - jen READ (čtení) nebo ADMIN (čtení i akce navíc).
API_KEY_READ = os.getenv("API_KEY_READ")
API_KEY_ADMIN = os.getenv("API_KEY_ADMIN")

# --- Lokace (výchozí: Litoměřice) ---
CITY_NAME = os.getenv("CITY_NAME", "Litomerice")
LATITUDE = float(os.getenv("LATITUDE", "50.5341"))
LONGITUDE = float(os.getenv("LONGITUDE", "14.1310"))

# --- Databáze ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "weather.db"))

# --- Logování ---
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def validate_config() -> None:
    """
    Zkontroluje, že je nastaven API klíč.
    Pokud chybí, vyhodí jasnou chybu hned na začátku - ne až uprostřed běhu.
    """
    if not OPENWEATHER_API_KEY:
        raise RuntimeError(
            "Chybí OPENWEATHER_API_KEY. Zkopíruj .env.example jako .env "
            "a vyplň svůj klíč (zdarma na https://openweathermap.org/api)."
        )
