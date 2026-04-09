"""
Backfill journal entries for validated deposits that never posted (e.g. CoA missing earlier).

Does not create duplicate affiliate commissions: reuses existing AffiliateCommission rows
for the deposit and only runs payment_accounting.*.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services.payment_accounting import payment_accounting

logger = logging.getLogger(__name__)

# Products that have payment_accounting handlers (commission_distribution.py)
_ACCOUNTED_PRODUCT_CODES = frozenset(
    {
        "kyc",
        "annual_membership",
        "mfm_membership",
        "efm_membership",
        "founding_membership",  # legacy product code in initial_data; same ledger as MFM
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
                payment_accounting.process_kyc_payment_accounting(
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
