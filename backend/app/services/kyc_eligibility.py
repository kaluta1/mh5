"""The one KYC rule for money: only an APPROVED verification qualifies.

Pending, in progress, proof of address pending, rejected, expired, under review or no verification at all do
not. Email verification, seller verification and wallet approval are never substitutes. Used for cashouts
(both methods) and for earning commissions and advertising revenue shares (owner rule 2026-11-02).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

NO_VERIFICATION = "none"


def kyc_status(db: Session, user_id: Optional[int]) -> str:
    """The member's authoritative KYC status now ('approved', 'pending', ..., or 'none')."""
    if user_id is None:
        return NO_VERIFICATION
    from app.crud import crud_kyc

    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=int(user_id))
    if verification is None or verification.status is None:
        return NO_VERIFICATION
    return str(getattr(verification.status, "value", verification.status))


def is_approved(db: Session, user_id: Optional[int]) -> bool:
    from app.models.kyc import KYCStatus

    return kyc_status(db, user_id) == KYCStatus.APPROVED.value
