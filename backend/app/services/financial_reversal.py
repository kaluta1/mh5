"""Compensating entries for provider-confirmed full payment refunds."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.payment import Deposit, DepositStatus
from app.models.fmr import MemberFmpBalance, MemberFmpLedger
from app.services.accounting_service import accounting_service
from app.services.financial_integrity import FinancialIntegrityError, money

logger = logging.getLogger(__name__)

_REFUND_MARKER = "Provider refund reconciled"


def _mentions_exact_deposit(description: str, deposit_id: int) -> bool:
    """Legacy journals carry the deposit only in text; match '#5' but never '#51'."""
    return re.search(rf"Deposit #{int(deposit_id)}(?!\d)", description or "") is not None


def _refund_amount(payload: dict[str, Any], deposit: Deposit) -> Decimal:
    expected = money(deposit.amount)
    explicit = payload.get("refund_amount")
    if explicit is None:
        return expected
    refunded = money(explicit)
    if refunded != expected:
        raise FinancialIntegrityError(
            "Partial refunds are not supported; reconcile this provider event manually"
        )
    return refunded


def reverse_provider_refund(
    db: Session,
    deposit: Deposit,
    payload: dict[str, Any],
    *,
    defer_commit: bool = False,
) -> bool:
    """Reverse a full refund once without deleting the original financial history."""
    locked = (
        db.query(Deposit)
        .filter(Deposit.id == deposit.id)
        .with_for_update()
        .one()
    )
    notes = str(locked.admin_notes or "")
    if _REFUND_MARKER in notes:
        return True

    _refund_amount(payload, locked)

    from app.services.new_model_ledger import is_new_model

    if is_new_model(getattr(locked, "business_model_version", None)):
        # NEW_V2: exact structured reversal of this deposit's own journals, revenue and commission.
        from app.services.new_model_payments import reverse_new_model_deposit

        reverse_new_model_deposit(db, locked, reason="Provider refund")
        locked.status = DepositStatus.FAILED
        locked.admin_notes = f"{notes}\n{_REFUND_MARKER} at {datetime.utcnow().isoformat()}Z".strip()
        db.flush()
        if not defer_commit:
            db.commit()
        return True

    commissions = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.deposit_id == locked.id)
        .with_for_update()
        .all()
    )
    if any(
        commission.status == CommissionStatus.APPROVED
        and str(commission.payout_reference or "").startswith("intent:")
        for commission in commissions
    ):
        raise FinancialIntegrityError(
            "Refund cannot race an unresolved payout intent; reconcile the payout first"
        )

    reversal_description = f"Refund reversal - Deposit #{locked.id}"
    reversal_exists = (
        db.query(JournalEntry.id)
        .filter(JournalEntry.description == reversal_description)
        .first()
        is not None
    )
    if not reversal_exists:
        original_entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.description.like(f"%Deposit #{locked.id}%"),
                JournalEntry.description != reversal_description,
            )
            .order_by(JournalEntry.id.asc())
            .all()
        )
        # The LIKE above is only a pre-filter; identity is the exact deposit number.
        original_entries = [e for e in original_entries if _mentions_exact_deposit(e.description, locked.id)]
        reversal_lines: list[dict] = []
        for entry in original_entries:
            rows = (
                db.query(ChartOfAccounts.account_code, JournalLine)
                .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
                .filter(JournalLine.entry_id == entry.id)
                .all()
            )
            for account_code, line in rows:
                reversal_lines.append(
                    {
                        "account_code": account_code,
                        "debit": money(line.credit_amount),
                        "credit": money(line.debit_amount),
                        "description": f"Reverse {entry.entry_number} for refunded deposit #{locked.id}",
                    }
                )
        if reversal_lines:
            accounting_service.create_journal_entry(
                db,
                description=reversal_description,
                lines=reversal_lines,
                date=datetime.utcnow(),
                commit=False,
            )
        else:
            logger.warning("Refunded deposit %s has no journal entries to reverse", locked.id)

    paid_level_one = sum(
        (money(c.commission_amount) for c in commissions if c.status == CommissionStatus.PAID and c.level == 1),
        Decimal("0.00"),
    )
    paid_indirect = sum(
        (money(c.commission_amount) for c in commissions if c.status == CommissionStatus.PAID and c.level != 1),
        Decimal("0.00"),
    )
    receivable_description = f"Refund paid-commission receivable - Deposit #{locked.id}"
    if (paid_level_one or paid_indirect) and not db.query(JournalEntry.id).filter(
        JournalEntry.description == receivable_description
    ).first():
        lines: list[dict] = [
            {
                "account_code": "1200",
                "debit": money(paid_level_one + paid_indirect),
                "credit": 0,
                "description": "Affiliate receivable after refunded source payment",
            }
        ]
        if paid_level_one:
            lines.append(
                {"account_code": "2001", "debit": 0, "credit": paid_level_one, "description": receivable_description}
            )
        if paid_indirect:
            lines.append(
                {"account_code": "2002", "debit": 0, "credit": paid_indirect, "description": receivable_description}
            )
        accounting_service.create_journal_entry(
            db,
            description=receivable_description,
            lines=lines,
            date=datetime.utcnow(),
            commit=False,
        )

    for commission in commissions:
        commission.status = CommissionStatus.CANCELLED

    founding_points = (
        db.query(MemberFmpLedger)
        .filter(
            MemberFmpLedger.user_id == locked.user_id,
            MemberFmpLedger.source_type == "FOUNDING_JOIN",
            MemberFmpLedger.source_id == locked.id,
        )
        .first()
    )
    fmp_reversal_exists = (
        db.query(MemberFmpLedger.id)
        .filter(
            MemberFmpLedger.user_id == locked.user_id,
            MemberFmpLedger.source_type == "FOUNDING_JOIN_REVERSAL",
            MemberFmpLedger.source_id == locked.id,
        )
        .first()
        is not None
    )
    if founding_points and not fmp_reversal_exists:
        points = Decimal(str(founding_points.points))
        db.add(
            MemberFmpLedger(
                user_id=locked.user_id,
                source_type="FOUNDING_JOIN_REVERSAL",
                source_id=locked.id,
                points=-points,
            )
        )
        balance = (
            db.query(MemberFmpBalance)
            .filter(MemberFmpBalance.user_id == locked.user_id)
            .with_for_update()
            .first()
        )
        if balance:
            balance.total_fmp = Decimal(str(balance.total_fmp or 0)) - points

    locked.status = DepositStatus.FAILED
    locked.admin_notes = f"{notes}\n{_REFUND_MARKER} at {datetime.utcnow().isoformat()}Z".strip()
    db.flush()
    if not defer_commit:
        db.commit()
    return True
