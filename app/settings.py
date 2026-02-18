from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    aemet_api_key: str
    database_url: str
    request_timeout_seconds: float
    gabriel_station_id: str
    juan_station_id: str
    cache_freshness_seconds: int
    station_catalog_freshness_seconds: int


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv_if_present() -> None:
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_wrapping_quotes(value.strip())
            if key:
                os.environ.setdefault(key, value)
        break


def get_settings() -> Settings:
    _load_dotenv_if_present()
    return Settings(
        aemet_api_key=os.getenv("AEMET_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./aemet_cache.db"),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        gabriel_station_id=os.getenv("AEMET_GABRIEL_STATION_ID", "89064"),
        juan_station_id=os.getenv("AEMET_JUAN_STATION_ID", "89070"),
        cache_freshness_seconds=int(os.getenv("CACHE_FRESHNESS_SECONDS", str(3 * 60 * 60))),
        station_catalog_freshness_seconds=int(os.getenv("STATION_CATALOG_FRESHNESS_SECONDS", str(7 * 24 * 60 * 60))),
    )
