from __future__ import annotations

import logging
from datetime import datetime, timedelta
from statistics import fmean
from zoneinfo import ZoneInfo

from app.core.exceptions import AppValidationError
from app.models import (
    AnalysisBootstrapResponse,
    FeasibilitySnapshotResponse,
    LatestStationSnapshot,
    MeasurementType,
    OutputMeasurement,
    SourceMeasurement,
    Station,
    StationFeasibilitySeries,
    StationFeasibilitySummary,
    StationProfile,
    StationRole,
    TimeAggregation,
)
from app.services.antarctic.constants import STATION_LOCAL_TZ, UTC
from app.services.antarctic.math_utils import (
    avg,
    dominant_angle_deg,
    expected_points,
    percentile,
    point_hours,
    wind_toward_direction_deg,
)
from app.services.antarctic.windows import split_month_windows_covering_range

logger = logging.getLogger(__name__)


class AnalysisMixin:
    repository: object
    aemet_client: object
    settings: object

    def get_analysis_bootstrap(self) -> AnalysisBootstrapResponse:
        checked_at_utc = datetime.now(UTC)
        map_station_ids = self._map_overlay_station_ids()
        self._warm_cache_for_station_ids(map_station_ids, checked_at_utc)

        profiles = self.get_station_profiles()
        selectable_station_ids = sorted([profile.station_id for profile in profiles if profile.is_selectable])
        latest_observation_by_station: dict[str, datetime | None] = {}
        suggested_start_by_station: dict[str, datetime | None] = {}
        latest_snapshots: list[LatestStationSnapshot] = []
        profile_by_station = {profile.station_id: profile for profile in profiles}

        for profile in profiles:
            latest_utc = self.repository.get_latest_measurement_timestamp(profile.station_id)
            latest_observation_by_station[profile.station_id] = latest_utc
            suggested_start_by_station[profile.station_id] = latest_utc - timedelta(days=730) if latest_utc is not None else None

        for station_id in map_station_ids:
            latest_row = self.repository.get_latest_measurement(station_id)
            profile = profile_by_station.get(station_id)
            if latest_row is None or profile is None:
                continue
            latest_snapshots.append(self._to_latest_snapshot(station_id, profile, latest_row))

        note = (
            "Warm cache loaded for Antarctic meteorological stations (89064, 89070). "
            "Selection is restricted to meteorological stations 89064 and 89070. "
            "Supplemental 89064R and archive 89064RA are preserved in catalog metadata only."
        )

        return AnalysisBootstrapResponse(
            checked_at_utc=checked_at_utc,
            note=note,
            stations=profiles,
            selectableStationIds=selectable_station_ids,
            mapStationIds=map_station_ids,
            latestObservationByStation=latest_observation_by_station,
            suggestedStartByStation=suggested_start_by_station,
            latestSnapshots=latest_snapshots,
        )

    def get_feasibility_snapshot(
        self,
        station: str | Station,
        start_local: datetime,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
        timezone_input: str | None = None,
    ) -> FeasibilitySnapshotResponse:
        checked_at_utc = datetime.now(UTC)
        selected_station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(selected_station_id)
        self._assert_station_selectable(selected_station_id)

        map_station_ids = self._map_overlay_station_ids()
        self._warm_cache_for_station_ids(map_station_ids, checked_at_utc)
        latest = self.get_latest_availability(selected_station_id)
        if latest.newest_observation_utc is None:
            raise AppValidationError(
                f"No recent observations are available for station '{selected_station_id}'. "
                "Try another station or wait for new AEMET updates."
            )

        latest_selected_local = latest.newest_observation_utc.astimezone(start_local.tzinfo or UTC)
        one_month_limit_local = start_local + timedelta(days=30)
        if latest_selected_local <= one_month_limit_local:
            effective_end_local = latest_selected_local
            effective_end_reason = "limited_by_latest_available_observation"
        else:
            effective_end_local = one_month_limit_local
            effective_end_reason = "limited_by_one_month_rule"

        if start_local >= effective_end_local:
            raise AppValidationError(
                "Start datetime must be earlier than the effective end datetime "
                "(latest available observation and one-month rule are both enforced)."
            )

        profiles = self.get_station_profiles()
        profile_by_station = {profile.station_id: profile for profile in profiles}
        output_tz = start_local.tzinfo or UTC
        if timezone_input:
            try:
                output_tz = ZoneInfo(timezone_input)
            except Exception:
                output_tz = start_local.tzinfo or UTC
        series: list[StationFeasibilitySeries] = []
        for station_id in map_station_ids:
            rows = self.get_data(
                station=station_id,
                start_local=start_local,
                end_local=effective_end_local,
                aggregation=aggregation,
                selected_types=selected_types,
                output_tz=output_tz,
            )
            profile = profile_by_station.get(station_id)
            station_name = profile.station_name if profile is not None else station_id
            role = profile.role if profile is not None else StationRole.SUPPLEMENTAL
            latest_utc = self.repository.get_latest_measurement_timestamp(station_id)
            summary = self._build_summary(
                station_id=station_id,
                station_name=station_name,
                role=role,
                rows=rows,
                start_local=start_local,
                end_local=effective_end_local,
                aggregation=aggregation,
                latest_observation_utc=latest_utc,
            )
            series.append(
                StationFeasibilitySeries(
                    stationId=station_id,
                    stationName=station_name,
                    role=role,
                    summary=summary,
                    data=rows,
                )
            )

        selected_profile = profile_by_station.get(selected_station_id)
        selected_station_name = selected_profile.station_name if selected_profile is not None else selected_station_id
        notes = [
            "The query end is automatically capped by the earliest constraint between one month from start and the latest selected-station observation.",
            "Map overlay and automatic warm cache include only meteorological IDs: 89064, 89070.",
            "89064R (supplemental) and 89064RA (archive) are excluded from automatic fetch to minimize API traffic.",
            "All fetched windows are persisted in SQLite and reused to reduce upstream calls and API-limit risk.",
        ]

        return FeasibilitySnapshotResponse(
            checked_at_utc=checked_at_utc,
            selectedStationId=selected_station_id,
            selectedStationName=selected_station_name,
            requestedStart=start_local,
            effectiveEnd=effective_end_local,
            effectiveEndReason=effective_end_reason,
            timezone_input=timezone_input or start_local.tzname() or "UTC",
            timezone_output=getattr(output_tz, "key", str(output_tz)),
            aggregation=aggregation,
            mapStationIds=map_station_ids,
            notes=notes,
            stations=series,
        )

    def _warm_cache_for_station_ids(self, station_ids: list[str], checked_at_utc: datetime) -> None:
        if not station_ids:
            return
        probe_window_hours = 720
        start_utc = checked_at_utc - timedelta(hours=probe_window_hours)
        month_windows = split_month_windows_covering_range(start_utc, checked_at_utc)

        for station_id in station_ids:
            self._assert_station_supported_by_antarctic_endpoint(station_id)
            for window_start_utc, window_end_utc in month_windows:
                has_cached = self.repository.has_cached_fetch_window(
                    station_id=station_id,
                    start_utc=window_start_utc,
                    end_utc=window_end_utc,
                )
                if has_cached:
                    continue
                try:
                    rows = self.aemet_client.fetch_station_data(window_start_utc, window_end_utc, station_id)
                except RuntimeError as exc:
                    logger.warning(
                        "Warm-cache fetch failed for station %s month window (%s to %s): %s",
                        station_id,
                        window_start_utc.isoformat(),
                        window_end_utc.isoformat(),
                        str(exc),
                    )
                    continue
                self.repository.upsert_measurements(
                    station_id=station_id,
                    rows=rows,
                    start_utc=window_start_utc,
                    end_utc=window_end_utc,
                )

    def _build_summary(
        self,
        station_id: str,
        station_name: str,
        role: StationRole,
        rows: list[OutputMeasurement],
        start_local: datetime,
        end_local: datetime,
        aggregation: TimeAggregation,
        latest_observation_utc: datetime | None,
    ) -> StationFeasibilitySummary:
        speeds = [row.speed_mps for row in rows if row.speed_mps is not None]
        temperatures = [row.temperature_c for row in rows if row.temperature_c is not None]
        pressures = [row.pressure_hpa for row in rows if row.pressure_hpa is not None]
        directions_toward = [
            wind_toward_direction_deg(row.direction_deg)
            for row in rows
            if row.direction_deg is not None
        ]
        if aggregation in {TimeAggregation.DAILY, TimeAggregation.MONTHLY}:
            coverage_start = start_local.astimezone(STATION_LOCAL_TZ)
            coverage_end = end_local.astimezone(STATION_LOCAL_TZ)
        else:
            coverage_start = start_local
            coverage_end = end_local
        points = expected_points(coverage_start, coverage_end, aggregation)
        coverage_ratio = round(min(1.0, len(rows) / float(points)), 3) if points > 0 else None
        per_point_hours = point_hours(aggregation)

        wind_power_density = None
        if rows:
            values: list[float] = []
            for row in rows:
                if row.speed_mps is None:
                    continue
                air_density = 1.225
                if row.pressure_hpa is not None and row.temperature_c is not None:
                    kelvin = row.temperature_c + 273.15
                    if kelvin > 0:
                        air_density = (row.pressure_hpa * 100.0) / (287.05 * kelvin)
                values.append(0.5 * air_density * (row.speed_mps ** 3))
            if values:
                wind_power_density = round(fmean(values), 3)

        return StationFeasibilitySummary(
            stationId=station_id,
            stationName=station_name,
            role=role,
            dataPoints=len(rows),
            coverageRatio=coverage_ratio,
            avgSpeed=avg(speeds),
            p90Speed=percentile(speeds, 0.9),
            maxSpeed=round(max(speeds), 3) if speeds else None,
            hoursAbove3mps=round(sum(1 for value in speeds if value >= 3.0) * per_point_hours, 3) if speeds else None,
            hoursAbove5mps=round(sum(1 for value in speeds if value >= 5.0) * per_point_hours, 3) if speeds else None,
            avgTemperature=avg(temperatures),
            minTemperature=round(min(temperatures), 3) if temperatures else None,
            maxTemperature=round(max(temperatures), 3) if temperatures else None,
            avgPressure=avg(pressures),
            prevailingDirection=dominant_angle_deg(directions_toward),
            estimatedWindPowerDensity=wind_power_density,
            latestObservationUtc=latest_observation_utc,
        )

    def _to_latest_snapshot(
        self,
        station_id: str,
        profile: StationProfile,
        row: SourceMeasurement,
    ) -> LatestStationSnapshot:
        return LatestStationSnapshot(
            stationId=station_id,
            stationName=profile.station_name,
            role=profile.role,
            datetime=row.measured_at_utc.astimezone(STATION_LOCAL_TZ),
            speed=row.speed_mps,
            direction=row.direction_deg,
            temperature=row.temperature_c,
            pressure=row.pressure_hpa,
            latitude=row.latitude,
            longitude=row.longitude,
            altitude=row.altitude_m,
        )
