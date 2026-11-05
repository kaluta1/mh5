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

# Verified-location foundation (owner-approved 2026-11-05). Provenance and status of every attestation:
EVIDENCE_KYC = "KYC_ADDRESS_DECLARED_CITY"      # declared profile city at an approved proof of address
ATTESTED, VERIFIED, REJECTED = "ATTESTED", "VERIFIED", "REJECTED"
USABLE = (ATTESTED, VERIFIED)                   # inventory evidence (Daily City/Local stay NOT READY regardless)


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
            from app.models.geography import City

            city = db.query(City).filter(City.id == int(user.city_id)).first()
            if city is None:
                return None                              # never attest a city that does not exist
            row = AdvGeoAttestation(user_id=user.id, city_id=city.id, country_id=city.country_id,
                                    kyc_verification_id=verification_id, attested_at=now,
                                    evidence_source=EVIDENCE_KYC, status=ATTESTED)
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
                        AdvGeoAttestation.status.in_(USABLE), AdvGeoAttestation.city_id == int(row.city_id)).first())
    return int(row.city_id) if attested is not None else None


# ---------------------------------------------------------------- administrator review

class GeoError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def review(db: Session, attestation_id: int, *, actor, decision: str, note: str,
           now: Optional[datetime] = None) -> AdvGeoAttestation:
    """An administrator with manage_advertising checked the evidence: ATTESTED -> VERIFIED or REJECTED. Never
    one's own attestation, never a revoked one; the decision and note are audited. A later profile change still
    revokes a VERIFIED row (on_profile_city_change)."""
    from app.models.accounting import AuditTrail
    from app.services.ad_campaigns import PERMISSION_MANAGE
    from app.services.admin_security import has_permission

    if actor is None or not has_permission(actor, PERMISSION_MANAGE):
        raise GeoError("FORBIDDEN", "Location review needs the manage_advertising permission", 403)
    if decision not in (VERIFIED, REJECTED):
        raise GeoError("INVALID_DECISION", "decision must be VERIFIED or REJECTED", 400)
    if len((note or "").strip()) < 3:
        raise GeoError("NOTE_REQUIRED", "A note describing the evidence checked is required", 400)
    row = db.query(AdvGeoAttestation).filter(AdvGeoAttestation.id == attestation_id).with_for_update().first()
    if row is None:
        raise GeoError("NOT_FOUND", "Attestation not found", 404)
    if int(row.user_id) == int(actor.id):
        raise GeoError("SELF_REVIEW", "Administrators cannot verify their own location", 403)
    if row.revoked_at is not None:
        raise GeoError("REVOKED", "This attestation was revoked; a new verification is needed")
    if row.status != ATTESTED:
        raise GeoError("ALREADY_REVIEWED", f"This attestation is already {row.status.lower()}")
    now = now or datetime.utcnow()
    row.status, row.reviewed_by_user_id, row.reviewed_at = decision, actor.id, now
    row.review_note = note.strip()[:300]
    db.add(AuditTrail(table_name="adv_geo_attestations", record_id=row.id, action=f"GEO_{decision}",
                      old_values={"status": ATTESTED}, new_values={"status": decision, "note": row.review_note},
                      user_id=actor.id))
    db.flush()
    return row


def view(row: AdvGeoAttestation) -> dict:
    return {"id": row.id, "user_id": row.user_id, "country_id": row.country_id, "city_id": row.city_id,
            "local_area_id": row.local_area_id, "evidence_source": row.evidence_source, "status": row.status,
            "kyc_verification_id": row.kyc_verification_id, "attested_at": row.attested_at.isoformat(),
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None, "revoke_reason": row.revoke_reason,
            "reviewed_by_user_id": row.reviewed_by_user_id,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None, "review_note": row.review_note}
