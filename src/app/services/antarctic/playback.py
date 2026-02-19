from __future__ import annotations

import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from math import cos, radians, sin, sqrt
from statistics import pvariance
from typing import Any
from zoneinfo import ZoneInfo

from app.core.exceptions import AppValidationError
from app.models import (
    ComparisonDelta,
    FeasibilitySnapshotResponse,
    FrameQuality,
    MeasurementType,
    OutputMeasurement,
    PlaybackFrame,
    PlaybackResponse,
    PlaybackStep,
    QueryJobCreatedResponse,
    QueryJobStatus,
    QueryJobStatusResponse,
    StationFeasibilitySeries,
    StationFeasibilitySummary,
    StationRole,
    TimeAggregation,
    TimeframeAnalyticsResponse,
    TimeframeBucket,
    TimeframeGroupBy,
    WindFarmSimulationParams,
    WindRoseBin,
    WindRoseSummary,
)
from app.services.antarctic.constants import STATION_LOCAL_TZ, UTC
from app.services.antarctic.math_utils import avg, avg_angle_deg, dominant_angle_deg, percentile, wind_toward_direction_deg
from app.services.antarctic.windows import split_month_windows_covering_range


class PlaybackAnalyticsMixin:
    repository: object
    aemet_client: object
    settings: object

    _query_job_lock = threading.Lock()
    _query_job_threads: dict[str, threading.Thread] = {}

    def create_query_job(
        self,
        station: str,
        start_local: datetime,
        timezone_input: str,
        playback_step: PlaybackStep,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
        history_start_local: datetime | None = None,
    ) -> QueryJobCreatedResponse:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        self._assert_station_selectable(station_id)

        latest = self.get_latest_availability(station_id)
        if latest.newest_observation_utc is None:
            raise AppValidationError(
                f"No recent observations are available for station '{station_id}'. Try another station later."
            )

        latest_local = latest.newest_observation_utc.astimezone(start_local.tzinfo or UTC)
        effective_end_local = latest_local
        if start_local >= effective_end_local:
            raise AppValidationError(
                "Start datetime must be earlier than the latest available observation for this station."
            )

        requested_history_start = history_start_local or start_local
        if requested_history_start > start_local:
            requested_history_start = start_local
        history_start_utc = requested_history_start.astimezone(UTC)
        requested_start_utc = start_local.astimezone(UTC)
        effective_end_utc = effective_end_local.astimezone(UTC)

        windows = self._split_windows(history_start_utc, effective_end_utc)
        window_states: list[dict[str, Any]] = []
        cached_windows = 0
        for window_start, window_end in windows:
            has_cached = self.repository.has_cached_fetch_window(
                station_id=station_id,
                start_utc=window_start,
                end_utc=window_end,
            )
            if has_cached:
                cached_windows += 1
            window_states.append(
                {
                    "startUtc": window_start.isoformat(),
                    "endUtc": window_end.isoformat(),
                    "status": "cached" if has_cached else "pending",
                    "apiCallsPlanned": 0 if has_cached else 2,
                    "apiCallsCompleted": 0,
                    "attempts": 0,
                    "errorDetail": None,
                }
            )

        total_windows = len(window_states)
        missing_windows = total_windows - cached_windows
        total_api_calls_planned = missing_windows * 2
        frames_planned = self._frame_count_for_range(start_local, effective_end_local, playback_step)
        frames_planned = max(frames_planned, 1)

        job_id = uuid.uuid4().hex
        status = QueryJobStatus.COMPLETE if missing_windows == 0 else QueryJobStatus.PENDING
        completed_windows = cached_windows if missing_windows else total_windows
        frames_ready = frames_planned if missing_windows == 0 else int((completed_windows / total_windows) * frames_planned)
        payload = {
            "job_id": job_id,
            "station_id": station_id,
            "requested_start_utc": requested_start_utc.isoformat(),
            "effective_end_utc": effective_end_utc.isoformat(),
            "history_start_utc": history_start_utc.isoformat(),
            "timezone_input": timezone_input,
            "aggregation": aggregation.value,
            "selected_types_json": [value.value for value in selected_types],
            "playback_step": playback_step.value,
            "status": status.value,
            "total_windows": total_windows,
            "cached_windows": cached_windows,
            "missing_windows": missing_windows,
            "completed_windows": completed_windows,
            "total_api_calls_planned": total_api_calls_planned,
            "completed_api_calls": 0,
            "frames_planned": frames_planned,
            "frames_ready": frames_ready,
            "playback_ready": missing_windows == 0,
            "message": "Ready from cache." if missing_windows == 0 else "Queued missing windows for fetch.",
            "error_detail": None,
            "windows_json": window_states,
            "created_at_utc": datetime.now(UTC).isoformat(),
        }
        self.repository.upsert_analysis_query_job(payload)

        if missing_windows > 0:
            self._start_query_job_thread(job_id)

        return self._to_query_job_created_response(payload)

    def _start_query_job_thread(self, job_id: str) -> None:
        with self._query_job_lock:
            existing = self._query_job_threads.get(job_id)
            if existing is not None and existing.is_alive():
                return

            worker = threading.Thread(target=self._run_query_job_worker, args=(job_id,), daemon=True)
            self._query_job_threads[job_id] = worker
            worker.start()

    def _run_query_job_worker(self, job_id: str) -> None:
        payload = self.repository.get_analysis_query_job(job_id)
        if payload is None:
            return

        payload["status"] = QueryJobStatus.RUNNING.value
        payload["message"] = "Fetching missing windows from AEMET."
        self.repository.upsert_analysis_query_job(payload)

        station_id = str(payload["station_id"])
        total_windows = int(payload["total_windows"])
        windows: list[dict[str, Any]] = list(payload["windows_json"])  # type: ignore[arg-type]
        if not windows:
            payload["status"] = QueryJobStatus.COMPLETE.value
            payload["playback_ready"] = True
            payload["message"] = "No fetch required."
            self.repository.upsert_analysis_query_job(payload)
            return

        for index, window in enumerate(windows):
            if window.get("status") in {"cached", "complete"}:
                continue

            attempts = int(window.get("attempts", 0))
            max_attempts = 4
            success = False
            while attempts < max_attempts and not success:
                attempts += 1
                window["attempts"] = attempts
                window["status"] = "running"
                windows[index] = window
                payload["windows_json"] = windows
                payload["message"] = f"Fetching window {index + 1}/{total_windows}."
                self.repository.upsert_analysis_query_job(payload)

                start_utc = datetime.fromisoformat(str(window["startUtc"]))
                end_utc = datetime.fromisoformat(str(window["endUtc"]))
                if self.repository.has_cached_fetch_window(station_id, start_utc, end_utc):
                    window["status"] = "cached"
                    window["apiCallsCompleted"] = 0
                    window["errorDetail"] = None
                    success = True
                    continue
                try:
                    rows = self.aemet_client.fetch_station_data(start_utc, end_utc, station_id)
                    self.repository.upsert_measurements(
                        station_id=station_id,
                        rows=rows,
                        start_utc=start_utc,
                        end_utc=end_utc,
                    )
                    window["status"] = "complete"
                    window["apiCallsCompleted"] = int(window.get("apiCallsPlanned", 2))
                    window["errorDetail"] = None
                    success = True
                except RuntimeError as exc:
                    detail = str(exc)
                    window["errorDetail"] = detail
                    is_rate_limited = "429" in detail
                    is_retryable_upstream = self._is_retryable_upstream_error(detail)
                    if (is_rate_limited or is_retryable_upstream) and attempts < max_attempts:
                        window["status"] = "pending"
                        windows[index] = window
                        payload["windows_json"] = windows
                        limiter_seconds = max(float(getattr(self.settings, "aemet_min_request_interval_seconds", 2.0)), 0.5)
                        if is_rate_limited:
                            retry_after_seconds = self._parse_retry_after_seconds(detail)
                            base_backoff = (
                                retry_after_seconds if retry_after_seconds is not None else max(limiter_seconds * 5.0, 5.0)
                            )
                        else:
                            base_backoff = max(limiter_seconds * 2.0, 2.0)
                        sleep_seconds = min(base_backoff * (2 ** (attempts - 1)), 300.0) + random.uniform(0.0, 1.0)
                        if is_rate_limited:
                            payload["message"] = (
                                f"AEMET rate limited on window {index + 1}/{total_windows}. "
                                f"Retry in ~{int(round(sleep_seconds))}s (attempt {attempts}/{max_attempts})."
                            )
                        else:
                            payload["message"] = (
                                f"AEMET temporary error on window {index + 1}/{total_windows}. "
                                f"Retry in ~{int(round(sleep_seconds))}s (attempt {attempts}/{max_attempts})."
                            )
                        self.repository.upsert_analysis_query_job(payload)
                        time.sleep(sleep_seconds)
                        continue

                    window["status"] = "failed"
                    windows[index] = window
                    payload["windows_json"] = windows
                    payload["status"] = QueryJobStatus.FAILED.value
                    payload["error_detail"] = detail
                    payload["message"] = "Backfill failed for at least one window."
                    self._update_query_job_progress(payload)
                    self.repository.upsert_analysis_query_job(payload)
                    return

            windows[index] = window
            payload["windows_json"] = windows
            self._update_query_job_progress(payload)
            self.repository.upsert_analysis_query_job(payload)

        payload["status"] = QueryJobStatus.COMPLETE.value
        payload["playback_ready"] = True
        payload["message"] = "All requested windows are available in cache."
        self._update_query_job_progress(payload)
        self.repository.upsert_analysis_query_job(payload)

    def _update_query_job_progress(self, payload: dict[str, Any]) -> None:
        windows: list[dict[str, Any]] = list(payload["windows_json"])
        completed_windows = sum(1 for window in windows if window.get("status") in {"cached", "complete"})
        completed_api_calls = sum(int(window.get("apiCallsCompleted", 0)) for window in windows)
        total_windows = max(int(payload.get("total_windows", 0)), 1)
        frames_planned = max(int(payload.get("frames_planned", 1)), 1)
        frames_ready = int((completed_windows / total_windows) * frames_planned)

        payload["completed_windows"] = completed_windows
        payload["completed_api_calls"] = completed_api_calls
        payload["frames_ready"] = min(frames_planned, frames_ready)
        payload["playback_ready"] = completed_windows == int(payload.get("total_windows", 0))

    def get_query_job_status(self, job_id: str) -> QueryJobStatusResponse:
        payload = self.repository.get_analysis_query_job(job_id)
        if payload is None:
            raise AppValidationError(f"Query job '{job_id}' was not found.")
        return self._to_query_job_status_response(payload)

    def get_query_job_result(self, job_id: str) -> FeasibilitySnapshotResponse:
        payload = self.repository.get_analysis_query_job(job_id)
        if payload is None:
            raise AppValidationError(f"Query job '{job_id}' was not found.")

        station_id = str(payload["station_id"])
        timezone_input = str(payload["timezone_input"])
        output_tz = self._resolve_output_timezone(timezone_input)
        start_local = datetime.fromisoformat(str(payload["requested_start_utc"])).astimezone(output_tz)
        end_local = datetime.fromisoformat(str(payload["effective_end_utc"])).astimezone(output_tz)
        aggregation = TimeAggregation(str(payload["aggregation"]))
        selected_types = [MeasurementType(value) for value in payload.get("selected_types_json", [])]
        snapshot = self.get_station_snapshot(
            station=station_id,
            start_local=start_local,
            end_local=end_local,
            aggregation=aggregation,
            selected_types=selected_types,
            timezone_input=timezone_input,
        )
        if payload["status"] != QueryJobStatus.COMPLETE.value:
            snapshot.notes.append(
                "Some historical windows are still loading. Values shown are based on currently cached observations."
            )
        return snapshot

    def get_station_snapshot(
        self,
        station: str,
        start_local: datetime,
        end_local: datetime | None,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
        timezone_input: str,
    ) -> FeasibilitySnapshotResponse:
        selected_station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(selected_station_id)
        self._assert_station_selectable(selected_station_id)
        output_tz = self._resolve_output_timezone(timezone_input, start_local.tzinfo or UTC)

        latest = self.get_latest_availability(selected_station_id)
        if latest.newest_observation_utc is None:
            raise AppValidationError(
                f"No recent observations are available for station '{selected_station_id}'."
            )

        latest_local = latest.newest_observation_utc.astimezone(output_tz)
        effective_end_local = latest_local
        if end_local is not None:
            effective_end_local = min(effective_end_local, end_local)

        if start_local >= effective_end_local:
            raise AppValidationError(
                "Start datetime must be earlier than effective end datetime for this station."
            )

        rows = self.get_data(
            station=selected_station_id,
            start_local=start_local,
            end_local=effective_end_local,
            aggregation=aggregation,
            selected_types=selected_types,
            output_tz=output_tz,
        )
        profile = next((item for item in self.get_station_profiles() if item.station_id == selected_station_id), None)
        station_name = profile.station_name if profile is not None else selected_station_id
        role = profile.role if profile is not None else StationRole.METEO
        latest_utc = self.repository.get_latest_measurement_timestamp(selected_station_id)
        summary = self._build_summary(
            station_id=selected_station_id,
            station_name=station_name,
            role=role,
            rows=rows,
            start_local=start_local,
            end_local=effective_end_local,
            aggregation=aggregation,
            latest_observation_utc=latest_utc,
        )

        return FeasibilitySnapshotResponse(
            checked_at_utc=datetime.now(UTC),
            selectedStationId=selected_station_id,
            selectedStationName=station_name,
            requestedStart=start_local,
            effectiveEnd=effective_end_local,
            effectiveEndReason="limited_by_station_constraints",
            timezone_input=timezone_input,
            timezone_output=getattr(output_tz, "key", str(output_tz)),
            aggregation=aggregation,
            mapStationIds=[selected_station_id],
            notes=[
                "Single-station snapshot generated from cache-first retrieval strategy.",
                "Data retrieval is chunked into full calendar-month upstream windows, but the analysis window can span multiple months/years.",
                "Window end is capped by latest available station observation.",
            ],
            stations=[
                StationFeasibilitySeries(
                    stationId=selected_station_id,
                    stationName=station_name,
                    role=role,
                    summary=summary,
                    data=rows,
                )
            ],
        )

    def get_playback_frames(
        self,
        station: str,
        start_local: datetime,
        end_local: datetime,
        step: PlaybackStep,
        timezone_input: str,
    ) -> PlaybackResponse:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        self._assert_station_selectable(station_id)
        if start_local >= end_local:
            raise AppValidationError("Start datetime must be before end datetime.")
        output_tz = self._resolve_output_timezone(timezone_input, start_local.tzinfo or UTC)

        effective_step = self._coerce_playback_step(start_local, end_local, step)
        rows = self._rows_for_playback(station_id, start_local, end_local, effective_step, output_tz=output_tz)
        frames = self._rows_to_frames(rows, start_local, end_local, effective_step, output_tz=output_tz)
        profile = next((item for item in self.get_station_profiles() if item.station_id == station_id), None)
        station_name = profile.station_name if profile is not None else station_id

        quality_counts = {
            FrameQuality.OBSERVED.value: 0,
            FrameQuality.AGGREGATED.value: 0,
            FrameQuality.GAP_FILLED.value: 0,
        }
        for frame in frames:
            quality_counts[frame.quality_flag.value] = quality_counts.get(frame.quality_flag.value, 0) + 1

        wind_rose = self._build_wind_rose(rows)

        return PlaybackResponse(
            stationId=station_id,
            stationName=station_name,
            requestedStep=step,
            effectiveStep=effective_step,
            timezone_input=timezone_input,
            timezone_output=getattr(output_tz, "key", str(output_tz)),
            start=start_local,
            end=end_local,
            frames=frames,
            framesPlanned=len(frames),
            framesReady=len(frames),
            qualityCounts=quality_counts,
            windRose=wind_rose,
        )

    def get_timeframe_analytics(
        self,
        station: str,
        start_local: datetime,
        end_local: datetime,
        group_by: TimeframeGroupBy,
        timezone_input: str,
        compare_start_local: datetime | None = None,
        compare_end_local: datetime | None = None,
        simulation_params: WindFarmSimulationParams | None = None,
        force_refresh_on_empty: bool = False,
    ) -> TimeframeAnalyticsResponse:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        self._assert_station_selectable(station_id)
        if start_local >= end_local:
            raise AppValidationError("Start datetime must be before end datetime.")
        output_tz = self._resolve_output_timezone(timezone_input, start_local.tzinfo or UTC)

        rows = self.get_data(
            station=station_id,
            start_local=start_local,
            end_local=end_local,
            aggregation=TimeAggregation.NONE,
            selected_types=[],
            output_tz=output_tz,
        )
        if not rows and force_refresh_on_empty:
            self.refresh_data_range(
                station=station_id,
                start_local=start_local,
                end_local=end_local,
            )
            rows = self.get_data(
                station=station_id,
                start_local=start_local,
                end_local=end_local,
                aggregation=TimeAggregation.NONE,
                selected_types=[],
                output_tz=output_tz,
            )
        buckets = self._group_timeframe_buckets(rows, group_by, simulation_params, output_tz=output_tz)

        comparison: list[ComparisonDelta] = []
        if compare_start_local is not None and compare_end_local is not None and compare_start_local < compare_end_local:
            compare_rows = self.get_data(
                station=station_id,
                start_local=compare_start_local,
                end_local=compare_end_local,
                aggregation=TimeAggregation.NONE,
                selected_types=[],
                output_tz=output_tz,
            )
            comparison = self._comparison_deltas(rows, compare_rows, simulation_params)

        profile = next((item for item in self.get_station_profiles() if item.station_id == station_id), None)
        station_name = profile.station_name if profile is not None else station_id
        wind_rose = self._build_wind_rose(rows)
        return TimeframeAnalyticsResponse(
            stationId=station_id,
            stationName=station_name,
            groupBy=group_by,
            timezone_input=timezone_input,
            timezone_output=getattr(output_tz, "key", str(output_tz)),
            requestedStart=start_local,
            requestedEnd=end_local,
            buckets=buckets,
            windRose=wind_rose,
            comparison=comparison,
        )

    def _rows_for_playback(
        self,
        station_id: str,
        start_local: datetime,
        end_local: datetime,
        step: PlaybackStep,
        output_tz: ZoneInfo,
    ) -> list[OutputMeasurement]:
        if step == PlaybackStep.TEN_MINUTES:
            return self.get_data(
                station=station_id,
                start_local=start_local,
                end_local=end_local,
                aggregation=TimeAggregation.NONE,
                selected_types=[],
                output_tz=output_tz,
            )
        if step == PlaybackStep.HOURLY:
            return self.get_data(
                station=station_id,
                start_local=start_local,
                end_local=end_local,
                aggregation=TimeAggregation.HOURLY,
                selected_types=[],
                output_tz=output_tz,
            )
        if step == PlaybackStep.DAILY:
            return self.get_data(
                station=station_id,
                start_local=start_local,
                end_local=end_local,
                aggregation=TimeAggregation.DAILY,
                selected_types=[],
                output_tz=output_tz,
            )

        hourly = self.get_data(
            station=station_id,
            start_local=start_local,
            end_local=end_local,
            aggregation=TimeAggregation.HOURLY,
            selected_types=[],
            output_tz=output_tz,
        )
        grouped: dict[datetime, list[OutputMeasurement]] = {}
        for row in hourly:
            dt = row.datetime_cet
            key = dt.replace(hour=(dt.hour // 3) * 3, minute=0, second=0, microsecond=0)
            grouped.setdefault(key, []).append(row)

        aggregated: list[OutputMeasurement] = []
        for key in sorted(grouped.keys()):
            points = grouped[key]
            aggregated.append(
                OutputMeasurement(
                    stationName=points[0].station_name,
                    datetime=key,
                    temperature=avg([point.temperature_c for point in points]),
                    pressure=avg([point.pressure_hpa for point in points]),
                    speed=avg([point.speed_mps for point in points]),
                    direction=avg_angle_deg(
                        [point.direction_deg for point in points if point.direction_deg is not None]
                    ),
                    latitude=points[0].latitude,
                    longitude=points[0].longitude,
                    altitude=points[0].altitude_m,
                )
            )
        return aggregated

    def _rows_to_frames(
        self,
        rows: list[OutputMeasurement],
        start_local: datetime,
        end_local: datetime,
        step: PlaybackStep,
        output_tz: ZoneInfo,
    ) -> list[PlaybackFrame]:
        if not rows and start_local >= end_local:
            return []

        step_delta = self._step_delta(step)
        aligned_start = self._floor_to_step(start_local.astimezone(output_tz), step)
        aligned_end = end_local.astimezone(output_tz)

        row_map: dict[str, OutputMeasurement] = {}
        for row in rows:
            key = self._floor_to_step(row.datetime_cet.astimezone(output_tz), step).isoformat()
            row_map[key] = row

        frames: list[PlaybackFrame] = []
        cursor = aligned_start
        last_observed: OutputMeasurement | None = None
        while cursor <= aligned_end:
            key = cursor.isoformat()
            matched = row_map.get(key)
            quality = FrameQuality.OBSERVED if step == PlaybackStep.TEN_MINUTES else FrameQuality.AGGREGATED
            if matched is None:
                matched = last_observed
                quality = FrameQuality.GAP_FILLED
            if matched is not None:
                last_observed = matched

            speed = matched.speed_mps if matched is not None else None
            direction_from = matched.direction_deg if matched is not None else None
            direction = wind_toward_direction_deg(direction_from)
            temperature = matched.temperature_c if matched is not None else None
            pressure = matched.pressure_hpa if matched is not None else None
            dx, dy = self._vector_components(speed, direction)
            frames.append(
                PlaybackFrame(
                    datetime=cursor,
                    speed=speed,
                    direction=direction,
                    temperature=temperature,
                    pressure=pressure,
                    qualityFlag=quality,
                    dx=dx,
                    dy=dy,
                )
            )
            cursor = cursor + step_delta
        return frames

    def _group_timeframe_buckets(
        self,
        rows: list[OutputMeasurement],
        group_by: TimeframeGroupBy,
        simulation_params: WindFarmSimulationParams | None,
        output_tz: ZoneInfo,
    ) -> list[TimeframeBucket]:
        groups: dict[tuple[str, datetime, datetime], list[OutputMeasurement]] = {}
        for row in rows:
            dt = row.datetime_cet.astimezone(STATION_LOCAL_TZ)
            if group_by == TimeframeGroupBy.HOUR:
                start = dt.replace(minute=0, second=0, microsecond=0)
                label = start.strftime("%Y-%m-%d %H:00")
                end = start + timedelta(hours=1)
            elif group_by == TimeframeGroupBy.DAY:
                start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                label = start.strftime("%Y-%m-%d")
                end = start + timedelta(days=1)
            elif group_by == TimeframeGroupBy.WEEK:
                start = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                label = f"{start.strftime('%Y')}-W{start.isocalendar().week:02d}"
                end = start + timedelta(days=7)
            elif group_by == TimeframeGroupBy.MONTH:
                start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                label = start.strftime("%Y-%m")
                if start.month == 12:
                    end = start.replace(year=start.year + 1, month=1)
                else:
                    end = start.replace(month=start.month + 1)
            else:
                season = self._season_label(dt)
                if season == "DJF":
                    season_year = dt.year if dt.month == 12 else dt.year - 1
                else:
                    season_year = dt.year
                label = f"{season_year}-{season}"
                month_start = 12 if season == "DJF" else (3 if season == "MAM" else (6 if season == "JJA" else 9))
                year_start = season_year
                start = dt.replace(year=year_start, month=month_start, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=92)

            key = (label, start, end)
            groups.setdefault(key, []).append(row)

        output: list[TimeframeBucket] = []
        for (label, start, end), points in sorted(groups.items(), key=lambda item: item[0][1]):
            speeds = [point.speed_mps for point in points if point.speed_mps is not None]
            temperatures = [point.temperature_c for point in points if point.temperature_c is not None]
            pressures = [point.pressure_hpa for point in points if point.pressure_hpa is not None]
            directions = [
                wind_toward_direction_deg(point.direction_deg)
                for point in points
                if point.direction_deg is not None
            ]
            variability = round(sqrt(pvariance(speeds)), 3) if len(speeds) > 1 else None
            generation = self._estimate_generation_mwh(points, simulation_params)
            output.append(
                TimeframeBucket(
                    label=label,
                    start=start.astimezone(output_tz),
                    end=end.astimezone(output_tz),
                    dataPoints=len(points),
                    avgSpeed=avg(speeds),
                    minSpeed=round(min(speeds), 3) if speeds else None,
                    maxSpeed=round(max(speeds), 3) if speeds else None,
                    p90Speed=percentile(speeds, 0.9) if speeds else None,
                    hoursAbove3mps=round(sum(1 for value in speeds if value >= 3.0) * (10.0 / 60.0), 3) if speeds else None,
                    hoursAbove5mps=round(sum(1 for value in speeds if value >= 5.0) * (10.0 / 60.0), 3) if speeds else None,
                    speedVariability=variability,
                    dominantDirection=dominant_angle_deg(directions),
                    avgTemperature=avg(temperatures),
                    minTemperature=round(min(temperatures), 3) if temperatures else None,
                    maxTemperature=round(max(temperatures), 3) if temperatures else None,
                    avgPressure=avg(pressures),
                    estimatedGenerationMwh=generation,
                )
            )
        return output

    @staticmethod
    def _resolve_output_timezone(timezone_input: str, fallback: Any = UTC) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_input)
        except Exception:
            if isinstance(fallback, ZoneInfo):
                return fallback
            return UTC

    def _comparison_deltas(
        self,
        current_rows: list[OutputMeasurement],
        baseline_rows: list[OutputMeasurement],
        simulation_params: WindFarmSimulationParams | None,
    ) -> list[ComparisonDelta]:
        def summary(rows: list[OutputMeasurement]) -> dict[str, float | None]:
            speeds = [point.speed_mps for point in rows if point.speed_mps is not None]
            return {
                "avgSpeed": avg(speeds),
                "p90Speed": percentile(speeds, 0.9) if speeds else None,
                "hoursAbove5mps": round(sum(1 for value in speeds if value >= 5.0) * (10.0 / 60.0), 3) if speeds else None,
                "estimatedGenerationMwh": self._estimate_generation_mwh(rows, simulation_params),
            }

        current = summary(current_rows)
        baseline = summary(baseline_rows)
        metrics = ["avgSpeed", "p90Speed", "hoursAbove5mps", "estimatedGenerationMwh"]
        output: list[ComparisonDelta] = []
        for metric in metrics:
            base = baseline.get(metric)
            cur = current.get(metric)
            absolute = None if base is None or cur is None else round(cur - base, 3)
            percent = None
            if absolute is not None and base not in {None, 0}:
                percent = round((absolute / abs(base)) * 100.0, 3)
            output.append(
                ComparisonDelta(
                    metric=metric,
                    baseline=base,
                    current=cur,
                    absoluteDelta=absolute,
                    percentDelta=percent,
                )
            )
        return output

    def _estimate_generation_mwh(
        self,
        rows: list[OutputMeasurement],
        params: WindFarmSimulationParams | None,
    ) -> float | None:
        if params is None:
            return None
        rated_total_kw = params.turbine_count * params.rated_power_kw
        if rated_total_kw <= 0:
            return None

        cut_in = params.cut_in_speed_mps
        rated = params.rated_speed_mps
        cut_out = params.cut_out_speed_mps
        reference_density = params.reference_air_density_kgm3
        if not (0 <= cut_in < rated < cut_out):
            return None
        if reference_density <= 0:
            return None

        usable_rows = [row for row in rows if row.datetime_cet is not None]
        if not usable_rows:
            return None
        usable_rows.sort(key=lambda row: row.datetime_cet)

        observed_steps_hours: list[float] = []
        for idx in range(len(usable_rows) - 1):
            delta_hours = (usable_rows[idx + 1].datetime_cet - usable_rows[idx].datetime_cet).total_seconds() / 3600.0
            if 0 < delta_hours <= 24:
                observed_steps_hours.append(delta_hours)
        fallback_step_hours = observed_steps_hours[0] if observed_steps_hours else (10.0 / 60.0)

        energy_mwh = 0.0
        denom = (rated ** 3) - (cut_in ** 3)
        for idx, row in enumerate(usable_rows):
            speed = row.speed_mps
            if speed is None:
                continue
            if not self._within_operating_envelope(row, params):
                continue
            if idx + 1 < len(usable_rows):
                step_hours = (usable_rows[idx + 1].datetime_cet - row.datetime_cet).total_seconds() / 3600.0
                if step_hours <= 0 or step_hours > 24:
                    step_hours = fallback_step_hours
            else:
                step_hours = fallback_step_hours
            density = self._air_density_kgm3(row, fallback_density_kgm3=reference_density)
            density_ratio = max(0.0, density / reference_density)
            effective_speed = speed * (density_ratio ** (1.0 / 3.0))
            if effective_speed < cut_in or effective_speed >= cut_out:
                power_kw = 0.0
            elif effective_speed >= rated:
                power_kw = rated_total_kw
            else:
                ratio = ((effective_speed ** 3) - (cut_in ** 3)) / denom if denom > 0 else 0.0
                ratio = max(0.0, min(1.0, ratio))
                power_kw = rated_total_kw * ratio
            energy_mwh += (power_kw * step_hours) / 1000.0
        return round(energy_mwh, 3)

    @staticmethod
    def _air_density_kgm3(row: OutputMeasurement, fallback_density_kgm3: float) -> float:
        if row.pressure_hpa is None or row.temperature_c is None:
            return fallback_density_kgm3
        kelvin = row.temperature_c + 273.15
        if kelvin <= 0:
            return fallback_density_kgm3
        density = (row.pressure_hpa * 100.0) / (287.05 * kelvin)
        return density if density > 0 else fallback_density_kgm3

    @staticmethod
    def _within_operating_envelope(row: OutputMeasurement, params: WindFarmSimulationParams) -> bool:
        temperature = row.temperature_c
        pressure = row.pressure_hpa
        if (
            temperature is not None
            and params.min_operating_temp_c is not None
            and temperature < params.min_operating_temp_c
        ):
            return False
        if (
            temperature is not None
            and params.max_operating_temp_c is not None
            and temperature > params.max_operating_temp_c
        ):
            return False
        if (
            pressure is not None
            and params.min_operating_pressure_hpa is not None
            and pressure < params.min_operating_pressure_hpa
        ):
            return False
        if (
            pressure is not None
            and params.max_operating_pressure_hpa is not None
            and pressure > params.max_operating_pressure_hpa
        ):
            return False
        return True

    def _build_wind_rose(self, rows: list[OutputMeasurement]) -> WindRoseSummary:
        sectors = [
            "N", "NNE", "NE", "ENE",
            "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW",
            "W", "WNW", "NW", "NNW",
        ]
        bins: list[dict[str, Any]] = [
            {"sector": sector, "speedBuckets": {"calm": 0, "breeze": 0, "strong": 0, "gale": 0}, "totalCount": 0}
            for sector in sectors
        ]

        directional_points = 0
        calm_points = 0
        for row in rows:
            if row.direction_deg is None or row.speed_mps is None:
                continue
            direction = wind_toward_direction_deg(row.direction_deg)
            if direction is None:
                continue
            index = int(((direction + 11.25) % 360) // 22.5)
            target = bins[index]
            speed = row.speed_mps
            if speed < 3.0:
                bucket = "calm"
                calm_points += 1
            elif speed < 8.0:
                bucket = "breeze"
            elif speed < 12.0:
                bucket = "strong"
            else:
                bucket = "gale"
            target["speedBuckets"][bucket] += 1
            target["totalCount"] += 1
            directional_points += 1

        dominant = max(bins, key=lambda item: item["totalCount"], default=None)
        dominant_sector = dominant["sector"] if dominant and dominant["totalCount"] > 0 else None
        directional_concentration = (
            round(dominant["totalCount"] / directional_points, 3)
            if dominant is not None and directional_points > 0
            else None
        )
        calm_share = round(calm_points / directional_points, 3) if directional_points > 0 else None
        return WindRoseSummary(
            bins=[WindRoseBin.model_validate(item) for item in bins],
            dominantSector=dominant_sector,
            directionalConcentration=directional_concentration,
            calmShare=calm_share,
        )

    def _coerce_playback_step(self, start_local: datetime, end_local: datetime, step: PlaybackStep) -> PlaybackStep:
        candidate = step
        while self._frame_count_for_range(start_local, end_local, candidate) > 1500:
            if candidate == PlaybackStep.TEN_MINUTES:
                candidate = PlaybackStep.HOURLY
                continue
            if candidate == PlaybackStep.HOURLY:
                candidate = PlaybackStep.THREE_HOURLY
                continue
            if candidate == PlaybackStep.THREE_HOURLY:
                candidate = PlaybackStep.DAILY
                continue
            break
        return candidate

    @staticmethod
    def _season_label(value: datetime) -> str:
        month = value.month
        if month in {12, 1, 2}:
            return "DJF"
        if month in {3, 4, 5}:
            return "MAM"
        if month in {6, 7, 8}:
            return "JJA"
        return "SON"

    @staticmethod
    def _step_delta(step: PlaybackStep) -> timedelta:
        if step == PlaybackStep.TEN_MINUTES:
            return timedelta(minutes=10)
        if step == PlaybackStep.HOURLY:
            return timedelta(hours=1)
        if step == PlaybackStep.THREE_HOURLY:
            return timedelta(hours=3)
        return timedelta(days=1)

    def _frame_count_for_range(self, start_local: datetime, end_local: datetime, step: PlaybackStep) -> int:
        if end_local <= start_local:
            return 0
        seconds = (end_local - start_local).total_seconds()
        interval = self._step_delta(step).total_seconds()
        return int(seconds // interval) + 1

    def _floor_to_step(self, value: datetime, step: PlaybackStep) -> datetime:
        if step == PlaybackStep.TEN_MINUTES:
            minute = (value.minute // 10) * 10
            return value.replace(minute=minute, second=0, microsecond=0)
        if step == PlaybackStep.HOURLY:
            return value.replace(minute=0, second=0, microsecond=0)
        if step == PlaybackStep.THREE_HOURLY:
            hour = (value.hour // 3) * 3
            return value.replace(hour=hour, minute=0, second=0, microsecond=0)
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _vector_components(speed: float | None, direction: float | None) -> tuple[float | None, float | None]:
        if speed is None or direction is None:
            return None, None
        rad = radians(direction % 360.0)
        dx = round(speed * sin(rad), 4)
        dy = round(speed * cos(rad), 4)
        return dx, dy

    @staticmethod
    def _parse_retry_after_seconds(detail: str) -> float | None:
        match = re.search(r"Retry-After=(\d+)s", detail)
        if match is None:
            return None
        try:
            value = float(match.group(1))
        except ValueError:
            return None
        if value < 1.0:
            return 1.0
        return min(value, 600.0)

    @staticmethod
    def _is_retryable_upstream_error(detail: str) -> bool:
        return any(code in detail for code in ("HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504"))

    @staticmethod
    def _split_windows(start_utc: datetime, end_utc: datetime) -> list[tuple[datetime, datetime]]:
        return split_month_windows_covering_range(start_utc, end_utc)

    @staticmethod
    def _to_query_job_created_response(payload: dict[str, Any]) -> QueryJobCreatedResponse:
        return QueryJobCreatedResponse(
            jobId=payload["job_id"],
            status=QueryJobStatus(str(payload["status"])),
            stationId=payload["station_id"],
            requestedStartUtc=datetime.fromisoformat(str(payload["requested_start_utc"])),
            effectiveEndUtc=datetime.fromisoformat(str(payload["effective_end_utc"])),
            historyStartUtc=datetime.fromisoformat(str(payload["history_start_utc"])),
            totalWindows=int(payload["total_windows"]),
            cachedWindows=int(payload["cached_windows"]),
            missingWindows=int(payload["missing_windows"]),
            totalApiCallsPlanned=int(payload["total_api_calls_planned"]),
            completedApiCalls=int(payload["completed_api_calls"]),
            framesPlanned=int(payload["frames_planned"]),
            framesReady=int(payload["frames_ready"]),
            playbackReady=bool(payload["playback_ready"]),
            message=str(payload.get("message", "")),
        )

    @staticmethod
    def _to_query_job_status_response(payload: dict[str, Any]) -> QueryJobStatusResponse:
        total_calls = int(payload["total_api_calls_planned"])
        completed_calls = int(payload["completed_api_calls"])
        if total_calls > 0:
            percent = round((completed_calls / total_calls) * 100.0, 2)
        elif payload["status"] == QueryJobStatus.COMPLETE.value:
            percent = 100.0
        else:
            percent = 0.0
        return QueryJobStatusResponse(
            jobId=payload["job_id"],
            status=QueryJobStatus(str(payload["status"])),
            stationId=payload["station_id"],
            totalWindows=int(payload["total_windows"]),
            cachedWindows=int(payload["cached_windows"]),
            missingWindows=int(payload["missing_windows"]),
            completedWindows=int(payload["completed_windows"]),
            totalApiCallsPlanned=total_calls,
            completedApiCalls=completed_calls,
            framesPlanned=int(payload["frames_planned"]),
            framesReady=int(payload["frames_ready"]),
            playbackReady=bool(payload["playback_ready"]),
            percent=percent,
            message=str(payload.get("message", "")),
            errorDetail=payload.get("error_detail"),
            updatedAtUtc=datetime.fromisoformat(str(payload["updated_at_utc"])),
        )
