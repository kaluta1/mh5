"""Read-only figures used before and after a correction (reconciliation)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services.financial_integrity import money

ACCOUNTS = ("1001", "1200", "2001", "2002", "2003", "2100", "2113", "4001", "4002", "5001")


def account_balance(db: Session, code: str) -> Decimal:
    """Signed debit - credit (assets/expenses positive, liabilities/revenue negative)."""
    value = (db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0) - func.coalesce(func.sum(JournalLine.credit_amount), 0))
             .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
             .filter(ChartOfAccounts.account_code == code).scalar())
    return money(value or 0)


def snapshot(db: Session) -> dict:
    from app.services.commission_payout_hold import historical_clause

    accounts = {code: str(account_balance(db, code)) for code in ACCOUNTS}
    by_status = {s.value: [int(n), str(money(a or 0))] for s, n, a in
                 db.query(AffiliateCommission.status, func.count(AffiliateCommission.id),
                          func.sum(AffiliateCommission.commission_amount))
                 .group_by(AffiliateCommission.status).all()}
    open_rows = AffiliateCommission.status.in_((CommissionStatus.PENDING, CommissionStatus.APPROVED))

    def total(*criteria) -> str:
        return str(money(db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
                         .filter(*criteria).scalar() or 0))

    unbalanced = (db.query(JournalLine.entry_id).group_by(JournalLine.entry_id)
                  .having(func.sum(JournalLine.debit_amount) != func.sum(JournalLine.credit_amount)).count())
    return {
        "accounts_debit_minus_credit": accounts,
        "commissions_by_status": by_status,
        "open_commissions": {
            "level_1": total(open_rows, AffiliateCommission.level == 1),
            "levels_2_10": total(open_rows, AffiliateCommission.level != 1),
            "legacy": total(open_rows, historical_clause()),
            "new_v2": total(open_rows, ~historical_clause()),
            "all": total(open_rows),
        },
        "ledger_vs_subledger": {
            "2001_liability": str(-account_balance(db, "2001")),
            "open_level_1": total(open_rows, AffiliateCommission.level == 1),
            "2002_liability": str(-account_balance(db, "2002")),
            "open_levels_2_10": total(open_rows, AffiliateCommission.level != 1),
            "5001_expense": str(account_balance(db, "5001")),
            "commissions_not_cancelled": total(AffiliateCommission.status != CommissionStatus.CANCELLED),
        },
        "journal_entries": db.query(JournalEntry).count(),
        "unbalanced_entries": unbalanced,
    }


def diff(before: dict, after: dict) -> dict:
    """Only what changed, as before -> after."""
    out = {}
    for section in ("accounts_debit_minus_credit", "open_commissions", "ledger_vs_subledger"):
        for key, value in after[section].items():
            if before[section].get(key) != value:
                out[f"{section}.{key}"] = f"{before[section].get(key)} -> {value}"
    if before["commissions_by_status"] != after["commissions_by_status"]:
        out["commissions_by_status"] = f"{before['commissions_by_status']} -> {after['commissions_by_status']}"
    if before["journal_entries"] != after["journal_entries"]:
        out["journal_entries"] = f"{before['journal_entries']} -> {after['journal_entries']}"
    return out
