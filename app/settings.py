from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    aemet_api_key: str
    database_url: str
    request_timeout_seconds: float
    gabriel_station_id: str
    juan_station_id: str
    cache_freshness_seconds: int



def get_settings() -> Settings:
    return Settings(
        aemet_api_key=os.getenv("AEMET_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./aemet_cache.db"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        gabriel_station_id=os.getenv("AEMET_GABRIEL_STATION_ID", "89064"),
        juan_station_id=os.getenv("AEMET_JUAN_STATION_ID", "89070"),
        cache_freshness_seconds=int(os.getenv("CACHE_FRESHNESS_SECONDS", str(3 * 60 * 60))),
    )
