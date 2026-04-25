"""
Server-side enforcement: user must satisfy contest verification flags before entry.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User
from app.models.contest import Contest
from app.models.verification import UserVerification, VerificationType, VerificationStatus


def _has_approved(db: Session, user_id: int, types: Tuple[str, ...]) -> bool:
    row = (
        db.query(UserVerification.id)
        .filter(
            UserVerification.user_id == user_id,
            UserVerification.verification_type.in_(types),
            UserVerification.status == VerificationStatus.APPROVED.value,
        )
        .first()
    )
    return row is not None


def raise_if_user_missing_contest_entry_requirements(
    db: Session, user: User, contest: Contest, entry_type: Optional[str] = None
) -> None:
    """
    Ensures the current user meets all contest-level verification requirements
    (KYC, visual, voice, brand, content) for participation entries.
    Nomination entries must not be blocked by KYC/verification requirements.
    """
    normalized_entry_type = (entry_type or "").strip().lower()
    if normalized_entry_type == "nomination":
        return

    if contest.requires_kyc:
        kyc_ok = bool(
            getattr(user, "is_verified", False)
            or (
                getattr(user, "identity_verified", False)
                and getattr(user, "address_verified", False)
            )
        )
        if not kyc_ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="KYC verification is required for this contest before you can participate.",
            )

    visual_types = (
        VerificationType.SELFIE.value,
        VerificationType.SELFIE_WITH_PET.value,
        VerificationType.SELFIE_WITH_DOCUMENT.value,
    )
    if getattr(contest, "requires_visual_verification", False):
        if not _has_approved(db, user.id, visual_types):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approved visual (selfie) verification is required for this contest.",
            )

    if getattr(contest, "requires_voice_verification", False):
        if not _has_approved(db, user.id, (VerificationType.VOICE.value,)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approved voice verification is required for this contest.",
            )

    if getattr(contest, "requires_brand_verification", False):
        if not _has_approved(db, user.id, (VerificationType.BRAND.value,)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approved brand verification is required for this contest.",
            )

    if getattr(contest, "requires_content_verification", False):
        if not _has_approved(db, user.id, (VerificationType.CONTENT.value,)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approved content ownership verification is required for this contest.",
            )
