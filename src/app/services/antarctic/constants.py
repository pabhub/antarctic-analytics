from zoneinfo import ZoneInfo

from app.models import StationRole

MADRID_TZ = ZoneInfo("Europe/Madrid")
STATION_LOCAL_TZ = ZoneInfo("Antarctica/Palmer")
UTC = ZoneInfo("UTC")

KNOWN_ANTARCTIC_STATIONS: dict[str, dict[str, object]] = {
    "89064": {
        "station_name": "Estación Meteorológica Juan Carlos I",
        "latitude": -62.66325,
        "longitude": -60.38959,
        "altitude": 12.0,
        "role": StationRole.METEO,
        "is_selectable": True,
        "primary_station_id": "89064",
        "include_on_map": True,
    },
    "89064R": {
        "station_name": "Estación Radiométrica Juan Carlos I",
        "latitude": -62.66325,
        "longitude": -60.38959,
        "altitude": 12.0,
        "role": StationRole.SUPPLEMENTAL,
        "is_selectable": False,
        "primary_station_id": "89064",
        "include_on_map": False,
    },
    "89064RA": {
        "station_name": "Estación Radiométrica Juan Carlos I (hasta 08/03/2007)",
        "latitude": -62.66325,
        "longitude": -60.38959,
        "altitude": 12.0,
        "role": StationRole.ARCHIVE,
        "is_selectable": False,
        "primary_station_id": "89064",
        "include_on_map": False,
    },
    "89070": {
        "station_name": "Estación Meteorológica Gabriel de Castilla",
        "latitude": -62.97697,
        "longitude": -60.67528,
        "altitude": 12.0,
        "role": StationRole.METEO,
        "is_selectable": True,
        "primary_station_id": "89070",
        "include_on_map": True,
    },
}
