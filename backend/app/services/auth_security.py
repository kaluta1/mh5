"""Account security operations shared by the auth endpoints (EMAIL-2).

Sessions
--------
Access tokens are self-contained JWTs; there is no session table. Each one
carries `sv`, the account's `security_version` when it was issued, and every
authenticated request compares it with the account's current value
(app.api.deps). `set_password` increments the value, so a password change or a
password reset invalidates EVERY access token issued before it, on every
device, at once. Tokens issued before this mechanism existed carry no `sv` and
count as 0, the column default: nobody is signed out by the deployment itself.

The check is specific to access tokens. Guardian tokens, nominee claim tokens,
KYC document view tokens, media-session cookies and referral attribution
tokens are separate credentials with their own validation and are untouched.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import access_token_security_version, decode_access_token, get_password_hash
from app.models.accounting import AuditTrail
from app.models.auth_security import PURPOSE_PASSWORD_RESET
from app.models.user import User
from app.services import auth_tokens

logger = logging.getLogger(__name__)

EMAIL_NOT_VERIFIED_CODE = "EMAIL_NOT_VERIFIED"
EMAIL_NOT_VERIFIED_MESSAGE = ("Please confirm your email address before signing in. Check your inbox for the "
                              "confirmation link, or request a new one.")

AUDIT_EMAIL_VERIFIED = "AUTH_EMAIL_VERIFIED"
AUDIT_PASSWORD_RESET = "AUTH_PASSWORD_RESET"
AUDIT_PASSWORD_CHANGED = "AUTH_PASSWORD_CHANGED"
AUDIT_SESSIONS_INVALIDATED = "AUTH_SESSIONS_INVALIDATED"


def normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def find_account(db: Session, email: Optional[str]) -> Optional[User]:
    """The single account an email address designates, or None.

    Exact match first. Otherwise a case-insensitive match, but only when it is
    unambiguous: historical data holds a few addresses that differ only by
    letter case, and guessing between two accounts would send one person's
    reset link to a lookup made for the other."""
    address = (email or "").strip()
    if not address:
        return None
    user = db.query(User).filter(User.email == address).first()
    if user is not None:
        return user
    matches = db.query(User).filter(func.lower(User.email) == normalize_email(address)).limit(2).all()
    return matches[0] if len(matches) == 1 else None


def email_in_use(db: Session, email: Optional[str]) -> bool:
    """Is there ANY account for this address, ignoring letter case? Used to
    refuse a duplicate registration."""
    return db.query(User.id).filter(func.lower(User.email) == normalize_email(email)).first() is not None


def audit(db: Session, user_id: int, action: str, *, ip: Optional[str] = None, details: Optional[dict] = None) -> None:
    """Add an audit row to the current transaction. `details` must never hold
    a password, a token, an email address or any other secret."""
    db.add(AuditTrail(table_name="users", record_id=int(user_id), action=action, old_values=None,
                      new_values=details or None, user_id=int(user_id), ip_address=(ip or None),
                      timestamp=datetime.utcnow()))


def set_password(db: Session, user: User, new_password: str, *, action: str, ip: Optional[str] = None,
                 now: Optional[datetime] = None) -> int:
    """Store a new password and invalidate everything that depended on the old
    one, in ONE transaction: all access tokens (security_version) and all
    outstanding password-reset credentials. Returns the new security_version.
    The caller commits."""
    now = now or datetime.utcnow()
    previous = int(user.security_version or 0)
    user.hashed_password = get_password_hash(new_password)
    user.security_version = previous + 1
    auth_tokens.revoke(db, user.id, PURPOSE_PASSWORD_RESET, now=now)
    audit(db, user.id, action, ip=ip)
    audit(db, user.id, AUDIT_SESSIONS_INVALIDATED, ip=ip,
          details={"reason": action, "security_version": previous + 1})
    db.add(user)
    return previous + 1


def access_token_is_current(payload: Optional[dict], user: Optional[User]) -> bool:
    """Was this (already signature/type checked) access token issued under the
    account's current security_version?"""
    return user is not None and access_token_security_version(payload) == int(user.security_version or 0)


def access_token_user_id(token: Optional[str], db: Optional[Session] = None) -> Optional[int]:
    """Account id proven by an access token, or None. For callers that hold no
    request-scoped session (Socket.IO handshake, media middleware). Applies the
    same security_version rule as the API dependencies."""
    payload = decode_access_token(token) if token else {}
    try:
        user_id = int((payload or {}).get("sub"))
    except (TypeError, ValueError):
        return None
    own = db is None
    if own:
        import app.db.session as session_module

        db = session_module.SessionLocal()
    try:
        current = db.query(User.security_version).filter(User.id == user_id).first()
    except Exception as exc:  # noqa: BLE001 - no identity rather than an unverified one
        logger.error("Access token could not be checked: %s", type(exc).__name__)
        return None
    finally:
        if own:
            db.close()
    if current is None or access_token_security_version(payload) != int(current[0] or 0):
        return None
    return user_id


def must_verify_email(user: Optional[User]) -> bool:
    """Is this account barred from signing in until its address is verified?

    True only for an account created under the verify-before-login rule
    (`email_verification_required`) whose address is still unverified. An
    account that predates the rule is never barred, verified or not."""
    return bool(user is not None and user.email_verification_required and not user.email_verified)
