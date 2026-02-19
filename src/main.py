"""Vercel FastAPI entrypoint shim.

Vercel auto-detects ``src/main.py`` for Python/FastAPI projects. Ensure the
local ``src`` directory is on ``sys.path`` before importing ``app.main``.
"""

from pathlib import Path
import sys

src_dir = Path(__file__).resolve().parent
src_path = str(src_dir)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from app.main import app

__all__ = ["app"]
