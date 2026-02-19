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
        from app.services.repository import TursoHttpClient
        auth_token = os.getenv("TURSO_AUTH_TOKEN", "")
        info["auth_token_present"] = bool(auth_token)
        info["auth_token_length"] = len(auth_token)
        client = TursoHttpClient(settings.database_url, auth_token=auth_token)
        # Basic connectivity test
        cursor = client.execute("SELECT 1 as ok")
        row = cursor.fetchone()
        info["connection_ok"] = row["ok"] == 1 if row else False
        # Try querying the measurements table (may not exist on fresh databases)
        try:
            cursor = client.execute("SELECT COUNT(*) as cnt FROM measurements")
            row = cursor.fetchone()
            info["measurement_count"] = row["cnt"] if row else "no rows"
        except Exception:
            info["measurement_count"] = "table not created yet"
        # Check fetch_windows
        try:
            cursor = client.execute("SELECT COUNT(*) as cnt FROM fetch_windows")
            row = cursor.fetchone()
            info["fetch_windows_count"] = row["cnt"] if row else 0
        except Exception as e:
            info["fetch_windows_count"] = f"error: {e}"
        # Test reading measurements back and constructing SourceMeasurement
        try:
            from app.models import SourceMeasurement
            cursor = client.execute(
                "SELECT station_name, measured_at_utc, temperature_c, pressure_hpa, speed_mps, "
                "direction_deg, latitude, longitude, altitude_m FROM measurements LIMIT 3"
            )
            test_rows = cursor.fetchall()
            parsed = []
            for row in test_rows:
                sm = SourceMeasurement(
                    station_name=row["station_name"],
                    measured_at_utc=row["measured_at_utc"],
                    temperature_c=row["temperature_c"],
                    pressure_hpa=row["pressure_hpa"],
                    speed_mps=row["speed_mps"],
                    direction_deg=row["direction_deg"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    altitude_m=row["altitude_m"],
                )
                parsed.append(sm.model_dump(mode="json"))
            info["test_read_rows"] = len(parsed)
            info["test_read_sample"] = parsed[0] if parsed else None
        except Exception as e:
            info["test_read_error"] = f"{type(e).__name__}: {e}"
            info["test_read_traceback"] = traceback.format_exc()
        # Show raw fetch_window rows to diagnose format issues
        try:
            cursor = client.execute(
                "SELECT station_id, start_utc, end_utc FROM fetch_windows ORDER BY start_utc DESC LIMIT 5"
            )
            raw_windows = [dict(row) for row in cursor.fetchall()]
            info["fetch_windows_sample"] = raw_windows
        except Exception as e:
            info["fetch_windows_sample_error"] = str(e)
        # Simulate has_cached_fetch_window check for most recent month
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
            prev_month = (now.replace(day=1) - __import__('datetime').timedelta(days=1)).replace(day=1)
            test_start = prev_month.isoformat()
            test_end = now.isoformat()
            cursor = client.execute(
                "SELECT station_id, start_utc, end_utc FROM fetch_windows "
                "WHERE station_id = '89070' AND start_utc <= ? AND end_utc >= ? LIMIT 1",
                (test_start, test_end),
            )
            match = cursor.fetchone()
            info["cache_check_start"] = test_start
            info["cache_check_end"] = test_end
            info["cache_check_result"] = dict(match) if match else "NO MATCH"
        except Exception as e:
            info["cache_check_error"] = str(e)
        info["turso_ok"] = True
        client.close()
    except Exception as e:
        info["turso_error"] = f"{type(e).__name__}: {e}"
        info["turso_traceback"] = traceback.format_exc()
    return info
