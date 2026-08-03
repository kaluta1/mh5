"""Lightweight in-memory rate limiting for auth and sensitive endpoints."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

# path prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (10, 60),
    "/api/v1/auth/register": (5, 3600),
    "/api/v1/auth/password-reset-request": (5, 3600),
    "/api/v1/auth/password-reset-confirm": (10, 3600),
    "/api/v1/share-links": (60, 60),
}

# Global fallback: 200 requests per minute per IP
GLOBAL_LIMIT = (200, 60)

_buckets: dict[str, list[float]] = defaultdict(list)
_MAX_BUCKET_KEYS = 50_000


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_rate_limited(key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    hits = _buckets[key]
    cutoff = now - window
    _buckets[key] = [t for t in hits if t > cutoff]
    if len(_buckets[key]) >= limit:
        return True
    _buckets[key].append(now)
    if len(_buckets) > _MAX_BUCKET_KEYS:
        oldest = min(_buckets, key=lambda k: _buckets[k][-1] if _buckets[k] else 0)
        _buckets.pop(oldest, None)
    return False


def check_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    path = request.url.path

    for prefix, (limit, window) in RATE_LIMITS.items():
        if path == prefix or path.startswith(prefix + "/"):
            if _is_rate_limited(f"{ip}:{prefix}", limit, window):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
            return

    g_limit, g_window = GLOBAL_LIMIT
    if _is_rate_limited(f"{ip}:global", g_limit, g_window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        if request.method != "OPTIONS":
            check_rate_limit(request)
        return await call_next(request)
