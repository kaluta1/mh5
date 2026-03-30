"""
Backward-compatible accounting integration wrappers.

The production posting logic now lives in `accounting_posting.py`.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit
from app.services.accounting_posting import accounting_posting_service


def record_payment_in_accounting(
    db: Session,
    deposit: Deposit,
    commissions: List[AffiliateCommission],
    created_by: Optional[int] = None
) -> Optional[JournalEntry]:
    try:
        return accounting_posting_service.post_validated_deposit(
            db,
            deposit,
            commissions,
            created_by=created_by,
        )
    except Exception:
        return None


def record_commission_payment_in_accounting(
    db: Session,
    commission: AffiliateCommission,
    created_by: Optional[int] = None
) -> Optional[JournalEntry]:
    try:
        return accounting_posting_service.post_affiliate_commission_settlement(
            db,
            commission,
            created_by=created_by,
        )
    except Exception:
        return None
