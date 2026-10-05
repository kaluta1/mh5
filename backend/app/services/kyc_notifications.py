"""KYC status emails (EMAIL-3).

One function, called AFTER a KYC transition has committed. It reads the
verification's COMMITTED status and sends the email that status calls for:

    PENDING_PROOF_OF_ADDRESS  -> KYC.ACTION_REQUIRED  (identity accepted; one step left)
    APPROVED                  -> KYC.APPROVED
    REJECTED                  -> KYC.REJECTED         (no reason: see below)

Every other status (pending, in progress, expired, requires review) is an
internal or provider-session state and sends nothing.

The email carries NO identity data, document data, date of birth, provider
payload or provider reason. A provider's rejection reason is internal text and
is never put in an email; only an administrator's own rejection (the admin
endpoint, unchanged) includes the reason that administrator typed for the
member.

Idempotency: one email per verification, attempt and status
(`kyc.<status>:<verification id>:<attempt>`), the same key the admin endpoints
already use. A webhook delivered twice, a webhook plus a status poll, or an
admin action after an automatic one cannot send the same decision twice.

It never raises: the KYC decision is committed and stays committed.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.kyc import KYCStatus, KYCVerification
from app.models.user import User
from app.services.email import email_service
from app.services.email_events import EmailEvent

logger = logging.getLogger(__name__)

_EVENTS = {
    KYCStatus.PENDING_PROOF_OF_ADDRESS: (EmailEvent.KYC_ACTION_REQUIRED, "action_required"),
    KYCStatus.APPROVED: (EmailEvent.KYC_APPROVED, "approved"),
    KYCStatus.REJECTED: (EmailEvent.KYC_REJECTED, "rejected"),
}


def notify_status(db: Session, verification_id: Optional[int]) -> None:
    if not verification_id:
        return
    try:
        verification = db.query(KYCVerification).filter(KYCVerification.id == verification_id).first()
        if verification is None:
            return
        db.refresh(verification)                     # the committed row, not what a caller believes
        mapping = _EVENTS.get(verification.status)
        if mapping is None:
            return
        event, name = mapping
        user = db.query(User).filter(User.id == verification.user_id).first()
        if user is None or not user.is_active or getattr(user, "is_deleted", False) or not (user.email or "").strip():
            return
        email_service.enqueue(
            db,
            event=event,
            recipient=user.email,
            user_id=user.id,
            lang=getattr(user, "preferred_language", None),
            idempotency_key=f"kyc.{name}:{verification.id}:{int(verification.attempts_count or 0)}",
        )
    except Exception as exc:  # noqa: BLE001 - the KYC decision is committed; email never undoes it
        logger.error("KYC email for verification %s could not be queued: %s", verification_id, type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
