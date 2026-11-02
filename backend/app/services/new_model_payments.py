"""NEW_V2 accounting for validated deposits (platform-sold products).

The Referral Pool is retired (2026-09-28). Historical pool postings are kept and still
reverse exactly on a provider refund. A pool invoice created before retirement but confirmed
after it gets no seat, no revenue and no commission: the real cash is held in 2100 for a
manual business decision (never auto-refunded or redistributed).

Every journal is linked by (source_type=DEPOSIT, source_id=deposit.id, posting_type) and a
unique idempotency key. Revenue is recognized gross of affiliate commission; the direct
commission is a separate expense (Dr 5001 / Cr 2001).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.business_model import RevenueRecognition
from app.models.payment import Deposit, ProductType
from app.services.financial_integrity import money
from app.services.new_model_ledger import (
    Line,
    PostingType,
    SourceType,
    entries_for_source,
    find_entry,
    idempotency_key,
    is_reversed,
    post_entry,
    reverse_entry,
)
from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE
from app.services.new_model_revenue import (
    RevenuePolicyMissing,
    accrue_direct_commission,
    compute_breakdown,
    recognize_deferred_commission_cost,
    get_policy,
    record_recognition,
    reverse_direct_commissions,
    reverse_recognition,
)

logger = logging.getLogger(__name__)

KYC_REVENUE_CATEGORY = "KYC_VERIFICATION"


INTERNAL_WALLET_PROVIDER = "internal_wallet"
WALLET_CLEARING_ACCOUNT = "1050"


def funding_account(deposit: Deposit) -> str:
    """Where a purchase's money comes from: cash (1001), or, for a purchase paid with commission earnings
    (Prompt 5), the internal wallet clearing account. The commission liability was settled into that
    account just before, so the clearing nets to zero and no cash is ever recorded."""
    return WALLET_CLEARING_ACCOUNT if (deposit.payment_provider or "") == INTERNAL_WALLET_PROVIDER else "1001"


def _received(deposit: Deposit) -> str:
    return "Paid with commission earnings" if funding_account(deposit) != "1001" else "Cash received"


def _product(db: Session, deposit: Deposit) -> ProductType:
    return db.query(ProductType).filter(ProductType.id == deposit.product_type_id).one()


def _recognize(db: Session, deposit: Deposit, *, credit_from: str, recognized_at: Optional[datetime] = None) -> None:
    """Recognize website revenue for the deposit (idempotent) and accrue the direct commission."""
    product = _product(db, deposit)
    breakdown = compute_breakdown(get_policy(db, product.code), deposit.amount)
    policy = breakdown.policy
    lines = [
        Line(credit_from, debit=breakdown.gross,
             description=_received(deposit) if credit_from == funding_account(deposit) else "Release deferred revenue"),
        Line(policy.revenue_account_code, credit=breakdown.website_revenue, description=f"Website revenue - {breakdown.revenue_category}"),
    ]
    if breakdown.provider_cost > 0:
        lines.append(Line(policy.provider_payable_account_code or "2003", credit=breakdown.provider_cost,
                          description="Provider cost payable (pass-through, not website revenue)"))
    entry = post_entry(
        db,
        source_type=SourceType.DEPOSIT,
        source_id=deposit.id,
        posting_type=PostingType.RECOGNITION,
        lines=lines,
        description=f"NEW_V2 revenue recognition - {product.code} - deposit {deposit.id} - user {deposit.user_id}",
        entry_date=recognized_at,
    )
    record_recognition(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, user_id=deposit.user_id,
        breakdown=breakdown, journal_entry_id=entry.id, recognized_at=recognized_at,
    )
    commission = accrue_direct_commission(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, payer_user_id=deposit.user_id,
        breakdown=breakdown, deposit_id=deposit.id, product_type_id=deposit.product_type_id,
    )
    # A KYC commission was already posted when the fee was paid: its cost moves
    # from the deferred cost account to the expense account with this revenue.
    recognize_deferred_commission_cost(db, commission, recognized_at=recognized_at)


def _hold_retired_pool_payment(db: Session, deposit: Deposit) -> None:
    """A Referral Pool payment confirmed after retirement: cash held for review, nothing earned."""
    if entries_for_source(db, SourceType.DEPOSIT, deposit.id):
        return  # already posted (historical recognition or an earlier hold): a retry adds nothing
    from app.services import referral_pool_service as pool

    pool.release_reservation_for_deposit(
        db, deposit.id, f"Referral Pool retired before payment of deposit #{deposit.id} was confirmed; held for review"
    )
    post_entry(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
        lines=[Line(funding_account(deposit), debit=money(deposit.amount), description=_received(deposit)),
               Line("2100", credit=money(deposit.amount),
                    description="Referral Pool retired: payment held for manual review (no seat, revenue or commission)")],
        description=f"NEW_V2 retired Referral Pool payment held for review - deposit {deposit.id}",
    )
    logger.warning("Referral Pool payment confirmed after retirement (deposit %s); cash held in 2100", deposit.id)


def process_new_model_deposit(db: Session, deposit: Deposit) -> None:
    """Post a validated NEW_V2 deposit. Never commits; safe to call repeatedly."""
    product = _product(db, deposit)
    from app.services.ad_campaigns import AD_CREDIT_PRODUCT_CODE

    if product.code == AD_CREDIT_PRODUCT_CODE:
        # Advertiser credit: a liability until validated ad delivery (Dr 1001 / Cr 2320). No revenue,
        # no affiliate commission.
        from app.services.ad_campaigns import on_credit_deposit_validated

        on_credit_deposit_validated(db, deposit)
        return
    if product.code == REFERRAL_POOL_PRODUCT_CODE:
        _hold_retired_pool_payment(db, deposit)
        # Multi-Unit pool (P3): the units of a recorded purchase, while sales are switched on.
        # Cash stays held in 2100; revenue and commission are posted by a later phase.
        from app.services import referral_pool_units

        referral_pool_units.on_pool_deposit_validated(db, deposit)
        return
    try:
        policy = get_policy(db, product.code)
    except RevenuePolicyMissing:
        # Cash is real but no approved revenue rule exists: hold it for review, recognize nothing.
        post_entry(
            db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
            lines=[Line(funding_account(deposit), debit=money(deposit.amount), description=_received(deposit)),
                   Line("2100", credit=money(deposit.amount), description="Unclassified receipt pending revenue policy")],
            description=f"NEW_V2 unclassified receipt - {product.code} - deposit {deposit.id}",
        )
        logger.warning("No NEW_V2 revenue policy for product %s (deposit %s); receipt held in 2100", product.code, deposit.id)
        return

    if policy.deferred_account_code:
        # Service not yet performed (e.g. KYC): cash to deferred revenue; recognized later.
        post_entry(
            db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
            lines=[Line(funding_account(deposit), debit=money(deposit.amount), description=_received(deposit)),
                   Line(policy.deferred_account_code, credit=money(deposit.amount), description="Deferred revenue")],
            description=f"NEW_V2 deferred receipt - {product.code} - deposit {deposit.id} - user {deposit.user_id}",
        )
        if policy.revenue_category == KYC_REVENUE_CATEGORY:
            # Owner rule (2026-10-18): the KYC commission is earned when the fee is
            # confirmed paid, not when the verification is approved. Three separate
            # events: payment (this receipt), commission (now, cost deferred in 1230),
            # revenue recognition (at approval, which also expenses the cost).
            accrue_direct_commission(
                db, source_type=SourceType.DEPOSIT, source_id=deposit.id, payer_user_id=deposit.user_id,
                breakdown=compute_breakdown(policy, deposit.amount), deposit_id=deposit.id,
                product_type_id=deposit.product_type_id, deferred_cost=True,
            )
        return
    _recognize(db, deposit, credit_from=funding_account(deposit))


def recognize_deferred_deposit(db: Session, deposit: Deposit, recognized_at: Optional[datetime] = None) -> bool:
    """Service performed (e.g. KYC approved): release deferred revenue. Returns True if posted now."""
    if find_entry(db, idempotency_key(SourceType.DEPOSIT, deposit.id, PostingType.RECOGNITION)) is not None:
        return False
    policy = get_policy(db, _product(db, deposit).code)
    if not policy.deferred_account_code:
        return False
    if find_entry(db, idempotency_key(SourceType.DEPOSIT, deposit.id, PostingType.RECEIPT)) is None:
        process_new_model_deposit(db, deposit)
    _recognize(db, deposit, credit_from=policy.deferred_account_code, recognized_at=recognized_at)
    return True


def reverse_new_model_deposit(db: Session, deposit: Deposit, *, reason: str) -> None:
    """Full refund of a NEW_V2 deposit: exact structured reversal of its own postings only."""
    from app.services import referral_pool_units

    referral_pool_units.refuse_full_reversal_after_unit_refunds(db, deposit)  # before anything is written
    reverse_direct_commissions(db, source_type=SourceType.DEPOSIT, source_id=deposit.id, reason=reason)
    reversal_entry_id = None
    for entry in entries_for_source(db, SourceType.DEPOSIT, deposit.id):
        if entry.reverses_entry_id is not None or is_reversed(db, entry):
            continue
        rev = reverse_entry(db, entry, reason=reason)
        if entry.posting_type == PostingType.RECOGNITION:
            reversal_entry_id = rev.id
    recognition = (
        db.query(RevenueRecognition)
        .filter(
            RevenueRecognition.source_type == SourceType.DEPOSIT,
            RevenueRecognition.source_id == deposit.id,
            RevenueRecognition.reverses_id.is_(None),
        )
        .first()
    )
    if recognition is not None:
        reverse_recognition(db, recognition, journal_entry_id=reversal_entry_id)
    from app.services import referral_pool_service as pool
    from app.services.ad_campaigns import AD_CREDIT_PRODUCT_CODE, on_credit_deposit_reversed

    if _product(db, deposit).code == AD_CREDIT_PRODUCT_CODE:
        on_credit_deposit_reversed(db, deposit, reason)
    pool.mark_refunded(db, deposit.id)
    referral_pool_units.on_deposit_refunded(db, deposit)
    db.flush()
