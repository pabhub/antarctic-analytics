from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import MeasurementType, SourceMeasurement, Station, StationCatalogItem, TimeAggregation
from app.service import AntartidaService
from app.settings import Settings

UTC = ZoneInfo("UTC")


class FakeRepo:
    def __init__(self, rows, has_fresh_cache=False):
        self.rows = rows
        self.has_fresh_cache = has_fresh_cache
        self.upsert_calls = 0
        self.station_rows = []
        self.station_fresh = False
        self.station_fetched_at = None

    def has_fresh_fetch_window(self, station_id, start_utc, end_utc, min_fetched_at_utc):
        return self.has_fresh_cache

    def upsert_measurements(self, station_id, rows, start_utc, end_utc):
        self.rows = rows
        self.upsert_calls += 1

    def get_measurements(self, station_id, start_utc, end_utc):
        return self.rows

    def has_fresh_station_catalog(self, min_fetched_at_utc):
        return self.station_fresh

    def get_station_catalog(self):
        return self.station_rows

    def get_station_catalog_last_fetched_at(self):
        return self.station_fetched_at

    def upsert_station_catalog(self, rows):
        self.station_rows = rows
        self.station_fresh = True
        self.station_fetched_at = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        return self.station_fetched_at


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_station_data(self, start_utc, end_utc, station_id):
        self.calls += 1
        return self.rows

    def fetch_station_inventory(self):
        return []


class FakeLatestClient:
    def __init__(self, by_hours):
        self.by_hours = by_hours
        self.calls = 0

    def fetch_station_data(self, start_utc, end_utc, station_id):
        self.calls += 1
        window_hours = int(round((end_utc - start_utc).total_seconds() / 3600))
        return self.by_hours.get(window_hours, [])

    def fetch_station_inventory(self):
        return []


class FakeInventoryClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_station_data(self, start_utc, end_utc, station_id):
        return []

    def fetch_station_inventory(self):
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
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
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


def test_latest_availability_returns_suggested_window_when_data_found():
    newest = datetime.now(UTC).replace(microsecond=0)
    rows = [
        SourceMeasurement(
            station_name="X",
            measured_at_utc=newest,
            temperature_c=1.0,
        )
    ]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=False)
    client = FakeLatestClient({24: rows})
    service = AntartidaService(settings, repo, client)

    out = service.get_latest_availability(Station.GABRIEL_DE_CASTILLA)

    assert out.station == Station.GABRIEL_DE_CASTILLA
    assert out.newest_observation_utc == newest
    assert out.suggested_end_utc == newest
    assert out.suggested_start_utc is not None
    assert out.suggested_end_utc >= out.suggested_start_utc
    assert out.suggested_aggregation == TimeAggregation.NONE
    assert out.probe_window_hours == 24


def test_latest_availability_no_data_returns_note():
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=False)
    client = FakeLatestClient({})
    service = AntartidaService(settings, repo, client)

    out = service.get_latest_availability(Station.JUAN_CARLOS_I)

    assert out.station == Station.JUAN_CARLOS_I
    assert out.newest_observation_utc is None
    assert out.suggested_start_utc is None
    assert out.suggested_end_utc is None
    assert out.suggested_aggregation is None
    assert out.probe_window_hours is None
    assert "No observations" in out.note


def test_station_catalog_cache_hit_uses_db_rows():
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=False)
    repo.station_fresh = True
    repo.station_rows = [StationCatalogItem(stationId="9999A", stationName="Test Station")]
    repo.station_fetched_at = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    client = FakeInventoryClient([])
    service = AntartidaService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=False)

    assert out.cache_hit is True
    assert client.calls == 0
    assert len(out.data) == 1
    assert out.data[0].station_id == "9999A"


def test_station_catalog_force_refresh_fetches_remote_and_updates_cache():
    rows = [StationCatalogItem(stationId="1234X", stationName="Remote Station", province="Cadiz")]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=False)
    client = FakeInventoryClient(rows)
    service = AntartidaService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=True)

    assert out.cache_hit is False
    assert client.calls == 1
    assert len(out.data) == 1
    assert out.data[0].station_id == "1234X"
