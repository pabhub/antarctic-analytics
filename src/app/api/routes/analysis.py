import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.dependencies import get_service, set_compliance_headers
from app.api.route_utils import (
    SERVICE_ERROR_RESPONSES,
    call_service_or_http,
    coerce_datetime_to_timezone,
    parse_local_range_or_400,
    parse_optional_local_datetime_or_400,
    parse_timezone_or_400,
    to_utc_iso,
)
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
router = APIRouter(tags=["Analysis"])


@router.get(
    "/api/analysis/bootstrap",
    response_model=AnalysisBootstrapResponse,
    tags=["Analysis"],
    summary="Bootstrap dashboard stations and latest map snapshots",
    responses=SERVICE_ERROR_RESPONSES,
)
def analysis_bootstrap(
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> AnalysisBootstrapResponse:
    logger.info("Handling analysis bootstrap request")
    payload = call_service_or_http(
        lambda: service.get_analysis_bootstrap(),
        logger=logger,
        endpoint="analysis/bootstrap",
    )

    payload_model = (
        payload if isinstance(payload, AnalysisBootstrapResponse) else AnalysisBootstrapResponse.model_validate(payload)
    )
    latest_values = [value for value in payload_model.latest_observation_by_station.values() if value is not None]
    latest_observation_utc = to_utc_iso(max(latest_values) if latest_values else None)
    set_compliance_headers(response, latest_observation_utc=latest_observation_utc)
    
    logger.info(
        "Analysis bootstrap served stations=%d selectable=%d snapshots=%d",
        len(payload_model.stations),
        len(payload_model.selectable_station_ids),
        len(payload_model.latest_snapshots),
    )
    return payload_model


@router.post(
    "/api/analysis/query-jobs",
    response_model=QueryJobCreatedResponse,
    tags=["Analysis"],
    summary="Create a cache-first backfill job for one station",
    responses=SERVICE_ERROR_RESPONSES,
)
def create_query_job(
    response: Response,
    payload: QueryJobCreateRequest,
    service: AntarcticService = Depends(get_service),
) -> QueryJobCreatedResponse:
    tz = parse_timezone_or_400(payload.location)
    start = coerce_datetime_to_timezone(payload.start, tz)
    end = None
    if payload.end is not None:
        end = coerce_datetime_to_timezone(payload.end, tz)

    history_start = payload.history_start
    if history_start is not None:
        history_start = coerce_datetime_to_timezone(history_start, tz)

    selected_types: list[MeasurementType] = []
    for value in payload.types:
        try:
            selected_types.append(MeasurementType(value))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid measurement type: {value}") from exc

    logger.info(
        "Creating query job station=%s timezone=%s aggregation=%s playback_step=%s",
        payload.station,
        payload.location,
        payload.aggregation.value,
        payload.playback_step.value,
    )
    job = call_service_or_http(
        lambda: service.create_query_job(
            station=payload.station,
            start_local=start,
            end_local=end,
            timezone_input=payload.location,
            playback_step=payload.playback_step,
            aggregation=payload.aggregation,
            selected_types=selected_types,
            history_start_local=history_start,
        ),
        logger=logger,
        endpoint="analysis/query-jobs",
        context={"station": payload.station},
    )
    job_model = job if isinstance(job, QueryJobCreatedResponse) else QueryJobCreatedResponse.model_validate(job)

    set_compliance_headers(response)
    logger.info(
        "Created query job id=%s station=%s total_windows=%d missing_windows=%d planned_calls=%d",
        job_model.job_id,
        job_model.station_id,
        job_model.total_windows,
        job_model.missing_windows,
        job_model.total_api_calls_planned,
    )
    return job_model


@router.get(
    "/api/analysis/query-jobs/{job_id}",
    response_model=QueryJobStatusResponse,
    tags=["Analysis"],
    summary="Poll cache/backfill job status",
    responses=SERVICE_ERROR_RESPONSES,
)
def query_job_status(
    job_id: str,
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> QueryJobStatusResponse:
    job = call_service_or_http(
        lambda: service.get_query_job_status(job_id),
        logger=logger,
        endpoint="analysis/query-jobs/status",
        context={"job_id": job_id},
    )
    set_compliance_headers(response)
    return job


@router.get(
    "/api/analysis/query-jobs/{job_id}/result",
    response_model=FeasibilitySnapshotResponse,
    tags=["Analysis"],
    summary="Get latest snapshot materialized for a completed/running job",
    responses=SERVICE_ERROR_RESPONSES,
)
def query_job_result(
    job_id: str,
    response: Response,
    service: AntarcticService = Depends(get_service),
) -> FeasibilitySnapshotResponse:
    snapshot = call_service_or_http(
        lambda: service.get_query_job_result(job_id),
        logger=logger,
        endpoint="analysis/query-jobs/result",
        context={"job_id": job_id},
    )
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
        latest_observation_utc=to_utc_iso(latest_observation_utc),
    )
    return snapshot_model


@router.get(
    "/api/analysis/playback",
    response_model=PlaybackResponse,
    tags=["Analysis"],
    summary="Build playback frames for a selected station window",
    responses=SERVICE_ERROR_RESPONSES,
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
    tz = parse_timezone_or_400(location)
    start_local, end_local = parse_local_range_or_400(start, end, tz, error_prefix="Datetime")
    payload = call_service_or_http(
        lambda: service.get_playback_frames(
            station=station,
            start_local=start_local,
            end_local=end_local,
            step=step,
            timezone_input=location,
        ),
        logger=logger,
        endpoint="analysis/playback",
        context={"station": station, "start": start_local.isoformat(), "end": end_local.isoformat()},
    )

    payload_model = payload if isinstance(payload, PlaybackResponse) else PlaybackResponse.model_validate(payload)
    latest_utc = None
    if payload_model.frames:
        latest_utc = to_utc_iso(max(frame.datetime_local for frame in payload_model.frames))
    set_compliance_headers(response, latest_observation_utc=latest_utc)
    return payload_model


@router.get(
    "/api/analysis/timeframes",
    response_model=TimeframeAnalyticsResponse,
    tags=["Analysis"],
    summary="Compute grouped timeframe analytics and optional comparison",
    responses=SERVICE_ERROR_RESPONSES,
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
    tz = parse_timezone_or_400(location)
    start_local, end_local = parse_local_range_or_400(start, end, tz, error_prefix="Datetime")
    compare_start_local = parse_optional_local_datetime_or_400(
        compare_start,
        tz,
        error_prefix="Comparison datetime",
    )
    compare_end_local = parse_optional_local_datetime_or_400(
        compare_end,
        tz,
        error_prefix="Comparison datetime",
    )
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

    logger.info(
        "Handling timeframe analysis station=%s group_by=%s force_refresh_on_empty=%s",
        station,
        group_by.value,
        force_refresh_on_empty,
    )
    payload = call_service_or_http(
        lambda: service.get_timeframe_analytics(
            station=station,
            start_local=start_local,
            end_local=end_local,
            group_by=group_by,
            timezone_input=location,
            compare_start_local=compare_start_local,
            compare_end_local=compare_end_local,
            simulation_params=simulation_params,
            force_refresh_on_empty=force_refresh_on_empty,
        ),
        logger=logger,
        endpoint="analysis/timeframes",
        context={"station": station, "start": start_local.isoformat(), "end": end_local.isoformat()},
    )

    payload_model = (
        payload
        if isinstance(payload, TimeframeAnalyticsResponse)
        else TimeframeAnalyticsResponse.model_validate(payload)
    )
    latest_utc = None
    if payload_model.buckets:
        latest_utc = to_utc_iso(payload_model.buckets[-1].end_local)
    set_compliance_headers(response, latest_observation_utc=latest_utc)
    logger.info(
        "Timeframe analysis completed station=%s buckets=%d group_by=%s",
        station,
        len(payload_model.buckets),
        payload_model.group_by.value,
    )
    return payload_model
