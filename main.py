"""Root ASGI entrypoint shim for Vercel auto-detection."""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent
src_path = str(project_root / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from app.main import app

__all__ = ["app"]

