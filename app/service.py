from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin
from statistics import fmean
from zoneinfo import ZoneInfo

from app.aemet_client import AemetClient
from app.database import SQLiteRepository
from app.models import MeasurementType, OutputMeasurement, SourceMeasurement, Station, TimeAggregation
from app.settings import Settings

MADRID_TZ = ZoneInfo("Europe/Madrid")
UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)

class AntartidaService:
    def __init__(self, settings: Settings, repository: SQLiteRepository, aemet_client: AemetClient) -> None:
        self.settings = settings
        self.repository = repository
        self.aemet_client = aemet_client

    def station_id_for(self, station: Station) -> str:
        return self.settings.gabriel_station_id if station == Station.GABRIEL_DE_CASTILLA else self.settings.juan_station_id

    def get_data(
        self,
        station: Station,
        start_local: datetime,
        end_local: datetime,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
    ) -> list[OutputMeasurement]:
        station_id = self.station_id_for(station)
        start_utc = start_local.astimezone(UTC)
        end_utc = end_local.astimezone(UTC)

        min_fetched_at_utc = datetime.utcnow() - timedelta(seconds=self.settings.cache_freshness_seconds)
        has_fresh_cache = self.repository.has_fresh_fetch_window(
            station_id=station_id,
            start_utc=start_utc,
            end_utc=end_utc,
            min_fetched_at_utc=min_fetched_at_utc,
        )

        if has_fresh_cache:
            logger.info("Using cached dataset for station %s and requested time window", station_id)
        else:
            logger.info("Refreshing cache from AEMET for station %s and requested time window", station_id)
            remote_rows = self.aemet_client.fetch_station_data(start_utc, end_utc, station_id)
            self.repository.upsert_measurements(
                station_id=station_id,
                rows=remote_rows,
                start_utc=start_utc,
                end_utc=end_utc,
            )

        rows = self.repository.get_measurements(station_id, start_utc, end_utc)
        transformed = self._aggregate(rows, aggregation)
        return [self._to_output(row, selected_types) for row in transformed]

    def _aggregate(self, rows: list[SourceMeasurement], aggregation: TimeAggregation) -> list[SourceMeasurement]:
        if aggregation == TimeAggregation.NONE:
            return rows

        grouped: dict[datetime, list[SourceMeasurement]] = defaultdict(list)
        for row in rows:
            local_dt = row.measured_at_utc.astimezone(MADRID_TZ)
            if aggregation == TimeAggregation.HOURLY:
                key = local_dt.replace(minute=0, second=0, microsecond=0)
            elif aggregation == TimeAggregation.DAILY:
                key = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                key = local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            grouped[key].append(row)

        aggregated: list[SourceMeasurement] = []
        for key, items in sorted(grouped.items(), key=lambda pair: pair[0]):
            aggregated.append(
                SourceMeasurement(
                    station_name=items[0].station_name,
                    measured_at_utc=key.astimezone(UTC),
                    temperature_c=self._avg([item.temperature_c for item in items]),
                    pressure_hpa=self._avg([item.pressure_hpa for item in items]),
                    speed_mps=self._avg([item.speed_mps for item in items]),
                    direction_deg=self._avg_angle_deg([item.direction_deg for item in items]),
                    latitude=items[0].latitude,
                    longitude=items[0].longitude,
                    altitude_m=items[0].altitude_m,
                )
            )
        return aggregated

    @staticmethod
    def _avg(values: list[float | None]) -> float | None:
        real = [v for v in values if v is not None]
        return round(fmean(real), 3) if real else None

    @staticmethod
    def _avg_angle_deg(values: list[float | None]) -> float | None:
        angles = [v for v in values if v is not None]
        if not angles:
            return None
        x = sum(cos(radians(a)) for a in angles)
        y = sum(sin(radians(a)) for a in angles)
        if x == 0 and y == 0:
            return None
        angle = atan2(y, x)
        deg = (angle * 180.0 / 3.141592653589793) % 360
        return round(deg, 3)

    @staticmethod
    def _to_output(row: SourceMeasurement, selected_types: list[MeasurementType]) -> OutputMeasurement:
        local_dt = row.measured_at_utc.astimezone(MADRID_TZ)
        include_all = not selected_types
        include_temperature = include_all or MeasurementType.TEMPERATURE in selected_types
        include_pressure = include_all or MeasurementType.PRESSURE in selected_types
        include_speed = include_all or MeasurementType.SPEED in selected_types
        include_direction = include_all or MeasurementType.DIRECTION in selected_types

        return OutputMeasurement(
            stationName=row.station_name,
            datetime=local_dt,
            temperature=row.temperature_c if include_temperature else None,
            pressure=row.pressure_hpa if include_pressure else None,
            speed=row.speed_mps if include_speed else None,
            direction=row.direction_deg if include_direction else None,
            latitude=row.latitude,
            longitude=row.longitude,
            altitude=row.altitude_m,
        )
