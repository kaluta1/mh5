"""Canonical derived balances for the active affiliate commission wallet."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services.financial_integrity import money


@dataclass(frozen=True)
class CommissionBalance:
    available: Decimal
    pending: Decimal
    paid_lifetime: Decimal
    earned_lifetime: Decimal
    reserved: Decimal


def get_commission_balance(db: Session, user_id: int) -> CommissionBalance:
    row = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (
                            (
                                (AffiliateCommission.status == CommissionStatus.APPROVED)
                                & AffiliateCommission.payout_reference.is_(None)
                            ),
                            AffiliateCommission.commission_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("available"),
            func.coalesce(
                func.sum(
                    case(
                        (AffiliateCommission.status == CommissionStatus.PENDING, AffiliateCommission.commission_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),
            func.coalesce(
                func.sum(
                    case(
                        (AffiliateCommission.status == CommissionStatus.PAID, AffiliateCommission.commission_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("paid_lifetime"),
            func.coalesce(
                func.sum(
                    case(
                        (AffiliateCommission.status != CommissionStatus.CANCELLED, AffiliateCommission.commission_amount),
                        else_=0,
                    )
                ),
                0,
            ).label("earned_lifetime"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (
                                (AffiliateCommission.status == CommissionStatus.APPROVED)
                                & AffiliateCommission.payout_reference.is_not(None)
                            ),
                            AffiliateCommission.commission_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("reserved"),
        )
        .filter(AffiliateCommission.user_id == user_id)
        .one()
    )
    return CommissionBalance(
        available=money(row.available),
        pending=money(row.pending),
        paid_lifetime=money(row.paid_lifetime),
        earned_lifetime=money(row.earned_lifetime),
        reserved=money(row.reserved),
    )

