from __future__ import annotations

import logging
import csv
import json
import re
import threading
import time
import unicodedata
from datetime import datetime
from io import StringIO
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.exceptions import UpstreamServiceError
from app.models import SourceMeasurement, StationCatalogItem

logger = logging.getLogger(__name__)


class AemetClient:
    BASE_URL = "https://opendata.aemet.es/opendata/api"
    _request_lock = threading.Lock()
    _last_request_monotonic = 0.0
    _rate_limited_until_monotonic = 0.0
    _ROW_NAME_KEYS = ("nombre", "name", "estacion", "stationname", "denominacion", "descripcion")
    _ROW_DATETIME_KEYS = ("fhora", "fecha", "datetime", "timestamp", "instante")
    _ROW_TEMPERATURE_KEYS = ("temp", "temperatura", "temperature", "ta", "tair", "t")
    _ROW_PRESSURE_KEYS = ("pres", "presion", "pressure", "patm", "press", "p")
    _ROW_SPEED_KEYS = ("vel", "windspeed", "speed", "viento", "vv", "ff", "f")
    _ROW_DIRECTION_KEYS = ("ddd", "dir", "direccion", "direction", "dd", "dvv", "vdir", "dr", "dddx")
    _ROW_LATITUDE_KEYS = ("lat", "latitud", "latitude")
    _ROW_LONGITUDE_KEYS = ("lon", "long", "longitud", "longitude", "lng")
    _ROW_ALTITUDE_KEYS = ("alt", "altitud", "altitude")

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 20.0,
        min_request_interval_seconds: float = 2.0,
        retry_after_cap_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = max(0.0, min_request_interval_seconds)
        cap = retry_after_cap_seconds if retry_after_cap_seconds is not None else self.min_request_interval_seconds
        self.retry_after_cap_seconds = max(self.min_request_interval_seconds, cap)
        self._http_client = httpx.Client(timeout=self.timeout_seconds)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http_client.close()

    def fetch_station_data(
        self,
        start_utc: datetime,
        end_utc: datetime,
        station_id: str,
    ) -> list[SourceMeasurement]:
        if not self.api_key:
            raise UpstreamServiceError("AEMET_API_KEY environment variable is required")

        endpoint = (
            f"{self.BASE_URL}/antartida/datos/fechaini/{start_utc.strftime('%Y-%m-%dT%H:%M:%SUTC')}"
            f"/fechafin/{end_utc.strftime('%Y-%m-%dT%H:%M:%SUTC')}/estacion/{station_id}"
        )
        logger.info("Requesting AEMET metadata URL for station %s", station_id)

        raw_items = self._request_data_items(endpoint, allow_no_data=True, no_data_log_context=f"station={station_id}")
        mapped: list[SourceMeasurement] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            measurement = self._map_row(row)
            if measurement is not None:
                mapped.append(measurement)
        return mapped

    def fetch_station_inventory(self) -> list[StationCatalogItem]:
        if not self.api_key:
            raise UpstreamServiceError("AEMET_API_KEY environment variable is required")

        endpoint = f"{self.BASE_URL}/valores/climatologicos/inventarioestaciones/todasestaciones"
        logger.info("Requesting AEMET station inventory metadata URL")
        raw_items = self._request_data_items(endpoint, allow_no_data=False)
        stations: list[StationCatalogItem] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            source = row.get("properties") if isinstance(row.get("properties"), dict) else row
            normalized = {str(k).strip().lower(): v for k, v in source.items()}
            station_id = self._extract_station_id(normalized)
            if not station_id:
                continue
            station_name = self._extract_station_name(normalized, station_id)
            if not station_name:
                station_name = station_id
            stations.append(
                StationCatalogItem(
                    stationId=station_id,
                    stationName=station_name,
                    province=self._normalize_province_code(normalized.get("provincia") or normalized.get("provincia_nombre")),
                    latitude=self._to_coordinate(
                        normalized.get("latitud") or normalized.get("lat") or normalized.get("latitude"),
                        is_longitude=False,
                    ),
                    longitude=self._to_coordinate(
                        normalized.get("longitud") or normalized.get("lon") or normalized.get("longitude"),
                        is_longitude=True,
                    ),
                    altitude=self._to_float(normalized.get("altitud") or normalized.get("alt") or normalized.get("altitude")),
                )
            )
        if stations:
            logger.info("Parsed %d stations from inventory payload (%d raw rows).", len(stations), len(raw_items))
            return stations

        sample_keys: list[str] = []
        for row in raw_items[:3]:
            if isinstance(row, dict):
                source = row.get("properties") if isinstance(row.get("properties"), dict) else row
                sample_keys.extend([str(k) for k in source.keys()])
        unique_keys = sorted({k for k in sample_keys})[:20]
        raise UpstreamServiceError(
            "AEMET station inventory parsed but no station identifiers were detected. "
            f"sample_keys={unique_keys}"
        )

    @staticmethod
    def _normalize_province_code(value: Any) -> str | None:
        if value in (None, ""):
            return None
        raw = str(value).strip()
        if not raw:
            return None
        canonical = unicodedata.normalize("NFD", raw).encode("ascii", "ignore").decode("ascii").upper()
        if canonical in {"ANTARTIDA", "ANTARCTIDA", "ANTARCTIC"}:
            return "ANTARCTIC"
        return canonical

    @staticmethod
    def _extract_station_name(normalized: dict[str, Any], fallback: str) -> str:
        for key in ("nombre", "name", "estacion", "station_name", "denominacion", "descripcion"):
            value = normalized.get(key)
            if value is None:
                continue
            name = str(value).strip()
            if name:
                return name
        for key, value in normalized.items():
            key_low = key.lower()
            if any(token in key_low for token in ("nombre", "name", "denominacion", "estacion")):
                name = str(value).strip()
                if name:
                    return name
        return fallback

    @staticmethod
    def _extract_station_id(normalized: dict[str, Any]) -> str:
        preferred_keys = (
            "indicativo",
            "idema",
            "indicatif",
            "estacion",
            "station_id",
            "stationid",
            "codigo",
            "code",
            "id",
        )
        for key in preferred_keys:
            value = normalized.get(key)
            if value is None:
                continue
            station_id = str(value).strip()
            if station_id:
                return station_id
        for key, value in normalized.items():
            key_low = key.lower()
            if any(token in key_low for token in ("indic", "idema", "station", "codigo", "code")):
                station_id = str(value).strip()
                if station_id:
                    return station_id
        return ""

    def _request_data_items(
        self,
        endpoint: str,
        allow_no_data: bool,
        no_data_log_context: str | None = None,
    ) -> list[dict[str, Any]]:
        client = self._http_client
        meta_response = self._throttled_get(client, endpoint, params={"api_key": self.api_key})
        try:
            meta_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = f"AEMET metadata request failed with HTTP {status}"
            if status == 429:
                retry_after = self._retry_after_seconds(exc.response)
                detail = f"{detail}. Retry-After={int(retry_after)}s"
            raise UpstreamServiceError(detail) from exc

        try:
            payload = meta_response.json()
        except ValueError as exc:
            raise UpstreamServiceError("AEMET metadata response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise UpstreamServiceError("AEMET metadata response has unexpected shape")

        data_url = payload.get("datos")
        if not data_url:
            estado = payload.get("estado")
            descripcion = payload.get("descripcion")
            if allow_no_data and str(estado) == "404" and isinstance(descripcion, str) and "no hay datos" in descripcion.lower():
                context = f" ({no_data_log_context})" if no_data_log_context else ""
                logger.info("AEMET returned no data for requested criteria%s", context)
                return []
            detail_parts = ["AEMET response missing 'datos' URL"]
            if estado is not None:
                detail_parts.append(f"estado={estado}")
            if descripcion:
                detail_parts.append(f"descripcion={descripcion}")
            raise UpstreamServiceError(".".join(detail_parts))

        # Presigned data URLs are not rate-limited by AEMET — skip throttle entirely.
        logger.info("Downloading AEMET data from temporary URL")
        try:
            data_response = client.get(data_url)
        except httpx.RequestError as exc:
            raise UpstreamServiceError(
                f"AEMET data download failed for URL {data_url}: {exc.__class__.__name__}"
            ) from exc
        try:
            data_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = f"AEMET data download failed with HTTP {status}"
            if status == 429:
                retry_after = self._retry_after_seconds(exc.response)
                detail = f"{detail}. Retry-After={int(retry_after)}s"
            raise UpstreamServiceError(detail) from exc

        try:
            raw_items = data_response.json()
        except ValueError as exc:
            json_rows = self._parse_json_rows(data_response.text)
            if json_rows is not None:
                return json_rows
            csv_rows = self._parse_csv_rows(data_response.text)
            if csv_rows is not None:
                return csv_rows
            raise UpstreamServiceError("AEMET data payload is not valid JSON") from exc

        if isinstance(raw_items, str):
            json_rows = self._parse_json_rows(raw_items)
            if json_rows is not None:
                return json_rows
            csv_rows = self._parse_csv_rows(raw_items)
            if csv_rows is not None:
                return csv_rows

        if isinstance(raw_items, dict):
            nested_lists = [value for value in raw_items.values() if isinstance(value, list)]
            if len(nested_lists) == 1:
                nested = nested_lists[0]
                if all(isinstance(item, dict) for item in nested):
                    return nested

        if not isinstance(raw_items, list):
            snippet = str(raw_items)[:240]
            raise UpstreamServiceError(f"AEMET data payload has unexpected shape (sample={snippet})")

        return raw_items

    def _throttled_get(
        self,
        client: httpx.Client,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        # Compute required wait under lock, then release lock before sleeping.
        with self.__class__._request_lock:
            now = time.monotonic()
            elapsed_since_last = now - self.__class__._last_request_monotonic
            wait_for_min_interval = self.min_request_interval_seconds - elapsed_since_last
            wait_for_rate_limit = self.__class__._rate_limited_until_monotonic - now
            wait_for = max(wait_for_min_interval, wait_for_rate_limit, 0.0)
            # Reserve our slot by advancing the timestamp optimistically.
            self.__class__._last_request_monotonic = now + wait_for

        if wait_for > 0:
            logger.debug("Throttling AEMET request for %.2fs before GET %s", wait_for, url)
            time.sleep(wait_for)

        try:
            response = client.get(url, **kwargs)
        except httpx.RequestError as exc:
            with self.__class__._request_lock:
                self.__class__._last_request_monotonic = time.monotonic()
            raise UpstreamServiceError(
                f"AEMET request failed for URL {url}: {exc.__class__.__name__}"
            ) from exc

        completed_at = time.monotonic()
        with self.__class__._request_lock:
            self.__class__._last_request_monotonic = completed_at
            if response.status_code == 429:
                retry_after = self._retry_after_seconds(response)
                cooldown_until = completed_at + retry_after
                if cooldown_until > self.__class__._rate_limited_until_monotonic:
                    self.__class__._rate_limited_until_monotonic = cooldown_until
                logger.warning(
                    "AEMET responded with HTTP 429; applying cooldown %.2fs for URL %s",
                    retry_after,
                    url,
                )
        return response

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return max(self.min_request_interval_seconds, 1.0)
        try:
            value = float(raw)
        except ValueError:
            return max(self.min_request_interval_seconds, 1.0)
        if value < 1.0:
            return 1.0
        if value < self.min_request_interval_seconds:
            value = self.min_request_interval_seconds
        return min(value, self.retry_after_cap_seconds)

    @staticmethod
    def _parse_json_rows(payload: str) -> list[dict[str, Any]] | None:
        text = payload.lstrip("\ufeff").strip()
        if not text:
            return []

        # NDJSON / one-object-per-line (optionally with trailing comma).
        lines = [line.strip().rstrip(",") for line in text.splitlines() if line.strip()]
        line_objects: list[dict[str, Any]] = []
        for line in lines:
            if not (line.startswith("{") and line.endswith("}")):
                line_objects = []
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                line_objects = []
                break
            if not isinstance(obj, dict):
                line_objects = []
                break
            line_objects.append(obj)
        if line_objects:
            return line_objects

        # Concatenated objects without delimiters/newlines.
        objects: list[dict[str, Any]] = []
        depth = 0
        start = -1
        for idx, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start != -1:
                        fragment = text[start: idx + 1]
                        try:
                            obj = json.loads(fragment)
                        except json.JSONDecodeError:
                            return None
                        if not isinstance(obj, dict):
                            return None
                        objects.append(obj)
                        start = -1
        return objects if objects else None

    @staticmethod
    def _parse_csv_rows(payload: str) -> list[dict[str, Any]] | None:
        text = payload.lstrip("\ufeff").strip()
        if not text:
            return []

        lines = text.splitlines()
        if not lines:
            return []

        candidate_delimiters = [";", ",", "\t", "|"]
        header_index = None
        delimiter = None

        for idx, line in enumerate(lines[:40]):
            lower = line.lower()
            if "indicativo" in lower and "nombre" in lower:
                counts = {d: line.count(d) for d in candidate_delimiters}
                best = max(counts, key=counts.get)
                if counts[best] > 0:
                    header_index = idx
                    delimiter = best
                    break
            counts = {d: line.count(d) for d in candidate_delimiters}
            best = max(counts, key=counts.get)
            if counts[best] >= 2:
                header_index = idx
                delimiter = best
                break

        if header_index is None or delimiter is None:
            return None

        candidate_text = "\n".join(lines[header_index:])
        reader = csv.DictReader(StringIO(candidate_text), delimiter=delimiter)
        rows: list[dict[str, Any]] = []
        for row in reader:
            normalized = {
                (k.strip() if isinstance(k, str) else k): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
            }
            if all((v in (None, "") for v in normalized.values())):
                continue
            rows.append(normalized)
        return rows if rows else None

    @classmethod
    def _to_coordinate(cls, value: Any, is_longitude: bool) -> float | None:
        # Some AEMET inventory payloads encode coordinates as DDMMSSH / DDDMMSSH.
        if value in (None, ""):
            return None
        if isinstance(value, str):
            raw = value.strip().upper()
            if raw and raw[-1] in {"N", "S", "E", "W"}:
                hemi = raw[-1]
                digits = raw[:-1]
                if digits.isdigit():
                    if is_longitude:
                        deg_len = 3 if len(digits) >= 7 else 2
                    else:
                        deg_len = 2
                    if len(digits) >= deg_len + 4:
                        deg = int(digits[:deg_len])
                        minutes = int(digits[deg_len:deg_len + 2])
                        seconds = int(digits[deg_len + 2:deg_len + 4])
                        decimal = deg + (minutes / 60.0) + (seconds / 3600.0)
                        if hemi in {"S", "W"}:
                            decimal *= -1
                        return round(decimal, 6)
        return cls._to_float(value)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
        if isinstance(value, str):
            match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
            if not match:
                return None
            try:
                return float(match.group(0).replace(",", "."))
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalized_key(key: str) -> str:
        ascii_key = unicodedata.normalize("NFD", key).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]", "", ascii_key.lower())

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {cls._normalized_key(str(key)): value for key, value in row.items()}

    @staticmethod
    def _first_non_empty(normalized: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key not in normalized:
                continue
            value = normalized[key]
            if value in (None, ""):
                continue
            return value
        return None

    @classmethod
    def _to_datetime(cls, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        raw = str(value).strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))

    @classmethod
    def _to_direction_deg(cls, value: Any) -> float | None:
        as_float = cls._to_float(value)
        if as_float is not None:
            return round(as_float % 360.0, 3)
        if value in (None, ""):
            return None
        token = cls._normalized_key(str(value))
        if not token or token in {"calma", "calm", "variable", "vrb"}:
            return None
        cardinal_map = {
            "n": 0.0,
            "nne": 22.5,
            "ne": 45.0,
            "ene": 67.5,
            "e": 90.0,
            "ese": 112.5,
            "se": 135.0,
            "sse": 157.5,
            "s": 180.0,
            "ssw": 202.5,
            "sso": 202.5,
            "sw": 225.0,
            "so": 225.0,
            "wsw": 247.5,
            "oso": 247.5,
            "w": 270.0,
            "o": 270.0,
            "wnw": 292.5,
            "ono": 292.5,
            "nw": 315.0,
            "no": 315.0,
            "nnw": 337.5,
            "nno": 337.5,
        }
        return cardinal_map.get(token)

    @classmethod
    def _map_row(cls, row: dict[str, Any]) -> SourceMeasurement | None:
        normalized = cls._normalize_row(row)
        measured_at_raw = cls._first_non_empty(normalized, cls._ROW_DATETIME_KEYS)
        measured_at_utc = cls._to_datetime(measured_at_raw)
        if measured_at_utc is None:
            return None

        station_name_raw = cls._first_non_empty(normalized, cls._ROW_NAME_KEYS)
        station_name = str(station_name_raw).strip() if station_name_raw not in (None, "") else ""
        return SourceMeasurement(
            station_name=station_name,
            measured_at_utc=measured_at_utc,
            temperature_c=cls._to_float(cls._first_non_empty(normalized, cls._ROW_TEMPERATURE_KEYS)),
            pressure_hpa=cls._to_float(cls._first_non_empty(normalized, cls._ROW_PRESSURE_KEYS)),
            speed_mps=cls._to_float(cls._first_non_empty(normalized, cls._ROW_SPEED_KEYS)),
            direction_deg=cls._to_direction_deg(cls._first_non_empty(normalized, cls._ROW_DIRECTION_KEYS)),
            latitude=cls._to_coordinate(cls._first_non_empty(normalized, cls._ROW_LATITUDE_KEYS), is_longitude=False),
            longitude=cls._to_coordinate(cls._first_non_empty(normalized, cls._ROW_LONGITUDE_KEYS), is_longitude=True),
            altitude_m=cls._to_float(cls._first_non_empty(normalized, cls._ROW_ALTITUDE_KEYS)),
        )
