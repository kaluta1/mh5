"""NEW_V2 website revenue and DIRECT affiliate commission.

Only the payer's direct sponsor (users.sponsor_id) can earn: there is no hierarchy walk.
commission_base   = gross - seller_base                         (COMMISSION_BASE_DEFINITION)
direct_commission = commission_base * policy.commission_rate
website_revenue   = gross - seller_base - provider_cost          (booked revenue / Leaders base)

Client-confirmed (2026-09-25): a provider cost (e.g. the KYC verifier) is a separate
pass-through/expense and never reduces the affiliate commission base; a seller's
principal (marketplace) is never MyHigh5 revenue and is never commissionable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.business_model import RevenuePolicy, RevenueRecognition
from app.models.user import User
from app.services.financial_integrity import FinancialIntegrityError, money
from app.services.new_model_ledger import Line, PostingType, SourceType, idempotency_key, post_entry, reverse_entry
from app.services.new_model_reference_data import NEW_MODEL_VERSION

_COMMISSION_TYPE_BY_CATEGORY = {
    "KYC_VERIFICATION": CommissionType.KYC_PAYMENT,
    "MEMBERSHIP": CommissionType.EFM_MEMBERSHIP,
    "PLATFORM_SUBSCRIPTION": CommissionType.CLUB_MEMBERSHIP,
    "SERVICE_FEE": CommissionType.CONTEST_PARTICIPATION,
    "MARKETPLACE_MARKUP": CommissionType.SHOP_PURCHASE,
    "REFERRAL_POOL_ENTRY": CommissionType.CLUB_MEMBERSHIP,
}


COMMISSION_BASE_DEFINITION = "GROSS_LESS_SELLER_BASE"


class RevenuePolicyMissing(FinancialIntegrityError):
    pass


@dataclass(frozen=True)
class RevenueBreakdown:
    product_code: str
    revenue_category: str
    gross: Decimal
    seller_base: Decimal
    provider_cost: Decimal
    website_revenue: Decimal
    commission_eligible: bool
    commission_rate: Decimal
    leaders_revenue_eligible: bool
    policy: RevenuePolicy

    @property
    def commission_base(self) -> Decimal:
        """Commissionable revenue: the full selling price MyHigh5 earns on (gross minus any
        seller principal). Provider cost is deliberately NOT deducted."""
        return money(self.gross - self.seller_base)

    @property
    def direct_commission(self) -> Decimal:
        if not self.commission_eligible or self.commission_base <= 0:
            return Decimal("0.00")
        return money(self.commission_base * self.commission_rate)


def get_policy(db: Session, product_code: str) -> RevenuePolicy:
    policy = (
        db.query(RevenuePolicy)
        .filter(
            RevenuePolicy.model_version == NEW_MODEL_VERSION,
            RevenuePolicy.product_code == product_code,
            RevenuePolicy.is_active == True,  # noqa: E712
        )
        .first()
    )
    if policy is None:
        raise RevenuePolicyMissing(f"No active NEW_V2 revenue policy for product '{product_code}'")
    return policy


def compute_breakdown(policy: RevenuePolicy, gross, seller_base=Decimal("0")) -> RevenueBreakdown:
    gross_d = money(gross)
    base_d = money(seller_base)
    if base_d < 0 or base_d > gross_d:
        raise FinancialIntegrityError("Seller base must be between 0 and the gross amount")
    after_seller = gross_d - base_d
    provider = money(after_seller * Decimal(str(policy.provider_cost_rate or 0)) + money(policy.provider_cost_fixed or 0))
    provider = min(provider, after_seller)
    return RevenueBreakdown(
        product_code=policy.product_code,
        revenue_category=policy.revenue_category,
        gross=gross_d,
        seller_base=base_d,
        provider_cost=provider,
        website_revenue=money(after_seller - provider),
        commission_eligible=bool(policy.commission_eligible),
        commission_rate=Decimal(str(policy.commission_rate or 0)),
        leaders_revenue_eligible=bool(policy.leaders_revenue_eligible),
        policy=policy,
    )


def record_recognition(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    user_id: Optional[int],
    breakdown: RevenueBreakdown,
    journal_entry_id: Optional[int],
    recognized_at: Optional[datetime] = None,
) -> RevenueRecognition:
    key = idempotency_key(source_type, source_id, "REVENUE")
    existing = db.query(RevenueRecognition).filter(RevenueRecognition.idempotency_key == key).first()
    if existing:
        return existing
    row = RevenueRecognition(
        model_version=NEW_MODEL_VERSION,
        source_type=source_type,
        source_id=int(source_id),
        idempotency_key=key,
        user_id=user_id,
        product_code=breakdown.product_code,
        revenue_category=breakdown.revenue_category,
        gross_amount=breakdown.gross,
        seller_base_amount=breakdown.seller_base,
        provider_cost_amount=breakdown.provider_cost,
        website_revenue_amount=breakdown.website_revenue,
        commission_eligible=breakdown.commission_eligible,
        leaders_revenue_eligible=breakdown.leaders_revenue_eligible,
        recognized_at=recognized_at or datetime.utcnow(),
        journal_entry_id=journal_entry_id,
    )
    db.add(row)
    db.flush()
    return row


def reverse_recognition(db: Session, original: RevenueRecognition, *, journal_entry_id: Optional[int]) -> RevenueRecognition:
    key = f"{original.idempotency_key}:REVERSAL"
    existing = db.query(RevenueRecognition).filter(RevenueRecognition.idempotency_key == key).first()
    if existing:
        return existing
    row = RevenueRecognition(
        model_version=original.model_version,
        source_type=original.source_type,
        source_id=original.source_id,
        idempotency_key=key,
        user_id=original.user_id,
        product_code=original.product_code,
        revenue_category=original.revenue_category,
        gross_amount=-money(original.gross_amount),
        seller_base_amount=-money(original.seller_base_amount),
        provider_cost_amount=-money(original.provider_cost_amount),
        website_revenue_amount=-money(original.website_revenue_amount),
        commission_eligible=original.commission_eligible,
        leaders_revenue_eligible=original.leaders_revenue_eligible,
        recognized_at=datetime.utcnow(),
        journal_entry_id=journal_entry_id,
        reverses_id=original.id,
    )
    db.add(row)
    db.flush()
    return row


def accrue_direct_commission(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    payer_user_id: int,
    breakdown: RevenueBreakdown,
    deposit_id: Optional[int] = None,
    product_type_id: Optional[int] = None,
) -> Optional[AffiliateCommission]:
    """Create the single level-1 commission for the payer's DIRECT sponsor, once per source."""
    amount = breakdown.direct_commission
    if amount <= 0:
        return None
    payer = db.query(User).filter(User.id == payer_user_id).first()
    if payer is None or not payer.sponsor_id or int(payer.sponsor_id) == int(payer_user_id):
        return None
    sponsor = db.query(User).filter(User.id == payer.sponsor_id).first()
    # Direct-only: an ineligible direct sponsor means no commission (no roll-up to anyone else).
    if sponsor is None or sponsor.is_active is False or sponsor.is_deleted is True:
        return None
    existing = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.source_type == source_type,
            AffiliateCommission.source_id == int(source_id),
            AffiliateCommission.user_id == sponsor.id,
        )
        .first()
    )
    if existing:
        return existing
    commission = AffiliateCommission(
        user_id=sponsor.id,
        source_user_id=payer_user_id,
        product_type_id=product_type_id,
        deposit_id=deposit_id,
        commission_type=_COMMISSION_TYPE_BY_CATEGORY.get(breakdown.revenue_category, CommissionType.KYC_PAYMENT),
        level=1,
        base_amount=breakdown.commission_base,
        commission_rate=breakdown.commission_rate,
        commission_amount=amount,
        status=CommissionStatus.APPROVED if (sponsor.usdt_wallet_address or "").strip() else CommissionStatus.PENDING,
        transaction_date=datetime.utcnow(),
        business_model_version=NEW_MODEL_VERSION,
        revenue_category=breakdown.revenue_category,
        source_type=source_type,
        source_id=int(source_id),
    )
    db.add(commission)
    db.flush()
    post_entry(
        db,
        source_type=SourceType.COMMISSION,
        source_id=commission.id,
        posting_type=PostingType.COMMISSION_ACCRUAL,
        lines=[
            Line("5001", debit=amount, description="Direct affiliate commission expense"),
            Line("2001", credit=amount, description=f"Direct affiliate commission payable - User #{sponsor.id}"),
        ],
        description=f"Direct affiliate commission #{commission.id} ({source_type} {source_id})",
    )
    return commission


def reverse_direct_commissions(db: Session, *, source_type: str, source_id: int, reason: str) -> list[AffiliateCommission]:
    """Cancel/claw back exactly the commissions of this source (structured match only)."""
    from app.models.accounting import JournalEntry

    rows = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.business_model_version == NEW_MODEL_VERSION,
            AffiliateCommission.source_type == source_type,
            AffiliateCommission.source_id == int(source_id),
        )
        .with_for_update()
        .all()
    )
    for commission in rows:
        if commission.status == CommissionStatus.CANCELLED:
            continue
        if commission.status == CommissionStatus.APPROVED and str(commission.payout_reference or "").startswith("intent:"):
            raise FinancialIntegrityError("Refund cannot race an unresolved payout intent; reconcile the payout first")
        accrual = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.source_type == SourceType.COMMISSION,
                JournalEntry.source_id == commission.id,
                JournalEntry.posting_type == PostingType.COMMISSION_ACCRUAL,
            )
            .first()
        )
        if commission.status == CommissionStatus.PAID:
            # Already paid out: the expense stays reversed against a receivable from the member.
            post_entry(
                db,
                source_type=SourceType.COMMISSION,
                source_id=commission.id,
                posting_type=PostingType.REVERSAL,
                key_suffix="clawback",
                lines=[
                    Line("1200", debit=money(commission.commission_amount), description="Receivable - paid commission clawback"),
                    Line("5001", credit=money(commission.commission_amount), description="Reverse direct commission expense"),
                ],
                description=f"Clawback of paid direct commission #{commission.id}: {reason}",
                reverses_entry_id=accrual.id if accrual else None,
            )
        elif accrual is not None:
            reverse_entry(db, accrual, reason=reason)
        commission.status = CommissionStatus.CANCELLED
    db.flush()
    return rows
