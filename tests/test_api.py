from fastapi.testclient import TestClient

from app.main import app, get_service
from app.models import MeasurementType, OutputMeasurement, Station, TimeAggregation


class FakeService:
    def get_data(self, station, start_local, end_local, aggregation, selected_types):
        return [
            OutputMeasurement(
                stationName="Dummy",
                datetime=start_local,
                temperature=1.0,
                pressure=2.0 if not selected_types or MeasurementType.PRESSURE in selected_types else None,
                speed=3.0,
                direction=180.0,
                latitude=-62.97,
                longitude=-60.68,
                altitude=15.0,
            )
        ]


class ErrorService:
    def get_data(self, station, start_local, end_local, aggregation, selected_types):
        raise RuntimeError("AEMET response missing 'datos' URL. estado=401")


class AvailabilityService:
    def get_latest_availability(self, station):
        return {
            "station": station.value,
            "checked_at_utc": "2026-02-18T10:00:00+00:00",
            "newest_observation_utc": "2026-02-18T08:50:00+00:00",
            "suggested_start_utc": "2026-02-17T08:50:00+00:00",
            "suggested_end_utc": "2026-02-18T08:50:00+00:00",
            "probe_window_hours": 24,
            "suggested_aggregation": "none",
            "note": "Suggested window targets latest available observations from AEMET.",
        }


app.dependency_overrides[get_service] = lambda: FakeService()
client = TestClient(app)


def test_endpoint_happy_path():
    response = client.get(
        "/api/antartida/datos/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
        params={"location": "UTC", "aggregation": "none", "types": ["pressure"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["station"] == Station.GABRIEL_DE_CASTILLA.value
    assert payload["aggregation"] == TimeAggregation.NONE.value


def test_endpoint_invalid_timezone():
    response = client.get(
        "/api/antartida/datos/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
        params={"location": "Mars/Base"},
    )
    assert response.status_code == 400


def test_available_data_metadata_endpoint():
    response = client.get("/api/metadata/available-data")
    assert response.status_code == 200
    payload = response.json()
    assert "nombre" in payload["currently_exposed_fields"]
    assert "lat/latitud" in payload["currently_exposed_fields"]
    assert "dir" in payload["currently_exposed_fields"]
    assert "hr" in payload["additional_fields_often_available"]


def test_export_csv_returns_downloadable_file():
    response = client.get(
        "/api/antartida/export/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
        params={"location": "UTC", "aggregation": "none", "format": "csv", "types": ["pressure"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "stationName,datetime,temperature,pressure,speed,direction,latitude,longitude,altitude" in response.text
    assert "Dummy" in response.text


def test_export_parquet_returns_not_implemented_without_extra_deps():
    response = client.get(
        "/api/antartida/export/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
        params={"location": "UTC", "aggregation": "none", "format": "parquet"},
    )

    assert response.status_code in {200, 501}
    if response.status_code == 501:
        assert "Parquet export requires" in response.json()["detail"]


def test_endpoint_runtime_error_returns_502():
    app.dependency_overrides[get_service] = lambda: ErrorService()
    try:
        response = client.get(
            "/api/antartida/datos/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
            params={"location": "UTC"},
        )
        assert response.status_code == 502
        assert "missing 'datos'" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_service] = lambda: FakeService()


def test_export_runtime_error_returns_502():
    app.dependency_overrides[get_service] = lambda: ErrorService()
    try:
        response = client.get(
            "/api/antartida/export/fechaini/2024-01-01T00:00:00/fechafin/2024-01-01T01:00:00/estacion/gabriel-de-castilla",
            params={"location": "UTC", "format": "csv"},
        )
        assert response.status_code == 502
        assert "missing 'datos'" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_service] = lambda: FakeService()


def test_latest_availability_endpoint_returns_payload():
    app.dependency_overrides[get_service] = lambda: AvailabilityService()
    try:
        response = client.get("/api/metadata/latest-availability/station/gabriel-de-castilla")
        assert response.status_code == 200
        payload = response.json()
        assert payload["station"] == "gabriel-de-castilla"
        assert payload["newest_observation_utc"] == "2026-02-18T08:50:00Z"
        assert payload["suggested_start_utc"] == "2026-02-17T08:50:00Z"
    finally:
        app.dependency_overrides[get_service] = lambda: FakeService()
