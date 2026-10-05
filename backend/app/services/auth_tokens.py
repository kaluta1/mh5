"""One-time credentials sent by email (EMAIL-2): email verification and
password reset.

Model
-----
* The credential is 256 random bits (`secrets.token_urlsafe(32)`). It is put in
  ONE email and is never stored, logged or returned by an API. The database
  keeps its SHA-256 digest only, so a database read does not yield a usable
  credential. (A slow hash adds nothing for a 256-bit random value.)
* Purpose-bound: a row has exactly one purpose and is looked up WITH that
  purpose. A reset credential presented as a verification credential (or the
  reverse, or an access token, or a guardian / claim token) matches no row.
* User-bound: the row names the account. There is no account identifier in the
  credential for a caller to swap.
* Short-lived: `expires_at`.
* One-time: consumed with a conditional UPDATE in the same transaction as the
  change it authorises. A second use, or a concurrent use, changes no row.
* Newest only: issuing a credential revokes the account's earlier unused ones
  of the same purpose.
* Invalid after an account security change:
    - the account's email address is no longer the one it was sent to;
    - the account is inactive or deleted;
    - verification: the address is already verified;
    - reset: the password was changed or reset since (security_version), which
      also revokes the rows explicitly.

Every refusal is reported to the caller as the same error.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET, TOKEN_PURPOSES, AuthToken
from app.models.user import User

# Anything longer is not one of ours: refuse before hashing or querying.
MAX_TOKEN_LENGTH = 128
MIN_TOKEN_LENGTH = 32
# Consumed / expired rows are kept this long for audit, then deleted.
RETENTION = timedelta(days=30)


class AuthTokenError(Exception):
    """The credential cannot be used. `reason` is for logs and tests only; it
    is never sent to the client."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def lifetime(purpose: str) -> timedelta:
    if purpose == PURPOSE_EMAIL_VERIFICATION:
        return timedelta(minutes=int(settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES))
    if purpose == PURPOSE_PASSWORD_RESET:
        return timedelta(minutes=int(settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES))
    raise ValueError(f"unknown token purpose: {purpose}")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def email_fingerprint(email: Optional[str]) -> str:
    normalized = (email or "").strip().lower()
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), f"auth-token-email:{normalized}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def revoke(db: Session, user_id: int, purpose: str, *, now: Optional[datetime] = None) -> int:
    """Revoke the account's unused credentials of one purpose. No commit."""
    now = now or datetime.utcnow()
    return int(db.query(AuthToken).filter(
        AuthToken.user_id == user_id, AuthToken.purpose == purpose,
        AuthToken.consumed_at.is_(None), AuthToken.revoked_at.is_(None),
    ).update({AuthToken.revoked_at: now, AuthToken.updated_at: now}, synchronize_session=False) or 0)


def issue(db: Session, user: User, purpose: str, *, now: Optional[datetime] = None) -> str:
    """Create a credential for `user` and return it (the only time it exists
    outside the email). Earlier unused credentials of the purpose are revoked.
    The caller commits."""
    if purpose not in TOKEN_PURPOSES:
        raise ValueError(f"unknown token purpose: {purpose}")
    now = now or datetime.utcnow()
    revoke(db, user.id, purpose, now=now)
    db.query(AuthToken).filter(AuthToken.expires_at < now - RETENTION).delete(synchronize_session=False)
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw),
                     email_hash=email_fingerprint(user.email), security_version=int(user.security_version or 0),
                     expires_at=now + lifetime(purpose), created_at=now, updated_at=now))
    db.flush()
    return raw


def _lookup(db: Session, raw: Optional[str], purpose: str, now: datetime) -> Tuple[AuthToken, User]:
    text = raw if isinstance(raw, str) else ""
    if not (MIN_TOKEN_LENGTH <= len(text) <= MAX_TOKEN_LENGTH):
        raise AuthTokenError("malformed")
    row = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(text), AuthToken.purpose == purpose).first()
    if row is None:
        raise AuthTokenError("unknown")
    if row.consumed_at is not None:
        raise AuthTokenError("used")
    if row.revoked_at is not None:
        raise AuthTokenError("revoked")
    if row.expires_at <= now:
        raise AuthTokenError("expired")
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or not user.is_active or getattr(user, "is_deleted", False):
        raise AuthTokenError("account_unavailable")
    if not hmac.compare_digest(row.email_hash, email_fingerprint(user.email)):
        raise AuthTokenError("email_changed")
    if purpose == PURPOSE_PASSWORD_RESET and int(row.security_version) != int(user.security_version or 0):
        raise AuthTokenError("security_changed")
    if purpose == PURPOSE_EMAIL_VERIFICATION and user.email_verified:
        raise AuthTokenError("already_verified")
    return row, user


def consume(db: Session, raw: Optional[str], purpose: str, *, now: Optional[datetime] = None) -> User:
    """Validate and use up a credential; returns its account. Raises
    AuthTokenError otherwise. The UPDATE is conditional, so of two concurrent
    uses exactly one succeeds. No commit: the caller commits it together with
    the change the credential authorises."""
    now = now or datetime.utcnow()
    row, user = _lookup(db, raw, purpose, now)
    if not mark_used(db, row.id, now):
        raise AuthTokenError("used")
    return user


def mark_used(db: Session, token_id: int, now: datetime) -> bool:
    """The one-time step: a conditional UPDATE. PostgreSQL serialises two of
    them on the row; the second sees `consumed_at` set and changes nothing."""
    return db.query(AuthToken).filter(
        AuthToken.id == token_id, AuthToken.consumed_at.is_(None), AuthToken.revoked_at.is_(None),
    ).update({AuthToken.consumed_at: now, AuthToken.updated_at: now}, synchronize_session=False) == 1
