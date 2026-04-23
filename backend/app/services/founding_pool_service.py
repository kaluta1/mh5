"""
Month-end Founding Members pool: accrual in 2104 (during the month) -> allocated 2105 (reclass).

Prepare reads net (credits - debits) on 2104 from posted journals in the calendar month.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime
from decimal import Decimal, ROUND_HALF_DOWN, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import FoundingMember
from app.models.founding_pool import FoundingPoolSnapshot, FoundingPoolSnapshotLine
from app.services.accounting_service import accounting_service
from app.services import fmr_service
from app.services.financial_report_service import POSTED_STATUSES

Q2 = Decimal("0.01")


def month_datetime_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    last = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0)
    end = datetime(year, month, last, 23, 59, 59)
    return start, end


def net_change_account_2104_in_month(db: Session, year: int, month: int) -> Decimal:
    """Net credit to 2104 in period (posted journals only)."""
    acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == "2104").first()
    if not acc:
        return Decimal("0")
    start, end = month_datetime_bounds(year, month)
    total = (
        db.query(func.coalesce(func.sum(JournalLine.credit_amount - JournalLine.debit_amount), 0))
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalLine.account_id == acc.id)
        .filter(JournalEntry.entry_date >= start)
        .filter(JournalEntry.entry_date <= end)
        .filter(JournalEntry.status.in_(POSTED_STATUSES))
    ).scalar()
    return Decimal(str(total or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def _active_founding_members(db: Session) -> Tuple[List[FoundingMember], Dict[int, Decimal]]:
    members = (
        db.query(FoundingMember)
        .filter(FoundingMember.is_active == True)  # noqa: E712
        .all()
    )
    weights: Dict[int, Decimal] = {}
    for m in members:
        weights[int(m.user_id)] = Decimal(str(m.founding_membership_ratio or 0))
    return members, weights


def _pool_recipients_and_weights(
    db: Session,
) -> Tuple[List[int], Dict[int, Decimal], str]:
    """
    Prefer Founding Membership Ratio from FMP (FMR = user FMP / global FMP).
    Falls back to legacy founding_members.founding_membership_ratio when no FMP balances.
    """
    uids, fmp_weights = fmr_service.fmp_weights_for_pool(db)
    if uids and fmp_weights:
        s = sum(fmp_weights.values(), Decimal(0))
        if s > 0:
            return uids, fmp_weights, "fmp"
    members, legacy_weights = _active_founding_members(db)
    return [int(m.user_id) for m in members], legacy_weights, "legacy_ratio"


def split_pool_amount(total: Decimal, user_ids: List[int], weights: Dict[int, Decimal]) -> Dict[int, Decimal]:
    """Proportional to founding_membership_ratio; equal split if weights sum to zero."""
    total = total.quantize(Q2, rounding=ROUND_HALF_UP)
    if not user_ids:
        return {}
    u_sorted = sorted(user_ids)
    s = sum((weights.get(uid, Decimal(0)) for uid in u_sorted), Decimal(0))
    out: Dict[int, Decimal] = {}
    if s <= 0:
        n = len(u_sorted)
        if n == 0:
            return {}
        base = (total / Decimal(n)).quantize(Q2, rounding=ROUND_HALF_DOWN)
        running = Decimal(0)
        for i, uid in enumerate(u_sorted):
            if i == n - 1:
                out[uid] = (total - running).quantize(Q2, rounding=ROUND_HALF_UP)
            else:
                out[uid] = base
                running += base
        return out
    allocated = Decimal(0)
    for i, uid in enumerate(u_sorted):
        if i == len(u_sorted) - 1:
            out[uid] = (total - allocated).quantize(Q2, rounding=ROUND_HALF_UP)
        else:
            w = weights.get(uid, Decimal(0))
            share = (total * (w / s)).quantize(Q2, rounding=ROUND_HALF_DOWN)
            out[uid] = share
            allocated += share
    return out


def prepare_founding_pool_month(
    db: Session,
    *,
    year: int,
    month: int,
    user_id: int,
    notes: Optional[str] = None,
) -> FoundingPoolSnapshot:
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12")

    existing = (
        db.query(FoundingPoolSnapshot)
        .filter(
            FoundingPoolSnapshot.period_year == year,
            FoundingPoolSnapshot.period_month == month,
        )
        .first()
    )
    if existing and existing.status == "posted":
        raise ValueError(f"Period {year}-{month:02d} is already posted")
    if existing and existing.status == "approved":
        raise ValueError(f"Period {year}-{month:02d} is approved — post the snapshot or reverse the journal first")

    accrued = net_change_account_2104_in_month(db, year, month)
    user_ids, weights, _weight_mode = _pool_recipients_and_weights(db)
    if not user_ids:
        raise ValueError("No founding members / FMP holders to allocate")

    shares = split_pool_amount(accrued, user_ids, weights)

    if existing and existing.status == "draft":
        db.execute(delete(FoundingPoolSnapshotLine).where(FoundingPoolSnapshotLine.snapshot_id == existing.id))
        snap = existing
        snap.accrued_pool_amount = float(accrued)
        snap.member_count = len(user_ids)
        snap.prepared_by_user_id = user_id
        if notes is not None:
            snap.notes = notes
        snap.status = "draft"
    else:
        snap = FoundingPoolSnapshot(
            period_year=year,
            period_month=month,
            accrued_pool_amount=float(accrued),
            member_count=len(user_ids),
            status="draft",
            prepared_by_user_id=user_id,
            notes=notes,
        )
        db.add(snap)

    db.flush()

    total_w = sum((weights.get(uid, Decimal(0)) for uid in user_ids), Decimal(0))
    for uid in user_ids:
        w = weights.get(uid, Decimal(0))
        fmr = (w / total_w) if total_w > 0 else Decimal(0)
        db.add(
            FoundingPoolSnapshotLine(
                snapshot_id=snap.id,
                user_id=uid,
                share_amount=float(shares.get(uid, Decimal(0))),
                weight_ratio=float(fmr),
            )
        )
    db.commit()
    db.refresh(snap)
    return snap


def approve_founding_pool_snapshot(db: Session, snapshot_id: int, approver_user_id: int) -> FoundingPoolSnapshot:
    snap = db.query(FoundingPoolSnapshot).filter(FoundingPoolSnapshot.id == snapshot_id).first()
    if not snap:
        raise ValueError("Snapshot not found")
    if snap.status != "draft":
        raise ValueError("Only draft snapshots can be approved")
    if snap.prepared_by_user_id is not None and approver_user_id == snap.prepared_by_user_id:
        raise ValueError("Approver must differ from preparer (maker-checker)")
    snap.status = "approved"
    snap.approved_by_user_id = approver_user_id
    db.commit()
    db.refresh(snap)
    return snap


def post_founding_pool_snapshot(db: Session, snapshot_id: int) -> FoundingPoolSnapshot:
    snap = db.query(FoundingPoolSnapshot).filter(FoundingPoolSnapshot.id == snapshot_id).first()
    if not snap:
        raise ValueError("Snapshot not found")
    if snap.status != "approved":
        raise ValueError("Snapshot must be approved before posting")
    amt = Decimal(str(snap.accrued_pool_amount)).quantize(Q2)
    if amt <= 0:
        raise ValueError("Accrued pool amount is zero — nothing to post")
    if snap.journal_entry_id:
        raise ValueError("Snapshot already linked to a journal entry")

    year, month = snap.period_year, snap.period_month
    _, end = month_datetime_bounds(year, month)
    desc = f"Founding Members pool month-end {year}-{month:02d}: Dr 2104 / Cr 2105 (allocated {amt})"
    lines = [
        {
            "account_code": "2104",
            "debit": float(amt),
            "credit": 0.0,
            "description": "Reclass accrued pool to allocated member payables",
        },
        {
            "account_code": "2105",
            "debit": 0.0,
            "credit": float(amt),
            "description": "Founding Members allocated payable (detail: founding_pool_snapshot_lines)",
        },
    ]
    entry = accounting_service.create_journal_entry(db, description=desc, lines=lines, date=end)
    snap = db.query(FoundingPoolSnapshot).filter(FoundingPoolSnapshot.id == snapshot_id).first()
    if not snap:
        raise ValueError("Snapshot not found after journal post")
    snap.journal_entry_id = entry.id
    snap.status = "posted"
    db.commit()
    db.refresh(snap)
    return snap
