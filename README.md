# Weather Pipeline

End-to-end projekt: stahuje počasí z externího API, ukládá historii do
databáze, nabízí ji dál přes vlastní zabezpečené REST rozhraní, umí
vygenerovat AI shrnutí a má jednoduchý webový dashboard. Postavený jako
konkrétní demonstrace dovedností požadovaných na pozici **IT Analytik
API & Data management** (Škoda Auto).

## Architektura

```
                         ┌─────────────────────┐
                         │  OpenWeatherMap API  │
                         └──────────┬───────────┘
                                    │  fetch_weather.py
                                    ▼
  pipeline.py  ──────────▶  database.py (SQLite)  ◀──────────  api_server.py
  (pravidelný běh,                  ▲                          (REST rozhraní,
   cron/GitHub Actions)             │                           role read/admin)
                                    │
                          ai_assistant.py (Anthropic API)
                                    │
                                    ▼
                          static/index.html (dashboard)
```

`config.py` a `auth.py` (autentizace + autorizace) a logging prostupují
všemi moduly napříč diagramem.

## Jak projekt naplňuje požadavky inzerátu

| Požadavek z inzerátu | Kde v projektu |
|---|---|
| API integrace a datové integrace napříč systémy | `fetch_weather.py` (konzumace OpenWeatherMap) + `api_server.py` (vlastní API, poskytuje data dál) |
| Implementace a propojení AI nástrojů a služeb | `ai_assistant.py` - volání Anthropic Claude API, generuje shrnutí a doporučení z dat |
| Frontendová řešení a UI/UX (výhodou) | `static/index.html` - dashboard se stavem deště, předpovědí a AI shrnutím |
| Integrace nových komponent do existující architektury | Modulární návrh - `ai_assistant.py` a `auth.py` byly přidány bez zásahu do `fetch_weather.py`/`database.py` |
| Bezpečnost - autentizace, autorizace, logování | `config.py` (.env, API klíče), `auth.py` (role read/admin), `logging` v každém modulu |
| Monitoring výkonu a optimalizace | Middleware v `api_server.py` měří odezvu každého požadavku, endpoint `/stats` |
| Analytické myšlení na základě dat | Pravidlové vyhodnocení rizika deště (práh 40 % v dashboardu) + AI shrnutí jako interpretace dat + proaktivní Telegram notifikace (`notify.py`) při změně stavu nebo blížícím se dešti |
| Iterativní vývoj a release management | `.github/workflows/weather-pipeline.yml` - automatizované pravidelné spouštění, viz sekce Release management níže |

## Komponenty

| Soubor | Role |
|---|---|
| `config.py` | Čte `.env`, validuje povinné klíče |
| `fetch_weather.py` | Volání OpenWeatherMap API, ošetření chyb (401/429/timeout) |
| `database.py` | SQLite - ukládání a čtení historie a předpovědi |
| `auth.py` | Role-based autorizace (read/admin) přes API klíče |
| `ai_assistant.py` | Volání Anthropic API - shrnutí dat do doporučení |
| `notify.py` | Telegram notifikace při změně stavu deště nebo blížícím se dešti |
| `api_server.py` | FastAPI - REST rozhraní, monitoring, servíruje dashboard |
| `pipeline.py` | Samostatný skript pro pravidelné stažení dat (cron/Actions) |
| `static/index.html` | Webový dashboard |

## Rozjezd

```bash
pip install -r requirements.txt
cp .env.example .env
# vyplň OPENWEATHER_API_KEY, ANTHROPIC_API_KEY a vlastní API_KEY_READ / API_KEY_ADMIN

python pipeline.py          # jednorázové stažení dat do databáze
uvicorn api_server:app --reload   # REST API + dashboard na http://localhost:8000
```

API klíč nového OpenWeatherMap účtu se aktivuje až 10 minut - 2 hodiny po
registraci - pokud první požadavek vrátí 401, není to chyba kódu.

## Bezpečnost

- API klíče výhradně v `.env` (mimo verzovaný kód, viz `.gitignore`)
- Endpointy rozlišují dvě role: `read` (čtení dat) a `admin` (čtení + vynucené
  stažení dat + statistiky) - autentizace (je klíč platný?) je oddělená od
  autorizace (smí tahle role tuhle akci?)
- Veškerá komunikace s externími API i interní REST rozhraní je logováno

## Monitoring

Middleware v `api_server.py` měří dobu odezvy každého požadavku a počet chyb;
výsledky jsou dostupné přes `GET /stats` (role admin). V produkčním nasazení
by se tyhle metriky exportovaly do Prometheus/Grafana - princip (měřit,
logovat, vystavit) je ale stejný už teď.

## Release management a rollback

- Pravidelné spouštění řeší `.github/workflows/weather-pipeline.yml`
  (scheduled + manuální spuštění). Databáze se mezi běhy persistuje commitnutím
  `data/weather.db` zpět do repozitáře (ne přes Actions artefakty - ty jsou
  ve verzi 4 izolované per běh a nehodí se na tento účel)
- Verzování přes git tagy (`git tag v1.0.0`) - rollback na předchozí funkční
  verzi znamená checkout staršího tagu a opětovné nasazení
- Pro produkční nasazení s reálným provozem by se tagy doplnily o Docker
  image verze a možnost spustit workflow s konkrétní starší verzí kódu

## Plánovaná rozšíření

- Automatizované testy (pytest) nad `api_server.py` a `fetch_weather.py`
- Perzistentní úložiště metrik místo in-memory `_stats` (přežije restart)
- Nasazení na Raspberry Pi s trvalým během přes `systemd` + vzdálený přístup (Tailscale)
