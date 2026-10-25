"""Manually recorded payments: two administrators (maker-checker).

A payment that did not arrive through the payment provider is entered in two
steps by two different people:

1. RECORD (maker). An administrator holding `grant_manual_payments` says that
   a member paid for a product, with a reason. The deposit is created (or an
   unfinished provider deposit for that product is attached) and stays
   PENDING: nothing is credited, posted to the ledger or commissioned.
2. CONFIRM (checker). A DIFFERENT administrator holding the same permission
   confirms that the money was received, citing where (evidence reference).
   Only then is the deposit VALIDATED and the normal pipeline run (accounting,
   product credit, NEW_V2 commission), in one transaction.

The checker is never the maker, never the member, never anybody above the
member in the referral structure, and the payment is refused if any resulting
commission would go to the maker or the checker. Every step needs the current
password and writes an audit record; every refusal is audited. A request is
decided once (row lock + state check): a second confirmation, rejection or
cancellation is refused with ALREADY_DECIDED.

REJECT (checker) and CANCEL (maker) close a request: a deposit the request
created becomes FAILED; an attached provider deposit is left as it was.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission
from app.models.financial_controls import ManualPaymentConfirmation
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import admin_security
from app.services.financial_integrity import money

GRANTABLE_PRODUCT_CODES = ["kyc", "mfm_membership", "annual_membership", "founding_membership"]
REASON_MIN_LENGTH = 10
EVIDENCE_MIN_LENGTH = 6
PERMISSION = admin_security.PERMISSION_GRANT_PAYMENTS

REQUESTED, CONFIRMED, REJECTED, CANCELLED = "REQUESTED", "CONFIRMED", "REJECTED", "CANCELLED"
AUDIT_REQUESTED = "MANUAL_PAYMENT_REQUESTED"
AUDIT_CONFIRMED = "ADMIN_PAYMENT_GRANT"          # the moment money is recorded as received (unchanged name)
AUDIT_REJECTED = "MANUAL_PAYMENT_REJECTED"
AUDIT_CANCELLED = "MANUAL_PAYMENT_CANCELLED"
AUDIT_SUPERSEDED = "MANUAL_PAYMENT_SUPERSEDED"


class ManualPaymentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class Outcome:
    status: str
    request: Optional[ManualPaymentConfirmation]
    deposit: Optional[Deposit]
    identity_verified: bool = False


def _clean(text: Optional[str]) -> str:
    """Whitespace-normalised administrator text. It is written into the deposit's notes,
    where the reversal markers live, so text carrying a marker is refused."""
    from app.services.financial_reversal import REVERSAL_MARKERS

    cleaned = " ".join((text or "").split())
    if any(marker.lower() in cleaned.lower() for marker in REVERSAL_MARKERS):
        raise ManualPaymentError("TEXT_NOT_ALLOWED", "This text is reserved for system reversal records.", 400)
    return cleaned


def _refuse(db: Session, actor, target_id: int, attempted: str, code: str, message: str, ip: Optional[str],
            status_code: int = 403) -> ManualPaymentError:
    admin_security.record_denial(db, actor=actor, target_id=target_id, attempted=attempted, code=code, ip=ip)
    return ManualPaymentError(code, message, status_code)


def _authorize(db: Session, actor, member_id: int, password: Optional[str], attempted: str,
               ip: Optional[str]) -> None:
    try:
        admin_security.authorize(db, actor, permission=PERMISSION, password=password, target_id=member_id,
                                 attempted=attempted, ip=ip)
    except admin_security.AdminSecurityError as exc:
        raise ManualPaymentError(exc.code, str(exc), exc.status_code) from None


def _locked_request(db: Session, request_id: int) -> ManualPaymentConfirmation:
    row = (db.query(ManualPaymentConfirmation).filter(ManualPaymentConfirmation.id == request_id)
           .with_for_update().populate_existing().first())
    if row is None:
        db.rollback()
        raise ManualPaymentError("NOT_FOUND", "Manual payment request not found.", 404)
    return row


def _close_deposit(db: Session, request: ManualPaymentConfirmation, note: str) -> None:
    """A deposit the request created is closed as FAILED; an attached provider deposit is left alone."""
    if not request.created_new_deposit:
        return
    deposit = db.query(Deposit).filter(Deposit.id == request.deposit_id).with_for_update().one()
    if deposit.status in (DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID):
        deposit.status = DepositStatus.FAILED
        deposit.admin_notes = f"{deposit.admin_notes or ''}\n{note}".strip()[:1000]


# ---------------------------------------------------------------------------
# 1. Record (maker)
# ---------------------------------------------------------------------------

def record(db: Session, actor, member_id: int, *, product_code: str, reason: str, password: Optional[str],
           amount: Optional[Decimal] = None, verify_identity: bool = False, ip: Optional[str] = None,
           now: Optional[datetime] = None) -> Outcome:
    """Record a payment received outside the provider. Credits nothing. Commits."""
    from app.crud import crud_deposit
    from app.services.legacy_business_model import is_legacy_founding_product
    from app.services.new_model_ledger import model_version_for_new_event

    now = now or datetime.utcnow()
    product_code = (product_code or "kyc").strip().lower()
    if is_legacy_founding_product(product_code):
        raise ManualPaymentError("RETIRED", "Founding memberships are retired and cannot be granted.", 410)
    if verify_identity:
        # KYC is decided by the provider only: a payment never marks an identity verified.
        raise ManualPaymentError("KYC_DECIDED_BY_PROVIDER", "KYC is verified automatically by the provider. "
                                 "A manual payment cannot mark an identity verified.", 410)
    _authorize(db, actor, member_id, password, "record manual payment", ip)
    reason = _clean(reason)
    if len(reason) < REASON_MIN_LENGTH:
        raise ManualPaymentError("REASON_REQUIRED", "Say which payment this is: a reference to the payment that was "
                                                    f"received (at least {REASON_MIN_LENGTH} characters).", 400)
    if product_code not in GRANTABLE_PRODUCT_CODES:
        raise ManualPaymentError("UNSUPPORTED_PRODUCT",
                                 "Unsupported product_code. Allowed: " + ", ".join(GRANTABLE_PRODUCT_CODES), 400)
    member = db.query(User).filter(User.id == member_id).with_for_update().first()
    if member is None:
        raise ManualPaymentError("NOT_FOUND", "User not found", 404)
    if not member.is_active or getattr(member, "is_deleted", False):
        raise ManualPaymentError("TARGET_NOT_ELIGIBLE", "A payment cannot be recorded for an inactive account.")
    if admin_security.earns_from_payment_by(db, actor.id, member.id):
        raise _refuse(db, actor, member_id, "record manual payment", "COMMISSION_CONFLICT",
                      "You cannot record a payment for a member in your own referral line: you would receive a "
                      "commission from it. Another authorized administrator has to record it.", ip)
    product = db.query(ProductType).filter(ProductType.code == product_code).first()
    if product is None:
        raise ManualPaymentError("NOT_FOUND", f"Product type '{product_code}' not found", 404)
    price = money(product.price)
    if amount is not None and money(amount) != price:
        raise ManualPaymentError("AMOUNT_MISMATCH", "Admin amount must match the server product price", 400)

    if crud_deposit.deposit.get_valid_deposit_for_product(db, user_id=member.id, product_code=product_code):
        db.rollback()
        return Outcome("already_paid", None, None)
    if db.query(ManualPaymentConfirmation.id).filter(ManualPaymentConfirmation.member_id == member.id,
                                                     ManualPaymentConfirmation.product_code == product_code,
                                                     ManualPaymentConfirmation.status == REQUESTED).first():
        db.rollback()
        raise ManualPaymentError("REQUEST_PENDING",
                                 "A manual payment for this member and product is already awaiting confirmation.")

    note = f"Manual payment recorded by admin #{actor.id}, awaiting confirmation by a second administrator: {reason}"
    # An unfinished provider deposit for this product is attached (keeps one history per payment).
    deposit = (db.query(Deposit)
               .filter(Deposit.user_id == member.id, Deposit.product_type_id == product.id,
                       Deposit.status.in_([DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID]))
               .order_by(Deposit.created_at.desc()).with_for_update().first())
    created_new = deposit is None
    if created_new:
        deposit = Deposit(user_id=member.id, product_type_id=product.id, amount=price,
                          currency=(product.currency or "USD"), order_id=f"ADMIN-{uuid.uuid4().hex}",
                          status=DepositStatus.PENDING, business_model_version=model_version_for_new_event(db),
                          admin_notes=note[:1000])
        db.add(deposit)
    else:
        deposit.admin_notes = f"{deposit.admin_notes or ''}\n{note}".strip()[:1000]
    db.flush()
    request = ManualPaymentConfirmation(
        deposit_id=deposit.id, member_id=member.id, product_code=product_code, amount=price,
        currency=(product.currency or "USD").upper(), status=REQUESTED, created_new_deposit=created_new,
        verify_identity_requested=bool(verify_identity), requested_by=actor.id, requested_at=now,
        request_reason=reason[:2000])
    db.add(request)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ManualPaymentError("REQUEST_PENDING",
                                 "A manual payment for this member and product is already awaiting confirmation.") from None
    admin_security.audit(db, actor_id=actor.id, record_id=member.id, action=AUDIT_REQUESTED, ip=ip,
                         new={"request_id": request.id, "deposit_id": deposit.id, "product_code": product_code,
                              "amount": str(price), "reason": reason[:300], "created_new_deposit": created_new,
                              "verify_identity_requested": bool(verify_identity)})
    db.commit()
    db.refresh(request)
    db.refresh(deposit)
    return Outcome("pending_confirmation", request, deposit)


# ---------------------------------------------------------------------------
# 2. Confirm (checker)
# ---------------------------------------------------------------------------

def confirm(db: Session, actor, request_id: int, *, password: Optional[str], evidence_reference: str,
            note: Optional[str] = None, ip: Optional[str] = None, now: Optional[datetime] = None) -> Outcome:
    """A second administrator confirms the money was received. Commits."""
    from app.services.commission_distribution import process_payment_validation
    from app.services.financial_reversal import is_reversed_deposit

    now = now or datetime.utcnow()
    probe = db.query(ManualPaymentConfirmation).filter(ManualPaymentConfirmation.id == request_id).first()
    if probe is None:
        raise ManualPaymentError("NOT_FOUND", "Manual payment request not found.", 404)
    member_id = int(probe.member_id)
    _authorize(db, actor, member_id, password, "confirm manual payment", ip)
    evidence = _clean(evidence_reference)
    note = _clean(note)                      # checked before anything is locked or credited
    if len(evidence) < EVIDENCE_MIN_LENGTH:
        raise ManualPaymentError("EVIDENCE_REQUIRED", "Say where the money was received (transaction id, bank "
                                                      f"reference...; at least {EVIDENCE_MIN_LENGTH} characters).", 400)
    request = _locked_request(db, request_id)
    if request.status != REQUESTED:
        db.rollback()
        raise ManualPaymentError("ALREADY_DECIDED", f"This request is already {request.status.lower()}.")
    if int(request.requested_by) == int(actor.id):
        raise _refuse(db, actor, member_id, "confirm manual payment", "SAME_ADMINISTRATOR",
                      "The administrator who recorded a payment cannot confirm it: a second administrator has to.", ip)
    if admin_security.earns_from_payment_by(db, actor.id, member_id):
        raise _refuse(db, actor, member_id, "confirm manual payment", "COMMISSION_CONFLICT",
                      "You cannot confirm a payment for a member in your own referral line.", ip)
    member = db.query(User).filter(User.id == member_id).with_for_update().one()
    if not member.is_active or getattr(member, "is_deleted", False):
        db.rollback()
        raise ManualPaymentError("TARGET_NOT_ELIGIBLE", "A payment cannot be recorded for an inactive account.")
    deposit = db.query(Deposit).filter(Deposit.id == request.deposit_id).with_for_update().populate_existing().one()
    if is_reversed_deposit(deposit):
        db.rollback()
        raise ManualPaymentError("DEPOSIT_REVERSED", "This deposit was reversed; it cannot be confirmed.")
    if deposit.status == DepositStatus.VALIDATED:
        # The provider confirmed it meanwhile: nothing more to credit.
        request.status, request.decided_by, request.decided_at = CANCELLED, actor.id, now
        request.decision_note = "Superseded: the payment provider validated this deposit."
        request.version = int(request.version or 0) + 1
        admin_security.audit(db, actor_id=actor.id, record_id=member_id, action=AUDIT_SUPERSEDED, ip=ip,
                             new={"request_id": request.id, "deposit_id": deposit.id})
        db.commit()
        return Outcome("superseded", request, deposit)

    product = db.query(ProductType).filter(ProductType.id == deposit.product_type_id).one()
    validity_days = int(getattr(product, "validity_days", 0) or 0)
    deposit.amount = money(request.amount)
    deposit.currency = (request.currency or "USD").upper()
    deposit.status = DepositStatus.VALIDATED
    deposit.validated_at = now
    deposit.validated_by = actor.id
    deposit.expires_at = now + timedelta(days=validity_days) if validity_days > 0 else None
    deposit.admin_notes = (f"{deposit.admin_notes or ''}\nConfirmed by admin #{actor.id} "
                           f"(recorded by #{request.requested_by}); evidence: {evidence}").strip()[:1000]
    db.flush()
    if not process_payment_validation(db, deposit, defer_commit=True):
        db.rollback()
        raise ManualPaymentError("VALIDATION_FAILED", "The payment could not be processed; nothing was recorded.", 500)
    db.flush()
    conflicted = db.query(AffiliateCommission.id).filter(
        AffiliateCommission.user_id.in_((int(actor.id), int(request.requested_by))),
        or_(AffiliateCommission.deposit_id == deposit.id,
            (AffiliateCommission.source_type == "DEPOSIT") & (AffiliateCommission.source_id == deposit.id)),
    ).first()
    if conflicted:
        raise _refuse(db, actor, member_id, "confirm manual payment", "COMMISSION_CONFLICT",
                      "This payment would pay a commission to an administrator who recorded or confirmed it.", ip)
    # KYC is decided by the provider only: an older request that asked for the identity
    # to be marked verified confirms the payment and leaves the identity as it is.
    identity_verified = False
    request.status, request.decided_by, request.decided_at = CONFIRMED, actor.id, now
    request.evidence_reference = evidence[:255]
    request.decision_note = note[:2000] or None
    request.version = int(request.version or 0) + 1
    admin_security.audit(db, actor_id=actor.id, record_id=member_id, action=AUDIT_CONFIRMED, ip=ip,
                         old={"deposit_id": deposit.id, "status": "pending"},
                         new={"deposit_id": deposit.id, "product_code": request.product_code,
                              "amount": str(money(request.amount)), "request_id": request.id,
                              "requested_by": request.requested_by, "confirmed_by": actor.id,
                              "evidence_reference": evidence[:255], "reason": request.request_reason[:300]})
    db.commit()
    db.refresh(request)
    db.refresh(deposit)
    return Outcome("granted", request, deposit, identity_verified)


# ---------------------------------------------------------------------------
# 3. Reject (checker) / cancel (maker)
# ---------------------------------------------------------------------------

def reject(db: Session, actor, request_id: int, *, password: Optional[str], reason: str,
           ip: Optional[str] = None, now: Optional[datetime] = None) -> Outcome:
    now = now or datetime.utcnow()
    probe = db.query(ManualPaymentConfirmation).filter(ManualPaymentConfirmation.id == request_id).first()
    if probe is None:
        raise ManualPaymentError("NOT_FOUND", "Manual payment request not found.", 404)
    _authorize(db, actor, int(probe.member_id), password, "reject manual payment", ip)
    reason = _clean(reason)
    if len(reason) < REASON_MIN_LENGTH:
        raise ManualPaymentError("REASON_REQUIRED", f"Say why (at least {REASON_MIN_LENGTH} characters).", 400)
    request = _locked_request(db, request_id)
    if request.status != REQUESTED:
        db.rollback()
        raise ManualPaymentError("ALREADY_DECIDED", f"This request is already {request.status.lower()}.")
    if int(request.requested_by) == int(actor.id):
        db.rollback()
        raise ManualPaymentError("SAME_ADMINISTRATOR", "Withdraw your own request with Cancel.", 403)
    _close_deposit(db, request, f"Manual payment rejected by admin #{actor.id}: {reason}")
    request.status, request.decided_by, request.decided_at = REJECTED, actor.id, now
    request.decision_note = reason[:2000]
    request.version = int(request.version or 0) + 1
    admin_security.audit(db, actor_id=actor.id, record_id=request.member_id, action=AUDIT_REJECTED, ip=ip,
                         new={"request_id": request.id, "deposit_id": request.deposit_id, "reason": reason[:300]})
    db.commit()
    db.refresh(request)
    return Outcome("rejected", request, None)


def cancel(db: Session, actor, request_id: int, *, password: Optional[str], reason: str,
           ip: Optional[str] = None, now: Optional[datetime] = None) -> Outcome:
    """The administrator who recorded the request withdraws it (nothing was credited)."""
    from app.services import reauth

    now = now or datetime.utcnow()
    request = _locked_request(db, request_id)
    if int(request.requested_by) != int(getattr(actor, "id", 0) or 0):
        db.rollback()
        raise ManualPaymentError("NOT_REQUESTER", "Only the administrator who recorded the payment can cancel it.", 403)
    db.rollback()
    try:
        reauth.verify(db, actor, password, ip=ip)
    except reauth.ReauthError as exc:
        raise ManualPaymentError(exc.code, str(exc), 429 if exc.code == reauth.LOCKED else 403) from None
    reason = _clean(reason)
    if len(reason) < REASON_MIN_LENGTH:
        raise ManualPaymentError("REASON_REQUIRED", f"Say why (at least {REASON_MIN_LENGTH} characters).", 400)
    request = _locked_request(db, request_id)
    if request.status != REQUESTED:
        db.rollback()
        raise ManualPaymentError("ALREADY_DECIDED", f"This request is already {request.status.lower()}.")
    _close_deposit(db, request, f"Manual payment cancelled by admin #{actor.id}: {reason}")
    request.status, request.decided_at = CANCELLED, now
    request.decision_note = reason[:2000]
    request.version = int(request.version or 0) + 1
    admin_security.audit(db, actor_id=actor.id, record_id=request.member_id, action=AUDIT_CANCELLED, ip=ip,
                         new={"request_id": request.id, "deposit_id": request.deposit_id, "reason": reason[:300]})
    db.commit()
    db.refresh(request)
    return Outcome("cancelled", request, None)


def view(row: ManualPaymentConfirmation) -> dict:
    return {
        "id": row.id, "deposit_id": row.deposit_id, "member_id": row.member_id, "product_code": row.product_code,
        "amount": f"{money(row.amount):.2f}", "currency": row.currency, "status": row.status,
        "created_new_deposit": row.created_new_deposit, "verify_identity_requested": row.verify_identity_requested,
        "requested_by": row.requested_by, "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "request_reason": row.request_reason, "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "evidence_reference": row.evidence_reference, "decision_note": row.decision_note, "version": row.version,
    }


def list_requests(db: Session, *, status: Optional[str] = None, limit: int = 100) -> list[dict]:
    query = db.query(ManualPaymentConfirmation, User).join(User, User.id == ManualPaymentConfirmation.member_id)
    if status:
        query = query.filter(ManualPaymentConfirmation.status == status.upper())
    rows = query.order_by(ManualPaymentConfirmation.id.desc()).limit(min(max(limit, 1), 200)).all()
    out = []
    for row, member in rows:
        item = view(row)
        item["member"] = {"id": member.id, "username": member.username, "full_name": member.full_name,
                          "email": member.email}
        out.append(item)
    return out
