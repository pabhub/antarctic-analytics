from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import MeasurementType, SourceMeasurement, Station, TimeAggregation
from app.service import AntartidaService
from app.settings import Settings

UTC = ZoneInfo("UTC")


class FakeRepo:
    def __init__(self, rows, has_fresh_cache=False):
        self.rows = rows
        self.has_fresh_cache = has_fresh_cache
        self.upsert_calls = 0

    def has_fresh_fetch_window(self, station_id, start_utc, end_utc, min_fetched_at_utc):
        return self.has_fresh_cache

    def upsert_measurements(self, station_id, rows, start_utc, end_utc):
        self.rows = rows
        self.upsert_calls += 1

    def get_measurements(self, station_id, start_utc, end_utc):
        return self.rows


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_station_data(self, start_utc, end_utc, station_id):
        self.calls += 1
        return self.rows


def build_service(rows, has_fresh_cache=False):
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
    )
    repo = FakeRepo(rows, has_fresh_cache=has_fresh_cache)
    client = FakeClient(rows)
    return AntartidaService(settings, repo, client), repo, client


def test_no_aggregation_returns_all_types_by_default():
    rows = [
        SourceMeasurement(
            station_name="X",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            temperature_c=1,
            pressure_hpa=2,
            speed_mps=3,
            direction_deg=45,
        )
    ]
    service, _, _ = build_service(rows)

    out = service.get_data(
        station=Station.GABRIEL_DE_CASTILLA,
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        aggregation=TimeAggregation.NONE,
        selected_types=[],
    )

    assert len(out) == 1
    assert out[0].temperature_c == 1
    assert out[0].pressure_hpa == 2
    assert out[0].speed_mps == 3
    assert out[0].direction_deg == 45


def test_hourly_aggregation_and_filter_types():
    rows = [
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 5, tzinfo=UTC), temperature_c=10.0, pressure_hpa=1000.0, speed_mps=5.0, direction_deg=350),
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 15, tzinfo=UTC), temperature_c=14.0, pressure_hpa=1002.0, speed_mps=7.0, direction_deg=10),
    ]
    service, _, _ = build_service(rows)

    out = service.get_data(
        station=Station.JUAN_CARLOS_I,
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        aggregation=TimeAggregation.HOURLY,
        selected_types=[MeasurementType.TEMPERATURE, MeasurementType.DIRECTION],
    )

    assert len(out) == 1
    assert out[0].temperature_c == 12.0
    assert out[0].pressure_hpa is None
    assert out[0].direction_deg in {0.0, 360.0}


def test_daily_aggregation_uses_europe_madrid_dst_boundary():
    rows = [
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 3, 30, 23, 30, tzinfo=UTC), temperature_c=2.0, pressure_hpa=1000.0, speed_mps=1.0),
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 3, 31, 21, 30, tzinfo=UTC), temperature_c=4.0, pressure_hpa=1002.0, speed_mps=3.0),
    ]
    service, _, _ = build_service(rows)

    out = service.get_data(
        station=Station.GABRIEL_DE_CASTILLA,
        start_local=datetime(2024, 3, 30, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 4, 1, 0, 0, tzinfo=UTC),
        aggregation=TimeAggregation.DAILY,
        selected_types=[],
    )

    assert len(out) == 1
    assert out[0].datetime_cet.isoformat().endswith("+01:00")
    assert out[0].temperature_c == 3.0


def test_geospatial_fields_are_exposed_for_mapping():
    rows = [
        SourceMeasurement(
            station_name="X",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            temperature_c=1,
            pressure_hpa=2,
            speed_mps=3,
            latitude=-62.97,
            longitude=-60.68,
            altitude_m=15.0,
        )
    ]
    service, _, _ = build_service(rows)

    out = service.get_data(
        station=Station.GABRIEL_DE_CASTILLA,
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        aggregation=TimeAggregation.NONE,
        selected_types=[],
    )

    assert len(out) == 1
    assert out[0].latitude == -62.97
    assert out[0].longitude == -60.68
    assert out[0].altitude_m == 15.0


def test_cache_hit_skips_remote_fetch():
    rows = [
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC), temperature_c=1.0)
    ]
    service, repo, client = build_service(rows, has_fresh_cache=True)

    out = service.get_data(
        station=Station.GABRIEL_DE_CASTILLA,
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        aggregation=TimeAggregation.NONE,
        selected_types=[],
    )

    assert len(out) == 1
    assert client.calls == 0
    assert repo.upsert_calls == 0


def test_cache_miss_fetches_remote_and_updates_db():
    rows = [
        SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC), temperature_c=1.0)
    ]
    service, repo, client = build_service(rows, has_fresh_cache=False)

    service.get_data(
        station=Station.GABRIEL_DE_CASTILLA,
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        aggregation=TimeAggregation.NONE,
        selected_types=[],
    )

    assert client.calls == 1
    assert repo.upsert_calls == 1
