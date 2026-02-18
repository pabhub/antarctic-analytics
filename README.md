# GS Inima Challenge – AEMET Antarctica Service

This repository contains a complete solution for the three parts of the challenge:

- **Part 1:** FastAPI service to query Antarctica weather station time series from AEMET.
- **Part 2:** SQLite cache to reduce pressure on AEMET API + structured logging.
- **Part 3:** Lightweight TypeScript front-end to query and view data quickly.

## Architecture overview

- `app/main.py`: FastAPI app + API endpoint + static frontend serving.
- `app/aemet_client.py`: HTTP client for AEMET API.
- `app/database.py`: SQLite repository with UPSERT strategy.
- `app/service.py`: business logic (timezone handling + aggregation + type filtering).
- `tests/`: API and service tests, including DST behavior.
- `frontend/src/app.ts`: TypeScript frontend source.
- `frontend/dist/*`: browser-ready static files.

## API endpoint

`GET /api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}`

### Path params

- `fechaIniStr`: `YYYY-MM-DDTHH:MM:SS`
- `fechaFinStr`: `YYYY-MM-DDTHH:MM:SS`
- `identificacion`:
  - `gabriel-de-castilla`
  - `juan-carlos-i`

### Query params

- `location`: IANA timezone string (`UTC`, `Europe/Berlin`, etc.)
- `aggregation`: `none | hourly | daily | monthly`
- `types`: repeatable list among `temperature`, `pressure`, `speed`, `direction`
  - if omitted, all are returned

### Output

- `datetime` always returned in `Europe/Madrid` (CET/CEST) with timezone offset.
- each row also includes station geospatial data when available: `latitude`, `longitude`, `altitude`.
- source 10-min granularity is kept for `aggregation=none`.
- `hourly/daily/monthly` perform mean aggregation.

### Export endpoint

`GET /api/antartida/export/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}`

Uses the same query parameters as the main data endpoint (`location`, `aggregation`, `types`) plus:

- `format`: `csv` (default) or `parquet`

Notes:

- CSV export is always available.
- Parquet export requires optional dependencies (`pandas` + `pyarrow`); otherwise the endpoint returns `501`.


## Other AEMET data that may be useful

For wind-farm feasibility studies, AEMET station payloads often include additional variables beyond the current MVP (`temp`, `pres`, `vel`). Useful examples are:

- `hr`: relative humidity
- `prec`: precipitation
- `dir`: wind direction
- `racha`: wind gust
- `vis`: visibility
- `tpr`: dew point

This project now exposes a helper endpoint to document what is currently returned and what can be added next. It also persists station coordinates in SQLite for map-based analytics:

- `GET /api/metadata/available-data`

> Note: exact field availability can vary by station and period in the source API.

## Environment variables

- `AEMET_API_KEY` (**required** for real calls)
- `DATABASE_URL` (default: `sqlite:///./aemet_cache.db`)
- `REQUEST_TIMEOUT_SECONDS` (default: `20`)
- `AEMET_GABRIEL_STATION_ID` (default: `89064`)
- `AEMET_JUAN_STATION_ID` (default: `89070`)
- `CACHE_FRESHNESS_SECONDS` (default: `10800`, i.e. 3 hours)

## Run backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

Open:

- Swagger: `http://127.0.0.1:8000/docs`
- UI: `http://127.0.0.1:8000/`

## Front-end notes

A minimal TypeScript frontend is provided in `frontend/src/*` and built static assets in `frontend/dist/*`.

The UI includes a **modern streamlined layout** and a **Leaflet + OpenStreetMap** map that overlays station coordinates returned by the API (`latitude`/`longitude`) with interactive popups (altitude/temperature). It also renders wind **flow vectors** from speed/direction, includes a **timeline playback** control, and shows an **average wind table** (avg speed and circular-mean direction over the selected window).

It now also includes chart visualizations and UX upgrades for date/time handling:

- Wind speed line chart over the selected timeline
- Combined temperature + pressure trend chart (dual-axis)
- Quick date-range buttons (last 6h / 24h / 7d)
- `datetime-local` pickers with automatic conversion to the API datetime format (`YYYY-MM-DDTHH:MM:SS`)
- User-selectable display timezone in the UI for table/map/timeline/chart labels (without changing API contract)
- KPI metric cards (rows, average/peak speed proxy, average temperature) for instant situational awareness
- Improved chart readability (smoother lines, gradient area fill, cleaner tooltips/legends)
- One-click export actions (CSV/Parquet) from the current query window
- Improved empty/error states (no-data table rows, chart placeholders, map guidance banners)

### Frontend production build pipeline

A reproducible frontend build pipeline is included:

```bash
bash scripts/build_frontend.sh
```

This compiles `frontend/src/app.ts` with `tsc` and outputs production-ready static assets (`app.js`, `index.html`, `style.css`) under `frontend/dist/`.

## AEMET API limits investigation

A dedicated investigation note is available at `docs/aemet_api_limits.md`, including:

- findings from this environment
- conservative operational recommendations
- a reproducible script (`scripts/check_aemet_limits.sh`) to validate limits from a network with internet access

## Tests

```bash
pytest -q
```

Includes:

- endpoint parameter validation
- measurement type filtering
- hourly aggregation
- daily aggregation behavior on DST transition (Europe/Madrid)

## TODO / future improvements

- add auth + role-based access if exposed beyond internal network.
