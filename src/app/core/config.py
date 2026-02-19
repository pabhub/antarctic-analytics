from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
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
    api_auth_enabled: bool = True
    api_auth_username: str = "analyst"
    api_auth_password: str = "antarctic"
    jwt_secret_key: str = "change-me-in-env"
    jwt_access_token_ttl_seconds: int = 3600
    jwt_issuer: str = "antarctic-analytics"
    aemet_min_request_interval_seconds: float = 2.0
    aemet_retry_after_cap_seconds: float = 2.0
    query_jobs_background_enabled: bool = True


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv_if_present() -> None:
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _default_database_url() -> str:
    # Priority 1: Turso env vars (set via Vercel dashboard integration)
    turso_url = os.getenv("TURSO_DATABASE_URL")
    turso_token = os.getenv("TURSO_AUTH_TOKEN")
    if turso_url:
        if turso_token:
            sep = "&" if "?" in turso_url else "?"
            return f"{turso_url}{sep}authToken={turso_token}"
        return turso_url
    # Priority 2: Generic DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    # Priority 3: Local file defaults
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        return "file:///tmp/aemet_cache.db"
    return "file:aemet_cache.db"


def _normalize_database_url(raw_url: str) -> str:
    """Convert database URLs to formats that libsql_client understands.
    
    libsql_client supports: file:, libsql://, https://, ws://, wss://
    - libsql:// uses WebSocket (fails in Vercel serverless) → convert to https://
    - sqlite:/// is legacy SQLAlchemy format → convert to file:
    """
    # libsql:// → https:// to force HTTP protocol (WebSocket fails in serverless)
    if raw_url.startswith("libsql://"):
        return "https://" + raw_url[len("libsql://"):]
    if raw_url.startswith(("https://", "http://", "ws://", "wss://", "file:")):
        return raw_url
    if raw_url.startswith("sqlite:///"):
        path = raw_url[len("sqlite:///"):]
        if path.startswith("/"):
            return f"file://{path}"
        return f"file:{path}"
    # Bare path like "aemet_cache.db" or "/tmp/aemet_cache.db"
    if raw_url.startswith("/"):
        return f"file://{raw_url}"
    return f"file:{raw_url}"


def get_settings() -> Settings:
    _load_dotenv_if_present()
    min_request_interval_seconds = float(os.getenv("AEMET_MIN_REQUEST_INTERVAL_SECONDS", "2"))
    retry_after_cap_seconds = float(
        os.getenv("AEMET_RETRY_AFTER_CAP_SECONDS", str(min_request_interval_seconds))
    )
    default_background_jobs = not (os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
    raw_db_url = _default_database_url()
    return Settings(
        aemet_api_key=os.getenv("AEMET_API_KEY", ""),
        database_url=_normalize_database_url(raw_db_url),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
        aemet_min_request_interval_seconds=min_request_interval_seconds,
        aemet_retry_after_cap_seconds=retry_after_cap_seconds,
        query_jobs_background_enabled=_env_bool("QUERY_JOBS_BACKGROUND_ENABLED", default_background_jobs),
        gabriel_station_id=os.getenv("AEMET_GABRIEL_STATION_ID", "89070"),
        juan_station_id=os.getenv("AEMET_JUAN_STATION_ID", "89064"),
        cache_freshness_seconds=int(os.getenv("CACHE_FRESHNESS_SECONDS", str(3 * 60 * 60))),
        station_catalog_freshness_seconds=int(os.getenv("STATION_CATALOG_FRESHNESS_SECONDS", str(7 * 24 * 60 * 60))),
        api_auth_enabled=_env_bool("API_AUTH_ENABLED", True),
        api_auth_username=os.getenv("API_AUTH_USERNAME", "analyst"),
        api_auth_password=os.getenv("API_AUTH_PASSWORD", "antarctic"),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "change-me-in-env"),
        jwt_access_token_ttl_seconds=int(os.getenv("JWT_ACCESS_TOKEN_TTL_SECONDS", "3600")),
        jwt_issuer=os.getenv("JWT_ISSUER", "antarctic-analytics"),
    )


get_settings = lru_cache(maxsize=1)(get_settings)


def clear_settings_cache() -> None:
    get_settings.cache_clear()  # type: ignore[attr-defined]
