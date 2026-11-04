"""The unpaid value of a commission row: ONE definition for wallet spending, cashouts, payouts and balances.

A commission row is never resized (its commission_amount is the original, audited amount). What internal
wallet payments used of it is recorded in internal_wallet_payment_lines (ACTIVE lines; a refunded payment's
lines are REVERSED). So, for any row:

    open amount = commission_amount - sum(ACTIVE internal wallet lines of the row)

A row's payout_reference says who may take that open amount:
  NULL       unreserved, never used by the wallet          -> wallet AND cashout may take it
  'iwp-rem'  unreserved, partly used by the wallet         -> wallet AND cashout may take its open amount
  intent:... reserved by ONE cashout (its whole open amount) -> nobody else (the wallet takes only the two above)
  other      paid (PAID rows) or legacy

The two operations never take the same money: both lock the member row first, then the unreserved rows
(SELECT ... FOR UPDATE). A cashout reserves a row's whole open amount by setting its payout_reference to the
cashout's intent, so the wallet no longer sees it; a wallet payment records its lines while holding the
row lock, so a cashout computed afterwards sees the smaller open amount. Nothing here writes.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from app.models.affiliate import AffiliateCommission
from app.models.internal_wallet import InternalWalletPaymentLine
from app.services.financial_integrity import FinancialIntegrityError, money

REMAINDER_MARK = "iwp-rem"
ACTIVE_LINE = "ACTIVE"


def unreserved_clause():
    """Rows no cashout or payout holds: never used by the wallet, or partly used by it."""
    return or_(AffiliateCommission.payout_reference.is_(None),
               AffiliateCommission.payout_reference == REMAINDER_MARK)


def wallet_used(db: Session, commission_ids: Iterable[int]) -> Dict[int, Decimal]:
    """What ACTIVE internal wallet payment lines used of each row (rows never used are absent)."""
    ids = sorted({int(i) for i in commission_ids})
    if not ids:
        return {}
    rows = (db.query(InternalWalletPaymentLine.commission_id,
                     func.coalesce(func.sum(InternalWalletPaymentLine.amount), 0))
            .filter(InternalWalletPaymentLine.commission_id.in_(ids), InternalWalletPaymentLine.status == ACTIVE_LINE)
            .group_by(InternalWalletPaymentLine.commission_id).all())
    return {int(k): money(v) for k, v in rows}


def open_amounts(rows: Iterable[AffiliateCommission], db: Optional[Session] = None) -> Dict[int, Decimal]:
    """{row id: open amount}. Refuses (never returns a negative or hides it) a row used beyond its amount."""
    rows = list(rows)
    if not rows:
        return {}
    session = db or object_session(rows[0])
    used = wallet_used(session, [r.id for r in rows]) if session is not None else {}
    out = {}
    for row in rows:
        left = money(money(row.commission_amount) - used.get(int(row.id), Decimal("0.00")))
        if left < 0:
            raise FinancialIntegrityError(f"Commission #{row.id} is used beyond its amount")
        out[int(row.id)] = left
    return out


def open_amount(row: AffiliateCommission, db: Optional[Session] = None) -> Decimal:
    return open_amounts([row], db)[int(row.id)]


def used_subquery():
    """(commission_id, used) of ACTIVE wallet lines, for an OUTER JOIN in aggregate queries."""
    return (select(InternalWalletPaymentLine.commission_id.label("commission_id"),
                   func.sum(InternalWalletPaymentLine.amount).label("used"))
            .where(InternalWalletPaymentLine.status == ACTIVE_LINE)
            .group_by(InternalWalletPaymentLine.commission_id)
            .subquery("wallet_used"))


def open_amount_sql(used):
    """SQL expression of the open amount; `used` is a used_subquery() outer-joined on commission_id."""
    return AffiliateCommission.commission_amount - func.coalesce(used.c.used, 0)


def wallet_used_sql(used):
    return func.coalesce(used.c.used, 0)
