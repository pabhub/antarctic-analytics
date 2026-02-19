from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.aemet_client import AemetClient

UTC = ZoneInfo("UTC")


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttpClient:
    """Fake httpx.Client that returns canned responses in sequence."""

    def __init__(self, responses):
        self._responses = responses
        self._idx = 0

    def get(self, *_args, **_kwargs):
        response = self._responses[self._idx]
        self._idx += 1
        return response

    def close(self):
        pass


def _make_client(responses, **kwargs):
    """Create an AemetClient with a fake HTTP client injected."""
    client = AemetClient(**kwargs)
    client._http_client = FakeHttpClient(responses)
    # Reset class-level throttle state so tests don't interfere with each other.
    AemetClient._last_request_monotonic = 0.0
    AemetClient._rate_limited_until_monotonic = 0.0
    return client


def test_retry_after_is_capped_to_configured_limiter_interval():
    client = AemetClient(
        api_key="ok-key",
        min_request_interval_seconds=2.0,
        retry_after_cap_seconds=2.0,
    )
    response = FakeResponse({}, status_code=429, headers={"Retry-After": "60"})
    assert client._retry_after_seconds(response) == 2.0


def test_fetch_station_data_raises_clear_error_when_metadata_has_no_datos():
    responses = [FakeResponse({"estado": 401, "descripcion": "API key no válida"})]
    client = _make_client(responses, api_key="bad-key")
    with pytest.raises(RuntimeError, match="missing 'datos' URL"):
        client.fetch_station_data(
            start_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            end_utc=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            station_id="89064",
        )


def test_fetch_station_data_returns_empty_for_aemet_no_data_404():
    responses = [FakeResponse({"estado": 404, "descripcion": "No hay datos que satisfagan esos criterios"})]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_data(
        start_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        end_utc=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
        station_id="89064",
    )
    assert out == []


def test_fetch_station_inventory_parses_station_rows():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.json"}),
        FakeResponse(
            [
                {
                    "indicativo": "89064",
                    "nombre": "GABRIEL DE CASTILLA",
                    "provincia": "ANTARTIDA",
                    "latitud": "-62.97",
                    "longitud": "-60.68",
                    "altitud": "14",
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_inventory()

    assert len(out) == 1
    assert out[0].station_id == "89064"
    assert out[0].station_name == "GABRIEL DE CASTILLA"
    assert out[0].province == "ANTARCTIC"


def test_fetch_station_inventory_parses_csv_payload():
    csv_payload = (
        "indicativo;nombre;provincia;latitud;longitud;altitud\n"
        "89070;JUAN CARLOS I;ANTARTIDA;625640S;603524W;12\n"
    )
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.csv"}),
        FakeResponse(csv_payload),
    ]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_inventory()

    assert len(out) == 1
    assert out[0].station_id == "89070"
    assert out[0].station_name == "JUAN CARLOS I"
    assert out[0].latitude is not None
    assert out[0].longitude is not None


def test_fetch_station_inventory_handles_uppercase_json_keys():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.json"}),
        FakeResponse(
            [
                {
                    "INDICATIVO": "89064",
                    "NOMBRE": "GABRIEL DE CASTILLA",
                    "PROVINCIA": "ANTARTIDA",
                    "LATITUD": "625826S",
                    "LONGITUD": "603936W",
                    "ALTITUD": "14",
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_inventory()

    assert len(out) == 1
    assert out[0].station_id == "89064"
    assert out[0].station_name == "GABRIEL DE CASTILLA"


def test_fetch_station_inventory_supports_nested_properties_shape():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/geo.json"}),
        FakeResponse(
            [
                {
                    "type": "Feature",
                    "properties": {
                        "IDEMA": "1234A",
                        "NOMBRE": "ESTACION TEST",
                        "PROVINCIA": "MADRID",
                        "LATITUD": "402540N",
                        "LONGITUD": "003420W",
                        "ALTITUD": "670",
                    },
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_inventory()

    assert len(out) == 1
    assert out[0].station_id == "1234A"
    assert out[0].station_name == "ESTACION TEST"


def test_fetch_station_inventory_parses_json_lines_payload():
    json_lines_payload = (
        '{"indicativo":"0016A","nombre":"ESCORCA, LLUC","provincia":"ILLES BALEARS","latitud":"394924N","longitud":"025309E","altitud":"525"}\n'
        '{"indicativo":"0017A","nombre":"ANOTHER STATION","provincia":"ILLES BALEARS","latitud":"394500N","longitud":"025000E","altitud":"100"}\n'
    )
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.txt"}),
        FakeResponse(json_lines_payload),
    ]
    client = _make_client(responses, api_key="ok-key")
    out = client.fetch_station_inventory()

    assert len(out) == 2
    assert out[0].station_id == "0016A"
    assert out[0].station_name == "ESCORCA, LLUC"


def test_fetch_station_data_parses_alternative_measurement_keys_and_cardinal_direction():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.json"}),
        FakeResponse(
            [
                {
                    "NOMBRE": "JUAN CARLOS I",
                    "FHORA": "2025-02-18T10:00:00Z",
                    "TEMPERATURA": "-1,7",
                    "PRESION": "978,2",
                    "VV": "6,4",
                    "DD": "SO",
                    "LATITUD": "625826S",
                    "LONGITUD": "603936W",
                    "ALTITUD": "14",
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    rows = client.fetch_station_data(
        start_utc=datetime(2025, 2, 18, 9, 0, tzinfo=UTC),
        end_utc=datetime(2025, 2, 18, 11, 0, tzinfo=UTC),
        station_id="89064",
    )

    assert len(rows) == 1
    assert rows[0].temperature_c == -1.7
    assert rows[0].pressure_hpa == 978.2
    assert rows[0].speed_mps == 6.4
    assert rows[0].direction_deg == 225.0
    assert rows[0].latitude is not None
    assert rows[0].longitude is not None


def test_fetch_station_data_parses_direction_numeric_with_symbol():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.json"}),
        FakeResponse(
            [
                {
                    "nombre": "GABRIEL DE CASTILLA",
                    "fhora": "2025-02-18T10:10:00Z",
                    "temp": "0.9",
                    "pres": "975.4",
                    "vel": "3.2",
                    "dir": "270º",
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    rows = client.fetch_station_data(
        start_utc=datetime(2025, 2, 18, 9, 0, tzinfo=UTC),
        end_utc=datetime(2025, 2, 18, 11, 0, tzinfo=UTC),
        station_id="89070",
    )

    assert len(rows) == 1
    assert rows[0].direction_deg == 270.0


def test_fetch_station_data_parses_ddd_direction_key():
    responses = [
        FakeResponse({"estado": 200, "datos": "https://example.test/data.json"}),
        FakeResponse(
            [
                {
                    "nombre": "JCI Estacion meteorologica",
                    "fhora": "2024-02-15T00:10:00Z",
                    "temp": 2.3,
                    "pres": 983.3,
                    "vel": 3.0,
                    "ddd": 67.0,
                }
            ]
        ),
    ]
    client = _make_client(responses, api_key="ok-key")
    rows = client.fetch_station_data(
        start_utc=datetime(2024, 2, 15, 0, 0, tzinfo=UTC),
        end_utc=datetime(2024, 2, 15, 1, 0, tzinfo=UTC),
        station_id="89064",
    )

    assert len(rows) == 1
    assert rows[0].direction_deg == 67.0
