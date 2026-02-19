import os
import sqlite3
import shutil
import json
import math
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.models import SourceMeasurement, StationCatalogItem


def _utc_iso(dt: datetime) -> str:
    """Normalize a datetime to a naive-UTC ISO string (no +00:00 suffix).

    Ensures consistent string comparisons in SQLite WHERE clauses.
    """
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()

logger = logging.getLogger(__name__)

# Store cold-start seed logs in memory so we can read them via a debug API endpoint
seed_debug_logs: list[str] = []

def _log_seed(msg: str) -> None:
    logger.info(msg)
    seed_debug_logs.append(msg)


class RowDict(dict):
    """Dict subclass that also supports attribute access for row values."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


class TursoHttpClient:
    """Thin wrapper around Turso's Hrana v2 pipeline HTTP API."""

    def __init__(self, base_url: str, auth_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        self._http = httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0)

    def execute(self, sql: str, args: tuple = ()) -> "TursoCursor":
        stmt = {"sql": sql}
        if args:
            stmt["args"] = [self._encode_arg(a) for a in args]
        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        }
        resp = self._http.post("/v2/pipeline", json=payload)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results and results[0].get("type") == "ok":
            result = results[0]["response"]["result"]
            cols = [c["name"] for c in result.get("cols", [])]
            raw_rows = result.get("rows", [])
            rows = []
            for raw_row in raw_rows:
                row_values = [self._decode_value(v) for v in raw_row]
                rows.append(RowDict(zip(cols, row_values)))
            return TursoCursor(rows)
        elif results and results[0].get("type") == "error":
            error = results[0].get("error", {})
            raise RuntimeError(f"Turso error: {error.get('message', str(error))}")
        return TursoCursor([])

    def executemany(self, sql: str, seq_of_params: list[tuple]) -> None:
        requests = []
        for args in seq_of_params:
            stmt = {"sql": sql}
            if args:
                stmt["args"] = [self._encode_arg(a) for a in args]
            requests.append({"type": "execute", "stmt": stmt})
        requests.append({"type": "close"})
        resp = self._http.post("/v2/pipeline", json={"requests": requests})
        resp.raise_for_status()

    def batch_execute(self, statements: list[str]) -> None:
        """Execute multiple SQL statements in a single pipeline request."""
        if not statements:
            return
        requests = [{"type": "execute", "stmt": {"sql": sql}} for sql in statements]
        requests.append({"type": "close"})
        resp = self._http.post("/v2/pipeline", json={"requests": requests})
        resp.raise_for_status()

    @staticmethod
    def _encode_arg(value):
        if value is None:
            return {"type": "null"}
        elif isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return {"type": "null"}
            return {"type": "float", "value": value}
        elif isinstance(value, str):
            return {"type": "text", "value": value}
        elif isinstance(value, bytes):
            import base64
            return {"type": "blob", "base64": base64.b64encode(value).decode()}
        return {"type": "text", "value": str(value)}

    @staticmethod
    def _decode_value(v):
        if v is None or v.get("type") == "null":
            return None
        t = v.get("type", "")
        val = v.get("value")
        if t == "integer":
            return int(val)
        elif t == "float":
            f = float(val)
            return None if (math.isnan(f) or math.isinf(f)) else f
        elif t == "blob":
            import base64
            return base64.b64decode(v.get("base64", ""))
        return val  # text or unknown

    def commit(self):
        pass

    def close(self):
        self._http.close()


class TursoCursor:
    def __init__(self, rows: list[RowDict]):
        self.rows = rows
        self._idx = 0

    def fetchone(self):
        if self._idx < len(self.rows):
            row = self.rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        return self.rows


class SQLiteRepository:
    def __init__(self, database_url: str, auth_token: str = "") -> None:
        self.db_path = database_url
        self.auth_token = auth_token
        self._is_remote = database_url.startswith("https://") or database_url.startswith("http://")
        _log_seed(f"Initializing repository url={self.db_path[:40]}... remote={self._is_remote}")
        try:
            if self._is_remote:
                self._turso = TursoHttpClient(self.db_path, auth_token=self.auth_token)
            else:
                self._turso = None
            self._initialize()
            _log_seed("Repository initialized successfully.")
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            _log_seed(f"FATAL Repository Init Error: {str(exc)} | Traceback: {tb}")

    def _new_local_connection(self) -> sqlite3.Connection:
        """Create a local sqlite3 connection for file: databases."""
        db_path = self.db_path
        if db_path.startswith("file:"):
            db_path = db_path.replace("file://", "").replace("file:", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _read_connection(self):
        if self._is_remote:
            yield self._turso
        else:
            conn = self._new_local_connection()
            conn.execute("PRAGMA query_only = ON")
            try:
                yield conn
            finally:
                conn.close()

    @contextmanager
    def _write_connection(self):
        if self._is_remote:
            yield self._turso
        else:
            conn = self._new_local_connection()
            try:
                yield conn
            finally:
                conn.close()

    _DDL_STATEMENTS = [
        """CREATE TABLE IF NOT EXISTS measurements (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_measurements_station_datetime ON measurements(station_id, measured_at_utc)",
        """CREATE TABLE IF NOT EXISTS fetch_windows (
            station_id TEXT NOT NULL,
            start_utc TEXT NOT NULL,
            end_utc TEXT NOT NULL,
            fetched_at_utc TEXT NOT NULL,
            direction_checked INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (station_id, start_utc, end_utc)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_fetch_windows_station_fetched_at ON fetch_windows(station_id, fetched_at_utc)",
        """CREATE TABLE IF NOT EXISTS station_catalog (
            station_id TEXT NOT NULL PRIMARY KEY,
            station_name TEXT NOT NULL,
            province TEXT,
            latitude REAL,
            longitude REAL,
            altitude_m REAL,
            data_endpoint TEXT NOT NULL DEFAULT 'valores-climatologicos-inventario',
            is_antarctic_station INTEGER NOT NULL DEFAULT 0,
            fetched_at_utc TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_station_catalog_fetched_at ON station_catalog(fetched_at_utc)",
        """CREATE TABLE IF NOT EXISTS analysis_query_jobs (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_analysis_query_jobs_updated_at ON analysis_query_jobs(updated_at_utc)",
    ]

    def _initialize(self) -> None:
        if self._is_remote:
            # Check if tables already exist to avoid unnecessary DDL on every cold start
            try:
                self._turso.execute("SELECT 1 FROM measurements LIMIT 1")
                _log_seed("Tables already exist in Turso, skipping DDL.")
            except Exception:
                _log_seed("Tables not found, running DDL...")
                self._turso.batch_execute(self._DDL_STATEMENTS)

            # Migrate: strip +00:00 timezone suffixes from stored timestamps
            # so that string comparisons in WHERE clauses work correctly.
            # This is idempotent (REPLACE on clean data is a no-op).
            self._turso.batch_execute([
                "UPDATE fetch_windows SET start_utc = REPLACE(start_utc, '+00:00', ''), end_utc = REPLACE(end_utc, '+00:00', '') WHERE start_utc LIKE '%+00:00' OR end_utc LIKE '%+00:00'",
                "UPDATE measurements SET measured_at_utc = REPLACE(measured_at_utc, '+00:00', '') WHERE measured_at_utc LIKE '%+00:00'",
            ])
            _log_seed("Timestamp migration complete.")
        else:
            with self._write_connection() as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                for stmt in self._DDL_STATEMENTS:
                    conn.execute(stmt)
                conn.commit()

    @staticmethod
    def _ensure_columns(conn) -> None:
        try:
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(measurements)").fetchall()}
        except Exception:
            existing_columns = set()
            
        required_columns = {
            "direction_deg": "ALTER TABLE measurements ADD COLUMN direction_deg REAL",
            "latitude": "ALTER TABLE measurements ADD COLUMN latitude REAL",
            "longitude": "ALTER TABLE measurements ADD COLUMN longitude REAL",
            "altitude_m": "ALTER TABLE measurements ADD COLUMN altitude_m REAL",
        }
        for column, ddl in required_columns.items():
            if column not in existing_columns:
                try:
                    conn.execute(ddl)
                except Exception:
                    pass

    @staticmethod
    def _ensure_station_catalog_columns(conn) -> None:
        try:
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(station_catalog)").fetchall()}
        except Exception:
            existing_columns = set()
            
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
                try:
                    conn.execute(ddl)
                except Exception:
                    pass

    @staticmethod
    def _ensure_fetch_windows_columns(conn) -> None:
        try:
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fetch_windows)").fetchall()}
        except Exception:
            existing_columns = set()
            
        required_columns = {
            "direction_checked": "ALTER TABLE fetch_windows ADD COLUMN direction_checked INTEGER NOT NULL DEFAULT 0",
        }
        for column, ddl in required_columns.items():
            if column not in existing_columns:
                try:
                    conn.execute(ddl)
                except Exception:
                    pass

    def upsert_measurements(
        self,
        station_id: str,
        rows: list[SourceMeasurement],
        start_utc: datetime,
        end_utc: datetime,
    ) -> None:
        now_utc = _utc_iso(datetime.utcnow())
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
                        _utc_iso(row.measured_at_utc),
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
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc), now_utc, direction_checked),
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
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc)),
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
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc)),
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
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc)),
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
        now_utc = _utc_iso(datetime.utcnow())
        with self._write_connection() as conn:
            conn.execute(
                """
                UPDATE fetch_windows
                SET direction_checked = 1
                WHERE station_id = ?
                  AND start_utc <= ?
                  AND end_utc >= ?
                """,
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc)),
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
                    _utc_iso(start_utc),
                    _utc_iso(end_utc),
                    now_utc,
                    station_id,
                    _utc_iso(start_utc),
                    _utc_iso(end_utc),
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
                (station_id, _utc_iso(start_utc), _utc_iso(end_utc)),
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
                        _utc_iso(now_utc),
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
        now_utc = _utc_iso(datetime.now(timezone.utc))
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
