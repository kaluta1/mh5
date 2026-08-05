"""
Route KYC operations to the active provider (Kaluta default, Shufti Pro legacy).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.kyc import KYCStatus, VerificationProvider
from app.models.user import User
from app.schemas.kyc import KYCVerificationUpdate
from app.services.kaluta_kyc import (
    active_kyc_provider,
    is_kaluta_active,
    kaluta_kyc_service,
    kyc_flags_from_kaluta_session,
)
from app.services.shufti_pro import kyc_flags_from_shufti_payload, shufti_pro_service

logger = logging.getLogger(__name__)


def provider_for_verification(verification) -> str:
    if verification and verification.provider:
        val = verification.provider.value if hasattr(verification.provider, "value") else str(verification.provider)
        if val in ("shufti_pro", "kaluta"):
            return val
    return active_kyc_provider()


def verification_provider_enum() -> VerificationProvider:
    return VerificationProvider.KALUTA if is_kaluta_active() else VerificationProvider.SHUFTI_PRO


def generate_kyc_reference(user_id: int) -> str:
    if is_kaluta_active():
        return kaluta_kyc_service.generate_reference(user_id)
    return shufti_pro_service.generate_reference()


async def check_kyc_session_validity(verification) -> Dict[str, Any]:
    if provider_for_verification(verification) == "shufti_pro":
        reference = verification.reference_id
        if not reference:
            return {"is_valid": False, "is_completed": False, "data": {}}
        return await shufti_pro_service.check_reference_validity(reference)
    return await kaluta_kyc_service.check_reference_validity(verification)


def _flags_from_validity(validity_check: Dict[str, Any], provider: str) -> Dict[str, bool]:
    raw = validity_check.get("data") or {}
    if not isinstance(raw, dict):
        raw = {}
    is_ok = bool(validity_check.get("is_accepted"))
    if provider == "shufti_pro":
        return kyc_flags_from_shufti_payload(raw, overall_accepted=is_ok)
    return kyc_flags_from_kaluta_session(raw)


async def initiate_kyc_session(
    *,
    db: Session,
    user: User,
    reference: str,
    language: str,
    country_iso: Optional[str],
    residential_address: Optional[str],
) -> Dict[str, Any]:
    if is_kaluta_active():
        return await kaluta_kyc_service.create_session(
            external_id=reference,
            user=user,
            country_iso=country_iso,
            residential_address=residential_address,
        )

    return await shufti_pro_service.initiate_verification(
        reference=reference,
        email=user.email,
        country=country_iso,
        language=language,
    )


def apply_provider_identity_accepted(db: Session, *, crud_kyc, verification, flags: Dict[str, bool], external_id: str, provider_response=None, webhook_data=None):
    """Shufti/Kaluta ID+face passed — PoA step unless Kaluta already verified address."""
    if flags.get("kaluta_poa_complete"):
        crud_kyc.kyc_verification.apply_shufti_identity_accepted(
            db,
            verification=verification,
            flags=flags,
            external_verification_id=external_id,
            provider_response=provider_response,
            webhook_data=webhook_data,
        )
        crud_kyc.kyc_verification.finalize_proof_of_address_auto(db, verification_id=verification.id)
        from app.services.payment_accounting import payment_accounting

        payment_accounting.post_kyc_verification_recognition_for_user(db, verification.user_id)
        return

    crud_kyc.kyc_verification.apply_shufti_identity_accepted(
        db,
        verification=verification,
        flags=flags,
        external_verification_id=external_id,
        provider_response=provider_response,
        webhook_data=webhook_data,
    )


def apply_provider_rejected(db: Session, *, crud_kyc, verification, flags: Dict[str, bool], reason: str, external_id: str, provider_response=None, webhook_data=None):
    crud_kyc.kyc_verification.reject_verification(db, verification_id=verification.id, reason=reason)
    update_data = KYCVerificationUpdate(
        external_verification_id=external_id,
        provider_response=str(provider_response) if provider_response is not None else None,
        webhook_data=str(webhook_data) if webhook_data is not None else None,
        rejection_reason=reason,
        identity_verified=flags.get("identity_verified", False),
        document_verified=flags.get("document_verified", False),
        face_verified=flags.get("face_verified", False),
    )
    crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)


async def sync_verification_from_provider(db: Session, *, crud_kyc, verification) -> Optional[Dict[str, Any]]:
    """Poll provider and update DB if terminal. Returns response dict when identity step completes."""
    if verification.status not in (KYCStatus.PENDING, KYCStatus.IN_PROGRESS) or not verification.reference_id:
        return None

    provider = provider_for_verification(verification)
    validity_check = await check_kyc_session_validity(verification)
    if not validity_check.get("is_completed"):
        return None

    flags = _flags_from_validity(validity_check, provider)
    raw = validity_check.get("data") or {}

    if validity_check.get("is_accepted"):
        apply_provider_identity_accepted(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            external_id=verification.reference_id,
            provider_response=json.dumps(raw) if raw else None,
        )
        db.refresh(verification)
        if verification.status == KYCStatus.APPROVED:
            return {"fully_approved": True}
        return {
            "status": "pending_proof_of_address",
            "kyc_step": 2,
            "needs_proof_of_address": True,
        }

    apply_provider_rejected(
        db,
        crud_kyc=crud_kyc,
        verification=verification,
        flags=flags,
        reason=(raw.get("rejection_reason") if isinstance(raw, dict) else None) or "Verification failed",
        external_id=verification.reference_id,
        provider_response=json.dumps(raw) if raw else None,
    )
    u = db.query(User).filter(User.id == verification.user_id).first()
    if u:
        u.identity_verified = False
        u.address_verified = False
    db.commit()
    db.refresh(verification)
    return {"status": "rejected"}


def process_kaluta_webhook_event(db: Session, *, crud_kyc, payload: Dict[str, Any]) -> bool:
    event = (payload.get("event") or "").lower()
    session = payload.get("session") if isinstance(payload.get("session"), dict) else payload
    if not isinstance(session, dict):
        logger.warning("Kaluta webhook missing session object")
        return False

    external_id = session.get("external_id")
    session_id = str(session.get("id") or session.get("session_id") or "")

    verification = None
    if external_id:
        verification = crud_kyc.kyc_verification.get_by_reference(db, reference_id=str(external_id))
    if not verification and session_id:
        verification = crud_kyc.kyc_verification.get_by_external_id(db, external_id=session_id)

    if not verification:
        logger.warning("Kaluta webhook: verification not found external_id=%s session_id=%s", external_id, session_id)
        return False

    wh_raw = json.dumps(payload)
    flags = kyc_flags_from_kaluta_session(session)

    if event in ("session.approved", "session.verified"):
        apply_provider_identity_accepted(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            external_id=session_id or str(external_id or ""),
            provider_response=json.dumps(session),
            webhook_data=wh_raw,
        )
        identity = session.get("identity") if isinstance(session.get("identity"), dict) else {}
        updates = {}
        if identity.get("first_name"):
            updates["verified_first_name"] = identity["first_name"]
        if identity.get("last_name"):
            updates["verified_last_name"] = identity["last_name"]
        if identity.get("nationality"):
            updates["verified_nationality"] = identity["nationality"]
        if updates:
            crud_kyc.kyc_verification.update(
                db,
                db_obj=verification,
                obj_in=KYCVerificationUpdate(**updates),
            )
        return True

    if event == "session.rejected":
        reason = session.get("rejection_reason") or "Verification rejected"
        apply_provider_rejected(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            reason=str(reason),
            external_id=session_id or str(external_id or ""),
            provider_response=json.dumps(session),
            webhook_data=wh_raw,
        )
        return True

    if event == "session.expired":
        crud_kyc.kyc_verification.mark_as_expired(db, verification_id=verification.id)
        return True

    # Informational events — store latest payload
    crud_kyc.kyc_verification.update(
        db,
        db_obj=verification,
        obj_in=KYCVerificationUpdate(webhook_data=wh_raw),
    )
    return True
