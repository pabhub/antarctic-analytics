from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import (
    MeasurementType,
    PlaybackStep,
    SourceMeasurement,
    Station,
    StationCatalogItem,
    TimeAggregation,
    TimeframeGroupBy,
    WindFarmSimulationParams,
)
from app.services.antarctic_service import AntarcticService
from app.core.config import Settings

UTC = ZoneInfo("UTC")


class FakeRepo:
    def __init__(self, rows, has_fresh_cache=False):
        self.rows = rows
        self.has_fresh_cache = has_fresh_cache
        self.upsert_calls = 0
        self.station_rows = []
        self.station_fresh = False
        self.station_fetched_at = None
        self.latest_measurement = None
        self.query_jobs = {}

    def has_fresh_fetch_window(self, station_id, start_utc, end_utc, min_fetched_at_utc):
        return self.has_fresh_cache

    def has_cached_fetch_window(self, station_id, start_utc, end_utc):
        return self.has_fresh_cache

    def upsert_measurements(self, station_id, rows, start_utc, end_utc):
        self.rows = rows
        self.upsert_calls += 1
        self.has_fresh_cache = True
        if rows:
            self.latest_measurement = max(row.measured_at_utc for row in rows)

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

    def get_station_catalog_item(self, station_id):
        for row in self.station_rows:
            if row.station_id == station_id:
                return row
        return None

    def get_latest_measurement_timestamp(self, station_id):
        if self.latest_measurement is not None:
            return self.latest_measurement
        if not self.rows:
            return None
        return max(row.measured_at_utc for row in self.rows)

    def get_latest_measurement(self, station_id):
        if not self.rows:
            return None
        return max(self.rows, key=lambda row: row.measured_at_utc)

    def upsert_analysis_query_job(self, payload):
        payload = dict(payload)
        payload["updated_at_utc"] = datetime(2024, 1, 1, 0, 0, tzinfo=UTC).isoformat()
        self.query_jobs[payload["job_id"]] = payload

    def get_analysis_query_job(self, job_id):
        return self.query_jobs.get(job_id)


class WindowAwareRepo(FakeRepo):
    def __init__(self, rows):
        super().__init__(rows, has_fresh_cache=False)
        self._cached_windows = set()

    def has_cached_fetch_window(self, station_id, start_utc, end_utc):
        return (station_id, start_utc, end_utc) in self._cached_windows

    def upsert_measurements(self, station_id, rows, start_utc, end_utc):
        self.rows = rows
        self.upsert_calls += 1
        self._cached_windows.add((station_id, start_utc, end_utc))
        if rows:
            self.latest_measurement = max(row.measured_at_utc for row in rows)


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


class FakeSequentialLatestClient:
    def __init__(self, sequences):
        self.sequences = list(sequences)
        self.calls = 0

    def fetch_station_data(self, start_utc, end_utc, station_id):
        self.calls += 1
        if self.sequences:
            return self.sequences.pop(0)
        return []

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
    return AntarcticService(settings, repo, client), repo, client


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


def test_daily_aggregation_uses_station_local_boundary():
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

    assert len(out) == 2
    assert out[0].datetime_cet.isoformat().endswith("+01:00")
    assert out[1].datetime_cet.isoformat().endswith("+02:00")
    assert out[0].temperature_c == 2.0
    assert out[1].temperature_c == 4.0


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
    repo = WindowAwareRepo([])
    client = FakeSequentialLatestClient([rows])
    service = AntarcticService(settings, repo, client)

    out = service.get_latest_availability(Station.GABRIEL_DE_CASTILLA)

    assert out.station == Station.GABRIEL_DE_CASTILLA
    assert out.newest_observation_utc == newest
    assert out.suggested_end_utc == newest
    assert out.suggested_start_utc is not None
    assert out.suggested_end_utc >= out.suggested_start_utc
    assert out.suggested_aggregation == TimeAggregation.NONE
    assert out.probe_window_hours is not None
    assert out.probe_window_hours > 0
    assert client.calls == 1


def test_latest_availability_prefers_cached_latest_timestamp():
    newest = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=True)
    repo.latest_measurement = newest
    client = FakeLatestClient({})
    service = AntarcticService(settings, repo, client)

    out = service.get_latest_availability(Station.GABRIEL_DE_CASTILLA)

    assert out.newest_observation_utc == newest
    assert out.probe_window_hours == 0
    assert client.calls == 0


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
    repo = WindowAwareRepo([])
    client = FakeLatestClient({})
    service = AntarcticService(settings, repo, client)

    out = service.get_latest_availability(Station.JUAN_CARLOS_I)

    assert out.station == Station.JUAN_CARLOS_I
    assert out.newest_observation_utc is None
    assert out.suggested_start_utc is None
    assert out.suggested_end_utc is None
    assert out.suggested_aggregation is None
    assert out.probe_window_hours is None
    assert "No observations" in out.note
    assert client.calls >= 1


def test_latest_availability_backscans_prior_windows_when_recent_window_is_empty():
    checked = datetime.now(UTC).replace(microsecond=0)
    older = checked - timedelta(days=35)
    rows = [
        SourceMeasurement(
            station_name="X",
            measured_at_utc=older,
            temperature_c=-4.0,
            speed_mps=6.0,
            direction_deg=180.0,
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
    repo = WindowAwareRepo([])
    client = FakeSequentialLatestClient([[], rows])
    service = AntarcticService(settings, repo, client)

    out = service.get_latest_availability(Station.JUAN_CARLOS_I)

    assert out.newest_observation_utc == older
    assert out.probe_window_hours is not None
    assert out.probe_window_hours >= 720
    assert client.calls == 2


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
    service = AntarcticService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=False)
    by_id = {row.station_id: row for row in out.data}

    assert out.cache_hit is True
    assert client.calls == 0
    assert "9999A" not in by_id
    assert "1" in by_id
    assert "2" in by_id


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
    service = AntarcticService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=True)
    by_id = {row.station_id: row for row in out.data}

    assert out.cache_hit is False
    assert client.calls == 1
    assert "1234X" not in by_id
    assert "1" in by_id
    assert "2" in by_id


def test_station_catalog_marks_antarctic_stations_with_endpoint_source():
    rows = [
        StationCatalogItem(stationId="1", stationName="GABRIEL DE CASTILLA"),
        StationCatalogItem(stationId="1234X", stationName="Remote Station", province="Cadiz"),
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
    client = FakeInventoryClient(rows)
    service = AntarcticService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=True)
    by_id = {row.station_id: row for row in out.data}

    assert by_id["1"].is_antarctic_station is True
    assert by_id["1"].data_endpoint == "antartida"
    assert by_id["1"].province == "ANTARCTIC"
    assert "1234X" not in by_id


def test_station_catalog_seeds_known_antarctic_station_ids_when_missing_from_inventory():
    rows = [StationCatalogItem(stationId="1234X", stationName="Remote Station")]
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
    service = AntarcticService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=True)
    by_id = {row.station_id: row for row in out.data}

    assert "1" in by_id
    assert "2" in by_id
    assert by_id["1"].is_antarctic_station is True
    assert by_id["2"].is_antarctic_station is True
    assert by_id["1"].data_endpoint == "antartida"
    assert by_id["2"].data_endpoint == "antartida"


def test_get_data_rejects_non_antarctic_station_when_catalog_marks_other_endpoint():
    rows = [SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC), temperature_c=1.0)]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.station_rows = [
        StationCatalogItem(
            stationId="1234X",
            stationName="Remote Station",
            dataEndpoint="valores-climatologicos-inventario",
            isAntarcticStation=False,
        )
    ]

    try:
        service.get_data(
            station="1234X",
            start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            aggregation=TimeAggregation.NONE,
            selected_types=[],
        )
        assert False, "Expected ValueError for non-Antarctic station"
    except ValueError as exc:
        assert "not classified for AEMET Antarctic endpoint" in str(exc)


def test_get_data_rejects_station_not_in_antarctic_catalog():
    rows = [SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC), temperature_c=1.0)]
    service, _, _ = build_service(rows, has_fresh_cache=True)

    try:
        service.get_data(
            station="9999X",
            start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            aggregation=TimeAggregation.NONE,
            selected_types=[],
        )
        assert False, "Expected ValueError for station missing from Antarctic catalog"
    except ValueError as exc:
        assert "not present in Antarctic station catalog" in str(exc)


def test_known_antarctic_ids_are_seeded_with_coordinates():
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="89070",
        juan_station_id="89064",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo([], has_fresh_cache=False)
    client = FakeInventoryClient([])
    service = AntarcticService(settings, repo, client)

    out = service.get_station_catalog(force_refresh=True)
    by_id = {row.station_id: row for row in out.data}

    assert "89064" in by_id
    assert "89064R" in by_id
    assert "89064RA" in by_id
    assert "89070" in by_id
    assert by_id["89064"].latitude is not None
    assert by_id["89064R"].latitude is not None
    assert by_id["89070"].latitude is not None


def test_second_request_for_same_loaded_window_uses_cache_without_upstream_call():
    rows = [SourceMeasurement(station_name="X", measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC), temperature_c=1.0)]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="1",
        juan_station_id="2",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo(rows, has_fresh_cache=False)
    repo.station_rows = [StationCatalogItem(stationId="1", stationName="Test Antarctic", dataEndpoint="antartida", isAntarcticStation=True)]
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)

    service.get_data(station="1", start_local=start, end_local=end, aggregation=TimeAggregation.NONE, selected_types=[])
    service.get_data(station="1", start_local=start, end_local=end, aggregation=TimeAggregation.NONE, selected_types=[])

    assert client.calls == 1


def test_get_data_fetches_full_calendar_month_windows_and_reuses_cached_windows():
    rows = [
        SourceMeasurement(
            station_name="X",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
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
    repo = WindowAwareRepo(rows)
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    start = datetime(2024, 1, 19, 0, 0, tzinfo=UTC)
    end = datetime(2024, 3, 15, 0, 0, tzinfo=UTC)

    service.get_data(station="1", start_local=start, end_local=end, aggregation=TimeAggregation.NONE, selected_types=[])
    first_pass_calls = client.calls
    first_pass_upserts = repo.upsert_calls
    assert first_pass_calls == 3  # Jan, Feb, Mar full-month windows
    assert first_pass_upserts == 3

    service.get_data(station="1", start_local=start, end_local=end, aggregation=TimeAggregation.NONE, selected_types=[])
    assert client.calls == first_pass_calls
    assert repo.upsert_calls == first_pass_upserts


def test_analysis_bootstrap_exposes_two_selectable_stations_and_two_map_overlays():
    rows = [
        SourceMeasurement(
            station_name="Juan Carlos I",
            measured_at_utc=datetime(2024, 1, 10, 0, 0, tzinfo=UTC),
            temperature_c=-3.0,
            pressure_hpa=990.0,
            speed_mps=5.0,
            direction_deg=180.0,
            latitude=-62.66325,
            longitude=-60.38959,
            altitude_m=12.0,
        )
    ]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="89070",
        juan_station_id="89064",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo(rows, has_fresh_cache=True)
    repo.latest_measurement = rows[0].measured_at_utc
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    out = service.get_analysis_bootstrap()

    assert out.selectable_station_ids == ["89064", "89070"]
    assert out.map_station_ids == ["89064", "89070"]
    assert any(item.station_id == "89064RA" for item in out.stations)


def test_analysis_bootstrap_survives_warm_cache_failure():
    rows = [
        SourceMeasurement(
            station_name="Juan Carlos I",
            measured_at_utc=datetime(2024, 1, 10, 0, 0, tzinfo=UTC),
            speed_mps=5.0,
        )
    ]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="89070",
        juan_station_id="89064",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo(rows, has_fresh_cache=True)
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError("boom")

    service._warm_cache_for_station_ids = _raise_unexpected

    out = service.get_analysis_bootstrap()

    assert out.selectable_station_ids == ["89064", "89070"]
    assert out.map_station_ids == ["89064", "89070"]
    assert len(out.stations) == 4


def test_feasibility_snapshot_rejects_non_selectable_station():
    rows = [
        SourceMeasurement(
            station_name="Supplemental",
            measured_at_utc=datetime(2024, 1, 10, 0, 0, tzinfo=UTC),
            speed_mps=4.0,
            direction_deg=120.0,
        )
    ]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="89070",
        juan_station_id="89064",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo(rows, has_fresh_cache=True)
    repo.latest_measurement = rows[0].measured_at_utc
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    try:
        service.get_feasibility_snapshot(
            station="89064R",
            start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            aggregation=TimeAggregation.HOURLY,
            selected_types=[],
            timezone_input="UTC",
        )
        assert False, "Expected ValueError for non-selectable station."
    except ValueError as exc:
        assert "not selectable" in str(exc)


def test_feasibility_snapshot_caps_end_and_returns_two_series():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 20, 0, 0, tzinfo=UTC),
            temperature_c=-2.0,
            pressure_hpa=995.0,
            speed_mps=6.0,
            direction_deg=210.0,
            latitude=-62.97,
            longitude=-60.67,
            altitude_m=12.0,
        )
    ]
    settings = Settings(
        aemet_api_key="dummy",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=1.0,
        gabriel_station_id="89070",
        juan_station_id="89064",
        cache_freshness_seconds=3600,
        station_catalog_freshness_seconds=7 * 24 * 60 * 60,
    )
    repo = FakeRepo(rows, has_fresh_cache=True)
    repo.latest_measurement = rows[0].measured_at_utc
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    out = service.get_feasibility_snapshot(
        station="89064",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        aggregation=TimeAggregation.HOURLY,
        selected_types=[],
        timezone_input="UTC",
    )

    assert out.selected_station_id == "89064"
    assert out.effective_end_local <= datetime(2024, 1, 31, 0, 0, tzinfo=UTC)
    assert out.map_station_ids == ["89064", "89070"]
    assert len(out.stations) == 2


def test_playback_step_is_upsized_for_long_frame_ranges():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=6.0,
            direction_deg=180.0,
            temperature_c=-3.0,
            pressure_hpa=995.0,
        )
    ]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.latest_measurement = datetime(2024, 1, 30, 0, 0, tzinfo=UTC)
    out = service.get_playback_frames(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 30, 0, 0, tzinfo=UTC),
        step=PlaybackStep.TEN_MINUTES,
        timezone_input="UTC",
    )
    assert out.effective_step in {PlaybackStep.HOURLY, PlaybackStep.THREE_HOURLY, PlaybackStep.DAILY}


def test_playback_wind_rose_uses_toward_heading_without_double_conversion():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=6.0,
            direction_deg=0.0,
            temperature_c=-3.0,
            pressure_hpa=995.0,
        )
    ]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.latest_measurement = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)

    out = service.get_playback_frames(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        step=PlaybackStep.HOURLY,
        timezone_input="UTC",
    )

    assert out.frames
    assert out.frames[0].direction_deg == 180.0
    assert out.wind_rose.dominant_sector == "S"


def test_three_hour_playback_keeps_toward_heading_consistent():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=6.0,
            direction_deg=0.0,
            temperature_c=-3.0,
            pressure_hpa=995.0,
        ),
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            speed_mps=6.2,
            direction_deg=0.0,
            temperature_c=-2.8,
            pressure_hpa=995.2,
        ),
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 2, 0, tzinfo=UTC),
            speed_mps=5.8,
            direction_deg=0.0,
            temperature_c=-3.1,
            pressure_hpa=994.8,
        ),
    ]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.latest_measurement = datetime(2024, 1, 1, 3, 0, tzinfo=UTC)

    out = service.get_playback_frames(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 3, 0, tzinfo=UTC),
        step=PlaybackStep.THREE_HOURLY,
        timezone_input="UTC",
    )

    assert out.frames
    assert out.frames[0].direction_deg == 180.0
    assert out.wind_rose.dominant_sector == "S"


def test_timeframe_analytics_returns_generation_when_simulation_params_passed():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=7.0,
            direction_deg=180.0,
            temperature_c=-2.0,
            pressure_hpa=990.0,
        ),
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 10, tzinfo=UTC),
            speed_mps=8.0,
            direction_deg=190.0,
            temperature_c=-1.0,
            pressure_hpa=991.0,
        ),
    ]
    service, _, _ = build_service(rows, has_fresh_cache=True)
    params = WindFarmSimulationParams(
        turbineCount=6,
        ratedPowerKw=900,
        cutInSpeedMps=3.0,
        ratedSpeedMps=12.0,
        cutOutSpeedMps=25.0,
    )
    out = service.get_timeframe_analytics(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        group_by=TimeframeGroupBy.HOUR,
        timezone_input="UTC",
        simulation_params=params,
    )
    assert out.buckets
    assert out.buckets[0].estimated_generation_mwh is not None


def test_timeframe_generation_accounts_for_air_density_correction():
    cold_dense_rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=8.0,
            direction_deg=180.0,
            temperature_c=-20.0,
            pressure_hpa=1030.0,
        )
    ]
    warm_thin_rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=8.0,
            direction_deg=180.0,
            temperature_c=15.0,
            pressure_hpa=980.0,
        )
    ]
    cold_service, _, _ = build_service(cold_dense_rows, has_fresh_cache=True)
    warm_service, _, _ = build_service(warm_thin_rows, has_fresh_cache=True)
    params = WindFarmSimulationParams(
        turbineCount=6,
        ratedPowerKw=900,
        cutInSpeedMps=3.0,
        ratedSpeedMps=12.0,
        cutOutSpeedMps=25.0,
        referenceAirDensityKgM3=1.225,
    )
    cold = cold_service.get_timeframe_analytics(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        group_by=TimeframeGroupBy.HOUR,
        timezone_input="UTC",
        simulation_params=params,
    )
    warm = warm_service.get_timeframe_analytics(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        group_by=TimeframeGroupBy.HOUR,
        timezone_input="UTC",
        simulation_params=params,
    )
    assert cold.buckets[0].estimated_generation_mwh is not None
    assert warm.buckets[0].estimated_generation_mwh is not None
    assert cold.buckets[0].estimated_generation_mwh > warm.buckets[0].estimated_generation_mwh


def test_timeframe_generation_respects_operating_temperature_pressure_limits():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            speed_mps=12.0,
            direction_deg=180.0,
            temperature_c=-50.0,
            pressure_hpa=790.0,
        )
    ]
    service, _, _ = build_service(rows, has_fresh_cache=True)
    params = WindFarmSimulationParams(
        turbineCount=6,
        ratedPowerKw=900,
        cutInSpeedMps=3.0,
        ratedSpeedMps=12.0,
        cutOutSpeedMps=25.0,
        minOperatingTempC=-40.0,
        maxOperatingTempC=45.0,
        minOperatingPressureHpa=850.0,
        maxOperatingPressureHpa=1085.0,
    )
    out = service.get_timeframe_analytics(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        group_by=TimeframeGroupBy.HOUR,
        timezone_input="UTC",
        simulation_params=params,
    )
    assert out.buckets
    assert out.buckets[0].estimated_generation_mwh == 0.0


def test_create_query_job_returns_cached_ready_when_window_already_available():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 15, 0, 0, tzinfo=UTC),
            speed_mps=5.0,
            direction_deg=200.0,
        )
    ]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.latest_measurement = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
    out = service.create_query_job(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=None,
        timezone_input="UTC",
        playback_step=PlaybackStep.HOURLY,
        aggregation=TimeAggregation.HOURLY,
        selected_types=[],
    )
    assert out.playback_ready is True
    assert out.total_api_calls_planned == 0


def test_create_query_job_uses_client_end_without_latest_probe():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 15, 0, 0, tzinfo=UTC),
            speed_mps=5.0,
            direction_deg=200.0,
        )
    ]
    service, repo, _ = build_service(rows, has_fresh_cache=True)
    repo.latest_measurement = None

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("latest availability probe should not run when end_local is provided")

    service.get_latest_availability = _raise_if_called

    out = service.create_query_job(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 1, 31, 0, 0, tzinfo=UTC),
        timezone_input="UTC",
        playback_step=PlaybackStep.HOURLY,
        aggregation=TimeAggregation.HOURLY,
        selected_types=[],
    )
    assert out.playback_ready is True
    assert out.total_windows == 1


def test_query_job_progresses_via_status_polling_when_background_workers_disabled():
    rows = [
        SourceMeasurement(
            station_name="Station A",
            measured_at_utc=datetime(2024, 1, 15, 0, 0, tzinfo=UTC),
            speed_mps=5.0,
            direction_deg=200.0,
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
        query_jobs_background_enabled=False,
    )
    repo = WindowAwareRepo(rows)
    client = FakeClient(rows)
    service = AntarcticService(settings, repo, client)

    created = service.create_query_job(
        station="1",
        start_local=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_local=datetime(2024, 3, 1, 0, 0, tzinfo=UTC),
        timezone_input="UTC",
        playback_step=PlaybackStep.HOURLY,
        aggregation=TimeAggregation.HOURLY,
        selected_types=[],
    )
    assert created.status.value == "pending"
    assert created.missing_windows > 0

    status = service.get_query_job_status(created.job_id)
    assert status.completed_windows >= 1

    for _ in range(8):
        status = service.get_query_job_status(created.job_id)
        if status.status.value == "complete":
            break

    assert status.status.value == "complete"
    assert status.completed_windows == status.total_windows
    # Bulk pre-fetch: one AEMET call covers all missing windows,
    # instead of one call per window.
    assert client.calls == 1
