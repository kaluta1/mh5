from typing import List

from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit
from app.services.accounting_posting import accounting_posting_service


class PaymentAccountingService:
    """
    Backward-compatible wrapper around the canonical posting service.
    """

    def process_kyc_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
    ):
        return accounting_posting_service.post_validated_deposit(db, deposit, commissions)

    def process_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
    ):
        return accounting_posting_service.post_validated_deposit(db, deposit, commissions)


payment_accounting = PaymentAccountingService()
