# GS Inima · Antarctic Wind Feasibility Dashboard

Antarctic-focused FastAPI + TypeScript application for Business Development analysts evaluating wind-farm pre-feasibility with AEMET weather data.

## Scope

This app is intentionally constrained to AEMET Antarctic stations and the wind-feasibility screening workflow.

## Codebase layout

The backend now follows a `src` package structure with clear boundaries:

```text
src/
├── main.py                     # deployment shim entrypoint (re-exports app.main:app)
└── app/
    ├── main.py                 # FastAPI app wiring
    ├── core/
    │   ├── config.py           # settings/env loading
    │   ├── exceptions.py       # custom exceptions
    │   └── logging.py          # logging setup
    ├── models/
    │   ├── station.py          # station/catalog/profile models
    │   ├── measurement.py      # time-series/query response models
    │   └── analysis.py         # feasibility snapshot models
    ├── services/
    │   ├── aemet_client.py     # upstream API client
    │   └── repository.py       # SQLite persistence
    │   ├── antarctic_service.py# service facade
    │   └── antarctic/          # split domain logic (stations/data/analysis)
    ├── api/
    │   ├── dependencies.py     # DI and compliance header helpers
    │   └── routes/             # split HTTP route modules (pages/metadata/analysis/data)
    └── utils/
        └── dates.py            # generic date-window helpers
```

A root `main.py` shim is also included for platforms that only auto-detect top-level entrypoints.

```text
main.py                         # root deployment shim (re-exports app.main:app)
```

Frontend files are also split by responsibility:

```text
frontend/src/
├── app.ts                      # dashboard composition/wiring entrypoint
├── login.ts                    # login entrypoint
├── config.ts                   # config entrypoint
├── pages/                      # thin HTML shells that host #app-root
├── styles/                     # shared CSS
├── components/                 # page/section templates (markup as components)
│   ├── render.ts               # root renderer
│   ├── layout/
│   │   ├── top_nav.ts          # reusable nav template
│   │   └── footer.ts           # reusable compliance footer template
│   ├── dashboard/              # dashboard section templates
│   ├── config/
│   │   └── page.ts             # config page template
│   └── login/
│       └── page.ts             # login page template
├── core/
│   ├── api.ts                  # fetch/auth/timezone helpers
│   ├── dom.ts                  # required DOM element resolver
│   ├── navigation.ts           # login redirect/next-path helpers
│   ├── settings.ts             # shared localStorage app settings (timezone/wind-farm/auth user)
│   └── types.ts                # frontend API types
└── features/
    ├── dashboard/
    │   ├── dom.ts              # typed DOM element registry
    │   ├── charts.ts           # chart facade
    │   ├── chart_data.ts       # chart aggregation/time-axis helpers
    │   ├── chart_core.ts       # wind + weather chart renderers
    │   ├── chart_timeframe.ts  # timeframe trend chart renderer
    │   ├── dashboard_actions.ts# action exports (bootstrap/query/export)
    │   ├── actions_types.ts    # shared action context types
    │   ├── analysis_job.ts     # cache-first query job workflow
    │   ├── bootstrap_flow.ts   # startup bootstrap workflow
    │   ├── export_actions.ts   # CSV/Parquet export workflow
    │   ├── dashboard_state.ts  # dashboard mutable state model
    │   ├── renderers.ts        # KPI/tables rendering
    │   ├── sections.ts         # UI section visibility/loading helpers
    │   ├── timeframe_manager.ts# timeframe options + analytics loader
    │   ├── playback_manager.ts # playback loading + control bindings
    │   ├── history.ts          # baseline window derivation helpers
    │   ├── progress.ts         # progress bar rendering
    │   ├── playback_controls.ts# play/pause/speed control helpers
    │   ├── date_ranges.ts      # season/year/custom range logic
    │   ├── measurement_types.ts# measurement payload selection helper
    │   └── stations.ts         # station label mapping
    ├── overlay.ts              # leaflet station + playback overlays
    ├── playback.ts             # playback controller
    ├── timeframes.ts           # timeframe tables/cards/comparison
    └── wind_rose.ts            # wind compass chart
```

### Selectable meteorological stations (UI selector)

- `89064` · Meteo Station Juan Carlos I
- `89070` · Meteo Station Gabriel de Castilla

### Automatic supplemental stations (map + comparison)

- `89064R` · Radiometric supplemental station for Juan Carlos I

### Archived station (metadata only)

- `89064RA` · Historical archive endpoint (until 08/03/2007), not part of startup map overlay to minimize calls

## What changed in this overhaul

- App is now Antarctic-only by design.
- Startup loads station map and station list immediately from the Antarctic model.
- Query now asks only for `start`; `end` is auto-capped by:
  - AEMET 30-day limit
  - latest available observation for selected station
- Single-station query jobs now drive analysis with explicit progress and cache reuse.
- New playback and timeframe endpoints provide synchronized spatiotemporal analysis.
- SQLite persistence and fetch-window reuse are central: once loaded, windows are reused and upstream calls are skipped.
- UI/UX redesigned for analyst decision support:
  - station overlay map (3 active Antarctic IDs)
  - single-station selection from list or map
  - query progress bar (windows/calls/frames)
  - playable wind overlays (direction arrow, trail, optional temperature/pressure overlays)
  - KPI cards (coverage, speed, P90, hours above thresholds, WPD proxy, temperature range)
  - wind timeline, weather timeline, 16-sector wind rose
  - timeframe analysis + compare mode
  - simulated wind farm expected generation (configured in `/config`)
  - AEMET/OSM attribution block

## API overview

### Authentication

`POST /api/auth/token`

- Body: `{ "username": "...", "password": "..." }`
- Returns short-lived JWT bearer token.
- `POST /api/auth/refresh` rotates token expiry for active sessions (requires bearer token).
- Frontend session policy is inactivity-based:
  - continuous interaction keeps session alive by refreshing token before expiry
  - 1 hour without interaction forces re-login
- All `/api/metadata/*`, `/api/analysis/*`, and `/api/antarctic/*` endpoints require `Authorization: Bearer <token>`.
- In non-local environments, terminate TLS at your reverse proxy so bearer tokens are never sent over plain HTTP.

### Frontend contract (only public API surface exposed in `/docs`)

`POST /api/auth/refresh`

- Extends access-token expiry for active authenticated sessions.

`GET /api/analysis/bootstrap`

- Warms cache for active Antarctic map stations.
- Returns station profiles, selectable IDs, latest snapshots, and suggested starts.

`POST /api/analysis/query-jobs`

- Creates a cache-first station analysis job for the selected station.
- Request supports:
  - `location` (IANA timezone used to interpret input datetimes and render output datetimes)
  - `aggregation` (`none|hourly|daily|monthly`)
- Returns planned windows, planned API calls, and frame planning metadata.

`GET /api/analysis/query-jobs/{jobId}`

- Poll job progress for UI loading bars.
- Includes calls progress, windows progress, and playback readiness.

`GET /api/analysis/query-jobs/{jobId}/result`

- Returns feasibility snapshot for the selected station using currently cached/fetched data.

`GET /api/analysis/playback`

Query params:

- `station`, `start`, `end`, `step` (`10m|1h|3h|1d`), `location`

Response includes ordered frames with:

- `datetime`, `speed`, `direction`, `temperature`, `pressure`
- `qualityFlag` (`observed|aggregated|gap_filled`)
- vector components `dx/dy`
- wind rose summary (`16` sectors, speed buckets, dominant sector, concentration, calm share)

`GET /api/analysis/timeframes`

Query params:

- `station`, `start`, `end`, `groupBy` (`hour|day|week|month|season`), `location`
- optional `forceRefreshOnEmpty=true` to force-refresh month windows when the initial cache pass returns no buckets
- optional compare range: `compareStart`, `compareEnd`
- optional simulated wind farm params:
  - `turbineCount`
  - `ratedPowerKw`
  - `cutInSpeedMps`
  - `ratedSpeedMps`
  - `cutOutSpeedMps`
  - `referenceAirDensityKgM3` (default `1.225`)
  - `minOperatingTempC`, `maxOperatingTempC`
  - `minOperatingPressureHpa`, `maxOperatingPressureHpa`

Returns grouped timeframe buckets and comparison deltas, including estimated generation (`MWh`) when simulation parameters are provided. Generation uses density-corrected wind speed (`rho/rho_ref`) when temperature+pressure are available and enforces configured operating temperature/pressure limits.
For daily/monthly grouping logic, station-local timezone boundaries are used to avoid day/month rollover bias.

For long timeframe/compare ranges, backend fetches missing data in sequential 30-day windows (cache-first) to comply with the AEMET one-month upstream constraint.

`GET /api/metadata/latest-availability/station/{identificacion}`

- Resolves latest known station observation (cache-first, month-window fallback probing).

`GET /api/antarctic/export/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}`

- Exports CSV/Parquet from cache-first retrieval.
- Accepts long windows; backend resolves them as month-sized AEMET windows internally.
- Supports `location` and `aggregation` (`none|hourly|daily|monthly`).
- Used by frontend export buttons in Raw Data Tables.

The following legacy endpoints are intentionally not exposed anymore:

- `/api/analysis/feasibility`
- `/api/metadata/available-data`
- `/api/metadata/stations`
- `/api/antarctic/datos/...`

## Low-call strategy and persistence

- Measurements are persisted in `SQLite` table `measurements`.
- Requested windows are persisted in `fetch_windows`.
- Repeated requests inside covered windows do not hit AEMET.
- Startup warm-cache pulls max 30-day probe for active map stations only when cache is stale.
- Latest availability is inferred from cached measurements first; remote probe is fallback.

## Feasibility metrics currently computed

Per station and selected window:

- row count and coverage ratio
- average / P90 / max wind speed
- hours above 3 m/s and 5 m/s
- min/avg/max temperature
- average pressure
- prevailing wind direction (circular mean)
- estimated wind power density proxy (`0.5 * rho * v^3`, rho from pressure + temperature when available)

These are screening metrics, not a bankable energy-yield model.

## Additional recommendation factors now included

- Air-density correction in generation estimates:
  - `rho = p / (R * T)` from measured pressure and temperature (fallback to `referenceAirDensityKgM3`)
  - density-corrected speed for power-curve lookup: `v_eq = v * (rho/rho_ref)^(1/3)`
- Operating envelope screening:
  - If a row is outside configured operating temperature or pressure bounds, simulated generation for that interval is set to `0`.
- This improves comparability between periods with different meteorological density conditions and highlights environment-driven operating risk.

## AEMET endpoint positioning decision

The app treats Antarctic IDs as belonging to the Antarctic endpoint workflow and does not rely on non-Antarctic climatological endpoints for core analysis.

Rationale:

- Antarctic availability and 30-day constraints are specific and strict.
- Other AEMET endpoint families use `idema` station semantics that are not guaranteed to provide equivalent Antarctic coverage.
- For reliability and minimum upstream pressure, this product keeps one authoritative data path for Antarctic feasibility.

See `docs/antarctic_api_positioning.md`.

## Setup

```bash
cp .env.example .env
```

Set:

```dotenv
AEMET_API_KEY=your_key_here
AEMET_MIN_REQUEST_INTERVAL_SECONDS=2
API_AUTH_USERNAME=analyst
API_AUTH_PASSWORD=change_this_password
JWT_SECRET_KEY=change_this_secret_key
```

Install + build:

```bash
bash scripts/setup.sh
```

Activate the virtual environment (required in each new terminal if you run commands manually):

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Run:

```bash
bash scripts/up_local.sh
```

Manual backend run (if you do not use `scripts/up_local.sh`):

```bash
source .venv/bin/activate
bash scripts/start.sh --reload
```

Open:

- Dashboard: `http://127.0.0.1:8000/`
- OpenAPI docs: `http://127.0.0.1:8000/docs`

Use the login page with `API_AUTH_USERNAME` / `API_AUTH_PASSWORD`. The frontend stores the JWT and attaches it to API requests automatically.

## Vercel deployment

This repository ships with:

- `main.py` and `src/main.py` FastAPI entrypoint shims for Vercel auto-detection.
- `vercel.json` with:
  - `buildCommand: bash scripts/vercel_build.sh`.

If your Vercel project uses `Root Directory = src`, this repo also includes:

- `src/scripts/vercel_build.sh`
- `src/vercel.json`

to provide the same behavior from the `src` root.

The build script installs frontend deps and creates `frontend/dist/` on each deployment, so `/`, `/login`, and `/config` can be served without committing `frontend/dist`.

## Tests

```bash
source .venv/bin/activate
pytest -q
npm --prefix frontend run build
```

## Legal and attribution compliance

This app implements AEMET and OpenStreetMap attribution requirements in both UI and API headers.

Included references:

- `© AEMET`
- `Fuente: AEMET`
- `Información elaborada utilizando, entre otras, la obtenida de la Agencia Estatal de Meteorología`
- `© OpenStreetMap contributors` (ODbL)

Response headers exposed:

- `X-AEMET-Copyright`
- `X-AEMET-Source`
- `X-AEMET-Value-Added-Notice`
- `X-AEMET-Legal-Notice`
- `X-OSM-Copyright`
- `X-OSM-Copyright-URL`
- `X-AEMET-Latest-Observation-UTC` (when available)

Frontend build outputs are treated as build artifacts (`frontend/dist/`) and are not versioned.

## Docs

- `docs/api_contract.md`: exact frontend API contract exposed in `/docs` + verification steps
- `docs/antarctic_api_positioning.md`: Antarctic endpoint strategy and station-ID handling
- `docs/feasibility_framework.md`: analyst interpretation framework + web references
- `docs/implementation_backlog.md`: updated delivery plan
