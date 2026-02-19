import csv
import logging
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.dependencies import compliance_headers, get_service
from app.models import MeasurementType, OutputMeasurement, TimeAggregation
from app.services import AntarcticService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Data Export"])


@router.get(
    "/api/antarctic/export/fechaini/{fechaIniStr}/fechafin/{fechaFinStr}/estacion/{identificacion}",
    summary="Export cached-or-fetched station observations as CSV/Parquet",
    description=(
        "Returns export files for the requested station window. Windows larger than one month are internally "
        "resolved through month-sized cache-first fetches to comply with AEMET limits. "
        "Use aggregation values: none, hourly, daily, monthly."
    ),
)
def export_antarctic_data(
    fechaIniStr: str,
    fechaFinStr: str,
    identificacion: str,
    location: str = Query("UTC", description="Timezone location, e.g. Europe/Berlin"),
    aggregation: TimeAggregation = Query(TimeAggregation.NONE),
    types: list[MeasurementType] = Query(default=[]),
    format: str = Query("csv", pattern="^(csv|parquet)$"),
    service: AntarcticService = Depends(get_service),
) -> Response:
    try:
        tz = ZoneInfo(location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {location}") from exc

    try:
        start_parsed = datetime.fromisoformat(fechaIniStr)
        end_parsed = datetime.fromisoformat(fechaFinStr)
        start = start_parsed.replace(tzinfo=tz) if start_parsed.tzinfo is None else start_parsed.astimezone(tz)
        end = end_parsed.replace(tzinfo=tz) if end_parsed.tzinfo is None else end_parsed.astimezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datetime format must be YYYY-MM-DDTHH:MM:SS") from exc

    try:
        try:
            data = service.get_data(
                station=identificacion,
                start_local=start,
                end_local=end,
                aggregation=aggregation,
                selected_types=types,
                output_tz=tz,
            )
        except TypeError as exc:
            if "output_tz" not in str(exc):
                raise
            data = service.get_data(
                station=identificacion,
                start_local=start,
                end_local=end,
                aggregation=aggregation,
                selected_types=types,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on export endpoint: station=%s start=%s end=%s format=%s detail=%s",
            identificacion,
            start.isoformat(),
            end.isoformat(),
            format,
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    filename_base = f"{identificacion}_{start.strftime('%Y%m%dT%H%M%S')}_{end.strftime('%Y%m%dT%H%M%S')}_{aggregation.value}"
    latest_observation_utc = None
    if data:
        latest = max(item.datetime_cet for item in data)
        latest_observation_utc = latest.astimezone(ZoneInfo("UTC")).isoformat()

    if format == "csv":
        csv_content = _build_csv(data)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename_base}.csv"',
            **compliance_headers(latest_observation_utc=latest_observation_utc),
        }
        return Response(content=csv_content, media_type="text/csv; charset=utf-8", headers=headers)

    parquet_bytes = _build_parquet(data)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename_base}.parquet"',
        **compliance_headers(latest_observation_utc=latest_observation_utc),
    }
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
