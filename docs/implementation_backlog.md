# Implementation Backlog (Actionable)

This backlog turns the AEMET endpoint research into concrete, incremental work items with acceptance criteria.

## P0: Data Availability + Station Discovery

### 1. Station catalog API with DB cache
- Status: Done
- Scope:
  - Add `GET /api/metadata/stations`
  - Source from AEMET station inventory endpoint
  - Cache in SQLite with 7-day freshness (`STATION_CATALOG_FRESHNESS_SECONDS`)
- Acceptance criteria:
  - Endpoint returns `checked_at_utc`, `cached_until_utc`, `cache_hit`, `data[]`
  - Repeated calls inside TTL do not hit upstream
  - `force_refresh=true` bypasses cache

### 2. Frontend station discovery UI
- Status: Todo
- Scope:
  - Add searchable station list component backed by `/api/metadata/stations`
  - Keep current Antarctica query mode unchanged until generic endpoint is ready
- Acceptance criteria:
  - User can browse/filter station catalog in UI
  - UI displays cache freshness timestamp and source count

### 3. Generic station query endpoint (non-Antarctica)
- Status: Todo
- Scope:
  - New endpoint using station code directly (e.g., `idema`) instead of fixed enum
  - Preserve existing Antarctica endpoint for backwards compatibility
- Acceptance criteria:
  - Query works for arbitrary station codes returned by catalog
  - Existing `/api/antartida/...` behavior remains unchanged

## P1: Climate Context Features

### 4. Climate normal vs observed anomaly cards
- Status: Todo
- Endpoints:
  - `valores/climatologicos/normales/estacion/{idema}`
  - `valores/climatologicos/diarios/.../estacion/{idema}`
- Acceptance criteria:
  - Dashboard shows anomaly (`observed - normal`) where available
  - Missing baseline data degrades gracefully with clear messaging

### 5. Historical benchmark mode (monthly/annual)
- Status: Todo
- Endpoint:
  - `valores/climatologicos/mensualesanuales/...`
- Acceptance criteria:
  - User can switch between current-window and historical benchmark panels
  - Data exports include benchmark columns when active

### 6. Record proximity alerts
- Status: Todo
- Endpoint:
  - `valores/climatologicos/valoresextremos/parametro/{parametro}/estacion/{idema}`
- Acceptance criteria:
  - UI shows “near record” badges based on configurable threshold
  - Alert logic covered by deterministic tests

## P2: Operational Context Modules

### 7. Synoptic context cards
- Status: Todo
- Endpoints:
  - `mapasygraficos/analisis`
  - `mapasygraficos/mapassignificativos/...`
- Acceptance criteria:
  - Dashboard shows latest map links with timestamps
  - Failures do not block primary station analytics flow

### 8. Warning timeline integration
- Status: Todo
- Endpoints:
  - `avisos_cap/ultimoelaborado/area/{area}`
  - `avisos_cap/archivo/...`
- Acceptance criteria:
  - Warnings can be overlaid on selected query period
  - Severity is clearly visible in table/timeline markers

## Technical debt / quality tasks

### 9. Response contract tests against saved fixtures
- Status: Todo
- Scope:
  - Add fixture-based tests for AEMET metadata/data payload variants
- Acceptance criteria:
  - Covers success, no-data, malformed payload, and HTTP error paths

### 10. Frontend build reproducibility in local dev
- Status: Todo
- Scope:
  - Add project-local TypeScript dependency and lockfile
  - Ensure `bash scripts/build_frontend.sh` works in clean environment
- Acceptance criteria:
  - `npm ci && npm run build` produces current `frontend/dist` deterministically

## P0/P1 Security & Access Control

### 11. Authentication foundation (JWT)
- Status: Todo
- Scope:
  - Add password-based login endpoint issuing JWT access tokens
  - Add refresh-token flow with rotation/revocation
  - Add auth middleware/dependency for protected endpoints
- Acceptance criteria:
  - Unauthenticated calls to protected routes return `401`
  - Access token expiry and refresh flow are covered by tests
  - Token signing key and TTL are fully env-configurable

### 12. User registration + lifecycle management
- Status: Todo
- Scope:
  - User registration endpoint with email uniqueness
  - User listing/details/update/deactivate endpoints (admin-protected)
  - Password hashing and password-change/reset primitives
- Acceptance criteria:
  - Users can register/login with secure password storage (hashed + salted)
  - Deactivated users cannot authenticate
  - Admin APIs enforce role checks and are audited in logs

### 13. Roles and authorization model
- Status: Todo
- Scope:
  - Define roles (`admin`, `analyst`, `viewer`) and per-route permissions
  - Enforce authorization in backend dependencies
  - Reflect role capabilities in frontend navigation/actions
- Acceptance criteria:
  - Role-based route matrix is documented and tested
  - Forbidden access returns `403` with consistent error contract

### 14. Security hardening
- Status: Todo
- Scope:
  - Rate limits on auth endpoints
  - Brute-force mitigation and lockout policy
  - Session/device revocation support
  - Optional MFA-ready schema hooks
- Acceptance criteria:
  - Auth endpoints are rate-limited and monitored
  - Security events (failed login, lockout, token revocation) are logged

### 15. Migration and rollout plan
- Status: Todo
- Scope:
  - DB schema migrations for users/roles/tokens
  - Backward-compatible rollout (public mode -> auth-required mode flag)
  - Seed first admin user flow
- Acceptance criteria:
  - Fresh install and upgrade paths are tested
  - Feature flag can enable/disable mandatory auth without code change
