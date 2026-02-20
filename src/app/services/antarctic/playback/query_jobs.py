from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from app.core.exceptions import AppValidationError
from app.models import (
    FeasibilitySnapshotResponse,
    MeasurementType,
    PlaybackStep,
    QueryJobCreatedResponse,
    QueryJobStatus,
    QueryJobStatusResponse,
    TimeAggregation,
)
from app.services.antarctic.constants import UTC
from app.services.antarctic.windows import split_month_windows_covering_range

logger = logging.getLogger(__name__)


class PlaybackQueryJobsMixin:
    repository: object
    aemet_client: object
    settings: object

    _query_job_lock = threading.Lock()
    _query_job_threads: dict[str, threading.Thread] = {}

    def _background_query_jobs_enabled(self) -> bool:
        return bool(getattr(self.settings, "query_jobs_background_enabled", True))

    def create_query_job(
        self,
        station: str,
        start_local: datetime,
        end_local: datetime | None,
        timezone_input: str,
        playback_step: PlaybackStep,
        aggregation: TimeAggregation,
        selected_types: list[MeasurementType],
        history_start_local: datetime | None = None,
    ) -> QueryJobCreatedResponse:
        station_id = self.station_id_for(station)
        self._assert_station_supported_by_antarctic_endpoint(station_id)
        self._assert_station_selectable(station_id)

        if end_local is not None:
            effective_end_local = end_local.astimezone(start_local.tzinfo or UTC)
        else:
            latest = self.get_latest_availability(station_id)
            if latest.newest_observation_utc is None:
                raise AppValidationError(
                    f"No recent observations are available for station '{station_id}'. Try another station later."
                )
            effective_end_local = latest.newest_observation_utc.astimezone(start_local.tzinfo or UTC)
        if start_local >= effective_end_local:
            raise AppValidationError(
                "Start datetime must be earlier than the effective end datetime."
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
        logger.info(
            "Created analysis query job id=%s station=%s total_windows=%d missing_windows=%d planned_calls=%d",
            job_id,
            station_id,
            total_windows,
            missing_windows,
            total_api_calls_planned,
        )

        if missing_windows > 0 and self._background_query_jobs_enabled():
            self._start_query_job_thread(job_id)
        elif missing_windows > 0:
            payload["message"] = "Queued missing months. Fetch progresses with status polling."
            self.repository.upsert_analysis_query_job(payload)

        return self._to_query_job_created_response(payload)

    def _start_query_job_thread(self, job_id: str) -> None:
        with self._query_job_lock:
            existing = self._query_job_threads.get(job_id)
            if existing is not None and existing.is_alive():
                return

            worker = threading.Thread(target=self._run_query_job_worker, args=(job_id,), daemon=True)
            self._query_job_threads[job_id] = worker
            worker.start()

    def _run_query_job_worker(self, job_id: str, max_windows: int | None = None) -> None:
        payload = self.repository.get_analysis_query_job(job_id)
        if payload is None:
            logger.warning("Query job worker could not find payload for job id=%s", job_id)
            return

        if payload.get("status") == QueryJobStatus.COMPLETE.value:
            return
        if payload.get("status") == QueryJobStatus.FAILED.value:
            return

        payload["status"] = QueryJobStatus.RUNNING.value
        payload["message"] = "Fetching missing months from AEMET."
        self.repository.upsert_analysis_query_job(payload)

        station_id = str(payload["station_id"])
        total_windows = int(payload["total_windows"])
        windows: list[dict[str, Any]] = list(payload["windows_json"])  # type: ignore[arg-type]
        if not windows:
            logger.info("Query job id=%s has no windows to process; marking complete.", job_id)
            payload["status"] = QueryJobStatus.COMPLETE.value
            payload["playback_ready"] = True
            payload["message"] = "No fetch required."
            self.repository.upsert_analysis_query_job(payload)
            return

        processed_windows = 0
        # Process newest windows first so months with real data (most recent) are fetched
        # before older months that may return empty results from AEMET.
        pending_indices = [
            i for i, w in enumerate(windows)
            if w.get("status") not in {"cached", "complete"}
        ]
        pending_indices.sort(key=lambda i: windows[i].get("startUtc", ""), reverse=True)

        for index in pending_indices:
            window = windows[index]

            attempts = int(window.get("attempts", 0))
            max_attempts = 4
            success = False
            while attempts < max_attempts and not success:
                attempts += 1
                window["attempts"] = attempts
                window["status"] = "running"
                windows[index] = window
                payload["windows_json"] = windows
                payload["message"] = f"Fetching month {index + 1}/{total_windows}."
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
                    if not rows:
                        # AEMET returned no data for this window — normal for historical gaps
                        # in Antarctic campaigns. Write the fetch_window to avoid re-fetching.
                        logger.info(
                            "AEMET returned no data for station=%s window=%s to %s (expected for gaps).",
                            station_id, start_utc.isoformat(), end_utc.isoformat(),
                        )
                    self.repository.upsert_measurements(
                        station_id=station_id,
                        rows=rows,
                        start_utc=start_utc,
                        end_utc=end_utc,
                    )
                    window["status"] = "complete"
                    window["apiCallsCompleted"] = int(window.get("apiCallsPlanned", 2)) if rows else 0
                    window["errorDetail"] = None
                    success = True
                except Exception as exc:
                    detail = str(exc)
                    window["errorDetail"] = detail
                    is_rate_limited = "429" in detail
                    is_retryable_upstream = self._is_retryable_upstream_error(detail)

                    if is_rate_limited or is_retryable_upstream:
                        window["status"] = "pending"
                        windows[index] = window
                        payload["windows_json"] = windows
                        limiter_seconds = max(float(getattr(self.settings, "aemet_min_request_interval_seconds", 2.0)), 0.5)
                        if is_rate_limited:
                            payload["message"] = (
                                f"AEMET rate limited on month {index + 1}/{total_windows}. "
                                f"Retrying with {int(round(limiter_seconds))}s pacing."
                            )
                        else:
                            payload["message"] = (
                                f"AEMET temporary upstream error on month {index + 1}/{total_windows}. "
                                "Will retry."
                            )
                        self._update_query_job_progress(payload)
                        self.repository.upsert_analysis_query_job(payload)
                        if attempts < max_attempts:
                            time.sleep(limiter_seconds)
                            continue

                    logger.error(
                        "Query job id=%s failed month %s/%s station=%s after %d attempts: %s",
                        job_id,
                        index + 1,
                        total_windows,
                        station_id,
                        attempts,
                        detail,
                    )
                    window["status"] = "failed"
                    windows[index] = window
                    payload["windows_json"] = windows
                    payload["status"] = QueryJobStatus.FAILED.value
                    payload["error_detail"] = detail
                    payload["message"] = "Backfill failed for at least one month."
                    self._update_query_job_progress(payload)
                    self.repository.upsert_analysis_query_job(payload)
                    return

            windows[index] = window
            payload["windows_json"] = windows
            self._update_query_job_progress(payload)
            self.repository.upsert_analysis_query_job(payload)

            if window.get("status") in {"cached", "complete"}:
                processed_windows += 1
                if max_windows is not None and processed_windows >= max_windows:
                    if int(payload.get("completed_windows", 0)) < int(payload.get("total_windows", 0)):
                        payload["status"] = QueryJobStatus.RUNNING.value
                        payload["message"] = (
                            f"Fetching months: {payload.get('completed_windows', 0)}/{payload.get('total_windows', 0)} loaded."
                        )
                        self.repository.upsert_analysis_query_job(payload)
                    return

        payload["status"] = QueryJobStatus.COMPLETE.value
        payload["playback_ready"] = True
        payload["message"] = "All requested months are available in cache."
        self._update_query_job_progress(payload)
        self.repository.upsert_analysis_query_job(payload)
        logger.info(
            "Query job completed id=%s station=%s completed_windows=%d/%d completed_calls=%d/%d",
            job_id,
            station_id,
            payload.get("completed_windows"),
            payload.get("total_windows"),
            payload.get("completed_api_calls"),
            payload.get("total_api_calls_planned"),
        )

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
        status_value = str(payload.get("status", ""))
        if status_value in {QueryJobStatus.PENDING.value, QueryJobStatus.RUNNING.value}:
            if self._background_query_jobs_enabled():
                self._start_query_job_thread(job_id)
            else:
                # Serverless-safe mode: progress one month per polling request.
                self._run_query_job_worker(job_id, max_windows=1)
            payload = self.repository.get_analysis_query_job(job_id) or payload
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
