"""Verified-city evidence for advertising (Advertising Phase A remediation, review defect D2).

What the KYC proof of address establishes: a member-typed, free-text residential address that the provider
checked against a document. It does NOT establish a structured MyHigh5 city, and this module never derives
one from that text. What is recorded instead (adv_geo_attestations) is the profile city the member had at
the moment the proof of address was approved, and it stays usable only while:
  * the member is active and still address-verified,
  * the profile city is unchanged (any change revokes the attestation; a new verification is needed),
  * the attestation is not revoked.
Verifications approved before this table existed have no attestation (nothing is backfilled), so those
members provide no geographic evidence until they verify again.

Because the city is declared rather than proven by the document, Daily City stays NOT READY in
ad_packages: this evidence is the minimum gate, not a sufficient one.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvGeoAttestation

logger = logging.getLogger(__name__)


def revoke(db: Session, user_id: int, reason: str, *, now: Optional[datetime] = None) -> int:
    """Revoke every active attestation of a member (idempotent). Returns how many were revoked."""
    now = now or datetime.utcnow()
    rows = (db.query(AdvGeoAttestation)
            .filter(AdvGeoAttestation.user_id == int(user_id), AdvGeoAttestation.revoked_at.is_(None)).all())
    for row in rows:
        row.revoked_at, row.revoke_reason = now, (reason or "REVOKED")[:40]
    if rows:
        db.flush()
    return len(rows)


def attest_on_address_approval(db: Session, user, verification_id: Optional[int],
                               *, now: Optional[datetime] = None) -> Optional[AdvGeoAttestation]:
    """Called inside a proof-of-address approval. Never raises into the KYC approval: a failure only means
    no geographic evidence is recorded (the safe outcome)."""
    try:
        with db.begin_nested():
            now = now or datetime.utcnow()
            revoke(db, user.id, "SUPERSEDED", now=now)
            if not getattr(user, "city_id", None):
                return None
            row = AdvGeoAttestation(user_id=user.id, city_id=int(user.city_id), kyc_verification_id=verification_id,
                                    attested_at=now)
            db.add(row)
            db.flush()
            return row
    except Exception:  # noqa: BLE001 - geographic evidence must never block a KYC decision
        logger.exception("Geographic attestation after address approval failed (user %s)", getattr(user, "id", None))
        return None


def on_profile_city_change(db: Session, user, new_city_id) -> None:
    """A member changed the profile city: the old attestation no longer describes them."""
    if (int(new_city_id) if new_city_id else None) != (int(user.city_id) if user.city_id else None):
        revoke(db, user.id, "CITY_CHANGED")


def verified_city(db: Session, user_id: Optional[int]) -> Optional[int]:
    """The member's city when it is backed by a current attestation; None otherwise (anonymous viewers,
    unverified addresses, changed cities, revoked or missing attestations). Never a request header."""
    if not user_id:
        return None
    from app.models.user import User

    row = (db.query(User.city_id, User.address_verified, User.is_active).filter(User.id == int(user_id)).first())
    if row is None or not row.address_verified or row.is_active is False or not row.city_id:
        return None
    attested = (db.query(AdvGeoAttestation.id)
                .filter(AdvGeoAttestation.user_id == int(user_id), AdvGeoAttestation.revoked_at.is_(None),
                        AdvGeoAttestation.city_id == int(row.city_id)).first())
    return int(row.city_id) if attested is not None else None
