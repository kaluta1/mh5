"""Multi-Unit Referral Pool: the money of each $100 unit (P5).

The deposit and the ledger stay the financial source of truth. A confirmed pool payment is
first held as a receipt (Dr 1001 cash / Cr 2100, existing hold, once per deposit). Each unit
then earns its share, once, when it is ACTIVE:

  recognition (per unit)   Dr 2100  100.00 / Cr 4008  100.00   source REFERRAL_POOL_UNIT:<unit>
  revenue subledger        RevenueRecognition website revenue 100.00 (Leaders base)
  direct commission        20% of the gross unit price to the purchaser's direct sponsor, through
                           the existing engine (Dr 5001 / Cr 2001; payable at once, existing policy)

A unit that is held for review, not yet active or refunded earns nothing; its cash stays in 2100.
A refund reverses exactly that unit's recognition and commission (a paid commission becomes a
1200 receivable under the existing clawback model, never an automatic debit). The cash leaves
either by the existing full provider refund of the deposit (its receipt is reversed) or by a
finance administrator recording a verified partial refund (Dr 2100 / Cr 1001 per unit).

Everything here runs under the caller's pool locks (referral_pool_units) and never commits.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.business_model import ReferralPoolPurchase, ReferralPoolUnit, RevenueRecognition
from app.models.payment import Deposit, DepositStatus
from app.services.financial_integrity import FinancialIntegrityError, money
from app.services.new_model_ledger import (
    Line,
    PostingType,
    SourceType,
    find_entry,
    idempotency_key,
    is_reversed,
    post_entry,
    reverse_entry,
)
from app.services.new_model_revenue import (
    accrue_direct_commission,
    compute_breakdown,
    get_policy,
    record_recognition,
    reverse_direct_commissions,
    reverse_recognition,
)

logger = logging.getLogger(__name__)

SOURCE_UNIT = "REFERRAL_POOL_UNIT"
POSTING_REFUND = "REFUND"
HOLD_ACCOUNT, REVENUE_ACCOUNT, CASH_ACCOUNT = "2100", "4008", "1001"


class PoolAccountingError(FinancialIntegrityError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- the deposit's receipt

def receipt_for(db: Session, deposit: Deposit) -> Optional[JournalEntry]:
    return find_entry(db, idempotency_key(SourceType.DEPOSIT, deposit.id, PostingType.RECEIPT))


def _held_amount(db: Session, entry: JournalEntry) -> Decimal:
    """What the receipt credited to the hold account."""
    rows = (db.query(JournalLine.credit_amount, JournalLine.debit_amount)
            .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
            .filter(JournalLine.entry_id == entry.id, ChartOfAccounts.account_code == HOLD_ACCOUNT).all())
    return money(sum((money(c) - money(d) for c, d in rows), Decimal("0")))


def receipt_ready(db: Session, deposit: Deposit) -> bool:
    """The deposit's cash is held in 2100 for exactly its amount, and was never reversed."""
    entry = receipt_for(db, deposit)
    return (entry is not None and not is_reversed(db, entry)
            and _held_amount(db, entry) == money(deposit.amount))


# ---------------------------------------------------------------- earning (unit ACTIVE)

def recognize_unit(db: Session, unit: ReferralPoolUnit) -> Optional[RevenueRecognition]:
    """$100 revenue and the direct commission of one ACTIVE paid unit, once. Returns the
    recognition (the existing one on a repeat). Refuses anything not verified and active."""
    if unit.revenue_recognition_id is not None:
        return db.get(RevenueRecognition, unit.revenue_recognition_id)
    if unit.source != "PAID" or unit.status != "ACTIVE":
        return None                                   # earns nothing (held, suspended at once, refunded, ...)
    purchase = db.get(ReferralPoolPurchase, unit.purchase_id)
    deposit = db.get(Deposit, purchase.deposit_id) if purchase is not None else None
    if purchase is None or purchase.status not in ("PAID", "PARTIALLY_REFUNDED"):
        raise PoolAccountingError("PURCHASE_NOT_PAID", f"Purchase of unit {unit.id} is not paid")
    if deposit is None or deposit.status != DepositStatus.VALIDATED or not receipt_ready(db, deposit):
        raise PoolAccountingError("RECEIPT_MISSING", f"The cash of unit {unit.id} is not held in 2100")
    if money(unit.amount) != money(purchase.unit_price):
        raise PoolAccountingError("UNIT_AMOUNT", f"Unit {unit.id} amount differs from its purchase")

    policy = get_policy(db, deposit_product_code(db, deposit))
    breakdown = compute_breakdown(policy, unit.amount)
    entry = post_entry(
        db, source_type=SOURCE_UNIT, source_id=unit.id, posting_type=PostingType.RECOGNITION,
        lines=[Line(HOLD_ACCOUNT, debit=breakdown.gross, description="Release held Referral Pool payment"),
               Line(policy.revenue_account_code, credit=breakdown.website_revenue,
                    description=f"Website revenue - Referral Pool unit {unit.id}")],
        description=f"Referral Pool unit {unit.id} (purchase {purchase.id}, deposit {deposit.id}): revenue recognized",
    )
    recognition = record_recognition(db, source_type=SOURCE_UNIT, source_id=unit.id, user_id=unit.user_id,
                                     breakdown=breakdown, journal_entry_id=entry.id)
    unit.revenue_recognition_id = recognition.id
    # One commission per unit (keyed by the unit; the deposit is reached through the purchase).
    commission = accrue_direct_commission(db, source_type=SOURCE_UNIT, source_id=unit.id,
                                          payer_user_id=unit.user_id, breakdown=breakdown, deposit_id=None,
                                          product_type_id=deposit.product_type_id)
    unit.direct_commission_id = commission.id if commission is not None else None
    db.flush()
    return recognition


def deposit_product_code(db: Session, deposit: Deposit) -> str:
    from app.models.payment import ProductType

    return db.query(ProductType.code).filter(ProductType.id == deposit.product_type_id).scalar()


# ---------------------------------------------------------------- reversing (unit refunded)

def reverse_unit(db: Session, unit: ReferralPoolUnit, *, reason: str, cash_refund: bool) -> None:
    """Undo what one unit earned, once: its recognition (journal + subledger) and its commission.
    With `cash_refund` (a verified partial refund) the unit's cash also leaves 2100; without it
    the cash leaves with the deposit's own receipt reversal (a full provider refund)."""
    recognition = db.get(RevenueRecognition, unit.revenue_recognition_id) if unit.revenue_recognition_id else None
    if recognition is not None:
        entry = db.get(JournalEntry, recognition.journal_entry_id) if recognition.journal_entry_id else None
        reversal_id = None
        if entry is not None:
            reversal_id = reverse_entry(db, entry, reason=reason).id
        reverse_recognition(db, recognition, journal_entry_id=reversal_id)
    # Existing engine: cancels an unpaid commission, books a 1200 receivable for a paid one,
    # and refuses while a payout of it is in flight (the whole refund then rolls back).
    reverse_direct_commissions(db, source_type=SOURCE_UNIT, source_id=unit.id, reason=reason)
    if cash_refund:
        refund = post_entry(
            db, source_type=SOURCE_UNIT, source_id=unit.id, posting_type=POSTING_REFUND,
            lines=[Line(HOLD_ACCOUNT, debit=money(unit.amount), description="Referral Pool unit refunded"),
                   Line(CASH_ACCOUNT, credit=money(unit.amount),
                        description=f"Cash refunded ({unit.refund_reference or reason})")],
            description=f"Referral Pool unit {unit.id}: verified refund {unit.refund_reference or ''}".strip(),
        )
        unit.refund_journal_entry_id = refund.id
    db.flush()


def link_cash_reversal(db: Session, deposit: Deposit, units_refunded) -> None:
    """A full provider refund: the deposit's receipt reversal (posted by the existing refund path)
    is where each unit's cash left; recorded on the unit for traceability."""
    receipt = receipt_for(db, deposit)
    cash_reversal = (db.query(JournalEntry).filter(JournalEntry.reverses_entry_id == receipt.id).first()
                     if receipt is not None else None)
    if cash_reversal is None:
        return
    for unit in units_refunded:
        unit.refund_journal_entry_id = cash_reversal.id
    db.flush()


# ---------------------------------------------------------------- reconciliation

def purchase_ledger(db: Session, purchase_id: int) -> dict:
    """Net balance per account of everything this purchase moved (deposit receipt, unit
    recognitions/refunds, unit commissions and their reversals). Debit positive."""
    from app.models.affiliate import AffiliateCommission

    purchase = db.get(ReferralPoolPurchase, purchase_id)
    unit_ids = [u for (u,) in db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.purchase_id == purchase_id)]
    commission_ids = [c for (c,) in db.query(AffiliateCommission.id).filter(
        AffiliateCommission.source_type == SOURCE_UNIT, AffiliateCommission.source_id.in_(unit_ids or [0]))]
    sources = [(SourceType.DEPOSIT, [purchase.deposit_id]), (SOURCE_UNIT, unit_ids),
               (SourceType.COMMISSION, commission_ids)]
    totals: dict = {}
    for source_type, ids in sources:
        if not ids:
            continue
        rows = (db.query(ChartOfAccounts.account_code, JournalLine.debit_amount, JournalLine.credit_amount)
                .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(JournalEntry.source_type == source_type, JournalEntry.source_id.in_(ids)).all())
        for code, debit, credit in rows:
            totals[code] = money(totals.get(code, Decimal("0")) + money(debit) - money(credit))
    return {code: amount for code, amount in totals.items() if amount != 0}


def reconcile_purchase(db: Session, purchase_id: int) -> list:
    """Problems found (empty = reconciled): what the ledger says against what the units say."""
    purchase = db.get(ReferralPoolPurchase, purchase_id)
    deposit = db.get(Deposit, purchase.deposit_id)
    units_ = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase_id).all()
    ledger = purchase_ledger(db, purchase_id)
    problems = []
    earning = [u for u in units_ if u.revenue_recognition_id is not None and u.status != "REFUNDED"]
    if -ledger.get(REVENUE_ACCOUNT, Decimal("0")) != money(sum((u.amount for u in earning), Decimal("0"))):
        problems.append(("REVENUE", ledger.get(REVENUE_ACCOUNT), len(earning)))
    refunded = [u for u in units_ if u.status == "REFUNDED"]
    cash_in = money(deposit.amount) if receipt_for(db, deposit) is not None else Decimal("0")
    expected_cash = money(cash_in - sum((u.amount for u in refunded), Decimal("0")))
    if not units_ and purchase.status == "REFUNDED":
        expected_cash = Decimal("0.00")
    if ledger.get(CASH_ACCOUNT, Decimal("0")) != expected_cash:
        problems.append(("CASH", ledger.get(CASH_ACCOUNT), expected_cash))
    held = [u for u in units_ if u.revenue_recognition_id is None and u.status != "REFUNDED"]
    expected_hold = -money(sum((u.amount for u in held), Decimal("0")))
    if not units_:
        expected_hold = -expected_cash
    if ledger.get(HOLD_ACCOUNT, Decimal("0")) != expected_hold:
        problems.append(("HOLD_2100", ledger.get(HOLD_ACCOUNT), expected_hold))
    return problems
