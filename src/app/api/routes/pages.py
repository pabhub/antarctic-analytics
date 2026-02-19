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
    return {"logs": seed_debug_logs}
