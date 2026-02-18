from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.models import SourceMeasurement

logger = logging.getLogger(__name__)


class AemetClient:
    BASE_URL = "https://opendata.aemet.es/opendata/api"

    def __init__(self, api_key: str, timeout_seconds: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def fetch_station_data(
        self,
        start_utc: datetime,
        end_utc: datetime,
        station_id: str,
    ) -> list[SourceMeasurement]:
        if not self.api_key:
            raise RuntimeError("AEMET_API_KEY environment variable is required")

        endpoint = (
            f"{self.BASE_URL}/antartida/datos/fechaini/{start_utc.strftime('%Y-%m-%dT%H:%M:%SUTC')}"
            f"/fechafin/{end_utc.strftime('%Y-%m-%dT%H:%M:%SUTC')}/estacion/{station_id}"
        )
        logger.info("Requesting AEMET metadata URL for station %s", station_id)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            meta_response = client.get(endpoint, params={"api_key": self.api_key})
            try:
                meta_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"AEMET metadata request failed with HTTP {exc.response.status_code}") from exc

            try:
                payload = meta_response.json()
            except ValueError as exc:
                raise RuntimeError("AEMET metadata response is not valid JSON") from exc

            if not isinstance(payload, dict):
                raise RuntimeError("AEMET metadata response has unexpected shape")

            data_url = payload.get("datos")
            if not data_url:
                estado = payload.get("estado")
                descripcion = payload.get("descripcion")
                if str(estado) == "404" and isinstance(descripcion, str) and "no hay datos" in descripcion.lower():
                    logger.info("AEMET returned no data for requested criteria (station=%s)", station_id)
                    return []
                detail_parts = ["AEMET response missing 'datos' URL"]
                if estado is not None:
                    detail_parts.append(f"estado={estado}")
                if descripcion:
                    detail_parts.append(f"descripcion={descripcion}")
                raise RuntimeError(". ".join(detail_parts))

            logger.info("Downloading AEMET data from temporary URL")
            data_response = client.get(data_url)
            try:
                data_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"AEMET data download failed with HTTP {exc.response.status_code}") from exc

            try:
                raw_items = data_response.json()
            except ValueError as exc:
                raise RuntimeError("AEMET data payload is not valid JSON") from exc

            if not isinstance(raw_items, list):
                raise RuntimeError("AEMET data payload has unexpected shape")

        return [self._map_row(row) for row in raw_items]

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _map_row(cls, row: dict) -> SourceMeasurement:
        return SourceMeasurement(
            station_name=row.get("nombre", ""),
            measured_at_utc=datetime.fromisoformat(row["fhora"].replace("Z", "+00:00")),
            temperature_c=cls._to_float(row.get("temp")),
            pressure_hpa=cls._to_float(row.get("pres")),
            speed_mps=cls._to_float(row.get("vel")),
            direction_deg=cls._to_float(row.get("dir")),
            latitude=cls._to_float(row.get("lat") or row.get("latitud")),
            longitude=cls._to_float(row.get("lon") or row.get("long") or row.get("longitud")),
            altitude_m=cls._to_float(row.get("alt") or row.get("altitud")),
        )
