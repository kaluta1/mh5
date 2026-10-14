"""
Route KYC operations to the active provider (Kaluta default, Shufti Pro legacy).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.services import kyc_notifications
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, VerificationProvider
from app.models.user import User
from app.schemas.kyc import KYCVerificationUpdate
from app.services.kaluta_kyc import (
    PROVIDER_REJECTION_MARK,
    active_kyc_provider,
    is_kaluta_active,
    kaluta_kyc_service,
    kyc_flags_from_kaluta_session,
    parse_provider_time,
    storable_session,
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
    # Child/Teen Safety Phase 10: no identity data leaves for a provider unless
    # the central gate allows KYC_INITIATION for this person NOW (confirmed adults
    # only; UNKNOWN -> HOLD, minors -> REVIEW_REQUIRED). Raises FinancialEligibilityHold.
    from app.services import financial_eligibility as fe

    fe.require(db, user, fe.FinancialOperation.KYC_INITIATION)
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
        kyc_notifications.notify_status(db, verification.id)          # committed: APPROVED
        return

    crud_kyc.kyc_verification.apply_shufti_identity_accepted(
        db,
        verification=verification,
        flags=flags,
        external_verification_id=external_id,
        provider_response=provider_response,
        webhook_data=webhook_data,
    )
    kyc_notifications.notify_status(db, verification.id)              # committed: proof of address expected


def apply_provider_rejected(db: Session, *, crud_kyc, verification, flags: Dict[str, bool], reason: str, external_id: str, provider_response=None, webhook_data=None, details: Optional[str] = None):
    crud_kyc.kyc_verification.reject_verification(db, verification_id=verification.id, reason=reason, details=details)
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
    # Committed: REJECTED. The provider's reason stays in the record; the email carries none.
    kyc_notifications.notify_status(db, verification.id)


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
    if provider == "kaluta" and isinstance(raw, dict):
        raw = storable_session(raw)

    # The provider was asked over the network; a webhook may have decided this
    # verification meanwhile. Decide once, on the row as it is now.
    verification = _locked_verification(db, verification.id)
    if verification is None or verification.status not in (KYCStatus.PENDING, KYCStatus.IN_PROGRESS):
        db.rollback()
        return None

    # Kaluta: the provider's session id (the reference is ours). Shufti: the reference is the id.
    provider_id = verification.reference_id
    if provider == "kaluta":
        provider_id = str((raw.get("id") if isinstance(raw, dict) else None)
                          or verification.external_verification_id or verification.reference_id)

    if validity_check.get("expired"):
        # The session ran out: not a rejection, and the attempt is not used up.
        current = str(verification.external_verification_id or "")
        if provider == "kaluta" and current and provider_id != current:
            db.rollback()
            return None
        if not _session_marked_expired(verification):
            _mark_session_ended(db, verification)
            try:
                db.add(KYCAuditLog(verification_id=verification.id, action="kaluta_session_expired",
                                   details=f"Session {provider_id} ran out (status read); the attempt stays open",
                                   old_status=getattr(verification.status, "value", verification.status),
                                   new_status=getattr(verification.status, "value", verification.status),
                                   performed_by_user_id=None, performed_by_admin=False, timestamp=datetime.utcnow()))
                db.commit()
            except Exception as exc:  # noqa: BLE001 - the state is committed; the trail must not undo it
                db.rollback()
                logger.error("KYC audit row could not be written (%s)", type(exc).__name__)
        else:
            db.rollback()
        return {"status": "session_expired"}

    if validity_check.get("is_accepted"):
        apply_provider_identity_accepted(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            external_id=provider_id,
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
        external_id=provider_id,
        provider_response=json.dumps(raw) if raw else None,
        details=(f"{PROVIDER_REJECTION_MARK}{raw.get('id') or verification.external_verification_id or ''}"
                 if provider == "kaluta" and isinstance(raw, dict) else None),
    )
    u = db.query(User).filter(User.id == verification.user_id).first()
    if u:
        u.identity_verified = False
        u.address_verified = False
    db.commit()
    db.refresh(verification)
    return {"status": "rejected"}


# Outcome of one webhook delivery. Everything except UNKNOWN is answered 2xx:
# the provider retries a delivery that is not acknowledged, and a delivery that
# changes nothing (a duplicate, a late or superseded event) must not be retried.
APPLIED, DUPLICATE, IGNORED, UNKNOWN = "applied", "duplicate", "ignored", "unknown"

_APPROVAL_EVENTS = ("session.approved", "session.verified")      # the second is the provider's alias of the first
_OPEN = (KYCStatus.PENDING, KYCStatus.IN_PROGRESS)
_IDENTITY_DONE = (KYCStatus.PENDING_PROOF_OF_ADDRESS, KYCStatus.APPROVED)


def _locked_verification(db: Session, verification_id: int):
    """The verification row, locked until the next commit and re-read from the
    database: two deliveries of the same event, or a delivery and a status
    poll, decide one after the other and the second sees what the first did."""
    return (db.query(KYCVerification).filter(KYCVerification.id == verification_id)
            .with_for_update().populate_existing().first())


def _session_marked_expired(verification) -> bool:
    return verification.expires_at is not None and verification.expires_at <= datetime.utcnow()


def _mark_session_ended(db: Session, verification) -> None:
    """The current provider session can no longer be used. The verification
    stays open (same attempt, same payment); its link is not handed out again."""
    verification.expires_at = datetime.utcnow()
    db.commit()


def _score(value: Any) -> Optional[int]:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _audit_kaluta(db: Session, verification, action: str, details: str, *, old_status, ip: Optional[str]) -> None:
    """One audit row per delivery that concerned a verification. Holds the event,
    the provider's session id and what was done: never a name, a document number
    or the provider's reason."""
    try:
        db.add(KYCAuditLog(
            verification_id=verification.id, action=action[:100], details=details[:1000],
            old_status=getattr(old_status, "value", old_status),
            new_status=getattr(verification.status, "value", verification.status),
            performed_by_user_id=None, performed_by_admin=False, timestamp=datetime.utcnow(),
            ip_address=(ip or None)))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the decision is already committed; the trail must not undo it
        db.rollback()
        logger.error("Kaluta audit row could not be written (%s)", type(exc).__name__)


def handle_kaluta_webhook(db: Session, *, crud_kyc, payload: Dict[str, Any], ip: Optional[str] = None) -> str:
    """Apply one VERIFIED Kaluta webhook delivery. Idempotent: the state of the
    verification decides, not the number of deliveries."""
    event = str(payload.get("event") or "").strip().lower()
    session = payload.get("session") if isinstance(payload.get("session"), dict) else payload
    if not isinstance(session, dict) or not event:
        logger.warning("Kaluta webhook without an event or a session object")
        return UNKNOWN

    external_id = session.get("external_id")
    session_id = str(session.get("id") or session.get("session_id") or "")

    verification = None
    if external_id:
        verification = crud_kyc.kyc_verification.get_by_reference(db, reference_id=str(external_id))
    if not verification and session_id:
        verification = crud_kyc.kyc_verification.get_by_external_id(db, external_id=session_id)

    if not verification:
        # A session of an earlier cycle (a new reference was issued since), or not ours at all.
        logger.warning("Kaluta webhook %s: no verification for this reference or session", event)
        return UNKNOWN

    verification = _locked_verification(db, verification.id)
    if verification is None:
        return UNKNOWN
    old_status = verification.status

    def done(outcome: str, note: str) -> str:
        retry = (session.get("metadata") or {}).get("_retry_index") if isinstance(session.get("metadata"), dict) else None
        _audit_kaluta(db, verification, f"kaluta_webhook:{event}"[:100],
                      f"{outcome}: {note}; session {session_id or '-'}"
                      + (f"; provider retry {retry}" if retry is not None else ""),
                      old_status=old_status, ip=ip)
        return outcome

    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    bound_user_id = metadata.get("user_id")
    if bound_user_id is not None and str(bound_user_id) != str(verification.user_id):
        logger.warning("Kaluta webhook user binding mismatch for verification_id=%s", verification.id)
        db.rollback()
        return UNKNOWN
    if provider_for_verification(verification) != "kaluta":
        return done(IGNORED, "this verification belongs to another provider")
    if external_id and str(external_id) != str(verification.reference_id or ""):
        return done(IGNORED, "the event is for an earlier reference of this verification")

    stored_session = storable_session(session)
    wh_raw = json.dumps({"event": event, "timestamp": payload.get("timestamp"), "session": stored_session})
    flags = kyc_flags_from_kaluta_session(session)
    reported = str(session.get("status") or "").strip().lower()

    if event in _APPROVAL_EVENTS:
        if reported and reported != "approved":
            return done(IGNORED, "the event and the session status disagree")
        if old_status in _IDENTITY_DONE:
            return done(DUPLICATE, "identity was already accepted")
        after_provider_rejection = (old_status == KYCStatus.REJECTED
                                    and str(verification.rejection_details or "").startswith(PROVIDER_REJECTION_MARK))
        if old_status not in _OPEN and not after_provider_rejection:
            # Rejected by an administrator, expired, or under review: the provider does not reopen it.
            return done(IGNORED, "the verification is closed and was not rejected by the provider")
        apply_provider_identity_accepted(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            external_id=session_id or str(external_id or ""),
            provider_response=json.dumps(stored_session),
            webhook_data=wh_raw,
        )
        identity = session.get("identity") if isinstance(session.get("identity"), dict) else {}
        scores = session.get("scores") if isinstance(session.get("scores"), dict) else {}
        updates: Dict[str, Any] = {}
        if identity.get("first_name"):
            updates["verified_first_name"] = str(identity["first_name"])[:100]
        if identity.get("last_name"):
            updates["verified_last_name"] = str(identity["last_name"])[:100]
        if identity.get("nationality"):
            updates["verified_nationality"] = str(identity["nationality"])[:100]
        born = parse_provider_time(identity.get("date_of_birth"))
        if born is not None:
            updates["verified_date_of_birth"] = born
        for column, value in (("identity_confidence_score", session.get("overall_score")),
                              ("document_confidence_score", scores.get("document")),
                              ("face_match_score", scores.get("face"))):
            if _score(value) is not None:
                updates[column] = _score(value)
        if after_provider_rejection:
            updates["rejection_reason"] = None
            updates["rejection_details"] = None
        if updates:
            crud_kyc.kyc_verification.update(
                db,
                db_obj=verification,
                obj_in=KYCVerificationUpdate(**updates),
            )
        return done(APPLIED, "identity accepted after a provider retry" if after_provider_rejection
                    else "identity accepted")

    if event == "session.rejected":
        if reported and reported != "rejected":
            return done(IGNORED, "the event and the session status disagree")
        if old_status == KYCStatus.REJECTED:
            return done(DUPLICATE, "already rejected")
        if old_status in _IDENTITY_DONE:
            logger.warning("Ignoring stale Kaluta rejection for verification_id=%s", verification.id)
            return done(IGNORED, "identity was already accepted")
        if old_status not in _OPEN:
            return done(IGNORED, "the verification is closed")
        reason = session.get("rejection_reason") or "Verification rejected"
        apply_provider_rejected(
            db,
            crud_kyc=crud_kyc,
            verification=verification,
            flags=flags,
            reason=str(reason)[:2000],
            external_id=session_id or str(external_id or ""),
            provider_response=json.dumps(stored_session),
            webhook_data=wh_raw,
            details=f"{PROVIDER_REJECTION_MARK}{session_id}",
        )
        return done(APPLIED, "rejected by the provider")

    if event == "session.expired":
        # The provider SESSION ran out, not the member's attempt: the attempt
        # stays open and is not used up. The member gets a fresh session for it,
        # without a payment (within the session limit of kyc_settings).
        if old_status == KYCStatus.EXPIRED:
            return done(DUPLICATE, "already expired")
        if old_status not in _OPEN:
            return done(IGNORED, "the verification is not open")
        current = str(verification.external_verification_id or "")
        if session_id and current and session_id != current:
            # An older session of the same reference ran out while a newer one is open.
            return done(IGNORED, "the expired session is not the current one")
        if _session_marked_expired(verification):
            return done(DUPLICATE, "the session was already marked as ended")
        _mark_session_ended(db, verification)
        return done(APPLIED, "session expired; the attempt stays open and is not used up")

    # Progress events (created, document_submitted, face_submitted, ...): noted
    # while the verification is open; never written over a decision.
    if old_status not in _OPEN:
        return done(IGNORED, "progress event after a decision")
    crud_kyc.kyc_verification.update(
        db,
        db_obj=verification,
        obj_in=KYCVerificationUpdate(webhook_data=wh_raw),
    )
    return done(APPLIED, "progress noted")


def process_kaluta_webhook_event(db: Session, *, crud_kyc, payload: Dict[str, Any], ip: Optional[str] = None) -> bool:
    """True when the delivery concerned one of our verifications (whatever it changed)."""
    return handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=payload, ip=ip) != UNKNOWN
