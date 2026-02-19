from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from enum import Enum

from app.models.measurement import OutputMeasurement, TimeAggregation
from app.models.station import StationProfile, StationRole


class LatestStationSnapshot(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    role: StationRole
    datetime_cet: datetime = Field(alias="datetime")
    speed_mps: float | None = Field(alias="speed")
    direction_deg: float | None = Field(alias="direction")
    temperature_c: float | None = Field(alias="temperature")
    pressure_hpa: float | None = Field(alias="pressure")
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = Field(default=None, alias="altitude")


class StationFeasibilitySummary(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    role: StationRole
    data_points: int = Field(alias="dataPoints")
    coverage_ratio: float | None = Field(alias="coverageRatio")
    avg_speed_mps: float | None = Field(alias="avgSpeed")
    p90_speed_mps: float | None = Field(alias="p90Speed")
    max_speed_mps: float | None = Field(alias="maxSpeed")
    hours_above_3mps: float | None = Field(alias="hoursAbove3mps")
    hours_above_5mps: float | None = Field(alias="hoursAbove5mps")
    avg_temperature_c: float | None = Field(alias="avgTemperature")
    min_temperature_c: float | None = Field(alias="minTemperature")
    max_temperature_c: float | None = Field(alias="maxTemperature")
    avg_pressure_hpa: float | None = Field(alias="avgPressure")
    prevailing_direction_deg: float | None = Field(alias="prevailingDirection")
    estimated_wind_power_density_wm2: float | None = Field(alias="estimatedWindPowerDensity")
    latest_observation_utc: datetime | None = Field(alias="latestObservationUtc")


class StationFeasibilitySeries(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    role: StationRole
    summary: StationFeasibilitySummary
    data: list[OutputMeasurement]


class AnalysisBootstrapResponse(BaseModel):
    checked_at_utc: datetime
    note: str
    stations: list[StationProfile]
    selectable_station_ids: list[str] = Field(alias="selectableStationIds")
    map_station_ids: list[str] = Field(alias="mapStationIds")
    latest_observation_by_station: dict[str, datetime | None] = Field(alias="latestObservationByStation")
    suggested_start_by_station: dict[str, datetime | None] = Field(alias="suggestedStartByStation")
    latest_snapshots: list[LatestStationSnapshot] = Field(alias="latestSnapshots")


class FeasibilitySnapshotResponse(BaseModel):
    checked_at_utc: datetime
    selected_station_id: str = Field(alias="selectedStationId")
    selected_station_name: str = Field(alias="selectedStationName")
    requested_start_local: datetime = Field(alias="requestedStart")
    effective_end_local: datetime = Field(alias="effectiveEnd")
    effective_end_reason: str = Field(alias="effectiveEndReason")
    timezone_input: str
    timezone_output: str
    aggregation: TimeAggregation
    map_station_ids: list[str] = Field(alias="mapStationIds")
    notes: list[str]
    stations: list[StationFeasibilitySeries]


class PlaybackStep(str, Enum):
    TEN_MINUTES = "10m"
    HOURLY = "1h"
    THREE_HOURLY = "3h"
    DAILY = "1d"


class QueryJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class FrameQuality(str, Enum):
    OBSERVED = "observed"
    AGGREGATED = "aggregated"
    GAP_FILLED = "gap_filled"


class TimeframeGroupBy(str, Enum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"


class WindFarmSimulationParams(BaseModel):
    turbine_count: int = Field(alias="turbineCount", ge=1, le=500)
    rated_power_kw: float = Field(alias="ratedPowerKw", gt=0)
    cut_in_speed_mps: float = Field(alias="cutInSpeedMps", ge=0)
    rated_speed_mps: float = Field(alias="ratedSpeedMps", gt=0)
    cut_out_speed_mps: float = Field(alias="cutOutSpeedMps", gt=0)
    reference_air_density_kgm3: float = Field(alias="referenceAirDensityKgM3", default=1.225, gt=0)
    min_operating_temp_c: float | None = Field(alias="minOperatingTempC", default=-40.0)
    max_operating_temp_c: float | None = Field(alias="maxOperatingTempC", default=45.0)
    min_operating_pressure_hpa: float | None = Field(alias="minOperatingPressureHpa", default=850.0)
    max_operating_pressure_hpa: float | None = Field(alias="maxOperatingPressureHpa", default=1085.0)

    @model_validator(mode="after")
    def _validate_envelope(self) -> "WindFarmSimulationParams":
        if self.cut_in_speed_mps >= self.rated_speed_mps:
            raise ValueError("cutInSpeedMps must be lower than ratedSpeedMps.")
        if self.rated_speed_mps >= self.cut_out_speed_mps:
            raise ValueError("ratedSpeedMps must be lower than cutOutSpeedMps.")
        if (
            self.min_operating_temp_c is not None
            and self.max_operating_temp_c is not None
            and self.min_operating_temp_c >= self.max_operating_temp_c
        ):
            raise ValueError("minOperatingTempC must be lower than maxOperatingTempC.")
        if (
            self.min_operating_pressure_hpa is not None
            and self.max_operating_pressure_hpa is not None
            and self.min_operating_pressure_hpa >= self.max_operating_pressure_hpa
        ):
            raise ValueError("minOperatingPressureHpa must be lower than maxOperatingPressureHpa.")
        return self


class QueryJobCreateRequest(BaseModel):
    station: str
    start: datetime
    location: str = "UTC"
    history_start: datetime | None = Field(default=None, alias="historyStart")
    aggregation: TimeAggregation = TimeAggregation.NONE
    types: list[str] = Field(default_factory=list)
    playback_step: PlaybackStep = Field(default=PlaybackStep.HOURLY, alias="playbackStep")


class QueryJobCreatedResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: QueryJobStatus
    station_id: str = Field(alias="stationId")
    requested_start_utc: datetime = Field(alias="requestedStartUtc")
    effective_end_utc: datetime = Field(alias="effectiveEndUtc")
    history_start_utc: datetime = Field(alias="historyStartUtc")
    total_windows: int = Field(alias="totalWindows")
    cached_windows: int = Field(alias="cachedWindows")
    missing_windows: int = Field(alias="missingWindows")
    total_api_calls_planned: int = Field(alias="totalApiCallsPlanned")
    completed_api_calls: int = Field(alias="completedApiCalls")
    frames_planned: int = Field(alias="framesPlanned")
    frames_ready: int = Field(alias="framesReady")
    playback_ready: bool = Field(alias="playbackReady")
    message: str


class QueryJobStatusResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: QueryJobStatus
    station_id: str = Field(alias="stationId")
    total_windows: int = Field(alias="totalWindows")
    cached_windows: int = Field(alias="cachedWindows")
    missing_windows: int = Field(alias="missingWindows")
    completed_windows: int = Field(alias="completedWindows")
    total_api_calls_planned: int = Field(alias="totalApiCallsPlanned")
    completed_api_calls: int = Field(alias="completedApiCalls")
    frames_planned: int = Field(alias="framesPlanned")
    frames_ready: int = Field(alias="framesReady")
    playback_ready: bool = Field(alias="playbackReady")
    percent: float
    message: str
    error_detail: str | None = Field(default=None, alias="errorDetail")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")


class WindRoseBin(BaseModel):
    sector: str
    speed_buckets: dict[str, int] = Field(alias="speedBuckets")
    total_count: int = Field(alias="totalCount")


class WindRoseSummary(BaseModel):
    bins: list[WindRoseBin]
    dominant_sector: str | None = Field(alias="dominantSector")
    directional_concentration: float | None = Field(alias="directionalConcentration")
    calm_share: float | None = Field(alias="calmShare")


class PlaybackFrame(BaseModel):
    datetime_local: datetime = Field(alias="datetime")
    speed_mps: float | None = Field(alias="speed")
    direction_deg: float | None = Field(alias="direction")
    temperature_c: float | None = Field(alias="temperature")
    pressure_hpa: float | None = Field(alias="pressure")
    quality_flag: FrameQuality = Field(alias="qualityFlag")
    dx: float | None = None
    dy: float | None = None


class PlaybackResponse(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    requested_step: PlaybackStep = Field(alias="requestedStep")
    effective_step: PlaybackStep = Field(alias="effectiveStep")
    timezone_input: str
    timezone_output: str
    start_local: datetime = Field(alias="start")
    end_local: datetime = Field(alias="end")
    frames: list[PlaybackFrame]
    frames_planned: int = Field(alias="framesPlanned")
    frames_ready: int = Field(alias="framesReady")
    quality_counts: dict[str, int] = Field(alias="qualityCounts")
    wind_rose: WindRoseSummary = Field(alias="windRose")


class TimeframeBucket(BaseModel):
    label: str
    start_local: datetime = Field(alias="start")
    end_local: datetime = Field(alias="end")
    data_points: int = Field(alias="dataPoints")
    avg_speed_mps: float | None = Field(alias="avgSpeed")
    min_speed_mps: float | None = Field(default=None, alias="minSpeed")
    max_speed_mps: float | None = Field(default=None, alias="maxSpeed")
    p90_speed_mps: float | None = Field(alias="p90Speed")
    hours_above_3mps: float | None = Field(alias="hoursAbove3mps")
    hours_above_5mps: float | None = Field(alias="hoursAbove5mps")
    speed_variability: float | None = Field(alias="speedVariability")
    dominant_direction_deg: float | None = Field(alias="dominantDirection")
    avg_temperature_c: float | None = Field(default=None, alias="avgTemperature")
    min_temperature_c: float | None = Field(alias="minTemperature")
    max_temperature_c: float | None = Field(alias="maxTemperature")
    avg_pressure_hpa: float | None = Field(default=None, alias="avgPressure")
    estimated_generation_mwh: float | None = Field(alias="estimatedGenerationMwh")


class ComparisonDelta(BaseModel):
    metric: str
    baseline: float | None
    current: float | None
    absolute_delta: float | None = Field(alias="absoluteDelta")
    percent_delta: float | None = Field(alias="percentDelta")


class TimeframeAnalyticsResponse(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    group_by: TimeframeGroupBy = Field(alias="groupBy")
    timezone_input: str
    timezone_output: str
    requested_start_local: datetime = Field(alias="requestedStart")
    requested_end_local: datetime = Field(alias="requestedEnd")
    buckets: list[TimeframeBucket]
    wind_rose: WindRoseSummary = Field(alias="windRose")
    comparison: list[ComparisonDelta]
