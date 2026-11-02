"""Annual Ads direct-sponsor commission and refund handling (Prompt 6, owner policy 2026-11-03).

Policy (approved; affiliate_rate_policy is the one place for the rates):
  * the BUYER's direct sponsor earns 20% of the GROSS Annual Ads purchase amount, or 40% once permanently
    qualified (10,000 KYC-verified direct referrals within six months of the sponsor's registration);
  * gross = the amount the signed Annual Ads payment reports (never the 70% net, never after fees);
  * direct sponsor only: no level 2-10, no roll-up; no valid direct sponsor -> no commission;
  * Prompt 2: a sponsor whose KYC is not APPROVED at this event gets no payable commission, only a
    missed-earning record; the amount stays MyHigh5 revenue (existing 4030 reclassification).

When: only on a signed `sponsor_payment_confirmed` event whose buyer is identified through the signed SSO
subject MyHigh5 issued (buyer_match MATCHED). An unidentified buyer earns nobody anything (no sponsor can be
proven). The decision is taken once per payment (idempotent; existing commission engine).

Refunds/cancellations (signed event for a recorded payment): the commission is reversed through the existing
engine when it is still unpaid and not in a payout; a paid or in-flight commission is NOT clawed back
automatically (no approved recovery policy): the payment goes to FINANCE_REVIEW. A partial refund also goes
to FINANCE_REVIEW. The cash side (Dr 1030 / Cr 2310 at the net amount) is never reversed automatically: how
Annual Ads returns or offsets the money is not specified by the provider contract, so it is a finance-review
item too. Nothing here commits.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvAnnualAdsPayment
from app.services.financial_integrity import money

SOURCE_TYPE = "ANNUAL_ADS_PAYMENT"
REVENUE_CATEGORY = "AD_SLOT_PURCHASE"
REVENUE_ACCOUNT = "4010"

# sponsor_commission_status values
RECORDED, MISSED_KYC, NO_SPONSOR, BUYER_NOT_IDENTIFIED, REVERSED, FINANCE_REVIEW = (
    "RECORDED", "MISSED_KYC", "NO_SPONSOR", "BUYER_UNIDENTIFIED", "REVERSED", "FINANCE_REVIEW")
# refund_status values
REFUND_REVERSED, REFUND_REVIEW = "REVERSED", "FINANCE_REVIEW"


def _breakdown(gross: Decimal, rate: Decimal):
    """The existing commission engine's input: base = full gross, rate = the sponsor's direct rate."""
    from app.models.business_model import RevenuePolicy
    from app.services.new_model_revenue import RevenueBreakdown

    policy = RevenuePolicy(model_version="NEW_V2", product_code="annual_ads", revenue_category=REVENUE_CATEGORY,
                           revenue_account_code=REVENUE_ACCOUNT, commission_eligible=True, commission_rate=rate)
    return RevenueBreakdown(product_code="annual_ads", revenue_category=REVENUE_CATEGORY, gross=money(gross),
                            seller_base=Decimal("0.00"), provider_cost=Decimal("0.00"), website_revenue=money(gross),
                            commission_eligible=True, commission_rate=rate, leaders_revenue_eligible=False,
                            policy=policy)


def decide_commission(db: Session, row: AdvAnnualAdsPayment, *, now: Optional[datetime] = None) -> str:
    """Decide the direct-sponsor commission of one recorded Annual Ads payment, once. Returns the status."""
    from app.models.missed_earning import CATEGORY_REFERRAL
    from app.services import affiliate_rate_policy as rates, missed_earnings
    from app.services.ad_revenue_policy import valid_direct_sponsor
    from app.services.new_model_revenue import accrue_direct_commission

    if row.sponsor_decided_at is not None:
        return row.sponsor_commission_status
    now = now or datetime.utcnow()
    row.sponsor_decided_at = now
    if row.buyer_match != "MATCHED" or not row.buyer_user_id:
        row.sponsor_commission_status = BUYER_NOT_IDENTIFIED
        return row.sponsor_commission_status
    sponsor = valid_direct_sponsor(db, row.buyer_user_id)
    if sponsor is None or money(row.gross_amount) <= 0:
        row.sponsor_commission_status = NO_SPONSOR
        return row.sponsor_commission_status
    status = rates.evaluate(db, sponsor)
    rate = status.rate
    row.sponsor_user_id, row.sponsor_rate, row.sponsor_rule_version = sponsor.id, rate, rates.RULE_VERSION
    row.sponsor_evidence = {"base": "GROSS", "gross": str(money(row.gross_amount)), "rate": str(rate),
                            "qualified": bool(status.permanently_qualified),
                            "qualified_at": status.qualified_at.isoformat() if status.qualified_at else None,
                            "qualifying_direct_kyc_referrals": int(status.qualifying_referral_count),
                            "required": int(status.required_referral_count),
                            "rule": rates.RULE_VERSION, "buyer_user_id": row.buyer_user_id}
    commission = accrue_direct_commission(db, source_type=SOURCE_TYPE, source_id=row.id,
                                          payer_user_id=row.buyer_user_id, breakdown=_breakdown(row.gross_amount, rate))
    if commission is not None:
        row.sponsor_commission_status = RECORDED
        row.sponsor_commission_id, row.sponsor_commission_amount = commission.id, money(commission.commission_amount)
        return RECORDED
    missed = missed_earnings.find(db, user_id=sponsor.id, category=CATEGORY_REFERRAL, source_type=SOURCE_TYPE,
                                  source_id=row.id)
    row.sponsor_commission_status = MISSED_KYC if missed is not None else NO_SPONSOR
    if missed is not None:
        row.sponsor_commission_amount = money(missed.amount)
    return row.sponsor_commission_status


def handle_refund(db: Session, row: AdvAnnualAdsPayment, *, event: str, amount, payload_sha256: str,
                  now: Optional[datetime] = None) -> str:
    """A signed refund/cancellation event for this recorded payment. Idempotent. Returns the refund status."""
    from app.models.affiliate import AffiliateCommission, CommissionStatus
    from app.services.financial_integrity import FinancialIntegrityError
    from app.services.new_model_revenue import reverse_direct_commissions

    if row.refund_status is not None:
        return row.refund_status
    now = now or datetime.utcnow()
    refunded = money(amount) if amount is not None else None
    row.refund_event, row.refund_amount, row.refunded_at = event[:100], refunded, now
    row.refund_payload_sha256 = payload_sha256
    if refunded is None or refunded != money(row.gross_amount):
        row.refund_status = REFUND_REVIEW                       # partial or unknown amount: finance decides
        if row.sponsor_commission_status == RECORDED:
            row.sponsor_commission_status = FINANCE_REVIEW
        return row.refund_status
    commission = db.get(AffiliateCommission, row.sponsor_commission_id) if row.sponsor_commission_id else None
    in_payout = commission is not None and (commission.status == CommissionStatus.PAID
                                            or commission.payout_reference is not None)
    if in_payout:
        # Already paid (or being paid): no automatic clawback without an approved recovery policy.
        row.refund_status, row.sponsor_commission_status = REFUND_REVIEW, FINANCE_REVIEW
        return row.refund_status
    try:
        with db.begin_nested():
            reverse_direct_commissions(db, source_type=SOURCE_TYPE, source_id=row.id,
                                       reason=f"Annual Ads refund {row.tx_hash[:40]}")
    except FinancialIntegrityError:
        row.refund_status, row.sponsor_commission_status = REFUND_REVIEW, FINANCE_REVIEW
        return row.refund_status
    row.refund_status = REFUND_REVERSED
    if row.sponsor_commission_status in (RECORDED, MISSED_KYC):
        row.sponsor_commission_status = REVERSED
    return row.refund_status


def reconciliation(db: Session) -> dict:
    """Read-only: every payment's commission decision against the commission rows and missed records."""
    from app.models.affiliate import AffiliateCommission, CommissionStatus
    from app.models.advertising_v2 import AdvAnnualAdsEvent
    from app.services import affiliate_rate_policy as rates

    issues, totals = [], {"payments": 0, "gross": Decimal("0.00"), "commission": Decimal("0.00")}
    for row in db.query(AdvAnnualAdsPayment).order_by(AdvAnnualAdsPayment.id.asc()):
        totals["payments"] += 1
        totals["gross"] += money(row.gross_amount)
        rows = db.query(AffiliateCommission).filter(AffiliateCommission.source_type == SOURCE_TYPE,
                                                    AffiliateCommission.source_id == row.id).all()
        live = [c for c in rows if c.status != CommissionStatus.CANCELLED]
        totals["commission"] += sum((money(c.commission_amount) for c in live), Decimal("0.00"))
        if len(live) > 1 or any(c.level != 1 for c in rows):
            issues.append({"type": "DUPLICATE_OR_INDIRECT_COMMISSION", "payment_id": row.id,
                           "expected": "at most one level-1 commission", "actual": len(live), "auto_fix_safe": False,
                           "owner_approval": True})
        for c in live:
            expected = money(money(row.gross_amount) * Decimal(str(c.commission_rate or 0)))
            if c.commission_rate not in (rates.STANDARD_DIRECT_RATE, rates.QUALIFIED_DIRECT_RATE) or \
                    money(c.commission_amount) != expected or money(c.base_amount) != money(row.gross_amount):
                issues.append({"type": "RATE_OR_BASE_MISMATCH", "payment_id": row.id, "commission_id": c.id,
                               "expected": f"{expected} on gross {money(row.gross_amount)}",
                               "actual": f"{money(c.commission_amount)} at {c.commission_rate} on {money(c.base_amount)}",
                               "auto_fix_safe": False, "owner_approval": True})
        if row.sponsor_commission_status == RECORDED and not live:
            issues.append({"type": "RECORDED_WITHOUT_COMMISSION", "payment_id": row.id, "expected": "1 commission",
                           "actual": 0, "auto_fix_safe": False, "owner_approval": True})
        if row.refund_status == REFUND_REVIEW:
            issues.append({"type": "REFUND_FINANCE_REVIEW", "payment_id": row.id, "expected": "finance decision",
                           "actual": row.sponsor_commission_status, "auto_fix_safe": False, "owner_approval": True})
        if row.sponsor_decided_at is None and row.event == "sponsor_payment_confirmed":
            issues.append({"type": "COMMISSION_NOT_DECIDED", "payment_id": row.id,
                           "expected": "a decision (pre-Prompt 6 payment)", "actual": row.sponsor_commission_status,
                           "auto_fix_safe": False, "owner_approval": True,
                           "suggestion": "No retroactive commission without owner approval"})
    by_status = {}
    for (s,) in db.query(AdvAnnualAdsPayment.sponsor_commission_status):
        by_status[s] = by_status.get(s, 0) + 1
    events = {}
    for (o,) in db.query(AdvAnnualAdsEvent.outcome):
        events[o] = events.get(o, 0) + 1
    return {"read_only": True, "payments": totals["payments"], "gross": str(totals["gross"]),
            "sponsor_commission_total": str(totals["commission"]), "by_commission_status": by_status,
            "events_by_outcome": events, "issues": issues, "ok": not issues}
