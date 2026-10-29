"""Canonical derived balances for the active affiliate commission wallet."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services.commission_payout_hold import card_hold_clause, held_clause, payable_clause
from app.services.financial_integrity import money


@dataclass(frozen=True)
class CommissionBalance:
    available: Decimal
    pending: Decimal
    paid_lifetime: Decimal
    earned_lifetime: Decimal
    reserved: Decimal
    # Historical commissions held from payout until reviewed (part of `pending`
    # or of what would otherwise be `available`; never paid while held).
    held: Decimal = Decimal("0.00")
    # PENDING rows that may be paid once a destination exists (never a held row).
    pending_payable: Decimal = Decimal("0.00")
    # Earned from a bank card payment still in its 14-day chargeback period: paid once it is over.
    card_hold: Decimal = Decimal("0.00")


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
                                & payable_clause()
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
                        (
                            AffiliateCommission.status.in_((CommissionStatus.PENDING, CommissionStatus.APPROVED))
                            & AffiliateCommission.payout_reference.is_(None)
                            & held_clause(),
                            AffiliateCommission.commission_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("held"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (AffiliateCommission.status == CommissionStatus.PENDING)
                            & AffiliateCommission.payout_reference.is_(None)
                            & payable_clause(),
                            AffiliateCommission.commission_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("pending_payable"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            AffiliateCommission.status.in_((CommissionStatus.PENDING, CommissionStatus.APPROVED))
                            & AffiliateCommission.payout_reference.is_(None)
                            & card_hold_clause(),
                            AffiliateCommission.commission_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("card_hold"),
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
        held=money(row.held),
        pending_payable=money(row.pending_payable),
        card_hold=money(row.card_hold),
    )

