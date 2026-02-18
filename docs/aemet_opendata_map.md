# AEMET OpenData: Relevant Documentation Map

This document summarizes the official AEMET OpenData documentation and maps the available API domains/endpoints, with focus on what matters for `antartica-analytics`.

## 1. How the API works (important for our backend)

- Base URL: `https://opendata.aemet.es/opendata/api`
- Most endpoints use a 2-step pattern:
  1. Call metadata endpoint (with API key)
  2. Response returns temporary `datos` URL
  3. Download JSON data from that `datos` URL
- Typical metadata payload fields:
  - `descripcion`
  - `estado`
  - `datos`
  - `metadatos`
- `estado=404` with message similar to `No hay datos que satisfagan esos criterios` means no data for the selected criteria/window.

## 2. Authentication

- Official OpenAPI schema shows `api_key` security.
- In practice, documented examples and working behavior use `api_key` as query parameter on metadata calls.
- Key is requested from AEMET OpenData portal:
  - <https://opendata.aemet.es/centrodedescargas/inicio>
  - <https://opendata.aemet.es/centrodedescargas/obtencionAPIKey>

## 3. Domain map (everything exposed at product/domain level)

OpenAPI tags in the official spec map to these domains:

1. `predicciones-especificas`
2. `predicciones-normalizadas-texto`
3. `observacion-convencional`
4. `observacion-avanzada`
5. `indices-uv`
6. `red-radares`
7. `red-rayos`
8. `satelites`
9. `avisos_cap`
10. `indices-incendios`
11. `mapas-y-graficos`
12. `maestro`
13. `valores-climatologicos`
14. `inventario-estaciones`
15. `antartida`

## 4. Endpoint families by domain

Below is the practical mapping of endpoint families visible in the official OpenAPI specification.

### 4.1 Predicciones específicas

- `prediccion/especifica/montaña/...` (mountain forecasts)
  - area + day variants
  - archive variants under `.../pasada/area/{area}`
- `prediccion/especifica/nivologica/...` (snow-related mountain prediction)
- `prediccion/especifica/municipio/diaria/{municipio}`
- `prediccion/especifica/municipio/horaria/{municipio}`
- `prediccion/especifica/playa/{playa}`
- `prediccion/especifica/uvi/{dia}`

### 4.2 Predicciones normalizadas texto

- National text forecasts:
  - `prediccion/nacional/hoy`
  - `prediccion/nacional/manana`
  - `prediccion/nacional/pasadomanana`
  - `prediccion/nacional/tendencia`
- CCAA text forecasts:
  - `prediccion/ccaa/hoy/{ccaa}`
  - `prediccion/ccaa/manana/{ccaa}`
  - `prediccion/ccaa/pasadomanana/{ccaa}`
  - `prediccion/ccaa/tendencia/{ccaa}`
- Province text forecasts:
  - `prediccion/provincia/hoy/{provincia}`
  - `prediccion/provincia/manana/{provincia}`
  - `prediccion/provincia/pasadomanana/{provincia}`
  - `prediccion/provincia/tendencia/{provincia}`
  - `prediccion/provincia/medioplazo/{provincia}`
- Archive/elaboration variants (`.../elaboracion/{fecha}`) for national/ccaa/provincia.

### 4.3 Observación convencional

- Station observations by date range and station:
  - `observacion/convencional/datos/estacion/{idema}`
  - `observacion/convencional/datos/fechaini/{...}/fechafin/{...}/estacion/{idema}`
- Observation messages:
  - `observacion/convencional/mensajes/tipomensaje/{tipomensaje}`

### 4.4 Observación avanzada

- Synoptic observations:
  - `observacion/convencional/todas`
- Surface network products:
  - `observacion/arep`
  - `observacion/atsup`

### 4.5 Índices UV

- UV index:
  - `prediccion/especifica/uvi/{dia}`

### 4.6 Red radares

- Radar products by radar and date:
  - `red/radar/{radar}/{fecha}`

### 4.7 Red rayos

- Lightning network products:
  - `red/rayos/mapa`

### 4.8 Satélites

- Satellite products by product/date:
  - `satelites/producto/{producto}/dia/{fecha}`

### 4.9 Avisos CAP

- Warnings by area/date:
  - `avisos_cap/ultimoelaborado/area/{area}`
  - `avisos_cap/fechaini/{...}/fechafin/{...}/area/{area}`
- Warnings by date:
  - `avisos_cap/fechaini/{...}/fechafin/{...}`
  - `avisos_cap/{fecha}`
- Last warning:
  - `avisos_cap/ultimoelaborado`

### 4.10 Índices incendios

- Fire weather index:
  - `indices/incendios/estimados/area/{area}`
  - `indices/incendios/mapasriesgo/area/{area}`

### 4.11 Mapas y gráficos

- Analysis/significant maps:
  - `mapasygraficos/analisis`
  - `mapasygraficos/analisis/{fecha}`
  - `mapasygraficos/mapassignificativos/{fecha}`

### 4.12 Maestro

- Municipal master data:
  - `maestro/municipios`

### 4.13 Valores climatológicos

- Daily climatological values:
  - `valores/climatologicos/diarios/datos/fechaini/{...}/fechafin/{...}/estacion/{idema}`
- Monthly climatological values:
  - `valores/climatologicos/mensualesanuales/datos/anioini/{...}/aniofin/{...}/estacion/{idema}`
- Normal values:
  - `valores/climatologicos/normales/estacion/{idema}`
- Phenological values:
  - `valores/climatologicos/efemerides/{idema}`

### 4.14 Inventario estaciones

- Station inventory:
  - `valores/climatologicos/inventarioestaciones/todasestaciones`
  - `valores/climatologicos/inventarioestaciones/estaciones/{estaciones}`

### 4.15 Antártida (our core domain)

- Antarctica station observations:
  - `antartida/datos/fechaini/{...}/fechafin/{...}/estacion/{idema}`
  - examples in official docs include `89064` (Gabriel de Castilla) and `89070` (Juan Carlos I)
- Radiometric Antarctica products:
  - `antartida/datos/radiometros/fechaini/{...}/fechafin/{...}/estacion/{idema}`
  - documented example station includes `9495X`
- Frequency noted in official docs for Antarctica dataset: annual.

## 5. What is most relevant for `antartica-analytics`

Primary:
- `antartida/datos/...` (already integrated)

High-value near-term additions:
- `antartida/datos/radiometros/...` (radiometric variables)
- `valores/climatologicos/inventarioestaciones/...` (station metadata validation/completeness)
- `valores/climatologicos/diarios/...` and `mensualesanuales/...` (contextual climatology baselines)

Useful UX/ops notes:
- No-data windows are expected; users should be guided to last available windows.
- Keep response/error handling based on `estado` + `descripcion`, not only HTTP status.
- Do not log API key values.

## 6. Sources

- OpenData portal home: <https://opendata.aemet.es/centrodedescargas/inicio>
- API key request page: <https://opendata.aemet.es/centrodedescargas/obtencionAPIKey>
- OpenAPI specification JSON: <https://opendata.aemet.es/AEMET_OpenData_specification.json>
- API docs (Swagger UI): <https://opendata.aemet.es/dist/index.html>
