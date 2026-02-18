# AEMET Endpoint Expansion Ideas (Feature-Oriented)

This document maps additional AEMET OpenData endpoints to potential product features for `antartica-analytics`.

## Scoring model

- Value: `High` / `Medium` / `Low` (product impact)
- Effort: `S` / `M` / `L` (implementation complexity)
- Fit: `Direct` (Antarctica core) or `Context` (adjacent decision support)

## 1) Direct-fit expansions

### 1.1 Climate anomaly engine

- Endpoints:
  - `GET /api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{idema}`
  - `GET /api/valores/climatologicos/normales/estacion/{idema}`
  - `GET /api/valores/climatologicos/mensualesanuales/datos/anioini/{anioIniStr}/aniofin/{anioFinStr}/estacion/{idema}`
- Feature:
  - Show anomaly metrics (`observed - normal`) for temperature/wind-related proxies.
  - Add percentile-style severity badge per window.
- Value/Effort/Fit: `High / M / Direct`

### 1.2 Record proximity alerts

- Endpoints:
  - `GET /api/valores/climatologicos/valoresextremos/parametro/{parametro}/estacion/{idema}`
  - `GET /api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}`
- Feature:
  - Detect when current values approach station historical extremes.
  - “Record watch” widget in dashboard.
- Value/Effort/Fit: `High / S-M / Direct`

### 1.3 Station intelligence panel

- Endpoints:
  - `GET /api/valores/climatologicos/inventarioestaciones/estaciones/{estaciones}`
  - `GET /api/valores/climatologicos/inventarioestaciones/todasestaciones`
- Feature:
  - Station metadata QA (coords/elevation/availability health).
  - Admin page to validate configured stations and suggest alternates.
- Value/Effort/Fit: `Medium / S / Direct`

### 1.4 Geospatial export workflows

- Endpoints:
  - `GET /api/productos/climatologicos/capasshape/{tipoestacion}`
- Feature:
  - GIS pack export (station layers + current query CSV/Parquet).
  - Direct handoff to QGIS/ArcGIS workflows.
- Value/Effort/Fit: `Medium / M / Direct`

## 2) Context-fit expansions (adjacent intelligence)

### 2.1 Synoptic context overlay

- Endpoints:
  - `GET /api/mapasygraficos/analisis`
  - `GET /api/mapasygraficos/mapassignificativos/fecha/{fecha}/{ambito}/{dia}`
- Feature:
  - Add “large-scale weather context” cards near station timeline.
  - Useful for interpreting abrupt station changes.
- Value/Effort/Fit: `Medium / M / Context`

### 2.2 Severe-weather awareness timeline

- Endpoints:
  - `GET /api/avisos_cap/ultimoelaborado/area/{area}`
  - `GET /api/avisos_cap/archivo/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}`
- Feature:
  - Events timeline correlated with observed measurements.
  - Alert banners for active warnings in selected area.
- Value/Effort/Fit: `Medium / M / Context`

### 2.3 Radar/lightning signal enrichment

- Endpoints:
  - `GET /api/red/radar/nacional`
  - `GET /api/red/radar/regional/{radar}`
  - `GET /api/red/rayos/mapa`
- Feature:
  - Event-intensity overlays to explain spikes and abrupt variability.
  - “Convective risk now” hint for operations.
- Value/Effort/Fit: `Medium / M-L / Context`

### 2.4 Maritime operations support

- Endpoints:
  - `GET /api/prediccion/maritima/altamar/area/{area}`
  - `GET /api/prediccion/maritima/costera/costa/{costa}`
- Feature:
  - Logistics planning module for maritime segments.
  - Combine with Antarctica station windows for mission planning.
- Value/Effort/Fit: `Medium / M / Context`

## 3) Longer-horizon ideas

### 3.1 Forecast-vs-observation skill tracking

- Endpoints:
  - `GET /api/prediccion/especifica/municipio/horaria/{municipio}`
  - `GET /api/prediccion/especifica/municipio/diaria/{municipio}`
  - `GET /api/observacion/convencional/datos/estacion/{idema}`
- Feature:
  - Evaluate forecast skill and confidence heuristics.
  - Requires mapping municipality/station comparability.
- Value/Effort/Fit: `Low-Medium / L / Context`

### 3.2 Document-driven reporting assistant

- Endpoints:
  - `GET /api/productos/climatologicos/resumenclimatologico/nacional/{anio}/{mes}`
  - `GET /api/productos/climatologicos/balancehidrico/{anio}/{decena}`
- Feature:
  - Auto-generated monthly briefing with linked official docs and local metrics.
- Value/Effort/Fit: `Medium / S-M / Context`

## 4) Suggested incremental roadmap

1. Build anomaly + normals comparison (`High value`, direct fit).
2. Add record proximity alerts (`High value`, quick win).
3. Add station intelligence/admin diagnostics.
4. Add synoptic context cards (analysis maps).
5. Add warning/radar overlays if users need operational alerting.

## 5) Risks / caveats

- Geographic scope mismatch:
  - Some endpoints are Spain-focused and may not directly cover Antarctica.
  - Keep these as context modules, not replacements for Antarctica endpoint.
- Data cadence variance:
  - Different products update at different rates; communicate freshness in UI.
- API contract quirks:
  - Continue parsing `estado/descripcion/datos` defensively.
