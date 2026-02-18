from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.models import SourceMeasurement, StationCatalogItem


class SQLiteRepository:
    def __init__(self, database_url: str) -> None:
        parsed = urlparse(database_url)
        if parsed.scheme != "sqlite":
            raise ValueError("Only sqlite database URLs are supported.")

        if parsed.path == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = parsed.path.lstrip("/") or "aemet_cache.db"

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
                    fetched_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_station_catalog_fetched_at ON station_catalog(fetched_at_utc)"
            )
            self._ensure_columns(conn)
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

    def upsert_measurements(
        self,
        station_id: str,
        rows: list[SourceMeasurement],
        start_utc: datetime,
        end_utc: datetime,
    ) -> None:
        now_utc = datetime.utcnow().isoformat()
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
                INSERT INTO fetch_windows (station_id, start_utc, end_utc, fetched_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(station_id, start_utc, end_utc)
                DO UPDATE SET fetched_at_utc = excluded.fetched_at_utc
                """,
                (station_id, start_utc.isoformat(), end_utc.isoformat(), now_utc),
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
        return fetched_at >= min_fetched_at_utc

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
        with self._write_connection() as conn:
            conn.executemany(
                """
                INSERT INTO station_catalog (
                    station_id, station_name, province, latitude, longitude, altitude_m, fetched_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id)
                DO UPDATE SET
                    station_name=excluded.station_name,
                    province=excluded.province,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    altitude_m=excluded.altitude_m,
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
                SELECT station_id, station_name, province, latitude, longitude, altitude_m
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
            )
            for row in result
        ]
