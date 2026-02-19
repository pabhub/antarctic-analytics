# GS Inima · Antarctic Wind Feasibility Dashboard

Antarctic-focused FastAPI + TypeScript app for Business Development analysts evaluating pre-feasibility of wind projects using AEMET data.

- Scope is Antarctic-only.
- Selectable stations are only:
  - `89064` · Meteo Station Juan Carlos I
  - `89070` · Meteo Station Gabriel de Castilla
- Non-selectable stations are catalog metadata only:
  - `89064R` supplemental
  - `89064RA` historical archive
- UI flow is production-ready:
  - login
  - station selection (map or selector)
  - cache-first history load
  - playback + charts + analysis report
  - CSV/Parquet exports and PDF export from report header
- API requests are month-windowed, cache-first, and rate-limit-aware.
- Frontend datetime rendering uses the user-configured timezone across dashboard, charts, tables, and PDF export.

## Product Scope

This app is intentionally constrained to Antarctic wind-feasibility screening:

- no generic national station workflow
- no non-Antarctic endpoint dependence for core analytics
- data retrieval compliant with AEMET one-month window limits

## Frontend User Flow

1. Authenticate on `/login`.
2. Open dashboard `/`.
3. Select one meteo station (`89064` or `89070`) from map or dropdown.
4. Choose history window (`2`, `3`, `5`, `10` years).
   - 2 years: Hourly
   - 3+ years: Daily
5. App runs a cache-first analysis job and loads missing month windows in background.
6. Analyst reviews:
   - wind playback overlay
   - wind speed/weather trends
   - wind direction compass
   - analysis & recommendations report
   - loaded-years comparison (month/season grouping)
7. Export:
   - CSV / Parquet from Raw Data Tables
   - PDF from Analysis Report header

## Codebase Layout

```text
src/
├── main.py                          # deployment shim (re-exports app.main:app)
└── app/
    ├── main.py                      # FastAPI app wiring + middleware
    ├── core/
    │   ├── config.py                # settings/env loading (cached)
    │   ├── exceptions.py            # custom exceptions
    │   └── logging.py               # logging setup
    ├── models/
    │   ├── station.py               # station/catalog/profile models
    │   ├── measurement.py           # time-series/query/export models
    │   └── analysis.py              # analysis/playback/timeframe models
    ├── services/
    │   ├── aemet_client.py          # AEMET client + throttling
    │   ├── repository.py            # SQLite persistence
    │   ├── antarctic_service.py     # service facade
    │   └── antarctic/
    │       ├── stations.py          # station catalog/selection constraints
    │       ├── data.py              # cache-first retrieval + aggregation
    │       ├── analysis.py          # bootstrap + snapshot summaries
    │       └── playback/
    │           ├── __init__.py      # playback facade
    │           ├── query_jobs.py    # async month-window job orchestration
    │           ├── frames.py        # playback frame generation
    │           └── timeframes.py    # timeframe analytics + generation math
    ├── api/
    │   ├── dependencies.py          # DI + compliance headers
    │   ├── route_utils.py           # shared datetime/tz parsing + error mapping
    │   └── routes/
    │       ├── pages.py             # /, /login, /config
    │       ├── auth.py              # JWT token + refresh
    │       ├── metadata.py          # latest availability
    │       ├── analysis.py          # bootstrap/jobs/playback/timeframes
    │       └── data.py              # CSV/Parquet exports
    └── utils/
        └── dates.py                 # date-window helpers
```

```text
frontend/src/
├── app.ts                           # dashboard entrypoint
├── login.ts                         # login entrypoint
├── config.ts                        # config entrypoint
├── pages/                           # HTML shells
├── styles/style.css                 # shared styles
├── components/                      # page/section templates
│   ├── layout/                      # top nav + footer
│   ├── dashboard/                   # dashboard sections
│   ├── config/page.ts
│   └── login/page.ts
├── core/
│   ├── api.ts                       # fetch/auth/date formatting helpers
│   ├── settings.ts                  # localStorage config (timezone/wind farm)
│   ├── logger.ts                    # frontend debug logging helper
│   ├── types.ts                     # API contracts
│   ├── dom.ts
│   └── navigation.ts
└── features/
    ├── dashboard/                   # dashboard workflows/state/render/actions
    ├── overlay.ts                   # Leaflet map overlays
    ├── playback.ts                  # playback controller
    ├── timeframes/
    │   ├── index.ts                 # timeframe cards/table facade
    │   ├── summary.ts               # summary/decision helpers
    │   └── comparison.ts            # loaded-years comparison renderer
    └── wind_rose.ts                 # compass chart
```

## API Overview

Auth:

- `POST /api/auth/token`
- `POST /api/auth/refresh`

Metadata:

- `GET /api/metadata/latest-availability/station/{identificacion}`

Analysis:

- `GET /api/analysis/bootstrap`
- `POST /api/analysis/query-jobs`
- `GET /api/analysis/query-jobs/{jobId}`
- `GET /api/analysis/query-jobs/{jobId}/result`
- `GET /api/analysis/playback`
- `GET /api/analysis/timeframes`

Export:

- `GET /api/antarctic/export/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}`

Swagger docs:

- `http://127.0.0.1:8000/docs`

## Timezone Behavior

- Config page timezone (`IANA`, e.g. `Europe/Madrid`) is used as API `location`.
- Frontend renders datetimes in configured timezone (dashboard, charts, tables, statuses).
- Timeframe grouping boundaries respect station-local timezone logic where required.
- PDF export uses the configured timezone for report timestamps and context fields.

## Cache-First Data Strategy

- Measurements stored in SQLite `measurements`.
- Fetch coverage stored in SQLite `fetch_windows`.
- Missing history is requested in full month windows to satisfy AEMET limits.
- Query jobs:
  - plan total windows
  - skip cached windows
  - fetch only missing windows
  - report progress (`completedWindows`, `completedApiCalls`, `framesReady`, etc.)
- Startup bootstrap warms cache for current 30-day month windows of map stations.
- Latest availability:
  - cache-first from stored data
  - fallback month-probing when cache has no recent rows

Rate-limit protections:

- outbound spacing controlled by `AEMET_MIN_REQUEST_INTERVAL_SECONDS`
- retries for transient upstream failures
- adaptive backoff when 429 is returned

## Feasibility and Simulation Metrics

Computed outputs include:

- data points and coverage
- avg / min / max / P90 wind speed
- hours above thresholds (>= 3, >= 5 m/s)
- dominant direction
- temperature and pressure statistics
- wind power density proxy
- estimated generation (`MWh`) when simulation parameters are configured

Simulation model includes:

- turbine power-curve thresholds (`cut-in`, `rated`, `cut-out`)
- reference air density (`rho_ref`)
- air-density correction using measured temperature/pressure when available
- operating envelope checks for temperature and pressure bounds

## Setup

Prerequisites:

- Python `>=3.11`
- Node.js + npm

1. Configure env:

```bash
cp .env.example .env
```

Set at least:

```dotenv
AEMET_API_KEY=your_key_here
AEMET_MIN_REQUEST_INTERVAL_SECONDS=2
API_AUTH_USERNAME=analyst
API_AUTH_PASSWORD=change_this_password
JWT_SECRET_KEY=change_this_secret_key
LOG_LEVEL=INFO
```

2. Install backend + frontend deps:

```bash
bash scripts/setup.sh
```

3. Activate virtualenv (required in every new terminal if running commands manually):

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

4. Run app:

```bash
bash scripts/up_local.sh
```

Manual backend start (without `up_local.sh`):

```bash
source .venv/bin/activate
bash scripts/start.sh --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000/`
- Login: `http://127.0.0.1:8000/login`
- Config: `http://127.0.0.1:8000/config`
- API docs: `http://127.0.0.1:8000/docs`

## Authentication and Session

- All `/api/metadata/*`, `/api/analysis/*`, `/api/antarctic/*` require bearer auth.
- Frontend stores access token and auto-attaches it to API calls.
- Session extends automatically during active use (`/api/auth/refresh`).
- Inactivity timeout is 1 hour, then user must log in again.

## Testing

```bash
source .venv/bin/activate
pytest -q
npm --prefix frontend run build
```

Coverage:

```bash
source .venv/bin/activate
pytest --cov=app --cov-report=term-missing
```

## Deployment (Vercel)

- Root and `src` entrypoint shims are included for FastAPI detection.
- `vercel.json` uses `bash scripts/vercel_build.sh`.
- Build script compiles frontend and serves from `frontend/dist` at deploy time.
- `frontend/dist` is build output and should not be committed.

## Logging and Troubleshooting

Backend:

- request lifecycle logs (`request.start`, `request.end`, `request.error`)
- `X-Request-ID` response header for correlation
- service-level logs for cache decisions, upstream calls, retries, and failures

Frontend:

- configurable debug logs:

```js
localStorage.setItem("aemet.debug_logging", "1"); location.reload();
```

Disable:

```js
localStorage.setItem("aemet.debug_logging", "0"); location.reload();
```

## Legal and Attribution Compliance

App UI and API headers include required AEMET and OpenStreetMap attribution:

- `© AEMET`
- `Fuente: AEMET`
- `Información elaborada utilizando, entre otras, la obtenida de la Agencia Estatal de Meteorología`
- `© OpenStreetMap contributors (ODbL)`

Compliance headers:

- `X-AEMET-Copyright`
- `X-AEMET-Source`
- `X-AEMET-Value-Added-Notice`
- `X-AEMET-Legal-Notice`
- `X-OSM-Copyright`
- `X-OSM-Copyright-URL`
- `X-AEMET-Latest-Observation-UTC` (when available)

## Supporting Docs

- `docs/api_contract.md`
- `docs/antarctic_api_positioning.md`
- `docs/feasibility_framework.md`
- `docs/implementation_backlog.md`
