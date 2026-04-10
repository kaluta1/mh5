"""
Backfill journal entries for validated deposits that never posted (e.g. CoA missing earlier).

Does not create duplicate affiliate commissions: reuses existing AffiliateCommission rows
for the deposit and only runs payment_accounting.*.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.kyc import KYCVerification, KYCStatus
from app.accounting.distribution_formulas import club_markup_split, kyc_verification_recognition_split
from app.services.accounting_service import accounting_service
from app.services.payment_accounting import (
    payment_accounting,
    kyc_deferred_receipt_posted,
    kyc_recognition_posted,
)

logger = logging.getLogger(__name__)

# Products that have payment_accounting handlers (commission_distribution.py)
_ACCOUNTED_PRODUCT_CODES = frozenset(
    {
        "kyc",
        "annual_membership",
        "mfm_membership",
        "efm_membership",
        "founding_membership",  # legacy product code in initial_data; same ledger as MFM
        "club_membership",
    }
)


def _journal_exists_for_deposit(db: Session, deposit_id: int) -> bool:
    """Match descriptions built in payment_accounting (always contain 'Deposit #{id} -')."""
    needle = f"Deposit #{deposit_id} -"
    return (
        db.query(JournalEntry.id)
        .filter(JournalEntry.description.like(f"%{needle}%"))
        .first()
        is not None
    )


def _founding_pool_accrual_exists(db: Session, deposit_id: int) -> bool:
    """True if a 2104 credit line exists on any journal whose description references this deposit."""
    needle = f"Deposit #{deposit_id}"
    return (
        db.query(JournalLine.id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(ChartOfAccounts, JournalLine.account_id == ChartOfAccounts.id)
        .filter(ChartOfAccounts.account_code == "2104")
        .filter(JournalEntry.description.like(f"%{needle}%"))
        .filter(JournalLine.credit_amount > 0)
        .first()
        is not None
    )


def _entry_date_for_deposit(deposit: Deposit) -> datetime:
    return deposit.validated_at or deposit.created_at or datetime.utcnow()


def backfill_missing_payment_journals(
    db: Session,
    *,
    dry_run: bool = False,
    deposit_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Create missing journal entries for validated deposits.

    - Skips deposits that already have any journal line referencing the deposit id in description.
    - Uses existing commissions for that deposit when present (no new AffiliateCommission rows).
    - Journal entry dates use deposit.validated_at (via payment_accounting entry_date=None).

    Returns counts and lists of processed / skipped / error deposit ids.
    """
    q = (
        db.query(Deposit)
        .join(ProductType, Deposit.product_type_id == ProductType.id)
        .filter(Deposit.status == DepositStatus.VALIDATED)
        .filter(ProductType.code.in_(_ACCOUNTED_PRODUCT_CODES))
        .order_by(Deposit.id.asc())
    )
    if deposit_ids is not None:
        q = q.filter(Deposit.id.in_(deposit_ids))

    deposits = q.all()

    processed: List[int] = []
    skipped_has_journal: List[int] = []
    errors: List[Dict[str, Any]] = []

    for deposit in deposits:
        # Clear failed transaction from previous iteration (e.g. INSERT error on enum column)
        db.rollback()

        if _journal_exists_for_deposit(db, deposit.id):
            skipped_has_journal.append(deposit.id)
            continue

        product_code = deposit.product_type.code
        commissions = (
            db.query(AffiliateCommission)
            .filter(AffiliateCommission.deposit_id == deposit.id)
            .all()
        )

        if dry_run:
            processed.append(deposit.id)
            continue

        did = deposit.id
        entry_date: Optional[datetime] = None  # use validated_at inside payment_accounting

        try:
            if product_code == "kyc":
                if not kyc_deferred_receipt_posted(db, did):
                    payment_accounting.process_kyc_cash_receipt_accounting(
                        db, deposit, entry_date=entry_date
                    )
                kyc_ok = (
                    db.query(KYCVerification.id)
                    .filter(
                        KYCVerification.user_id == deposit.user_id,
                        KYCVerification.status == KYCStatus.APPROVED,
                    )
                    .first()
                    is not None
                )
                if kyc_ok and not kyc_recognition_posted(db, did):
                    payment_accounting.process_kyc_verification_performed_accounting(
                        db, deposit, commissions, entry_date=entry_date
                    )
            elif product_code == "annual_membership":
                payment_accounting.process_membership_payment_accounting(
                    db, deposit, commissions, entry_date=entry_date
                )
            elif product_code in ("mfm_membership", "efm_membership", "founding_membership"):
                payment_accounting.process_founding_membership_payment_accounting(
                    db, deposit, commissions, entry_date=entry_date
                )
            elif product_code == "club_membership":
                payment_accounting.process_club_membership_payment_accounting(
                    db, deposit, commissions, entry_date=entry_date
                )
            else:
                errors.append({"deposit_id": did, "detail": f"unsupported product {product_code}"})
                continue

            processed.append(did)
            logger.info("Backfilled accounting journals for deposit %s (%s)", did, product_code)
        except Exception as e:
            db.rollback()
            logger.exception("Backfill failed for deposit %s", did)
            errors.append({"deposit_id": did, "detail": str(e)})

    return {
        "dry_run": dry_run,
        "candidates": len(deposits),
        "posted": len(processed),
        "processed_deposit_ids": processed,
        "skipped_already_in_ledger": skipped_has_journal,
        "errors": errors,
    }


def backfill_missing_founding_pool_accruals(
    db: Session,
    *,
    dry_run: bool = False,
    deposit_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Post adjusting Dr revenue / Cr 2104 for deposits that already have payment journals but no
    founding-members 10% accrual (legacy postings). Idempotent: skips when any 2104 credit exists
    for that deposit id in the journal description.

    - KYC: only when verification recognition is already posted; pool = split from policy (10% gross).
    - Annual / founding membership:10% of gross, revenue from 4002.

    Deposits with no journal lines yet should use backfill_missing_payment_journals first.
    """
    q = (
        db.query(Deposit)
        .join(ProductType, Deposit.product_type_id == ProductType.id)
        .filter(Deposit.status == DepositStatus.VALIDATED)
        .filter(ProductType.code.in_(_ACCOUNTED_PRODUCT_CODES))
        .order_by(Deposit.id.asc())
    )
    if deposit_ids is not None:
        q = q.filter(Deposit.id.in_(deposit_ids))

    deposits = q.all()

    processed: List[int] = []
    skipped_has_pool: List[int] = []
    skipped_no_journal: List[int] = []
    skipped_kyc_no_recognition: List[int] = []
    errors: List[Dict[str, Any]] = []

    for deposit in deposits:
        db.rollback()

        dep_id = deposit.id
        product_code = deposit.product_type.code

        if not _journal_exists_for_deposit(db, dep_id):
            skipped_no_journal.append(dep_id)
            continue

        if _founding_pool_accrual_exists(db, dep_id):
            skipped_has_pool.append(dep_id)
            continue

        amount = Decimal(str(deposit.amount))

        if product_code == "kyc":
            if not kyc_recognition_posted(db, dep_id):
                skipped_kyc_no_recognition.append(dep_id)
                continue
            commissions = (
                db.query(AffiliateCommission)
                .filter(AffiliateCommission.deposit_id == dep_id)
                .all()
            )
            total_comm = sum(Decimal(str(c.commission_amount)) for c in commissions)
            split = kyc_verification_recognition_split(amount, total_comm)
            pool_amt = float(split.founding_pool_accrual)
            revenue_code = "4001"
            base_desc = f"KYC Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        elif product_code == "annual_membership":
            pool_amt = float(amount) * 0.10
            revenue_code = "4002"
            base_desc = f"Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        elif product_code in ("mfm_membership", "efm_membership", "founding_membership"):
            pool_amt = float(amount) * 0.10
            revenue_code = "4002"
            base_desc = f"Founding Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        elif product_code == "club_membership":
            base = (amount / Decimal("1.2")).quantize(Decimal("0.01"))
            split = club_markup_split(base)
            pool_amt = float(split.founding_pool)
            revenue_code = "4003"
            base_desc = f"Club Membership Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        else:
            errors.append({"deposit_id": dep_id, "detail": f"unsupported product {product_code}"})
            continue

        if pool_amt <= 0:
            continue

        if dry_run:
            processed.append(dep_id)
            continue

        jdate = _entry_date_for_deposit(deposit)
        try:
            accounting_service.create_journal_entry(
                db,
                description=base_desc + " (Founding pool accrual — backfill)",
                lines=[
                    {
                        "account_code": revenue_code,
                        "debit": pool_amt,
                        "credit": 0.0,
                        "description": "Founding Members 10% commission — revenue adjustment (historical)",
                    },
                    {
                        "account_code": "2104",
                        "debit": 0.0,
                        "credit": pool_amt,
                        "description": "Accrued liability — Founding Members 10% commission pool",
                    },
                ],
                date=jdate,
            )
            processed.append(dep_id)
            logger.info(
                "Backfilled founding pool accrual for deposit %s (%s) amount=%s",
                dep_id,
                product_code,
                pool_amt,
            )
        except Exception as e:
            db.rollback()
            logger.exception("Founding pool accrual backfill failed for deposit %s", dep_id)
            errors.append({"deposit_id": dep_id, "detail": str(e)})

    return {
        "dry_run": dry_run,
        "candidates": len(deposits),
        "posted": len(processed),
        "processed_deposit_ids": processed,
        "skipped_already_has_pool": skipped_has_pool,
        "skipped_no_deposit_journal": skipped_no_journal,
        "skipped_kyc_recognition_not_posted": skipped_kyc_no_recognition,
        "errors": errors,
    }
