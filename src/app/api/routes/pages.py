from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.dependencies import frontend_dist

router = APIRouter()


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    html_path = frontend_dist / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not built yet")
    return FileResponse(html_path)


@router.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    html_path = frontend_dist / "login.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Login page not built yet")
    return FileResponse(html_path)


@router.get("/config", include_in_schema=False)
def config_page() -> FileResponse:
    html_path = frontend_dist / "config.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Config page not built yet")
    return FileResponse(html_path)

from app.services.repository import seed_debug_logs

@router.get("/api/analysis/debug-logs", include_in_schema=False)
def get_debug_logs():
    import os, traceback
    from app.core.config import get_settings
    info = {}
    info["seed_debug_logs"] = seed_debug_logs
    info["DATABASE_URL_set"] = bool(os.getenv("DATABASE_URL"))
    info["DATABASE_URL_prefix"] = (os.getenv("DATABASE_URL") or "")[:40]
    info["VERCEL"] = os.getenv("VERCEL", "")
    info["VERCEL_ENV"] = os.getenv("VERCEL_ENV", "")
    try:
        settings = get_settings()
        info["resolved_database_url_prefix"] = settings.database_url[:40]
    except Exception as e:
        info["settings_error"] = f"{type(e).__name__}: {e}"
    try:
        import libsql_client
        kwargs = {"url": settings.database_url}
        auth_token = os.getenv("TURSO_AUTH_TOKEN", "")
        if auth_token:
            kwargs["auth_token"] = auth_token
            info["auth_token_present"] = True
        client = libsql_client.create_client_sync(**kwargs)
        rs = client.execute("SELECT COUNT(*) as cnt FROM measurements")
        info["measurement_count"] = rs.rows[0][0] if rs.rows else "no rows"
        info["turso_ok"] = True
        client.close()
    except Exception as e:
        info["turso_error"] = f"{type(e).__name__}: {e}"
        info["turso_traceback"] = traceback.format_exc()
    return info
