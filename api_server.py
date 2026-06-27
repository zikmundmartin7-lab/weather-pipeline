"""
REST API rozhraní nad nasbíranými daty o počasí.

Endpointy:
    GET  /health            - veřejný health check (bez autentizace)
    GET  /weather/latest     - poslední záznam aktuálního počasí       [read]
    GET  /weather/history     - historie záznamů                       [read]
    GET  /weather/forecast    - poslední uložená předpověď              [read]
    GET  /weather/summary     - AI shrnutí + doporučení                 [read]
    POST /weather/refresh     - vynutí nové stažení dat z API           [admin]
    GET  /stats               - metriky využití a výkonu API            [admin]
    GET  /                    - jednoduchý webový dashboard

Spuštění (vývoj):
    uvicorn api_server:app --reload

Autentizace: hlavička "X-API-Key" s hodnotou z .env (API_KEY_READ / API_KEY_ADMIN).
"""
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import ai_assistant
import auth
import config
import database
import fetch_weather

logger = logging.getLogger(__name__)

# --- Jednoduché in-memory metriky pro monitoring výkonu ---
# V produkci by tohle nahradil Prometheus/Grafana; princip (měřit, logovat,
# vystavit přes endpoint) je ale identický.
_stats = {
    "request_count": defaultdict(int),
    "total_duration_ms": defaultdict(float),
    "errors": defaultdict(int),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    logger.info("API server spuštěn, databáze inicializována.")
    yield
    logger.info("API server se vypíná.")


app = FastAPI(title="Weather Pipeline API", lifespan=lifespan)


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    """Middleware pro monitoring - měří odezvu každého požadavku a loguje ji."""
    start = time.perf_counter()
    path = request.url.path

    try:
        response = await call_next(request)
    except Exception:
        _stats["errors"][path] += 1
        logger.exception("Neočekávaná chyba při zpracování %s", path)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    _stats["request_count"][path] += 1
    _stats["total_duration_ms"][path] += duration_ms
    if response.status_code >= 400:
        _stats["errors"][path] += 1

    logger.info(
        "%s %s -> %d (%.1f ms)", request.method, path, response.status_code, duration_ms
    )
    return response


@app.get("/health")
def health():
    """Veřejný health check - bez autentizace, pro monitoring/uptime nástroje."""
    return {"status": "ok"}


@app.get("/weather/latest")
def weather_latest(role: str = Depends(auth.require_read)):
    data = database.get_latest_weather()
    if data is None:
        raise HTTPException(status_code=404, detail="Zatím nejsou uložena žádná data.")
    return data


@app.get("/weather/history")
def weather_history(limit: int = 50, role: str = Depends(auth.require_read)):
    return database.get_weather_history(limit=limit)


@app.get("/weather/forecast")
def weather_forecast(role: str = Depends(auth.require_read)):
    return database.get_latest_forecast()


@app.get("/weather/summary")
def weather_summary(role: str = Depends(auth.require_read)):
    current = database.get_latest_weather()
    forecast = database.get_latest_forecast()
    if current is None:
        raise HTTPException(status_code=404, detail="Zatím nejsou uložena žádná data.")
    try:
        summary = ai_assistant.generate_weather_summary(current, forecast)
    except ai_assistant.AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"summary": summary}


@app.post("/weather/refresh")
def weather_refresh(role: str = Depends(auth.require_admin)):
    """Vynutí okamžité nové stažení dat z OpenWeatherMap - vyžaduje roli admin."""
    try:
        current = fetch_weather.get_current_weather()
        database.save_current_weather(current)
        forecast = fetch_weather.get_forecast()
        database.save_forecast(forecast)
    except fetch_weather.WeatherAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"status": "refreshed", "current": current}


@app.get("/stats")
def stats(role: str = Depends(auth.require_admin)):
    """Metriky využití a výkonu API (počty požadavků, průměrná odezva, chyby) - role admin."""
    result = {}
    for path, count in _stats["request_count"].items():
        total = _stats["total_duration_ms"][path]
        result[path] = {
            "request_count": count,
            "avg_duration_ms": round(total / count, 1) if count else 0,
            "errors": _stats["errors"].get(path, 0),
        }
    return result


# Statický frontend - jednoduchý dashboard v static/index.html
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")
