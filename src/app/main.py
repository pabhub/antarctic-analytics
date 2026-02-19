import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.staticfiles import StaticFiles

from app.api import get_service, router
from app.api.dependencies import clear_dependency_caches, frontend_dist
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "Authentication", "description": "JWT token issuance and refresh for API access."},
    {"name": "Metadata", "description": "Station metadata and latest-availability probing endpoints."},
    {"name": "Analysis", "description": "Cache-first backfill jobs, playback frames, and timeframe analytics."},
    {"name": "Data Export", "description": "CSV and Parquet exports for cached Antarctic station windows."},
]


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield
    # Shutdown: close the persistent httpx.Client connection pool.
    try:
        service = get_service()
        if hasattr(service, "aemet_client") and hasattr(service.aemet_client, "close"):
            service.aemet_client.close()
    except Exception:  # noqa: BLE001
        pass
    clear_dependency_caches()


app = FastAPI(
    title="GS Inima Antarctic Wind Feasibility API",
    version="1.1.0",
    description=(
        "Antarctic-only API for wind-feasibility screening using AEMET data, with cache-first month-window retrieval, "
        "playback analytics, and export endpoints."
    ),
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
app.include_router(router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    request.state.request_id = request_id
    started = perf_counter()
    logger.info(
        "request.start id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started) * 1000.0
        logger.exception(
            "request.error id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise
    elapsed_ms = (perf_counter() - started) * 1000.0
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request.end id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    # Let Vercel's Edge CDN cache API responses (s-maxage controls CDN caching,
    # max-age=0 forces browsers to always revalidate with the CDN).
    if request.url.path.startswith("/api/") and 200 <= response.status_code < 300:
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=0, s-maxage=10800, stale-while-revalidate=1800"
    return response


if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")

__all__ = ["app", "get_service"]

