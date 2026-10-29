"""Which commissions may enter a payout, and the review that releases a held one.

THE rule, used by every path that selects commissions to pay (cashout
reservation, the crypto engine, the older payout service, release of PENDING
rows) and by the balances shown to members:

  * a NEW_V2 commission (business_model_version = 'NEW_V2') is payable as before;
  * a commission earned from a SoncoPay BANK CARD payment is held until CARD_HOLD_DAYS after that
    payment was confirmed: SoncoPay keeps card funds for that long (the card networks' chargeback
    period, documented `payout_hold.card_rule`), so nothing it funded leaves before then. The hold
    ends by itself; nothing is written when it does (card_hold_clause);
  * a HISTORICAL commission (any other stamp, NULL included: the codebase's
    rule in new_model_ledger.is_new_model; production's are NULL, written by
    the retired 10-level engine) is HELD until an authorised administrator records
    a RELEASE decision for it (commission_payout_reviews). A CANCEL decision
    keeps it held; the reconciliation procedure carries the cancellation out.

The hold changes no commission row: status, amount and history stay exactly
as they are. A decision is final (one per commission), needs the explicit
process_cashouts permission (or a Super Admin) and the administrator's current
password, is never taken on one's own commission, and is audited.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.financial_controls import CommissionPayoutReview
from app.services import payment_config
from app.services.new_model_ledger import is_new_model
from app.services.new_model_reference_data import NEW_MODEL_VERSION

RELEASE, CANCEL = "RELEASE", "CANCEL"
AUDIT_REVIEW = "COMMISSION_PAYOUT_REVIEWED"
REASON_MIN_LENGTH = 10


class CommissionReviewError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _released():
    return exists(select(CommissionPayoutReview.id).where(
        CommissionPayoutReview.commission_id == AffiliateCommission.id,
        CommissionPayoutReview.decision == RELEASE))


def historical_clause():
    """SQL condition: written by the retired engine (anything but NEW_V2, NULL included)."""
    return func.coalesce(AffiliateCommission.business_model_version, "") != NEW_MODEL_VERSION


CARD_HOLD_DAYS = 14          # SoncoPay: card payments are withdrawable 14 days after they are paid
CARD_METHOD_CODE = "card"    # payment_methods.code of a bank card (compared case-insensitively)
SOURCE_POOL_UNIT = "REFERRAL_POOL_UNIT"     # referral_pool_accounting.SOURCE_UNIT


def card_hold_clause(now: Optional[datetime] = None):
    """SQL condition: this commission was earned from a SoncoPay bank card payment confirmed less than
    CARD_HOLD_DAYS ago (or not confirmed at all). Reached through the commission's own deposit, or, for a
    Referral Pool unit's commission, through the unit's purchase."""
    from app.models.business_model import ReferralPoolPurchase, ReferralPoolUnit
    from app.models.payment import Deposit, PaymentMethod

    since = (now or datetime.utcnow()) - timedelta(days=CARD_HOLD_DAYS)
    card_deposit = and_(Deposit.payment_provider == "soncopay",
                        Deposit.payment_method_id.in_(select(PaymentMethod.id).where(
                            func.lower(PaymentMethod.code) == CARD_METHOD_CODE)),
                        or_(Deposit.validated_at.is_(None), Deposit.validated_at > since))
    direct = exists(select(Deposit.id).where(Deposit.id == AffiliateCommission.deposit_id, card_deposit))
    pool = exists(select(ReferralPoolUnit.id)
                  .join(ReferralPoolPurchase, ReferralPoolPurchase.id == ReferralPoolUnit.purchase_id)
                  .join(Deposit, Deposit.id == ReferralPoolPurchase.deposit_id)
                  .where(AffiliateCommission.source_type == SOURCE_POOL_UNIT,
                         ReferralPoolUnit.id == AffiliateCommission.source_id, card_deposit))
    return or_(direct, pool)


def payable_clause():
    """SQL condition: this commission row may enter a payout (status checks are separate)."""
    return and_(or_(not_(historical_clause()), _released()), not_(card_hold_clause()))


def held_clause():
    """SQL condition: this commission row is held for review."""
    return and_(historical_clause(), not_(_released()))


def is_payable(db: Session, commission: AffiliateCommission) -> bool:
    if db.query(AffiliateCommission.id).filter(AffiliateCommission.id == commission.id,
                                               card_hold_clause()).first() is not None:
        return False                                # card payment still in its chargeback period
    if is_new_model(commission.business_model_version):
        return True
    return db.query(CommissionPayoutReview.id).filter(
        CommissionPayoutReview.commission_id == commission.id,
        CommissionPayoutReview.decision == RELEASE).first() is not None


def review(db: Session, actor, commission_id: int, *, decision: str, reason: str, password: Optional[str],
           evidence_reference: Optional[str] = None, ip: Optional[str] = None,
           now: Optional[datetime] = None) -> CommissionPayoutReview:
    """Record THE decision for one held historical commission. Commits."""
    now = now or datetime.utcnow()
    if decision not in (RELEASE, CANCEL):
        raise CommissionReviewError("INVALID_DECISION", "The decision is RELEASE or CANCEL.")
    reason = " ".join((reason or "").split())
    if len(reason) < REASON_MIN_LENGTH:
        raise CommissionReviewError("REASON_REQUIRED",
                                    f"Say why (at least {REASON_MIN_LENGTH} characters).")
    if not payment_config.has_permission(actor, payment_config.PERMISSION_PROCESS):
        raise CommissionReviewError("FORBIDDEN", f"The {payment_config.PERMISSION_PROCESS} permission is required.")
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise CommissionReviewError(exc.code, str(exc)) from None

    row = (db.query(AffiliateCommission).filter(AffiliateCommission.id == commission_id)
           .with_for_update().populate_existing().first())
    if row is None:
        db.rollback()
        raise CommissionReviewError("NOT_FOUND", "Commission not found.")
    if is_new_model(row.business_model_version):
        db.rollback()
        raise CommissionReviewError("NOT_HELD", "Only a historical commission is held for review.")
    if int(row.user_id) == int(getattr(actor, "id", 0) or 0):
        db.rollback()
        raise CommissionReviewError("SELF_ACTION_FORBIDDEN", "Nobody reviews their own commission.")
    if row.status not in (CommissionStatus.PENDING, CommissionStatus.APPROVED) or row.payout_reference:
        db.rollback()
        raise CommissionReviewError("NOT_OPEN", "This commission is not open (paid, cancelled or reserved).")
    if db.query(CommissionPayoutReview.id).filter(CommissionPayoutReview.commission_id == row.id).first():
        db.rollback()
        raise CommissionReviewError("ALREADY_DECIDED", "A decision already exists for this commission.")
    record = CommissionPayoutReview(commission_id=row.id, decision=decision, reason=reason[:2000],
                                    evidence_reference=(evidence_reference or "").strip()[:255] or None,
                                    decided_by=actor.id, decided_at=now)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise CommissionReviewError("ALREADY_DECIDED", "A decision already exists for this commission.") from None
    db.add(AuditTrail(table_name="affiliate_commissions", record_id=row.id, action=AUDIT_REVIEW, user_id=actor.id,
                      ip_address=(ip or None), timestamp=now,
                      old_values={"status": row.status.value, "amount": str(row.commission_amount), "held": True},
                      new_values={"decision": decision, "reason": reason[:300],
                                  "evidence_reference": record.evidence_reference}))
    db.commit()
    db.refresh(record)
    return record


def held_view(db: Session) -> list[dict]:
    """Every held historical commission with its facts (ids and amounts only)."""
    from app.models.payment import Deposit

    rows = (db.query(AffiliateCommission, Deposit, CommissionPayoutReview)
            .outerjoin(Deposit, Deposit.id == AffiliateCommission.deposit_id)
            .outerjoin(CommissionPayoutReview, CommissionPayoutReview.commission_id == AffiliateCommission.id)
            .filter(historical_clause(),
                    AffiliateCommission.status.in_((CommissionStatus.PENDING, CommissionStatus.APPROVED)))
            .order_by(AffiliateCommission.id).all())
    return [{
        "commission_id": c.id, "beneficiary_id": c.user_id, "payer_id": c.source_user_id, "level": c.level,
        "amount": f"{c.commission_amount:.2f}", "status": c.status.value, "deposit_id": c.deposit_id,
        "deposit_recorded_by_admin": bool(d is not None and d.validated_by is not None),
        "transaction_date": c.transaction_date.isoformat() if c.transaction_date else None,
        "decision": r.decision if r else None, "decided_at": r.decided_at.isoformat() if r else None,
        "executed_at": r.executed_at.isoformat() if r and r.executed_at else None,
    } for c, d, r in rows]
