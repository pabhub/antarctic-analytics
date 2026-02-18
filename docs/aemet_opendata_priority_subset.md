# AEMET OpenData: Priority Subset For Antarctica Analytics

This is the focused endpoint subset most relevant to our current product direction (Antarctica observations, station metadata, and climatology context).

Source spec: `https://opendata.aemet.es/AEMET_OpenData_specification.json`

## Tier 1 (Integrate first)

| Endpoint | Tag | Why it matters | Suggested use in app |
|---|---|---|---|
| `GET /api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}` | `antartida` | Core live/near-live observations for our current dashboard. | Keep as primary data source for map/charts/export. |
| `GET /api/valores/climatologicos/inventarioestaciones/estaciones/{estaciones}` | `valores-climatologicos` | Confirms station metadata and valid station codes. | Validate configured station IDs and enrich metadata panel. |
| `GET /api/valores/climatologicos/inventarioestaciones/todasestaciones` | `valores-climatologicos` | Complete station catalog for discovery/future expansion. | Build station selector that supports future non-Antarctica expansion. |
| `GET /api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{idema}` | `valores-climatologicos` | Historical baseline at daily granularity. | Compare current values vs historical daily averages/anomalies. |

## Tier 2 (High value next)

| Endpoint | Tag | Why it matters | Suggested use in app |
|---|---|---|---|
| `GET /api/valores/climatologicos/mensualesanuales/datos/anioini/{anioIniStr}/aniofin/{anioFinStr}/estacion/{idema}` | `valores-climatologicos` | Long-range monthly/annual climatology. | Monthly climate context cards and trend benchmarking. |
| `GET /api/valores/climatologicos/normales/estacion/{idema}` | `valores-climatologicos` | Official climate normals (1991-2020). | “Normal vs observed” KPI and anomaly percentages. |
| `GET /api/valores/climatologicos/valoresextremos/parametro/{parametro}/estacion/{idema}` | `valores-climatologicos` | Extreme records by parameter. | Record proximity alerts (e.g., high winds near record). |
| `GET /api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/todasestaciones` | `valores-climatologicos` | Bulk multi-station historical values. | Regional comparisons and nearest-neighbor interpolation. |

## Tier 3 (Context/document products)

| Endpoint | Tag | Why it matters | Suggested use in app |
|---|---|---|---|
| `GET /api/productos/climatologicos/resumenclimatologico/nacional/{anio}/{mes}` | `productos-climatologicos` | Official monthly climate summary document. | Monthly briefing download for analysts/stakeholders. |
| `GET /api/productos/climatologicos/balancehidrico/{anio}/{decena}` | `productos-climatologicos` | Hydric balance product (document). | Contextual report tab for operations planning. |
| `GET /api/productos/climatologicos/capasshape/{tipoestacion}` | `productos-climatologicos` | GIS layers for stations. | Improve map overlays / GIS export workflows. |

## Integration notes

- All listed endpoints follow the AEMET 2-step data flow (`metadata` -> `datos` URL).
- Preserve current robust handling:
  - no-data (`estado=404` + no-data message) => empty dataset, not hard failure
  - upstream shape changes => clear warnings and `502` only when truly upstream-invalid
- For UX:
  - always expose “latest available observation” guidance
  - show if requested window is outside known recent availability
