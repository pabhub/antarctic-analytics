from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, tzinfo

from app.models import (
    LatestAvailabilityResponse,
    MeasurementType,
    OutputMeasurement,
    SourceMeasurement,
    Station,
    TimeAggregation,
)
from app.services.antarctic.constants import MADRID_TZ, STATION_LOCAL_TZ, UTC
from app.services.antarctic.math_utils import avg, avg_angle_deg
from app.services.antarctic.windows import next_month_start, previous_month_start, split_month_windows_covering_range, start_of_month

logger = logging.getLogger(__name__)


class DataMixin:
    repository: object
    aemet_client: object
    _LATEST_AVAILABILITY_MAX_LOOKBACK_DAYS = 720

    def get_data(
        self,
        station: str | Station,
        start_local: datetime,
        end_local: datetime,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
        output_tz: tzinfo = MADRID_TZ,
    ) -> list[OutputMeasurement]:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        start_utc = start_local.astimezone(UTC)
        end_utc = end_local.astimezone(UTC)
        if start_utc >= end_utc:
            raise ValueError("Start datetime must be before end datetime")

        upstream_windows = self._split_upstream_windows(start_utc, end_utc)
        for index, (window_start_utc, window_end_utc) in enumerate(upstream_windows, start=1):
            has_cached_window = self.repository.has_cached_fetch_window(
                station_id=station_id,
                start_utc=window_start_utc,
                end_utc=window_end_utc,
            )
            if has_cached_window:
                should_refresh_direction = self._needs_direction_recovery_refresh(
                    station_id=station_id,
                    start_utc=window_start_utc,
                    end_utc=window_end_utc,
                    selected_types=selected_types,
                )
                if should_refresh_direction:
                    logger.info(
                        "Refreshing cached window %s/%s for station %s to recover wind direction values with updated parser (%s to %s)",
                        index,
                        len(upstream_windows),
                        station_id,
                        window_start_utc.isoformat(),
                        window_end_utc.isoformat(),
                    )
                else:
                    logger.info(
                        "Using cached dataset for station %s and window %s/%s (%s to %s)",
                        station_id,
                        index,
                        len(upstream_windows),
                        window_start_utc.isoformat(),
                        window_end_utc.isoformat(),
                    )
                    continue

            logger.info(
                "Cache miss for station %s; fetching window %s/%s from AEMET (%s to %s)",
                station_id,
                index,
                len(upstream_windows),
                window_start_utc.isoformat(),
                window_end_utc.isoformat(),
            )
            remote_rows = self.aemet_client.fetch_station_data(window_start_utc, window_end_utc, station_id)
            self.repository.upsert_measurements(
                station_id=station_id,
                rows=remote_rows,
                start_utc=window_start_utc,
                end_utc=window_end_utc,
            )

        rows = self.repository.get_measurements(station_id, start_utc, end_utc)
        transformed = self._aggregate(rows, aggregation)
        return [self._to_output(row, selected_types, output_tz=output_tz) for row in transformed]

    def refresh_data_range(
        self,
        station: str | Station,
        start_local: datetime,
        end_local: datetime,
    ) -> None:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        start_utc = start_local.astimezone(UTC)
        end_utc = end_local.astimezone(UTC)
        if start_utc >= end_utc:
            raise ValueError("Start datetime must be before end datetime")

        upstream_windows = self._split_upstream_windows(start_utc, end_utc)
        for index, (window_start_utc, window_end_utc) in enumerate(upstream_windows, start=1):
            logger.info(
                "Forced refresh for station %s window %s/%s (%s to %s)",
                station_id,
                index,
                len(upstream_windows),
                window_start_utc.isoformat(),
                window_end_utc.isoformat(),
            )
            remote_rows = self.aemet_client.fetch_station_data(window_start_utc, window_end_utc, station_id)
            self.repository.upsert_measurements(
                station_id=station_id,
                rows=remote_rows,
                start_utc=window_start_utc,
                end_utc=window_end_utc,
            )

    def _needs_direction_recovery_refresh(
        self,
        station_id: str,
        start_utc: datetime,
        end_utc: datetime,
        selected_types: list[MeasurementType],
    ) -> bool:
        include_all = not selected_types
        if not include_all and MeasurementType.DIRECTION not in selected_types:
            return False

        selectable_method = getattr(self, "_selectable_meteo_station_ids", None)
        if callable(selectable_method):
            selectable_ids = selectable_method()
            if station_id not in selectable_ids:
                return False

        is_direction_checked = getattr(self.repository, "is_fetch_window_direction_checked", None)
        if callable(is_direction_checked) and is_direction_checked(station_id, start_utc, end_utc):
            return False
        mark_direction_checked = getattr(self.repository, "mark_fetch_window_direction_checked", None)

        rows = self.repository.get_measurements(station_id, start_utc, end_utc)
        if not rows:
            if callable(mark_direction_checked):
                mark_direction_checked(station_id, start_utc, end_utc)
            return False
        rows_with_speed = [row for row in rows if row.speed_mps is not None]
        if not rows_with_speed:
            if callable(mark_direction_checked):
                mark_direction_checked(station_id, start_utc, end_utc)
            return False
        has_direction = any(row.direction_deg is not None for row in rows_with_speed)
        if has_direction:
            if callable(mark_direction_checked):
                mark_direction_checked(station_id, start_utc, end_utc)
            return False
        return True

    def get_latest_availability(self, station: str | Station) -> LatestAvailabilityResponse:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        station_label = station.value if isinstance(station, Station) else station
        checked_at_utc = datetime.now(UTC)
        cached_newest = self.repository.get_latest_measurement_timestamp(station_id)
        if cached_newest is not None:
            suggested_end = cached_newest
            suggested_start = cached_newest - timedelta(hours=24)
            suggested_aggregation = (
                TimeAggregation.NONE if (suggested_end - suggested_start) <= timedelta(days=2) else TimeAggregation.HOURLY
            )
            return LatestAvailabilityResponse(
                station=station_label,
                checked_at_utc=checked_at_utc,
                newest_observation_utc=cached_newest,
                suggested_start_utc=suggested_start,
                suggested_end_utc=suggested_end,
                probe_window_hours=0,
                suggested_aggregation=suggested_aggregation,
                note="Suggested window derived from cached observations.",
            )

        lookback_limit_utc = checked_at_utc - timedelta(days=self._LATEST_AVAILABILITY_MAX_LOOKBACK_DAYS)
        lookback_month_start_utc = start_of_month(lookback_limit_utc)
        probe_month_start_utc = start_of_month(checked_at_utc)

        while probe_month_start_utc >= lookback_month_start_utc:
            start_utc = probe_month_start_utc
            end_utc = next_month_start(probe_month_start_utc)
            has_cached_window = self.repository.has_cached_fetch_window(
                station_id=station_id,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            if has_cached_window:
                rows = self.repository.get_measurements(station_id, start_utc, end_utc)
            else:
                rows = self.aemet_client.fetch_station_data(start_utc, end_utc, station_id)
                self.repository.upsert_measurements(
                    station_id=station_id,
                    rows=rows,
                    start_utc=start_utc,
                    end_utc=end_utc,
                )

            if rows:
                newest = max(row.measured_at_utc for row in rows)
                suggested_end = newest
                suggested_start = max(start_utc, newest - timedelta(hours=24))
                suggested_aggregation = (
                    TimeAggregation.NONE if (suggested_end - suggested_start) <= timedelta(days=2) else TimeAggregation.HOURLY
                )
                scanned_hours = int(round((checked_at_utc - start_utc).total_seconds() / 3600))
                source = "cached observations" if has_cached_window else "AEMET backscan"
                return LatestAvailabilityResponse(
                    station=station_label,
                    checked_at_utc=checked_at_utc,
                    newest_observation_utc=newest,
                    suggested_start_utc=suggested_start,
                    suggested_end_utc=suggested_end,
                    probe_window_hours=scanned_hours,
                    suggested_aggregation=suggested_aggregation,
                    note=f"Suggested window targets latest available observations from {source}.",
                )

            probe_month_start_utc = previous_month_start(probe_month_start_utc)

        return LatestAvailabilityResponse(
            station=station_label,
            checked_at_utc=checked_at_utc,
            note=f"No observations were found in the last {self._LATEST_AVAILABILITY_MAX_LOOKBACK_DAYS} days for this station.",
        )

    def _aggregate(self, rows: list[SourceMeasurement], aggregation: TimeAggregation) -> list[SourceMeasurement]:
        if aggregation == TimeAggregation.NONE:
            return rows

        grouped: dict[datetime, list[SourceMeasurement]] = defaultdict(list)
        for row in rows:
            local_dt = row.measured_at_utc.astimezone(STATION_LOCAL_TZ)
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
                    temperature_c=avg([item.temperature_c for item in items]),
                    pressure_hpa=avg([item.pressure_hpa for item in items]),
                    speed_mps=avg([item.speed_mps for item in items]),
                    direction_deg=avg_angle_deg([item.direction_deg for item in items]),
                    latitude=items[0].latitude,
                    longitude=items[0].longitude,
                    altitude_m=items[0].altitude_m,
                )
            )
        return aggregated

    @staticmethod
    def _split_upstream_windows(
        start_utc: datetime,
        end_utc: datetime,
        max_days: int = 30,
    ) -> list[tuple[datetime, datetime]]:
        _ = max_days
        return split_month_windows_covering_range(start_utc, end_utc)

    @staticmethod
    def _to_output(
        row: SourceMeasurement,
        selected_types: list[MeasurementType],
        output_tz: tzinfo,
    ) -> OutputMeasurement:
        local_dt = row.measured_at_utc.astimezone(output_tz)
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
