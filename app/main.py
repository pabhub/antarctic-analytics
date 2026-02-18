from __future__ import annotations

import logging
from io import StringIO
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.aemet_client import AemetClient
from app.database import SQLiteRepository
from app.models import (
    AvailableDataResponse,
    LatestAvailabilityResponse,
    MeasurementResponse,
    MeasurementType,
    OutputMeasurement,
    Station,
    StationCatalogResponse,
    TimeAggregation,
)
from app.service import AntartidaService
from app.settings import Settings, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title="AEMET Antarctica API", version="1.0.0")

CURRENTLY_EXPOSED_FIELDS = {
    "nombre": "Station name",
    "fhora": "Observation datetime",
    "temp": "Air temperature (ºC)",
    "pres": "Pressure (hPa)",
    "vel": "Wind speed (m/s)",
    "dir": "Wind direction (degrees)",
    "lat/latitud": "Station latitude",
    "lon/longitud": "Station longitude",
    "alt/altitud": "Station altitude (m)",
}

ADDITIONAL_FIELDS_OFTEN_AVAILABLE = {
    "hr": "Relative humidity (%)",
    "prec": "Precipitation (mm)",
    "racha": "Wind gust (m/s)",
    "vis": "Visibility",
    "nieve": "Snow-related indicators",
    "tpr": "Dew point temperature (ºC)",
}

frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")


def get_service(settings: Settings = Depends(get_settings)) -> AntartidaService:
    repository = SQLiteRepository(settings.database_url)
    client = AemetClient(settings.aemet_api_key, settings.request_timeout_seconds)
    return AntartidaService(settings=settings, repository=repository, aemet_client=client)


@app.get("/")
def index() -> FileResponse:
    html_path = frontend_dist / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not built yet")
    return FileResponse(html_path)


@app.get("/config")
def config_page() -> FileResponse:
    html_path = frontend_dist / "config.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Config page not built yet")
    return FileResponse(html_path)


@app.get("/api/metadata/available-data", response_model=AvailableDataResponse)
def available_data() -> AvailableDataResponse:
    return AvailableDataResponse(
        source_endpoint="/api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}",
        currently_exposed_fields=CURRENTLY_EXPOSED_FIELDS,
        additional_fields_often_available=ADDITIONAL_FIELDS_OFTEN_AVAILABLE,
    )


@app.get("/api/metadata/latest-availability/station/{identificacion}", response_model=LatestAvailabilityResponse)
def latest_availability(
    identificacion: Station,
    service: AntartidaService = Depends(get_service),
) -> LatestAvailabilityResponse:
    try:
        return service.get_latest_availability(identificacion)
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on availability endpoint: station=%s detail=%s",
            identificacion.value,
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/metadata/stations", response_model=StationCatalogResponse)
def stations_catalog(
    force_refresh: bool = Query(False, description="Force refresh from AEMET instead of DB cache"),
    service: AntartidaService = Depends(get_service),
) -> StationCatalogResponse:
    try:
        return service.get_station_catalog(force_refresh=force_refresh)
    except RuntimeError as exc:
        logger.warning("Upstream AEMET failure on stations endpoint: detail=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get(
    "/api/antartida/datos/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}",
    response_model=MeasurementResponse,
)
def antartida_data(
    fechaIniStr: str,
    fechaFinStr: str,
    identificacion: Station,
    location: str = Query("UTC", description="Timezone location, e.g. Europe/Berlin"),
    aggregation: TimeAggregation = Query(TimeAggregation.NONE),
    types: list[MeasurementType] = Query(default=[]),
    service: AntartidaService = Depends(get_service),
) -> MeasurementResponse:
    try:
        tz = ZoneInfo(location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {location}") from exc

    try:
        start = datetime.fromisoformat(fechaIniStr).replace(tzinfo=tz)
        end = datetime.fromisoformat(fechaFinStr).replace(tzinfo=tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datetime format must be YYYY-MM-DDTHH:MM:SS") from exc

    if start >= end:
        raise HTTPException(status_code=400, detail="Start datetime must be before end datetime")

    try:
        data = service.get_data(
            station=identificacion,
            start_local=start,
            end_local=end,
            aggregation=aggregation,
            selected_types=types,
        )
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on data endpoint: station=%s start=%s end=%s detail=%s",
            identificacion.value,
            start.isoformat(),
            end.isoformat(),
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MeasurementResponse(
        station=identificacion,
        aggregation=aggregation,
        selected_types=types,
        timezone_input=location,
        data=data,
    )


@app.get(
    "/api/antartida/export/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}",
)
def export_antartida_data(
    fechaIniStr: str,
    fechaFinStr: str,
    identificacion: Station,
    location: str = Query("UTC", description="Timezone location, e.g. Europe/Berlin"),
    aggregation: TimeAggregation = Query(TimeAggregation.NONE),
    types: list[MeasurementType] = Query(default=[]),
    format: str = Query("csv", pattern="^(csv|parquet)$"),
    service: AntartidaService = Depends(get_service),
) -> Response:
    try:
        tz = ZoneInfo(location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {location}") from exc

    try:
        start = datetime.fromisoformat(fechaIniStr).replace(tzinfo=tz)
        end = datetime.fromisoformat(fechaFinStr).replace(tzinfo=tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datetime format must be YYYY-MM-DDTHH:MM:SS") from exc

    if start >= end:
        raise HTTPException(status_code=400, detail="Start datetime must be before end datetime")

    try:
        data = service.get_data(
            station=identificacion,
            start_local=start,
            end_local=end,
            aggregation=aggregation,
            selected_types=types,
        )
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on export endpoint: station=%s start=%s end=%s format=%s detail=%s",
            identificacion.value,
            start.isoformat(),
            end.isoformat(),
            format,
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    filename_base = f"{identificacion.value}_{start.strftime('%Y%m%dT%H%M%S')}_{end.strftime('%Y%m%dT%H%M%S')}_{aggregation.value}"

    if format == "csv":
        csv_content = _build_csv(data)
        headers = {"Content-Disposition": f'attachment; filename="{filename_base}.csv"'}
        return Response(content=csv_content, media_type="text/csv; charset=utf-8", headers=headers)

    parquet_bytes = _build_parquet(data)
    headers = {"Content-Disposition": f'attachment; filename="{filename_base}.parquet"'}
    return Response(content=parquet_bytes, media_type="application/octet-stream", headers=headers)


def _build_csv(data: list[OutputMeasurement]) -> str:
    output = StringIO()
    fieldnames = [
        "stationName",
        "datetime",
        "temperature",
        "pressure",
        "speed",
        "direction",
        "latitude",
        "longitude",
        "altitude",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        payload = row.model_dump(by_alias=True)
        if isinstance(payload.get("datetime"), datetime):
            payload["datetime"] = payload["datetime"].isoformat()
        writer.writerow({key: payload.get(key) for key in fieldnames})
    return output.getvalue()


def _build_parquet(data: list[OutputMeasurement]) -> bytes:
    try:
        import pandas as pd
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="Parquet export requires pandas/pyarrow. Install optional dependencies to enable it.",
        ) from exc

    rows: list[dict[str, object]] = []
    for row in data:
        payload = row.model_dump(by_alias=True)
        dt = payload.get("datetime")
        if isinstance(dt, datetime):
            payload["datetime"] = dt.isoformat()
        rows.append(payload)

    df = pd.DataFrame(rows)
    return df.to_parquet(index=False)
