import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.dependencies import get_service, set_compliance_headers
from app.models import (
    AnalysisBootstrapResponse,
    FeasibilitySnapshotResponse,
    MeasurementType,
    PlaybackResponse,
    PlaybackStep,
    QueryJobCreateRequest,
    QueryJobCreatedResponse,
    QueryJobStatusResponse,
    TimeframeAnalyticsResponse,
    TimeframeGroupBy,
    WindFarmSimulationParams,
)
from app.services import AntarcticService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/api/analysis/bootstrap",
    response_model=AnalysisBootstrapResponse,
    tags=["Analysis"],
    summary="Bootstrap dashboard stations and latest map snapshots",
)
def analysis_bootstrap(
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> AnalysisBootstrapResponse:
    try:
        payload = service.get_analysis_bootstrap()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Upstream AEMET failure on analysis bootstrap endpoint: detail=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload_model = (
        payload if isinstance(payload, AnalysisBootstrapResponse) else AnalysisBootstrapResponse.model_validate(payload)
    )
    latest_values = [value for value in payload_model.latest_observation_by_station.values() if value is not None]
    latest_observation_utc = max(latest_values).astimezone(ZoneInfo("UTC")).isoformat() if latest_values else None
    set_compliance_headers(response, latest_observation_utc=latest_observation_utc)
    return payload_model


@router.post(
    "/api/analysis/query-jobs",
    response_model=QueryJobCreatedResponse,
    tags=["Analysis"],
    summary="Create a cache-first backfill job for one station",
)
def create_query_job(
    response: Response,
    payload: QueryJobCreateRequest,
    service: AntarcticService = Depends(get_service),
) -> QueryJobCreatedResponse:
    try:
        tz = ZoneInfo(payload.location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {payload.location}") from exc

    start = payload.start
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    else:
        start = start.astimezone(tz)

    history_start = payload.history_start
    if history_start is not None:
        if history_start.tzinfo is None:
            history_start = history_start.replace(tzinfo=tz)
        else:
            history_start = history_start.astimezone(tz)

    selected_types: list[MeasurementType] = []
    for value in payload.types:
        try:
            selected_types.append(MeasurementType(value))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid measurement type: {value}") from exc

    try:
        job = service.create_query_job(
            station=payload.station,
            start_local=start,
            timezone_input=payload.location,
            playback_step=payload.playback_step,
            aggregation=payload.aggregation,
            selected_types=selected_types,
            history_start_local=history_start,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("Upstream AEMET failure on query-jobs endpoint: detail=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    set_compliance_headers(response)
    return job


@router.get(
    "/api/analysis/query-jobs/{job_id}",
    response_model=QueryJobStatusResponse,
    tags=["Analysis"],
    summary="Poll cache/backfill job status",
)
def query_job_status(
    job_id: str,
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> QueryJobStatusResponse:
    try:
        job = service.get_query_job_status(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    set_compliance_headers(response)
    return job


@router.get(
    "/api/analysis/query-jobs/{job_id}/result",
    response_model=FeasibilitySnapshotResponse,
    tags=["Analysis"],
    summary="Get latest snapshot materialized for a completed/running job",
)
def query_job_result(
    job_id: str,
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> FeasibilitySnapshotResponse:
    try:
        snapshot = service.get_query_job_result(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_model = (
        snapshot if isinstance(snapshot, FeasibilitySnapshotResponse) else FeasibilitySnapshotResponse.model_validate(snapshot)
    )
    latest_observation_utc = None
    for series in snapshot_model.stations:
        latest = series.summary.latest_observation_utc
        if latest is None:
            continue
        if latest_observation_utc is None or latest > latest_observation_utc:
            latest_observation_utc = latest
    set_compliance_headers(
        response,
        latest_observation_utc=latest_observation_utc.astimezone(ZoneInfo("UTC")).isoformat()
        if latest_observation_utc is not None
        else None,
    )
    return snapshot_model


@router.get(
    "/api/analysis/playback",
    response_model=PlaybackResponse,
    tags=["Analysis"],
    summary="Build playback frames for a selected station window",
)
def playback(
    response: Response,
    station: str = Query(...),
    start: str = Query(..., description="Start datetime in local input timezone. Format: YYYY-MM-DDTHH:MM:SS"),
    end: str = Query(..., description="End datetime in local input timezone. Format: YYYY-MM-DDTHH:MM:SS"),
    step: PlaybackStep = Query(PlaybackStep.HOURLY),
    location: str = Query("UTC", description="Input timezone location, e.g. Europe/Madrid"),
    service: AntarcticService = Depends(get_service),
) -> PlaybackResponse:
    try:
        tz = ZoneInfo(location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {location}") from exc

    try:
        start_parsed = datetime.fromisoformat(start)
        end_parsed = datetime.fromisoformat(end)
        start_local = start_parsed.replace(tzinfo=tz) if start_parsed.tzinfo is None else start_parsed.astimezone(tz)
        end_local = end_parsed.replace(tzinfo=tz) if end_parsed.tzinfo is None else end_parsed.astimezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datetime format must be YYYY-MM-DDTHH:MM:SS") from exc
    try:
        payload = service.get_playback_frames(
            station=station,
            start_local=start_local,
            end_local=end_local,
            step=step,
            timezone_input=location,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on playback endpoint: station=%s start=%s end=%s detail=%s",
            station,
            start_local.isoformat(),
            end_local.isoformat(),
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload_model = payload if isinstance(payload, PlaybackResponse) else PlaybackResponse.model_validate(payload)
    latest_utc = None
    if payload_model.frames:
        latest_utc = max(frame.datetime_local for frame in payload_model.frames).astimezone(ZoneInfo("UTC")).isoformat()
    set_compliance_headers(response, latest_observation_utc=latest_utc)
    return payload_model


@router.get(
    "/api/analysis/timeframes",
    response_model=TimeframeAnalyticsResponse,
    tags=["Analysis"],
    summary="Compute grouped timeframe analytics and optional comparison",
)
def timeframe_analytics(
    response: Response,
    station: str = Query(...),
    start: str = Query(..., description="Start datetime in local input timezone. Format: YYYY-MM-DDTHH:MM:SS"),
    end: str = Query(..., description="End datetime in local input timezone. Format: YYYY-MM-DDTHH:MM:SS"),
    group_by: TimeframeGroupBy = Query(TimeframeGroupBy.DAY, alias="groupBy"),
    compare_start: str | None = Query(default=None, alias="compareStart"),
    compare_end: str | None = Query(default=None, alias="compareEnd"),
    force_refresh_on_empty: bool = Query(default=False, alias="forceRefreshOnEmpty"),
    location: str = Query("UTC", description="Input timezone location, e.g. Europe/Madrid"),
    turbine_count: int | None = Query(default=None, alias="turbineCount"),
    rated_power_kw: float | None = Query(default=None, alias="ratedPowerKw"),
    cut_in_speed_mps: float | None = Query(default=None, alias="cutInSpeedMps"),
    rated_speed_mps: float | None = Query(default=None, alias="ratedSpeedMps"),
    cut_out_speed_mps: float | None = Query(default=None, alias="cutOutSpeedMps"),
    reference_air_density_kgm3: float | None = Query(default=None, alias="referenceAirDensityKgM3"),
    min_operating_temp_c: float | None = Query(default=None, alias="minOperatingTempC"),
    max_operating_temp_c: float | None = Query(default=None, alias="maxOperatingTempC"),
    min_operating_pressure_hpa: float | None = Query(default=None, alias="minOperatingPressureHpa"),
    max_operating_pressure_hpa: float | None = Query(default=None, alias="maxOperatingPressureHpa"),
    service: AntarcticService = Depends(get_service),
) -> TimeframeAnalyticsResponse:
    try:
        tz = ZoneInfo(location)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid timezone location: {location}") from exc

    try:
        start_parsed = datetime.fromisoformat(start)
        end_parsed = datetime.fromisoformat(end)
        start_local = start_parsed.replace(tzinfo=tz) if start_parsed.tzinfo is None else start_parsed.astimezone(tz)
        end_local = end_parsed.replace(tzinfo=tz) if end_parsed.tzinfo is None else end_parsed.astimezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Datetime format must be YYYY-MM-DDTHH:MM:SS") from exc

    compare_start_local = None
    compare_end_local = None
    try:
        if compare_start is not None:
            compare_start_parsed = datetime.fromisoformat(compare_start)
            compare_start_local = (
                compare_start_parsed.replace(tzinfo=tz)
                if compare_start_parsed.tzinfo is None
                else compare_start_parsed.astimezone(tz)
            )
        if compare_end is not None:
            compare_end_parsed = datetime.fromisoformat(compare_end)
            compare_end_local = (
                compare_end_parsed.replace(tzinfo=tz)
                if compare_end_parsed.tzinfo is None
                else compare_end_parsed.astimezone(tz)
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Comparison datetime format must be YYYY-MM-DDTHH:MM:SS") from exc
    if (compare_start_local is None) != (compare_end_local is None):
        raise HTTPException(
            status_code=400,
            detail="Comparison range requires both compareStart and compareEnd.",
        )
    if (
        compare_start_local is not None
        and compare_end_local is not None
        and compare_start_local >= compare_end_local
    ):
        raise HTTPException(
            status_code=400,
            detail="Comparison start datetime must be before comparison end datetime.",
        )

    simulation_params = None
    has_simulation_inputs = any(
        value is not None
        for value in (turbine_count, rated_power_kw, cut_in_speed_mps, rated_speed_mps, cut_out_speed_mps)
    )
    if has_simulation_inputs:
        if None in (turbine_count, rated_power_kw, cut_in_speed_mps, rated_speed_mps, cut_out_speed_mps):
            raise HTTPException(
                status_code=400,
                detail=(
                    "To calculate expected generation provide all simulation parameters: "
                    "turbineCount, ratedPowerKw, cutInSpeedMps, ratedSpeedMps, cutOutSpeedMps."
                ),
            )
        payload: dict[str, float | int] = {
            "turbineCount": turbine_count,
            "ratedPowerKw": rated_power_kw,
            "cutInSpeedMps": cut_in_speed_mps,
            "ratedSpeedMps": rated_speed_mps,
            "cutOutSpeedMps": cut_out_speed_mps,
        }
        if reference_air_density_kgm3 is not None:
            payload["referenceAirDensityKgM3"] = reference_air_density_kgm3
        if min_operating_temp_c is not None:
            payload["minOperatingTempC"] = min_operating_temp_c
        if max_operating_temp_c is not None:
            payload["maxOperatingTempC"] = max_operating_temp_c
        if min_operating_pressure_hpa is not None:
            payload["minOperatingPressureHpa"] = min_operating_pressure_hpa
        if max_operating_pressure_hpa is not None:
            payload["maxOperatingPressureHpa"] = max_operating_pressure_hpa
        try:
            simulation_params = WindFarmSimulationParams(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        payload = service.get_timeframe_analytics(
            station=station,
            start_local=start_local,
            end_local=end_local,
            group_by=group_by,
            timezone_input=location,
            compare_start_local=compare_start_local,
            compare_end_local=compare_end_local,
            simulation_params=simulation_params,
            force_refresh_on_empty=force_refresh_on_empty,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "Upstream AEMET failure on timeframe endpoint: station=%s start=%s end=%s detail=%s",
            station,
            start_local.isoformat(),
            end_local.isoformat(),
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload_model = (
        payload
        if isinstance(payload, TimeframeAnalyticsResponse)
        else TimeframeAnalyticsResponse.model_validate(payload)
    )
    latest_utc = None
    if payload_model.buckets:
        latest_utc = payload_model.buckets[-1].end_local.astimezone(ZoneInfo("UTC")).isoformat()
    set_compliance_headers(response, latest_observation_utc=latest_utc)
    return payload_model
