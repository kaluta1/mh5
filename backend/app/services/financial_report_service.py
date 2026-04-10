"""
Financial statements from posted journal lines (admin reporting).

Balances use normal accounting rules:
- ASSET, EXPENSE: debit − credit
- LIABILITY, EQUITY, REVENUE: credit − debit
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, List, Tuple

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry, JournalLine

POSTED_STATUSES = ("posted", "POSTED", "Posted")


def _coa_id_map(db: Session) -> dict[int, ChartOfAccounts]:
    rows = (
        db.query(ChartOfAccounts)
        .filter(ChartOfAccounts.is_active == True)  # noqa: E712
        .all()
    )
    return {a.id: a for a in rows}


def _enrich_account_fields(acc: ChartOfAccounts, id_map: dict[int, ChartOfAccounts]) -> dict[str, Any]:
    pid = acc.parent_id
    parent = id_map.get(pid) if pid else None
    at = acc.account_type.value if hasattr(acc.account_type, "value") else str(acc.account_type)
    return {
        "account_id": acc.id,
        "account_code": acc.account_code,
        "account_name": acc.account_name,
        "description": acc.description,
        "account_type": at,
        "parent_id": acc.parent_id,
        "parent_account_code": parent.account_code if parent else None,
    }


def _has_journal_tables(db: Session) -> bool:
    bind = db.get_bind()
    insp = inspect(bind)
    return insp.has_table("journal_entries") and insp.has_table("journal_lines")


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max)


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _signed_balance(account_type: AccountType, total_debit: float, total_credit: float) -> float:
    td = float(total_debit or 0)
    tc = float(total_credit or 0)
    if account_type in (AccountType.ASSET, AccountType.EXPENSE):
        return round(td - tc, 2)
    return round(tc - td, 2)


def account_totals_through_date(
    db: Session, end_dt: datetime
) -> List[Tuple[ChartOfAccounts, float, float]]:
    """Per account: sum debits/credits for posted entries with entry_date <= end_dt."""
    if not _has_journal_tables(db):
        return []

    subq = (
        db.query(
            JournalLine.account_id.label("aid"),
            func.coalesce(func.sum(JournalLine.debit_amount), 0).label("deb"),
            func.coalesce(func.sum(JournalLine.credit_amount), 0).label("cred"),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.entry_date <= end_dt)
        .filter(JournalEntry.status.in_(POSTED_STATUSES))
        .group_by(JournalLine.account_id)
    ).subquery()

    rows = (
        db.query(ChartOfAccounts, subq.c.deb, subq.c.cred)
        .outerjoin(subq, ChartOfAccounts.id == subq.c.aid)
        .filter(ChartOfAccounts.is_active == True)  # noqa: E712
        .order_by(ChartOfAccounts.account_code)
        .all()
    )
    return [(acc, float(deb or 0), float(cred or 0)) for acc, deb, cred in rows]


def account_totals_in_period(
    db: Session, start_dt: datetime, end_dt: datetime
) -> List[Tuple[ChartOfAccounts, float, float]]:
    """Per account: activity in [start_dt, end_dt] for posted entries."""
    if not _has_journal_tables(db):
        return []

    rows = (
        db.query(
            ChartOfAccounts,
            func.coalesce(func.sum(JournalLine.debit_amount), 0).label("deb"),
            func.coalesce(func.sum(JournalLine.credit_amount), 0).label("cred"),
        )
        .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(ChartOfAccounts.is_active == True)  # noqa: E712
        .filter(JournalEntry.entry_date >= start_dt)
        .filter(JournalEntry.entry_date <= end_dt)
        .filter(JournalEntry.status.in_(POSTED_STATUSES))
        .group_by(ChartOfAccounts.id)
        .order_by(ChartOfAccounts.account_code)
        .all()
    )
    return [(acc, float(deb or 0), float(cred or 0)) for acc, deb, cred in rows]


def generate_balance_sheet_payload(db: Session, as_of: date) -> dict[str, Any]:
    end_dt = _end_of_day(as_of)
    rows = account_totals_through_date(db, end_dt)
    id_map = _coa_id_map(db)
    assets: List[dict] = []
    liabilities: List[dict] = []
    equity: List[dict] = []
    total_a = total_l = total_e = 0.0
    for acc, td, tc in rows:
        bal = _signed_balance(acc.account_type, td, tc)
        if abs(bal) < 0.00001:
            continue
        base = _enrich_account_fields(acc, id_map)
        item = {**base, "balance": bal}
        if acc.account_type == AccountType.ASSET:
            assets.append(item)
            total_a += bal
        elif acc.account_type == AccountType.LIABILITY:
            liabilities.append(item)
            total_l += bal
        elif acc.account_type == AccountType.EQUITY:
            equity.append(item)
            total_e += bal
    total_a, total_l, total_e = round(total_a, 2), round(total_l, 2), round(total_e, 2)
    diff = round(total_a - (total_l + total_e), 2)
    return {
        "as_of_date": as_of.isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_a,
        "total_liabilities": total_l,
        "total_equity": total_e,
        "is_balanced": abs(diff) < 0.02,
        "assets_minus_liabilities_and_equity": diff,
    }


def generate_income_statement_payload(db: Session, start: date, end: date) -> dict[str, Any]:
    start_dt = _start_of_day(start)
    end_dt = _end_of_day(end)
    rows = account_totals_in_period(db, start_dt, end_dt)
    id_map = _coa_id_map(db)
    revenues: List[dict] = []
    expenses: List[dict] = []
    tr = te = 0.0
    for acc, td, tc in rows:
        td_f, tc_f = float(td), float(tc)
        if acc.account_type == AccountType.REVENUE:
            amt = round(tc_f - td_f, 2)
            if abs(amt) < 0.00001:
                continue
            base = _enrich_account_fields(acc, id_map)
            revenues.append({**base, "amount": amt})
            tr += amt
        elif acc.account_type == AccountType.EXPENSE:
            amt = round(td_f - tc_f, 2)
            if abs(amt) < 0.00001:
                continue
            base = _enrich_account_fields(acc, id_map)
            expenses.append({**base, "amount": amt})
            te += amt
    tr, te = round(tr, 2), round(te, 2)
    net = round(tr - te, 2)
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "revenues": revenues,
        "expenses": expenses,
        "total_revenue": tr,
        "total_expenses": te,
        "net_income": net,
        "gross_profit": net,
    }


def generate_trial_balance_payload(db: Session, as_of: date) -> dict[str, Any]:
    end_dt = _end_of_day(as_of)
    rows = account_totals_through_date(db, end_dt)
    id_map = _coa_id_map(db)
    accounts: List[dict] = []
    total_debits = total_credits = 0.0
    for acc, td, tc in rows:
        td_f, tc_f = float(td), float(tc)
        bal = _signed_balance(acc.account_type, td_f, tc_f)
        if acc.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            deb = max(bal, 0.0)
            cred = max(-bal, 0.0)
        else:
            cred = max(bal, 0.0)
            deb = max(-bal, 0.0)
        if deb < 0.00001 and cred < 0.00001:
            continue
        deb, cred = round(deb, 2), round(cred, 2)
        base = _enrich_account_fields(acc, id_map)
        accounts.append(
            {
                **base,
                "debit": deb,
                "credit": cred,
            }
        )
        total_debits += deb
        total_credits += cred
    total_debits = round(total_debits, 2)
    total_credits = round(total_credits, 2)
    return {
        "as_of_date": as_of.isoformat(),
        "accounts": accounts,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": abs(total_debits - total_credits) < 0.02,
    }


def generate_cash_flow_payload(db: Session, start: date, end: date) -> dict[str, Any]:
    inc = generate_income_statement_payload(db, start, end)
    net_income = inc["net_income"]
    begin_cash = 0.0
    end_cash = 0.0
    treasury_usdt_bsc = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == "1001").first()
    if treasury_usdt_bsc and _has_journal_tables(db):
        pre_end = _end_of_day(start - timedelta(days=1))
        for acc, d, c in account_totals_through_date(db, pre_end):
            if acc.id == treasury_usdt_bsc.id:
                begin_cash = _signed_balance(acc.account_type, d, c)
                break
        for acc, d, c in account_totals_through_date(db, _end_of_day(end)):
            if acc.id == treasury_usdt_bsc.id:
                end_cash = _signed_balance(acc.account_type, d, c)
                break
    begin_cash, end_cash = round(begin_cash, 2), round(end_cash, 2)
    change = round(end_cash - begin_cash, 2)
    other = round(change - net_income, 2)
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "note": "Summary: net income from the income statement and the change in on-chain USDT (BEP-20, BSC) "
        "held in treasury account 1001 when present. Amounts are in USDT. "
        "Line-by-line operating / investing / financing classification is not implemented yet.",
        "net_income": net_income,
        "beginning_cash_balance": begin_cash,
        "ending_cash_balance": end_cash,
        "net_change_in_cash": change,
        "operating_activities": [
            {"label": "Net income", "amount": net_income},
            {
                "label": "Other (reconciliation to USDT BSC treasury — 1001)",
                "amount": other,
            },
        ],
        "investing_activities": [],
        "financing_activities": [],
    }


def generate_general_ledger_payload(
    db: Session,
    account_code: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    if not _has_journal_tables(db):
        return {
            "account": None,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "opening_balance": 0.0,
            "closing_balance": 0.0,
            "lines": [],
        }

    acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == account_code).first()
    if not acc:
        return {
            "account": None,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "opening_balance": 0.0,
            "closing_balance": 0.0,
            "lines": [],
            "error": f"Unknown account code: {account_code}",
        }

    pre_end = _end_of_day(start - timedelta(days=1))
    opening = 0.0
    for a, d, c in account_totals_through_date(db, pre_end):
        if a.id == acc.id:
            opening = _signed_balance(a.account_type, d, c)
            break

    start_dt = _start_of_day(start)
    end_dt = _end_of_day(end)
    q = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalLine.account_id == acc.id)
        .filter(JournalEntry.entry_date >= start_dt)
        .filter(JournalEntry.entry_date <= end_dt)
        .filter(JournalEntry.status.in_(POSTED_STATUSES))
        .order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)
    )
    running = opening
    lines_out: List[dict] = []
    for jl, je in q.all():
        d_amt = float(jl.debit_amount or 0)
        c_amt = float(jl.credit_amount or 0)
        if acc.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            running = round(running + d_amt - c_amt, 2)
        else:
            running = round(running + c_amt - d_amt, 2)
        ed = je.entry_date
        lines_out.append(
            {
                "entry_date": ed.isoformat() if hasattr(ed, "isoformat") else str(ed),
                "entry_number": je.entry_number,
                "description": jl.description or je.description,
                "debit": round(d_amt, 2),
                "credit": round(c_amt, 2),
                "balance": running,
            }
        )

    at = acc.account_type.value if hasattr(acc.account_type, "value") else str(acc.account_type)
    return {
        "account": {
            "account_code": acc.account_code,
            "account_name": acc.account_name,
            "account_type": at,
        },
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "opening_balance": round(opening, 2),
        "closing_balance": running,
        "lines": lines_out,
    }


def generate_chart_of_accounts_register_payload(db: Session, as_of: date) -> dict[str, Any]:
    """
    Full chart of accounts: every active account with cumulative debits, credits,
    and signed balance as of `as_of` (posted journals only).
    """
    end_dt = _end_of_day(as_of)
    id_map = _coa_id_map(db)
    all_accs = (
        db.query(ChartOfAccounts)
        .filter(ChartOfAccounts.is_active == True)  # noqa: E712
        .order_by(ChartOfAccounts.account_code)
        .all()
    )
    rows = account_totals_through_date(db, end_dt)
    aid_dc = {acc.id: (float(td), float(tc)) for acc, td, tc in rows}

    register: List[dict] = []
    subtotals: dict[str, dict[str, Any]] = {}
    for at in AccountType:
        subtotals[at.value] = {"signed_balance": 0.0, "account_count": 0}

    for acc in all_accs:
        td_f, tc_f = aid_dc.get(acc.id, (0.0, 0.0))
        signed = _signed_balance(acc.account_type, td_f, tc_f)
        base = _enrich_account_fields(acc, id_map)
        at_key = acc.account_type.value if hasattr(acc.account_type, "value") else str(acc.account_type)
        register.append(
            {
                **base,
                "total_debit": round(td_f, 2),
                "total_credit": round(tc_f, 2),
                "signed_balance": signed,
            }
        )
        subtotals[at_key]["signed_balance"] = round(subtotals[at_key]["signed_balance"] + signed, 2)
        subtotals[at_key]["account_count"] += 1

    return {
        "as_of_date": as_of.isoformat(),
        "accounts": register,
        "subtotals_by_type": subtotals,
    }


def generate_period_activity_payload(db: Session, start: date, end: date) -> dict[str, Any]:
    """Posted debit/credit activity and natural signed effect per account for the period."""
    start_dt = _start_of_day(start)
    end_dt = _end_of_day(end)
    rows = account_totals_in_period(db, start_dt, end_dt)
    id_map = _coa_id_map(db)
    lines: List[dict] = []
    for acc, td, tc in rows:
        td_f, tc_f = float(td), float(tc)
        if td_f < 0.00001 and tc_f < 0.00001:
            continue
        signed = _signed_balance(acc.account_type, td_f, tc_f)
        base = _enrich_account_fields(acc, id_map)
        lines.append(
            {
                **base,
                "period_debit": round(td_f, 2),
                "period_credit": round(tc_f, 2),
                "period_net_signed": signed,
            }
        )
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "lines": lines,
    }


def generate_full_financial_report_payload(
    db: Session,
    *,
    as_of: date,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    """
    Single package: balance sheet (as_of), P&L and USDT (BSC) treasury summary (period), trial balance (as_of),
    full CoA register (as_of), period activity, validation summary.
    """
    bs = generate_balance_sheet_payload(db, as_of)
    inc = generate_income_statement_payload(db, period_start, period_end)
    tb = generate_trial_balance_payload(db, as_of)
    cf = generate_cash_flow_payload(db, period_start, period_end)
    coa_reg = generate_chart_of_accounts_register_payload(db, as_of)
    period_act = generate_period_activity_payload(db, period_start, period_end)

    equity_highlights = {
        "net_income_for_period": inc["net_income"],
        "total_equity_per_balance_sheet": bs["total_equity"],
        "note": "Detailed statement of changes in equity requires opening balances and distribution accounts.",
    }

    summary = {
        "trial_balance_debits_equal_credits": tb["is_balanced"],
        "balance_sheet_equation_holds": bs["is_balanced"],
        "trial_balance_difference": round(tb["total_debits"] - tb["total_credits"], 2),
        "balance_sheet_equation_difference": bs["assets_minus_liabilities_and_equity"],
        "accounts_in_chart_of_accounts": len(coa_reg["accounts"]),
        "accounts_with_period_postings": len(period_act["lines"]),
    }

    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": generated_at,
        "as_of_date": as_of.isoformat(),
        "income_statement_period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "summary": summary,
        "balance_sheet": bs,
        "income_statement": inc,
        "trial_balance": tb,
        "cash_flow_statement": cf,
        "chart_of_accounts_register": coa_reg,
        "period_activity_by_account": period_act,
        "equity_highlights": equity_highlights,
    }
