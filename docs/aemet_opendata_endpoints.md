# AEMET OpenData: Exhaustive Endpoint Inventory

This file is generated from the official AEMET OpenAPI specification:
- `https://opendata.aemet.es/AEMET_OpenData_specification.json`

- Total unique paths: `62`
- Total operations (method + path): `62`

## Tag Index

- [antartida](#antartida) (1 ops)
- [avisos_cap](#avisos-cap) (2 ops)
- [indices-incendios](#indices-incendios) (2 ops)
- [informacion-satelite](#informacion-satelite) (2 ops)
- [maestro](#maestro) (2 ops)
- [mapas-y-graficos](#mapas-y-graficos) (2 ops)
- [observacion-convencional](#observacion-convencional) (3 ops)
- [prediccion-maritima](#prediccion-maritima) (2 ops)
- [predicciones-especificas](#predicciones-especificas) (7 ops)
- [predicciones-normalizadas-texto](#predicciones-normalizadas-texto) (22 ops)
- [productos-climatologicos](#productos-climatologicos) (3 ops)
- [red-radares](#red-radares) (2 ops)
- [red-rayos](#red-rayos) (1 ops)
- [redes-especiales](#redes-especiales) (4 ops)
- [valores-climatologicos](#valores-climatologicos) (7 ops)

## antartida

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}` | `Datos Antártida.` | Datos Antártida. |

## avisos_cap

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/avisos_cap/archivo/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}` | `Avisos de Fenómenos Meteorológicos Adversos. Archivo` | Avisos de Fenómenos Meteorológicos Adversos. Archivo. |
| `GET` | `/api/avisos_cap/ultimoelaborado/area/{area}` | `Avisos de Fenómenos Meteorológicos Adversos. Último.` | Avisos de Fenómenos Meteorológicos Adversos. Último. |

## indices-incendios

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/incendios/mapasriesgo/estimado/area/{area}` | `Mapa de niveles de riesgo estimado meteorológico de incendios forestales.` | Mapa de niveles de riesgo estimado meteorológico de incendios forestales. |
| `GET` | `/api/incendios/mapasriesgo/previsto/dia/{dia}/area/{area}` | `Mapa de niveles de riesgo previsto meteorológico de incendios forestales.` | Mapa de niveles de riesgo previsto meteorológico de incendios forestales. |

## informacion-satelite

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/satelites/producto/nvdi` | `Índice normalizado de vegetación.` | Índice normalizado de vegetación. |
| `GET` | `/api/satelites/producto/sst` | `Temperatura del agua del mar.` | Temperatura del agua del mar. |

## maestro

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/maestro/municipio/{municipio}` | `getMunicipioUsingGET` | Información específica municipio. |
| `GET` | `/api/maestro/municipios` | `getMunicipiosUsingGET` | Información específica municipios. |

## mapas-y-graficos

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/mapasygraficos/analisis` | `Mapas de análisis. Última pasada.` | Mapas de análisis. Última pasada. |
| `GET` | `/api/mapasygraficos/mapassignificativos/fecha/{fecha}/{ambito}/{dia}` | `Mapas significativos. Tiempo actual.` | Mapas significativos. Tiempo actual. |

## observacion-convencional

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/observacion/convencional/datos/estacion/{idema}` | `Datos de observación. Tiempo actual._1` | Datos de observación. Tiempo actual. |
| `GET` | `/api/observacion/convencional/mensajes/tipomensaje/{tipomensaje}` | `Mensajes de observación. Último elaborado.` | Mensajes de observación. Último elaborado. |
| `GET` | `/api/observacion/convencional/todas` | `Datos de observación. Tiempo actual.` | Datos de observación. Tiempo actual. |

## prediccion-maritima

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/prediccion/maritima/altamar/area/{area}` | `Predicción marítima de alta mar.` | Predicción marítima de alta mar. |
| `GET` | `/api/prediccion/maritima/costera/costa/{costa}` | `Predicción marítima costera.` | Predicción marítima costera. |

## predicciones-especificas

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/prediccion/especifica/montaña/pasada/area/{area}` | `Predicción de montaña. Tiempo pasado.` | Predicción de montaña. Tiempo pasado. |
| `GET` | `/api/prediccion/especifica/montaña/pasada/area/{area}/dia/{dia}` | `Predicción de montaña. Tiempo actual.` | Predicción de montaña. Tiempo actual. |
| `GET` | `/api/prediccion/especifica/municipio/diaria/{municipio}` | `Predicción por municipios diaria. Tiempo actual.` | Predicción por municipios diaria. Tiempo actual. |
| `GET` | `/api/prediccion/especifica/municipio/horaria/{municipio}` | `Predicción por municipios horaria. Tiempo actual.` | Predicción por municipios horaria. Tiempo actual. |
| `GET` | `/api/prediccion/especifica/nivologica/{area}` | `Informacion nivologica.` | Información nivológica. |
| `GET` | `/api/prediccion/especifica/playa/{playa}` | `Predicción para las playas. Tiempo actual.` | Predicción para las playas. Tiempo actual. |
| `GET` | `/api/prediccion/especifica/uvi/{dia}` | `Predicción de radiación ultravioleta (UVI).` | Predicción de radiación ultravioleta (UVI). |

## predicciones-normalizadas-texto

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/prediccion/ccaa/hoy/{ccaa}` | `Predicción CCAA hoy. Tiempo actual.` | Predicción CCAA hoy. Tiempo actual. |
| `GET` | `/api/prediccion/ccaa/hoy/{ccaa}/elaboracion/{fecha}` | `Predicción CCAA hoy. Archivo.` | Predicción CCAA hoy. Archivo. |
| `GET` | `/api/prediccion/ccaa/manana/{ccaa}` | `Predicción CCAA mañana. Tiempo actual.` | Predicción CCAA mañana. Tiempo actual. |
| `GET` | `/api/prediccion/ccaa/manana/{ccaa}/elaboracion/{fecha}` | `Predicción CCAA mañana. Archivo.` | Predicción CCAA mañana. Archivo. |
| `GET` | `/api/prediccion/ccaa/medioplazo/{ccaa}` | `Predicción CCAA medio plazo. Tiempo actual.` | Predicción CCAA medio plazo. Tiempo actual. |
| `GET` | `/api/prediccion/ccaa/medioplazo/{ccaa}/elaboracion/{fecha}` | `Predicción CCAA medio plazo. Archivo.` | Predicción CCAA medio plazo. Archivo. |
| `GET` | `/api/prediccion/ccaa/pasadomanana/{ccaa}` | `Predicción CCAA pasado mañana. Tiempo actual.` | Predicción CCAA pasado mañana. Tiempo actual. |
| `GET` | `/api/prediccion/ccaa/pasadomanana/{ccaa}/elaboracion/{fecha}` | `Predicción CCAA pasado mañana. Archivo.` | Predicción CCAA pasado mañana. Archivo. |
| `GET` | `/api/prediccion/nacional/hoy` | `Predicción nacional hoy. Tiempo actual.` | Predicción nacional hoy. Última elaborada. |
| `GET` | `/api/prediccion/nacional/hoy/elaboracion/{fecha}` | `Predicción nacional hoy. Archivo.` | Predicción nacional hoy. Archivo. |
| `GET` | `/api/prediccion/nacional/manana` | `Predicción nacional mañana. Tiempo actual.` | Predicción nacional mañana. Tiempo actual. |
| `GET` | `/api/prediccion/nacional/manana/elaboracion/{fecha}` | `Predicción nacional mañana. Archivo.` | Predicción nacional mañana. Archivo. |
| `GET` | `/api/prediccion/nacional/medioplazo` | `Predicción nacional medio plazo. Tiempo actual.` | Predicción nacional medio plazo. Tiempo actual. |
| `GET` | `/api/prediccion/nacional/medioplazo/elaboracion/{fecha}` | `Predicción nacional medio plazo. Archivo.` | Predicción nacional medio plazo. Archivo. |
| `GET` | `/api/prediccion/nacional/pasadomanana` | `Predicción nacional pasado mañana. Tiempo actual.` | Predicción nacional pasado mañana. Tiempo actual. |
| `GET` | `/api/prediccion/nacional/pasadomanana/elaboracion/{fecha}` | `Predicción nacional pasado mañana. Archivo.` | Predicción nacional pasado mañana. Archivo. |
| `GET` | `/api/prediccion/nacional/tendencia` | `Predicción nacional tendencia. Tiempo actual.` | Predicción nacional tendencia. Tiempo actual. |
| `GET` | `/api/prediccion/nacional/tendencia/elaboracion/{fecha}` | `Predicción nacional tendencia. Archivo.` | Predicción nacional tendencia. Archivo. |
| `GET` | `/api/prediccion/provincia/hoy/{provincia}` | `Predicción provincial e insular hoy. Tiempo actual.` | Predicción provincial e insular hoy. Tiempo actual. |
| `GET` | `/api/prediccion/provincia/hoy/{provincia}/elaboracion/{fecha}` | `Predicción provincial e insular hoy. Archivo.` | Predicción provincial e insular hoy. Archivo. |
| `GET` | `/api/prediccion/provincia/manana/{provincia}` | `Predicción provincial e insular mañana. Tiempo actual.` | Predicción provincial e insular mañana. Tiempo actual. |
| `GET` | `/api/prediccion/provincia/manana/{provincia}/elaboracion/{fecha}` | `Predicción provincial o insular mañana. Archivo.` | Predicción provincial e insular mañana. Archivo. |

## productos-climatologicos

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/productos/climatologicos/balancehidrico/{anio}/{decena}` | `Balance hídrico nacional (documento).` | Balance hídrico nacional (documento). |
| `GET` | `/api/productos/climatologicos/capasshape/{tipoestacion}` | `Capas SHAPE de estaciones climatológicas.` | Capas SHAPE de estaciones climatológicas de AEMET. |
| `GET` | `/api/productos/climatologicos/resumenclimatologico/nacional/{anio}/{mes}` | `Resumen mensual climatológico nacional (documento).` | Resumen mensual climatológico nacional (documento). |

## red-radares

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/red/radar/nacional` | `Imagen composición nacional radares. Tiempo actual estándar.` | Imagen composición nacional radares. Tiempo actual estándar. |
| `GET` | `/api/red/radar/regional/{radar}` | `Radar Regional` | Imagen gráfica radar regional. Tiempo actual estándar. |

## red-rayos

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/red/rayos/mapa` | `Mapa con los rayos registrados en periodo standard. Último elaborado.` | Mapa con los rayos registrados en periodo standard. Último elaborado. |

## redes-especiales

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/red/especial/contaminacionfondo/estacion/{nombre_estacion}` | `Datos de contaminación de fondo. Tiempo actual.` | Datos de contaminación de fondo. Tiempo actual. |
| `GET` | `/api/red/especial/ozono` | `Contenido total de ozono. Tiempo actual.` | Contenido total de ozono. Tiempo actual. |
| `GET` | `/api/red/especial/perfilozono/estacion/{estacion}` | `Perfiles verticales de ozono. Tiempo actual.` | Perfiles verticales de ozono. Tiempo actual. |
| `GET` | `/api/red/especial/radiacion` | `Datos de radiación global, directa o difusa. Tiempo actual.` | Datos de radiación global, directa o difusa. Tiempo actual. |

## valores-climatologicos

| Method | Path | Operation ID | Summary |
|---|---|---|---|
| `GET` | `/api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{idema}` | `Climatologías diarias.` | Climatologías diarias. |
| `GET` | `/api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/todasestaciones` | `Climatologías diarias._1` | Climatologías diarias. |
| `GET` | `/api/valores/climatologicos/inventarioestaciones/estaciones/{estaciones}` | `Estaciones por indicativo.` | Estaciones por indicativo. |
| `GET` | `/api/valores/climatologicos/inventarioestaciones/todasestaciones` | `Inventario de estaciones (valores climatológicos).` | Inventario de estaciones (valores climatológicos). |
| `GET` | `/api/valores/climatologicos/mensualesanuales/datos/anioini/{anioIniStr}/aniofin/{anioFinStr}/estacion/{idema}` | `Climatologías mensuales anuales.` | Climatologías mensuales anuales. |
| `GET` | `/api/valores/climatologicos/normales/estacion/{idema}` | `Climatologías normales (1991-2020).` | Climatologías normales (1991-2020). |
| `GET` | `/api/valores/climatologicos/valoresextremos/parametro/{parametro}/estacion/{idema}` | `Valores extremos.` | Valores extremos. |

## Flat List (All Operations)

| Method | Path | Tags |
|---|---|---|
| `GET` | `/api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}` | `antartida` |
| `GET` | `/api/avisos_cap/archivo/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}` | `avisos_cap` |
| `GET` | `/api/avisos_cap/ultimoelaborado/area/{area}` | `avisos_cap` |
| `GET` | `/api/incendios/mapasriesgo/estimado/area/{area}` | `indices-incendios` |
| `GET` | `/api/incendios/mapasriesgo/previsto/dia/{dia}/area/{area}` | `indices-incendios` |
| `GET` | `/api/maestro/municipio/{municipio}` | `maestro` |
| `GET` | `/api/maestro/municipios` | `maestro` |
| `GET` | `/api/mapasygraficos/analisis` | `mapas-y-graficos` |
| `GET` | `/api/mapasygraficos/mapassignificativos/fecha/{fecha}/{ambito}/{dia}` | `mapas-y-graficos` |
| `GET` | `/api/observacion/convencional/datos/estacion/{idema}` | `observacion-convencional` |
| `GET` | `/api/observacion/convencional/mensajes/tipomensaje/{tipomensaje}` | `observacion-convencional` |
| `GET` | `/api/observacion/convencional/todas` | `observacion-convencional` |
| `GET` | `/api/prediccion/ccaa/hoy/{ccaa}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/hoy/{ccaa}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/manana/{ccaa}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/manana/{ccaa}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/medioplazo/{ccaa}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/medioplazo/{ccaa}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/pasadomanana/{ccaa}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/ccaa/pasadomanana/{ccaa}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/especifica/montaña/pasada/area/{area}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/montaña/pasada/area/{area}/dia/{dia}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/municipio/diaria/{municipio}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/municipio/horaria/{municipio}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/nivologica/{area}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/playa/{playa}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/especifica/uvi/{dia}` | `predicciones-especificas` |
| `GET` | `/api/prediccion/maritima/altamar/area/{area}` | `prediccion-maritima` |
| `GET` | `/api/prediccion/maritima/costera/costa/{costa}` | `prediccion-maritima` |
| `GET` | `/api/prediccion/nacional/hoy` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/hoy/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/manana` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/manana/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/medioplazo` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/medioplazo/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/pasadomanana` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/pasadomanana/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/tendencia` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/nacional/tendencia/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/provincia/hoy/{provincia}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/provincia/hoy/{provincia}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/provincia/manana/{provincia}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/prediccion/provincia/manana/{provincia}/elaboracion/{fecha}` | `predicciones-normalizadas-texto` |
| `GET` | `/api/productos/climatologicos/balancehidrico/{anio}/{decena}` | `productos-climatologicos` |
| `GET` | `/api/productos/climatologicos/capasshape/{tipoestacion}` | `productos-climatologicos` |
| `GET` | `/api/productos/climatologicos/resumenclimatologico/nacional/{anio}/{mes}` | `productos-climatologicos` |
| `GET` | `/api/red/especial/contaminacionfondo/estacion/{nombre_estacion}` | `redes-especiales` |
| `GET` | `/api/red/especial/ozono` | `redes-especiales` |
| `GET` | `/api/red/especial/perfilozono/estacion/{estacion}` | `redes-especiales` |
| `GET` | `/api/red/especial/radiacion` | `redes-especiales` |
| `GET` | `/api/red/radar/nacional` | `red-radares` |
| `GET` | `/api/red/radar/regional/{radar}` | `red-radares` |
| `GET` | `/api/red/rayos/mapa` | `red-rayos` |
| `GET` | `/api/satelites/producto/nvdi` | `informacion-satelite` |
| `GET` | `/api/satelites/producto/sst` | `informacion-satelite` |
| `GET` | `/api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{idema}` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/diarios/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/todasestaciones` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/inventarioestaciones/estaciones/{estaciones}` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/inventarioestaciones/todasestaciones` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/mensualesanuales/datos/anioini/{anioIniStr}/aniofin/{anioFinStr}/estacion/{idema}` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/normales/estacion/{idema}` | `valores-climatologicos` |
| `GET` | `/api/valores/climatologicos/valoresextremos/parametro/{parametro}/estacion/{idema}` | `valores-climatologicos` |
