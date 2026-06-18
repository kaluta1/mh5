"""Load backend/.env once — single source for DATABASE_URL and other secrets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# backend/ (parents: core -> app -> backend)
BACKEND_DIR = Path(__file__).resolve().parents[2]


def load_backend_env(*, override_local: bool = True) -> Path:
    """Load backend/.env (+ optional .env.local). Safe to call multiple times."""
    load_dotenv(BACKEND_DIR / ".env", encoding="utf-8-sig")
    if override_local:
        load_dotenv(BACKEND_DIR / ".env.local", override=True, encoding="utf-8-sig")
    return BACKEND_DIR


def ensure_backend_on_path() -> Path:
    """Ensure backend/ is on sys.path so `app.*` imports work from standalone scripts."""
    backend = str(BACKEND_DIR)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return BACKEND_DIR


def require_database_url() -> str:
    """Return DATABASE_URL from backend/.env or raise."""
    load_backend_env()
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Add it to {BACKEND_DIR / '.env'}"
        )
    return url


# Importing this module loads env immediately (same as app.core.config).
load_backend_env()
