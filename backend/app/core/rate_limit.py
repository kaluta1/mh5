"""Lightweight in-memory rate limiting for auth and sensitive endpoints.

The middleware RETURNS the 429 response. An HTTPException raised inside a
BaseHTTPMiddleware never reaches FastAPI's exception handlers (they sit inside
all user middleware), so it used to surface as a 500 with a server traceback.
"""
from __future__ import annotations

import logging
import time
import os
import ipaddress
from collections import defaultdict
from typing import Callable, Optional, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

ROUTE_LIMIT_MESSAGE = "Too many requests. Please try again later."
GLOBAL_LIMIT_MESSAGE = "Rate limit exceeded. Please slow down."

# path prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (10, 60),
    "/api/v1/auth/register": (5, 3600),
    "/api/v1/guardian": (30, 3600),
    "/api/v1/contest-eligibility/claims": (30, 3600),
    "/api/v1/auth/password-reset-request": (5, 3600),
    "/api/v1/auth/password-reset-confirm": (10, 3600),
    "/api/v1/share-links": (60, 60),
    "/api/v1/kyc/initiate": (10, 3600),
    "/api/v1/kyc/webhook": (300, 60),
    "/api/v1/payments": (20, 60),
    "/api/v1/wallet": (30, 60),
    "/api/v1/votes": (120, 60),
    "/api/v1/comments": (30, 60),
    "/api/v1/media/upload": (20, 60),
    "/api/v1/search": (60, 60),
}

# Global fallback: 200 requests per minute per IP
GLOBAL_LIMIT = (200, 60)

_buckets: dict[str, list[float]] = defaultdict(list)
_MAX_BUCKET_KEYS = 50_000


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted = {item.strip() for item in os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if item.strip()}
    if peer in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    if peer:
        return peer
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


def rate_limit_exceeded(request: Request) -> Optional[Tuple[str, str]]:
    """Record this request; return (category, client message) when a limit is
    exceeded, else None. Policy (limits, windows, keys) is unchanged."""
    ip = _client_ip(request)
    path = request.url.path

    for prefix, (limit, window) in RATE_LIMITS.items():
        if path == prefix or path.startswith(prefix + "/"):
            if _is_rate_limited(f"{ip}:{prefix}", limit, window):
                return prefix, ROUTE_LIMIT_MESSAGE
            return None

    g_limit, g_window = GLOBAL_LIMIT
    if _is_rate_limited(f"{ip}:global", g_limit, g_window):
        return "global", GLOBAL_LIMIT_MESSAGE
    return None


def check_rate_limit(request: Request) -> None:
    """Raising variant for use OUTSIDE middleware (e.g. a route dependency)."""
    exceeded = rate_limit_exceeded(request)
    if exceeded:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=exceeded[1])


def rate_limit_response(message: str) -> JSONResponse:
    """Same body the app's HTTPException handler produces for a 429."""
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": message, "code": "HTTP_429", "message": message})


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        if request.method != "OPTIONS":
            exceeded = rate_limit_exceeded(request)
            if exceeded:
                # An expected control event: no traceback, no client IP, no body.
                logger.warning("Rate limit exceeded: %s %s", request.method, exceeded[0])
                return rate_limit_response(exceeded[1])
        return await call_next(request)
