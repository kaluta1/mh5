"""Public site/API base URLs for emails, redirects, and absolute media paths."""
from __future__ import annotations

import os
import re

from app.core.config import settings

_LOOPBACK = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?", re.I)


def _is_dev_environment() -> bool:
    return os.getenv("ENVIRONMENT", "").strip().lower() in ("development", "dev", "local")


def _sanitize_public_base(url: str, *, dev_fallback: str) -> str:
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return dev_fallback if _is_dev_environment() else "https://myhigh5.com"
    if _LOOPBACK.match(cleaned) and not _is_dev_environment():
        return "https://myhigh5.com"
    return cleaned


def public_site_base() -> str:
    """Frontend origin for email links and user-facing redirects."""
    return _sanitize_public_base(
        settings.FRONTEND_URL,
        dev_fallback="http://localhost:3001",
    )


def public_api_base() -> str:
    """Public API origin for absolute media URLs returned to browsers."""
    raw = (
        (settings.BACKEND_PUBLIC_URL or "").strip()
        or (settings.FRONTEND_URL or "").strip()
        or os.getenv("API_BASE_URL", "").strip()
    )
    return _sanitize_public_base(raw, dev_fallback="http://localhost:8001")


def absolutize_media_path(path: str | None) -> str | None:
    """Turn a relative /media/... path into a public https URL."""
    if not path:
        return None
    value = str(path).strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        if _LOOPBACK.match(value) and not _is_dev_environment():
            return _LOOPBACK.sub("https://myhigh5.com", value, count=1)
        return value
    if value.startswith("/"):
        return f"{public_api_base()}{value}"
    return value
