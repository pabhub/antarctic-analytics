from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.services import AemetClient, AntarcticService, AuthService, SQLiteRepository
from app.services.auth_service import AuthUser

AEMET_COPYRIGHT_NOTICE = "(c) AEMET"
AEMET_SOURCE_NOTICE = "Fuente: AEMET"
AEMET_VALUE_ADDED_NOTICE = (
    "Informacion elaborada utilizando, entre otras, la obtenida de la Agencia Estatal de Meteorologia"
)
AEMET_LEGAL_NOTICE_URL = "https://www.aemet.es/en/nota_legal"
OSM_COPYRIGHT_NOTICE = "OpenStreetMap contributors"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"

project_root = Path(__file__).resolve().parents[3]
src_root = Path(__file__).resolve().parents[2]
frontend_dist_candidates = [
    project_root / "frontend" / "dist",
    src_root / "frontend" / "dist",
]
frontend_dist = next((path for path in frontend_dist_candidates if path.exists()), frontend_dist_candidates[0])
http_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _cached_repository(database_url: str, auth_token: str = "") -> SQLiteRepository:
    return SQLiteRepository(database_url, auth_token=auth_token)


@lru_cache(maxsize=1)
def _cached_aemet_client(
    api_key: str,
    timeout_seconds: float,
    min_request_interval_seconds: float,
    retry_after_cap_seconds: float,
) -> AemetClient:
    return AemetClient(
        api_key,
        timeout_seconds,
        min_request_interval_seconds,
        retry_after_cap_seconds,
    )


@lru_cache(maxsize=1)
def _cached_auth_service(settings: Settings) -> AuthService:
    return AuthService(settings=settings)


@lru_cache(maxsize=1)
def _cached_service(settings: Settings) -> AntarcticService:
    repository = _cached_repository(settings.database_url, settings.turso_auth_token)
    client = _cached_aemet_client(
        settings.aemet_api_key,
        settings.request_timeout_seconds,
        settings.aemet_min_request_interval_seconds,
        settings.aemet_retry_after_cap_seconds,
    )
    return AntarcticService(settings=settings, repository=repository, aemet_client=client)


def get_service(settings: Settings = Depends(get_settings)) -> AntarcticService:
    return _cached_service(settings)


def get_auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    return _cached_auth_service(settings)


def require_api_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUser:
    if not auth_service.auth_enabled:
        return AuthUser(username="anonymous")

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return auth_service.validate_access_token(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def compliance_headers(latest_observation_utc: str | None = None) -> dict[str, str]:
    headers = {
        "X-AEMET-Copyright": AEMET_COPYRIGHT_NOTICE,
        "X-AEMET-Source": AEMET_SOURCE_NOTICE,
        "X-AEMET-Value-Added-Notice": AEMET_VALUE_ADDED_NOTICE,
        "X-AEMET-Legal-Notice": AEMET_LEGAL_NOTICE_URL,
        "X-OSM-Copyright": OSM_COPYRIGHT_NOTICE,
        "X-OSM-Copyright-URL": OSM_COPYRIGHT_URL,
    }
    if latest_observation_utc:
        headers["X-AEMET-Latest-Observation-UTC"] = latest_observation_utc
    return headers


def set_compliance_headers(response: Response, latest_observation_utc: str | None = None) -> None:
    for key, value in compliance_headers(latest_observation_utc=latest_observation_utc).items():
        response.headers[key] = value


def clear_dependency_caches() -> None:
    _cached_repository.cache_clear()
    _cached_aemet_client.cache_clear()
    _cached_service.cache_clear()
    _cached_auth_service.cache_clear()
