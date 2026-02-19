import os
import shutil
import sqlite3
import json
import logging
import httpx
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.models import SourceMeasurement, StationCatalogItem

logger = logging.getLogger(__name__)


def _seed_from_blob_storage(target_path: str) -> None:
    """Download the pre-built cache DB from Vercel Blob Storage to the writable target path on Vercel."""
    if not (os.getenv("VERCEL") or os.getenv("VERCEL_ENV")):
        return
    if os.path.exists(target_path):
        return
        
    blob_url = os.environ.get("CACHE_DB_BLOB_URL")
    if not blob_url:
        logger.warning("Vercel cold start but CACHE_DB_BLOB_URL is missing. Starting with an empty cache.")
        return
        
    logger.info("SEED: Starting cache DB download. target=%s", target_path)
    
    try:
        # Stream the DB to disk to avoid loading 150MB into memory
        with httpx.stream("GET", blob_url, follow_redirects=True, timeout=60.0) as response:
            response.raise_for_status()
            with open(target_path, "wb") as f_out:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f_out.write(chunk)
        
        logger.info("SEED: Success! File size is %d bytes", os.path.getsize(target_path))
    except Exception as exc:
        logger.error("SEED: Failed to download DB from Blob Storage: %s", str(exc))
        if os.path.exists(target_path):
            os.remove(target_path)


class SQLiteRepository:
    def __init__(self, database_url: str) -> None:
        parsed = urlparse(database_url)
        if parsed.scheme != "sqlite":
            raise ValueError("Only sqlite database URLs are supported.")

        if parsed.path in {":memory:", "/:memory:"}:
            self.db_path = ":memory:"
        else:
            raw_path = parsed.path or ""
            # sqlite:///./file.db -> /./file.db (relative path encoded with leading slash)
            if raw_path.startswith("/./") or raw_path.startswith("/../"):
                normalized_path = raw_path[1:]
            # sqlite:////tmp/file.db may parse as //tmp/file.db; normalize to /tmp/file.db
            elif raw_path.startswith("//"):
                normalized_path = raw_path[1:]
            # sqlite:///tmp/file.db should remain absolute /tmp/file.db
            elif raw_path.startswith("/"):
                normalized_path = raw_path
            else:
                normalized_path = raw_path

            self.db_path = normalized_path or "aemet_cache.db"

        logger.info("Initializing SQLite repository path=%s", self.db_path)
        _seed_from_blob_storage(self.db_path)
        try:
            self._initialize()
        except sqlite3.OperationalError as exc:
            fallback_path = "/tmp/aemet_cache.db"
            if self.db_path == fallback_path:
                raise
            logger.warning(
                "SQLite initialization failed for path=%s (%s). Retrying with fallback path=%s",
                self.db_path,
                str(exc),
                fallback_path,
            )
            self.db_path = fallback_path
            self._initialize()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _read_connection(self):
        conn = self._new_connection()
        conn.execute("PRAGMA query_only = ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write_connection(self):
        conn = self._new_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._write_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    station_id TEXT NOT NULL,
                    station_name TEXT NOT NULL,
                    measured_at_utc TEXT NOT NULL,
                    temperature_c REAL,
                    pressure_hpa REAL,
                    speed_mps REAL,
                    direction_deg REAL,
                    latitude REAL,
                    longitude REAL,
                    altitude_m REAL,
                    fetched_at_utc TEXT NOT NULL,
                    PRIMARY KEY (station_id, measured_at_utc)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_measurements_station_datetime ON measurements(station_id, measured_at_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fetch_windows (
                    station_id TEXT NOT NULL,
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    fetched_at_utc TEXT NOT NULL,
                    direction_checked INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (station_id, start_utc, end_utc)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fetch_windows_station_fetched_at ON fetch_windows(station_id, fetched_at_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS station_catalog (
                    station_id TEXT NOT NULL PRIMARY KEY,
                    station_name TEXT NOT NULL,
                    province TEXT,
                    latitude REAL,
                    longitude REAL,
                    altitude_m REAL,
                    data_endpoint TEXT NOT NULL DEFAULT 'valores-climatologicos-inventario',
                    is_antarctic_station INTEGER NOT NULL DEFAULT 0,
                    fetched_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_station_catalog_fetched_at ON station_catalog(fetched_at_utc)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_query_jobs (
                    job_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    requested_start_utc TEXT NOT NULL,
                    effective_end_utc TEXT NOT NULL,
                    history_start_utc TEXT NOT NULL,
                    timezone_input TEXT NOT NULL,
                    aggregation TEXT NOT NULL,
                    selected_types_json TEXT NOT NULL,
                    playback_step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_windows INTEGER NOT NULL,
                    cached_windows INTEGER NOT NULL,
                    missing_windows INTEGER NOT NULL,
                    completed_windows INTEGER NOT NULL,
                    total_api_calls_planned INTEGER NOT NULL,
                    completed_api_calls INTEGER NOT NULL,
                    frames_planned INTEGER NOT NULL,
                    frames_ready INTEGER NOT NULL,
                    playback_ready INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL,
                    error_detail TEXT,
                    windows_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_query_jobs_updated_at ON analysis_query_jobs(updated_at_utc)"
            )
            self._ensure_columns(conn)
            self._ensure_station_catalog_columns(conn)
            self._ensure_fetch_windows_columns(conn)
            conn.commit()

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(measurements)").fetchall()}
        required_columns = {
            "direction_deg": "ALTER TABLE measurements ADD COLUMN direction_deg REAL",
            "latitude": "ALTER TABLE measurements ADD COLUMN latitude REAL",
            "longitude": "ALTER TABLE measurements ADD COLUMN longitude REAL",
            "altitude_m": "ALTER TABLE measurements ADD COLUMN altitude_m REAL",
        }
        for column, ddl in required_columns.items():
            if column not in existing_columns:
                conn.execute(ddl)

    @staticmethod
    def _ensure_station_catalog_columns(conn: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(station_catalog)").fetchall()}
        required_columns = {
            "data_endpoint": (
                "ALTER TABLE station_catalog ADD COLUMN data_endpoint TEXT NOT NULL "
                "DEFAULT 'valores-climatologicos-inventario'"
            ),
            "is_antarctic_station": (
                "ALTER TABLE station_catalog ADD COLUMN is_antarctic_station INTEGER NOT NULL DEFAULT 0"
            ),
        }
        for column, ddl in required_columns.items():
            if column not in existing_columns:
                conn.execute(ddl)

    @staticmethod
    def _ensure_fetch_windows_columns(conn: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fetch_windows)").fetchall()}
        required_columns = {
            "direction_checked": "ALTER TABLE fetch_windows ADD COLUMN direction_checked INTEGER NOT NULL DEFAULT 0",
        }
        for column, ddl in required_columns.items():
            if column not in existing_columns:
                conn.execute(ddl)

    def upsert_measurements(
        self,
        station_id: str,
        rows: list[SourceMeasurement],
        start_utc: datetime,
        end_utc: datetime,
    ) -> None:
        now_utc = datetime.utcnow().isoformat()
        direction_checked = 1
        logger.debug(
            "Upsert measurements station=%s rows=%d start=%s end=%s",
            station_id,
            len(rows),
            start_utc.isoformat(),
            end_utc.isoformat(),
        )
        with self._write_connection() as conn:
            conn.executemany(
                """
                INSERT INTO measurements (
                    station_id, station_name, measured_at_utc,
                    temperature_c, pressure_hpa, speed_mps, direction_deg,
                    latitude, longitude, altitude_m, fetched_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id, measured_at_utc)
                DO UPDATE SET
                    station_name=excluded.station_name,
                    temperature_c=excluded.temperature_c,
                    pressure_hpa=excluded.pressure_hpa,
                    speed_mps=excluded.speed_mps,
                    direction_deg=excluded.direction_deg,
                    latitude=COALESCE(excluded.latitude, measurements.latitude),
                    longitude=COALESCE(excluded.longitude, measurements.longitude),
                    altitude_m=COALESCE(excluded.altitude_m, measurements.altitude_m),
                    fetched_at_utc=excluded.fetched_at_utc
                """,
                [
                    (
                        station_id,
                        row.station_name,
                        row.measured_at_utc.isoformat(),
                        row.temperature_c,
                        row.pressure_hpa,
                        row.speed_mps,
                        row.direction_deg,
                        row.latitude,
                        row.longitude,
                        row.altitude_m,
                        now_utc,
                    )
                    for row in rows
                ],
            )
            conn.execute(
                """
                INSERT INTO fetch_windows (station_id, start_utc, end_utc, fetched_at_utc, direction_checked)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(station_id, start_utc, end_utc)
                DO UPDATE SET
                    fetched_at_utc = excluded.fetched_at_utc,
                    direction_checked = excluded.direction_checked
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat(), now_utc, direction_checked),
            )
            conn.commit()

    def has_fresh_fetch_window(
        self,
        station_id: str,
        start_utc: datetime,
        end_utc: datetime,
        min_fetched_at_utc: datetime,
    ) -> bool:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT fetched_at_utc
                FROM fetch_windows
                WHERE station_id = ?
                  AND start_utc <= ?
                  AND end_utc >= ?
                ORDER BY fetched_at_utc DESC
                LIMIT 1
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
        if row is None:
            return False
        fetched_at = datetime.fromisoformat(row["fetched_at_utc"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return fetched_at >= min_fetched_at_utc

    def has_cached_fetch_window(
        self,
        station_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> bool:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM fetch_windows
                WHERE station_id = ?
                  AND start_utc <= ?
                  AND end_utc >= ?
                LIMIT 1
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
        return row is not None

    def is_fetch_window_direction_checked(
        self,
        station_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> bool:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT direction_checked
                FROM fetch_windows
                WHERE station_id = ?
                  AND start_utc <= ?
                  AND end_utc >= ?
                ORDER BY fetched_at_utc DESC
                LIMIT 1
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
        if row is None or row["direction_checked"] is None:
            return False
        return bool(row["direction_checked"])

    def mark_fetch_window_direction_checked(
        self,
        station_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> None:
        now_utc = datetime.utcnow().isoformat()
        with self._write_connection() as conn:
            conn.execute(
                """
                UPDATE fetch_windows
                SET direction_checked = 1
                WHERE station_id = ?
                  AND start_utc <= ?
                  AND end_utc >= ?
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat()),
            )
            conn.execute(
                """
                INSERT INTO fetch_windows (station_id, start_utc, end_utc, fetched_at_utc, direction_checked)
                SELECT ?, ?, ?, ?, 1
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM fetch_windows
                    WHERE station_id = ?
                      AND start_utc <= ?
                      AND end_utc >= ?
                )
                """,
                (
                    station_id,
                    start_utc.isoformat(),
                    end_utc.isoformat(),
                    now_utc,
                    station_id,
                    start_utc.isoformat(),
                    end_utc.isoformat(),
                ),
            )
            conn.commit()

    def get_measurements(self, station_id: str, start_utc: datetime, end_utc: datetime) -> list[SourceMeasurement]:
        with self._read_connection() as conn:
            result = conn.execute(
                """
                SELECT station_name, measured_at_utc, temperature_c, pressure_hpa, speed_mps,
                       direction_deg, latitude, longitude, altitude_m
                FROM measurements
                WHERE station_id = ?
                  AND measured_at_utc >= ?
                  AND measured_at_utc <= ?
                ORDER BY measured_at_utc ASC
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
        return [
            SourceMeasurement(
                station_name=row["station_name"],
                measured_at_utc=datetime.fromisoformat(row["measured_at_utc"]),
                temperature_c=row["temperature_c"],
                pressure_hpa=row["pressure_hpa"],
                speed_mps=row["speed_mps"],
                direction_deg=row["direction_deg"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                altitude_m=row["altitude_m"],
            )
            for row in result
        ]

    def upsert_station_catalog(self, rows: list[StationCatalogItem]) -> datetime:
        now_utc = datetime.now(timezone.utc)
        logger.debug("Upsert station catalog rows=%d", len(rows))
        with self._write_connection() as conn:
            conn.executemany(
                """
                INSERT INTO station_catalog (
                    station_id, station_name, province, latitude, longitude, altitude_m,
                    data_endpoint, is_antarctic_station, fetched_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id)
                DO UPDATE SET
                    station_name=excluded.station_name,
                    province=excluded.province,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    altitude_m=excluded.altitude_m,
                    data_endpoint=excluded.data_endpoint,
                    is_antarctic_station=excluded.is_antarctic_station,
                    fetched_at_utc=excluded.fetched_at_utc
                """,
                [
                    (
                        row.station_id,
                        row.station_name,
                        row.province,
                        row.latitude,
                        row.longitude,
                        row.altitude_m,
                        row.data_endpoint,
                        int(row.is_antarctic_station),
                        now_utc.isoformat(),
                    )
                    for row in rows
                ],
            )
            conn.commit()
        return now_utc

    def has_fresh_station_catalog(self, min_fetched_at_utc: datetime) -> bool:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT MAX(fetched_at_utc) AS last_fetched_at_utc
                FROM station_catalog
                """
            ).fetchone()
        if row is None or row["last_fetched_at_utc"] is None:
            return False
        fetched_at = datetime.fromisoformat(row["last_fetched_at_utc"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return fetched_at >= min_fetched_at_utc

    def get_station_catalog_last_fetched_at(self) -> datetime | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT MAX(fetched_at_utc) AS last_fetched_at_utc
                FROM station_catalog
                """
            ).fetchone()
        if row is None or row["last_fetched_at_utc"] is None:
            return None
        return datetime.fromisoformat(row["last_fetched_at_utc"])

    def get_station_catalog(self) -> list[StationCatalogItem]:
        with self._read_connection() as conn:
            result = conn.execute(
                """
                SELECT station_id, station_name, province, latitude, longitude, altitude_m,
                       data_endpoint, is_antarctic_station
                FROM station_catalog
                ORDER BY station_name ASC
                """
            ).fetchall()
        return [
            StationCatalogItem(
                stationId=row["station_id"],
                stationName=row["station_name"],
                province=row["province"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                altitude=row["altitude_m"],
                dataEndpoint=row["data_endpoint"],
                isAntarcticStation=bool(row["is_antarctic_station"]),
            )
            for row in result
        ]

    def get_station_catalog_item(self, station_id: str) -> StationCatalogItem | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT station_id, station_name, province, latitude, longitude, altitude_m,
                       data_endpoint, is_antarctic_station
                FROM station_catalog
                WHERE station_id = ?
                LIMIT 1
                """,
                (station_id,),
            ).fetchone()

        if row is None:
            return None

        return StationCatalogItem(
            stationId=row["station_id"],
            stationName=row["station_name"],
            province=row["province"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            altitude=row["altitude_m"],
            dataEndpoint=row["data_endpoint"],
            isAntarcticStation=bool(row["is_antarctic_station"]),
        )

    def get_latest_measurement_timestamp(self, station_id: str) -> datetime | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT MAX(measured_at_utc) AS latest_measured_at_utc
                FROM measurements
                WHERE station_id = ?
                """,
                (station_id,),
            ).fetchone()
        if row is None or row["latest_measured_at_utc"] is None:
            return None
        return datetime.fromisoformat(row["latest_measured_at_utc"])

    def get_latest_measurement(self, station_id: str) -> SourceMeasurement | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT station_name, measured_at_utc, temperature_c, pressure_hpa, speed_mps,
                       direction_deg, latitude, longitude, altitude_m
                FROM measurements
                WHERE station_id = ?
                ORDER BY measured_at_utc DESC
                LIMIT 1
                """,
                (station_id,),
            ).fetchone()
        if row is None:
            return None
        return SourceMeasurement(
            station_name=row["station_name"],
            measured_at_utc=datetime.fromisoformat(row["measured_at_utc"]),
            temperature_c=row["temperature_c"],
            pressure_hpa=row["pressure_hpa"],
            speed_mps=row["speed_mps"],
            direction_deg=row["direction_deg"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            altitude_m=row["altitude_m"],
        )

    def upsert_analysis_query_job(self, payload: dict[str, object]) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        logger.debug(
            "Upsert query job id=%s status=%s completed_windows=%s total_windows=%s",
            payload.get("job_id"),
            payload.get("status"),
            payload.get("completed_windows"),
            payload.get("total_windows"),
        )
        created_at = str(payload.get("created_at_utc") or now_utc)
        windows_json = payload.get("windows_json", "[]")
        if isinstance(windows_json, list):
            windows_json = json.dumps(windows_json)
        types_json = payload.get("selected_types_json", "[]")
        if isinstance(types_json, list):
            types_json = json.dumps(types_json)

        with self._write_connection() as conn:
            conn.execute(
                """
                INSERT INTO analysis_query_jobs (
                    job_id, station_id, requested_start_utc, effective_end_utc, history_start_utc,
                    timezone_input, aggregation, selected_types_json, playback_step, status,
                    total_windows, cached_windows, missing_windows, completed_windows,
                    total_api_calls_planned, completed_api_calls, frames_planned, frames_ready,
                    playback_ready, message, error_detail, windows_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id)
                DO UPDATE SET
                    station_id=excluded.station_id,
                    requested_start_utc=excluded.requested_start_utc,
                    effective_end_utc=excluded.effective_end_utc,
                    history_start_utc=excluded.history_start_utc,
                    timezone_input=excluded.timezone_input,
                    aggregation=excluded.aggregation,
                    selected_types_json=excluded.selected_types_json,
                    playback_step=excluded.playback_step,
                    status=excluded.status,
                    total_windows=excluded.total_windows,
                    cached_windows=excluded.cached_windows,
                    missing_windows=excluded.missing_windows,
                    completed_windows=excluded.completed_windows,
                    total_api_calls_planned=excluded.total_api_calls_planned,
                    completed_api_calls=excluded.completed_api_calls,
                    frames_planned=excluded.frames_planned,
                    frames_ready=excluded.frames_ready,
                    playback_ready=excluded.playback_ready,
                    message=excluded.message,
                    error_detail=excluded.error_detail,
                    windows_json=excluded.windows_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    payload["job_id"],
                    payload["station_id"],
                    payload["requested_start_utc"],
                    payload["effective_end_utc"],
                    payload["history_start_utc"],
                    payload["timezone_input"],
                    payload["aggregation"],
                    str(types_json),
                    payload["playback_step"],
                    payload["status"],
                    int(payload.get("total_windows", 0)),
                    int(payload.get("cached_windows", 0)),
                    int(payload.get("missing_windows", 0)),
                    int(payload.get("completed_windows", 0)),
                    int(payload.get("total_api_calls_planned", 0)),
                    int(payload.get("completed_api_calls", 0)),
                    int(payload.get("frames_planned", 0)),
                    int(payload.get("frames_ready", 0)),
                    int(1 if payload.get("playback_ready", False) else 0),
                    payload.get("message", ""),
                    payload.get("error_detail"),
                    str(windows_json),
                    created_at,
                    now_utc,
                ),
            )
            conn.commit()

    def get_analysis_query_job(self, job_id: str) -> dict[str, object] | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """
                SELECT job_id, station_id, requested_start_utc, effective_end_utc, history_start_utc,
                       timezone_input, aggregation, selected_types_json, playback_step, status,
                       total_windows, cached_windows, missing_windows, completed_windows,
                       total_api_calls_planned, completed_api_calls, frames_planned, frames_ready,
                       playback_ready, message, error_detail, windows_json, created_at_utc, updated_at_utc
                FROM analysis_query_jobs
                WHERE job_id = ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        selected_types_raw = row["selected_types_json"] or "[]"
        windows_raw = row["windows_json"] or "[]"
        try:
            selected_types = json.loads(selected_types_raw)
        except json.JSONDecodeError:
            selected_types = []
        try:
            windows = json.loads(windows_raw)
        except json.JSONDecodeError:
            windows = []

        return {
            "job_id": row["job_id"],
            "station_id": row["station_id"],
            "requested_start_utc": row["requested_start_utc"],
            "effective_end_utc": row["effective_end_utc"],
            "history_start_utc": row["history_start_utc"],
            "timezone_input": row["timezone_input"],
            "aggregation": row["aggregation"],
            "selected_types_json": selected_types,
            "playback_step": row["playback_step"],
            "status": row["status"],
            "total_windows": row["total_windows"],
            "cached_windows": row["cached_windows"],
            "missing_windows": row["missing_windows"],
            "completed_windows": row["completed_windows"],
            "total_api_calls_planned": row["total_api_calls_planned"],
            "completed_api_calls": row["completed_api_calls"],
            "frames_planned": row["frames_planned"],
            "frames_ready": row["frames_ready"],
            "playback_ready": bool(row["playback_ready"]),
            "message": row["message"],
            "error_detail": row["error_detail"],
            "windows_json": windows,
            "created_at_utc": row["created_at_utc"],
            "updated_at_utc": row["updated_at_utc"],
        }
