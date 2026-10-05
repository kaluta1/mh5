"""Durable rate limits for the public authentication endpoints (EMAIL-2).

The in-memory limiter (app.core.rate_limit) lives in one process and forgets
everything on restart. These counters live in PostgreSQL (`auth_rate_limits`),
the durable store the application already depends on, so they hold across
restarts, workers and deployments. Redis is not used: it is an optional cache
here, and a limiter that silently disappears with it is not a limiter.

Fixed windows. One row per (scope, key, window); a request is allowed by a
conditional `count = count + 1 WHERE count < limit`. Once a key is at its
limit, further requests write nothing at all.

Write amplification is bounded by construction:
  * per-address rows:  one per client address and window;
  * per-account rows:  written only for an account that exists, so they are
                       bounded by the number of accounts, not by what a caller
                       types into the email field;
  * global rows:       one per window.
Unknown emails never create a row. Expired windows are deleted in passing.

Keys are stored as keyed hashes (no address, no email, no account id).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_security import AuthRateLimit

logger = logging.getLogger(__name__)

HOUR = 3600
DAY = 86400


@dataclass(frozen=True)
class Limit:
    scope: str
    limit: int
    window: int       # seconds


# Password reset request -----------------------------------------------------
RESET_IP = (Limit("reset:ip", 5, HOUR), Limit("reset:ip:day", 20, DAY))
RESET_ACCOUNT = (Limit("reset:account", 3, HOUR), Limit("reset:account:day", 6, DAY))
RESET_GLOBAL = (Limit("reset:global", 300, HOUR),)
# Verification email (resend endpoint, and registration with an address that
# already has an unverified account) ------------------------------------------
VERIFY_IP = (Limit("verify:ip", 5, HOUR), Limit("verify:ip:day", 20, DAY))
VERIFY_ACCOUNT = (Limit("verify:account", 3, HOUR), Limit("verify:account:day", 6, DAY))
VERIFY_GLOBAL = (Limit("verify:global", 300, HOUR),)
# Presenting a credential (guessing is hopeless at 256 bits; this bounds noise).
CONFIRM_IP = (Limit("confirm:ip", 20, HOUR),)

GLOBAL_KEY = "*"
_RETENTION = timedelta(days=2)


def _key_hash(scope: str, key) -> str:
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), f"auth-throttle:{scope}:{key}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def window_start(now: datetime, window: int) -> datetime:
    epoch = int((now - datetime(1970, 1, 1)).total_seconds())
    return datetime(1970, 1, 1) + timedelta(seconds=epoch - (epoch % window))


def _increment(db: Session, rule: Limit, key_hash: str, start: datetime, now: datetime) -> int:
    return int(db.query(AuthRateLimit).filter(
        AuthRateLimit.scope == rule.scope, AuthRateLimit.key_hash == key_hash,
        AuthRateLimit.window_start == start, AuthRateLimit.count < rule.limit,
    ).update({AuthRateLimit.count: AuthRateLimit.count + 1, AuthRateLimit.updated_at: now},
             synchronize_session=False) or 0)


def _hit_one(db: Session, rule: Limit, key, now: datetime) -> bool:
    key_hash = _key_hash(rule.scope, key)
    start = window_start(now, rule.window)
    if _increment(db, rule, key_hash, start, now):
        return True
    exists = db.query(AuthRateLimit.id).filter(
        AuthRateLimit.scope == rule.scope, AuthRateLimit.key_hash == key_hash,
        AuthRateLimit.window_start == start).first()
    if exists:
        return False                                    # at the limit: nothing is written
    try:
        with db.begin_nested():
            db.add(AuthRateLimit(scope=rule.scope, key_hash=key_hash, window_start=start, count=1,
                                 created_at=now, updated_at=now))
            db.flush()
        return True
    except IntegrityError:                              # a concurrent request created the window
        return bool(_increment(db, rule, key_hash, start, now))


def hit(db: Session, rules: Sequence[Limit], key, *, now: Optional[datetime] = None) -> bool:
    """Count one request against every rule; True when all allow it.

    The decision is committed at once, on its own, so a later failure in the
    request cannot give the attempt back. If the store itself fails the
    request is REFUSED (fail closed): these endpoints send email and change
    credentials, and an unlimited one is worse than a briefly unavailable one.
    """
    now = now or datetime.utcnow()
    try:
        allowed = True
        for rule in rules:
            if not _hit_one(db, rule, key, now):
                allowed = False
                break
        if rules and rules[0].scope.endswith(":global"):
            db.query(AuthRateLimit).filter(AuthRateLimit.window_start < now - _RETENTION).delete(
                synchronize_session=False)
        db.commit()
        return allowed
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("Auth rate limit store unavailable (%s): request refused", type(exc).__name__)
        return False
