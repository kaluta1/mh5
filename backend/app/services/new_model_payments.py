"""NEW_V2 accounting for validated deposits (platform-sold products and the Referral Pool).

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
    get_policy,
    record_recognition,
    reverse_direct_commissions,
    reverse_recognition,
)

logger = logging.getLogger(__name__)


def _product(db: Session, deposit: Deposit) -> ProductType:
    return db.query(ProductType).filter(ProductType.id == deposit.product_type_id).one()


def _recognize(db: Session, deposit: Deposit, *, credit_from: str, recognized_at: Optional[datetime] = None) -> None:
    """Recognize website revenue for the deposit (idempotent) and accrue the direct commission."""
    product = _product(db, deposit)
    breakdown = compute_breakdown(get_policy(db, product.code), deposit.amount)
    policy = breakdown.policy
    lines = [
        Line(credit_from, debit=breakdown.gross, description="Cash received" if credit_from == "1001" else "Release deferred revenue"),
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
    accrue_direct_commission(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, payer_user_id=deposit.user_id,
        breakdown=breakdown, deposit_id=deposit.id, product_type_id=deposit.product_type_id,
    )


def process_new_model_deposit(db: Session, deposit: Deposit) -> None:
    """Post a validated NEW_V2 deposit. Never commits; safe to call repeatedly."""
    product = _product(db, deposit)
    try:
        policy = get_policy(db, product.code)
    except RevenuePolicyMissing:
        # Cash is real but no approved revenue rule exists: hold it for review, recognize nothing.
        post_entry(
            db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
            lines=[Line("1001", debit=money(deposit.amount), description="Cash received"),
                   Line("2100", credit=money(deposit.amount), description="Unclassified receipt pending revenue policy")],
            description=f"NEW_V2 unclassified receipt - {product.code} - deposit {deposit.id}",
        )
        logger.warning("No NEW_V2 revenue policy for product %s (deposit %s); receipt held in 2100", product.code, deposit.id)
        return

    if product.code == REFERRAL_POOL_PRODUCT_CODE:
        from app.services import referral_pool_service as pool

        membership = pool.activate_from_deposit(db, deposit)
        if membership.status != pool.ACTIVE:
            post_entry(
                db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
                lines=[Line("1001", debit=money(deposit.amount), description="Cash received"),
                       Line("2100", credit=money(deposit.amount),
                            description=f"Referral Pool payment held for review ({membership.status})")],
                description=f"NEW_V2 Referral Pool payment held for review - deposit {deposit.id}",
            )
            return

    if policy.deferred_account_code:
        # Service not yet performed (e.g. KYC): cash to deferred revenue; recognized later.
        post_entry(
            db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
            lines=[Line("1001", debit=money(deposit.amount), description="Cash received"),
                   Line(policy.deferred_account_code, credit=money(deposit.amount), description="Deferred revenue")],
            description=f"NEW_V2 deferred receipt - {product.code} - deposit {deposit.id} - user {deposit.user_id}",
        )
        return
    _recognize(db, deposit, credit_from="1001")


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

    pool.mark_refunded(db, deposit.id)
    db.flush()
