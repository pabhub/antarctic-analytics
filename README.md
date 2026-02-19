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

## Technology Stack, Versions, and Engineering Decisions

This section documents the exact technology baseline currently used by the project, where versions come from, and why these choices were made.

### Runtime and language baseline

| Layer | Technology | Version / Constraint | Source of truth | Why it was chosen |
| --- | --- | --- | --- | --- |
| Backend runtime | Python | `>=3.11` | `pyproject.toml` | Modern stdlib (`zoneinfo`, typing, perf improvements) and broad compatibility. |
| API framework | FastAPI | `>=0.111.0` | `pyproject.toml` | Strong OpenAPI generation, explicit request/response models, fast iteration for data APIs. |
| ASGI server | Uvicorn | `>=0.30.0` | `pyproject.toml` | Standard ASGI runtime with reliable local/dev deployment behavior. |
| HTTP client | httpx | `>=0.27.0` | `pyproject.toml` | Async/sync friendly client for upstream AEMET requests with robust timeout handling. |
| Data validation | Pydantic | `>=2.7.0` | `pyproject.toml` | Strong typed schemas shared across API, service, and OpenAPI docs. |
| Storage engine | SQLite (`sqlite3`) | stdlib | `src/app/services/repository.py` | Simple file-based persistence for cache-first station history and fetch windows. |
| Auth token implementation | Custom HS256 JWT (stdlib crypto) | current internal implementation | `src/app/core/auth.py` | Keep auth dependency surface minimal; explicit control of token claims and validation. |
| Timezone engine | `zoneinfo` | stdlib | backend service/router modules | Correct timezone-aware boundaries for daily/monthly aggregation and UI rendering. |
| Frontend language | TypeScript | `5.9.3` (dev dependency) | `frontend/package.json` | Static typing and safer refactoring for large dashboard logic. |
| Frontend compile target | ES modules (`ES2020`) | `target/module ES2020`, `strict=true` | `frontend/tsconfig.json` | Native browser modules, no framework lock-in, strict compile-time checks. |
| Map rendering | Leaflet | `1.9.4` | CDN in `frontend/src/pages/index.html` | Lightweight, reliable map interactions and overlay support. |
| Charting | Chart.js | `4.4.3` | CDN in `frontend/src/pages/index.html` | Mature chart library used for timelines, envelopes, and wind compass. |
| Fonts | IBM Plex Sans + Space Grotesk | Google Fonts hosted | `frontend/src/pages/*.html` | Readability + strong headings for analytic dashboard content. |
| Frontend build | TypeScript compiler (`tsc`) | uses installed TS | `scripts/build_frontend.sh` | Deterministic build with low complexity; no bundler required. |
| Test framework | pytest | `>=8.2.0` | `pyproject.toml` | Fast backend unit/integration test workflow. |
| Coverage | pytest-cov | `>=5.0.0` | `pyproject.toml` | Coverage reporting for regression control. |
| Optional export stack | pandas + pyarrow | `pandas>=2.2.0`, `pyarrow>=15.0.0` | `pyproject.toml` optional deps | Enables Parquet export without forcing heavy dependencies for all installs. |
| Deployment platform | Vercel + custom build script | current project config | `vercel.json`, `scripts/vercel_build.sh` | Simple deployment for API + static frontend bundle in one service. |

### Architecture decisions (and tradeoffs)

1. Domain boundary: Antarctic-only by design.
   - Decision: Restrict selection and analytics to the two meteo stations (`89064`, `89070`); keep `89064R` and `89064RA` as metadata-only supplemental sources.
   - Why: Match business scope and prevent accidental non-relevant data use.
   - Tradeoff: Less generic platform, but much lower ambiguity and cleaner analyst workflow.

2. Cache-first, month-window retrieval strategy.
   - Decision: All upstream AEMET retrieval is planned in full month windows; cache windows are tracked and reused.
   - Why: AEMET endpoint constraints and rate-limit resilience.
   - Tradeoff: Slightly more orchestration logic, but drastically fewer repeated calls.

3. Persistent upsert model for measurements.
   - Decision: Always upsert station measurements and fetch-window coverage on successful retrieval.
   - Why: Idempotent re-runs, safe retries, and quick warm starts.
   - Tradeoff: More DB writes, but reduced network dependency and better reliability.

4. Async analysis jobs with progress polling.
   - Decision: Long retrieval/backfill operations run as server-side jobs with progress endpoints.
   - Why: Keeps UI responsive while loading multi-year windows and generating playback frames.
   - Tradeoff: Extra state management complexity in backend and frontend.

5. API-first typed contracts.
   - Decision: Backend Pydantic response/request models map directly to frontend TypeScript interfaces.
   - Why: Strong cross-layer contract clarity and fewer runtime mismatches.
   - Tradeoff: Requires disciplined model evolution when extending endpoints.

6. Timezone as a first-class parameter.
   - Decision: User-selected IANA timezone from Config page is propagated into API calls (`location`) and used across UI and PDF rendering.
   - Why: Daily/monthly aggregations are timezone-sensitive; analysts need consistent temporal interpretation.
   - Tradeoff: Additional conversion logic and boundary handling complexity.

7. Thin frontend framework approach (no React/Vue).
   - Decision: Static HTML + modular TypeScript + CSS, composed with feature/components folders.
   - Why: Lower runtime overhead, explicit control, and minimal dependencies for a targeted internal analytical app.
   - Tradeoff: More manual state orchestration and DOM wiring.

8. Frontend-side PDF export from rendered report.
   - Decision: PDF generation is built from the rendered report DOM, preserving visible analyst context and configured timezone.
   - Why: Ensures what analysts review is exactly what is exported.
   - Tradeoff: Print layout tuning is required to avoid page overflow/clipping.

9. Minimal auth dependency surface.
   - Decision: Use internal HS256 JWT primitives (token issue, verify, refresh) with inactivity policy enforced through refresh flow.
   - Why: Predictable behavior and fewer external security package attack surfaces.
   - Tradeoff: Team must maintain token logic carefully and test thoroughly.

10. SQLite for current scale, explicit migration path for growth.
   - Decision: Use file DB now; keep repository/service boundaries ready for DB/backend swaps.
   - Why: Quick setup, zero infra overhead, stable local/dev behavior.
   - Tradeoff: Write concurrency and distributed scaling are naturally limited vs. Postgres/managed stores.

### Scalability posture (current + next steps)

- Current strengths:
  - cache-first monthly windows reduce repeated upstream traffic.
  - rate-limit-aware client spacing via `AEMET_MIN_REQUEST_INTERVAL_SECONDS`.
  - background job orchestration prevents blocking request handlers.
  - clear service/repository boundaries ease replacement of persistence or queue backends.

- Known scale ceilings:
  - SQLite write contention under high parallelism.
  - in-process job state not shared across multiple API instances.
  - CDN runtime deps (Leaflet/Chart.js) require external availability at client load time.

- Recommended evolution path when load grows:
  - move cache store from SQLite to Postgres.
  - move job state/queue to Redis + worker system.
  - add distributed rate-limit coordination if multiple API replicas are introduced.
  - optionally pin frontend third-party assets locally to remove CDN runtime dependency.

### Dependency policy

- Keep runtime dependencies intentionally small.
- Put heavier data tooling in optional extras (`[parquet]`), not base install.
- Prefer Python stdlib where practical (`sqlite3`, `zoneinfo`, crypto primitives, dataclasses).
- Enforce strict TS compilation (`strict`, `noUnusedLocals`, `noUnusedParameters`) to reduce frontend drift.

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
  - execution mode:
    - local/default: background worker thread
    - serverless (Vercel): poll-driven progression (each `GET /api/analysis/query-jobs/{jobId}` advances queued work)
- Startup bootstrap warms cache for current 30-day month windows of map stations.
- Latest availability:
  - cache-first from stored data
  - fallback month-probing when cache has no recent rows

Rate-limit protections:

- outbound spacing controlled by `AEMET_MIN_REQUEST_INTERVAL_SECONDS`
- upstream `Retry-After` cooldown is capped by `AEMET_RETRY_AFTER_CAP_SECONDS` (set to `2` for steady pacing)
- retries for transient upstream failures
- worker retries are aligned to the configured limiter interval (no long extra exponential waits)

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
AEMET_RETRY_AFTER_CAP_SECONDS=2
API_AUTH_USERNAME=analyst
API_AUTH_PASSWORD=change_this_password
JWT_SECRET_KEY=change_this_secret_key
LOG_LEVEL=INFO
```

2. Install backend + frontend deps:

```bash
bash scripts/setup.sh
```

`scripts/setup.sh` installs dev + parquet extras (`pandas`, `pyarrow`) so Parquet export works out of the box.


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
