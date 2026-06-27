"""
Ukládání naměřených a předpovězených dat do SQLite databáze.

SQLite je zvolena pro jednoduchost startu (žádný server navíc) -
přechod na PostgreSQL by později znamenal jen úpravu connection stringu,
struktura kódu zůstává stejná.
"""
from __future__ import annotations  # kompatibilita typových anotací s Python < 3.10

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """Context manager - otevře spojení s DB a po skončení ho bezpečně zavře."""
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Vytvoří tabulky, pokud ještě neexistují. Bezpečné volat opakovaně."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS current_weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                city TEXT NOT NULL,
                temperature REAL,
                feels_like REAL,
                humidity INTEGER,
                wind_speed REAL,
                description TEXT,
                clouds_percent INTEGER,
                rain_last_hour_mm REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                forecast_datetime TEXT NOT NULL,
                temperature REAL,
                rain_probability REAL,
                rain_volume_mm REAL,
                description TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_current_weather_fetched_at
            ON current_weather(fetched_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
    logger.info("Databáze inicializována (%s)", config.DB_PATH)


def save_current_weather(weather: dict) -> None:
    """Uloží jeden záznam aktuálního počasí."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO current_weather
                (fetched_at, city, temperature, feels_like, humidity,
                 wind_speed, description, clouds_percent, rain_last_hour_mm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fetched_at,
                weather["city"],
                weather["temperature"],
                weather["feels_like"],
                weather["humidity"],
                weather["wind_speed"],
                weather["description"],
                weather["clouds_percent"],
                weather["rain_last_hour_mm"],
            ),
        )
    logger.info("Uložen záznam aktuálního počasí (%s)", fetched_at)


def save_forecast(forecast: list[dict]) -> None:
    """Uloží celou předpověď (více řádků najednou)."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            fetched_at,
            f["datetime"],
            f["temperature"],
            f["rain_probability"],
            f["rain_volume_mm"],
            f["description"],
        )
        for f in forecast
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO forecast
                (fetched_at, forecast_datetime, temperature,
                 rain_probability, rain_volume_mm, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    logger.info("Uloženo %d řádků předpovědi (%s)", len(rows), fetched_at)


def get_latest_weather() -> dict | None:
    """Vrátí poslední uložený záznam aktuálního počasí (nebo None, pokud DB je prázdná)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM current_weather ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_weather_history(limit: int = 100) -> list[dict]:
    """Vrátí historii posledních N záznamů aktuálního počasí (nejnovější první)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM current_weather ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_forecast() -> list[dict]:
    """Vrátí nejnovější uloženou předpověď (všechny řádky z posledního stažení)."""
    with get_connection() as conn:
        latest = conn.execute(
            "SELECT MAX(fetched_at) AS latest FROM forecast"
        ).fetchone()
        if not latest or not latest["latest"]:
            return []
        rows = conn.execute(
            """
            SELECT * FROM forecast
            WHERE fetched_at = ?
            ORDER BY forecast_datetime ASC
            """,
            (latest["latest"],),
        ).fetchall()
    return [dict(row) for row in rows]


def get_state(key: str) -> str | None:
    """Vrátí uloženou hodnotu jednoduchého stavu (např. pro deduplikaci notifikací)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_state(key: str, value: str) -> None:
    """Uloží/aktualizuje hodnotu jednoduchého stavu."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
