"""Passwords whose stored hash is known to have been exposed.

When a copy of the user table leaves the platform (a database dump in the
wrong place, for example), every password hash in it can be attacked offline,
whatever the hashing scheme. The account stays usable, but it must not be given
more power until its password has been changed.

What is kept is only a FINGERPRINT: the SHA-256 of the stored hash string
(table exposed_password_fingerprints, loaded from the exposed copy by
app/scripts/load_exposed_password_fingerprints.py). Neither the password nor
the stored hash can be recovered from it, and it names no account: it only
answers "is this account's CURRENT hash one of the exposed ones?". A new
password always produces a new hash (a fresh salt), so the answer turns to no
as soon as the password is changed, and nothing has to be removed by hand.

Used to refuse the Super Admin role (granting and the first bootstrap) to an
account whose password was exposed.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.auth_security import ExposedPasswordFingerprint

PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


def fingerprint(hashed_password: Optional[str]) -> str:
    return hashlib.sha256((hashed_password or "").encode("utf-8")).hexdigest()


def loaded_count(db: Session) -> int:
    return db.query(ExposedPasswordFingerprint).count()


def is_exposed(db: Session, user) -> bool:
    """Is this account's CURRENT password hash one of the exposed ones?"""
    hashed = getattr(user, "hashed_password", None)
    if not hashed:
        return False
    return db.query(ExposedPasswordFingerprint.id).filter(
        ExposedPasswordFingerprint.fingerprint == fingerprint(hashed)).first() is not None


def add(db: Session, hashed_passwords: Iterable[str], *, source: str) -> int:
    """Record the fingerprints of these exposed hashes; returns how many were new. The caller commits."""
    known = {row[0] for row in db.query(ExposedPasswordFingerprint.fingerprint).all()}
    fresh = {fingerprint(h) for h in hashed_passwords if h} - known
    for fp in sorted(fresh):
        db.add(ExposedPasswordFingerprint(fingerprint=fp, source=source[:100]))
    return len(fresh)
