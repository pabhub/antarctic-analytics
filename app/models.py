from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Station(str, Enum):
    GABRIEL_DE_CASTILLA = "gabriel-de-castilla"
    JUAN_CARLOS_I = "juan-carlos-i"


class TimeAggregation(str, Enum):
    NONE = "none"
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class MeasurementType(str, Enum):
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    SPEED = "speed"
    DIRECTION = "direction"


class SourceMeasurement(BaseModel):
    station_name: str
    measured_at_utc: datetime
    temperature_c: float | None = None
    pressure_hpa: float | None = None
    speed_mps: float | None = None
    direction_deg: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None


class OutputMeasurement(BaseModel):
    station_name: str = Field(alias="stationName")
    datetime_cet: datetime = Field(alias="datetime")
    temperature_c: float | None = Field(alias="temperature")
    pressure_hpa: float | None = Field(alias="pressure")
    speed_mps: float | None = Field(alias="speed")
    direction_deg: float | None = Field(default=None, alias="direction")
    latitude: float | None = Field(default=None, alias="latitude")
    longitude: float | None = Field(default=None, alias="longitude")
    altitude_m: float | None = Field(default=None, alias="altitude")


class MeasurementResponse(BaseModel):
    station: Station
    aggregation: TimeAggregation
    selected_types: list[MeasurementType]
    timezone_input: str
    timezone_output: Literal["Europe/Madrid"] = "Europe/Madrid"
    data: list[OutputMeasurement]


class AvailableDataResponse(BaseModel):
    source_endpoint: str
    currently_exposed_fields: dict[str, str]
    additional_fields_often_available: dict[str, str]


class LatestAvailabilityResponse(BaseModel):
    station: Station
    checked_at_utc: datetime
    newest_observation_utc: datetime | None = None
    suggested_start_utc: datetime | None = None
    suggested_end_utc: datetime | None = None
    probe_window_hours: int | None = None
    suggested_aggregation: TimeAggregation | None = None
    note: str


class StationCatalogItem(BaseModel):
    station_id: str = Field(alias="stationId")
    station_name: str = Field(alias="stationName")
    province: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = Field(default=None, alias="altitude")


class StationCatalogResponse(BaseModel):
    checked_at_utc: datetime
    cached_until_utc: datetime
    cache_hit: bool
    data: list[StationCatalogItem]
