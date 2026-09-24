"""MyHigh5 Leaders: 5% of a month's eligible company revenue shared by up to the top
10,000 members ranked by DIRECT (NEW_V2, level 1) commission earned in that month.

Workflow: DRAFT (prepare, re-preparable) -> APPROVED (different admin) -> POSTED (journal)
-> REVERSED (only while no reward has been paid). Posted history is never rewritten.

Revenue base (definition LEADERS_REVENUE_V1): sum of the website-revenue subledger
(revenue_recognitions, signed, so refunds net out) where the product's policy marks it
Leaders-eligible, recognized inside the calendar month (UTC).

Ranking eligibility (client-confirmed 2026-09-25, RANKING_DEFINITION): only PAID direct
commissions count. The authoritative paid state is AffiliateCommission.status == PAID,
which the payout service sets only after the provider confirms the transfer, together with
paid_date and the provider payout_reference. PENDING and APPROVED-but-unpaid never count.
The month a commission belongs to is still its transaction_date (unchanged).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import LeadersAllocationLine, LeadersPeriod, RevenueRecognition
from app.services.financial_integrity import money
from app.services.new_model_ledger import Line, PostingType, SourceType, find_entry, post_entry, reverse_entry
from app.services.new_model_reference_data import LEADERS_MAX_MEMBERS, LEADERS_POOL_RATE, NEW_MODEL_VERSION

REVENUE_DEFINITION = "LEADERS_REVENUE_V1"
RANKING_DEFINITION = "PAID_DIRECT_COMMISSION_ONLY"
_CENT = Decimal("0.01")


class LeadersError(ValueError):
    pass


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if not 1 <= int(month) <= 12:
        raise LeadersError("month must be 1-12")
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def eligible_company_revenue(db: Session, year: int, month: int) -> Decimal:
    start, end = month_bounds(year, month)
    total = (
        db.query(func.coalesce(func.sum(RevenueRecognition.website_revenue_amount), 0))
        .filter(
            RevenueRecognition.model_version == NEW_MODEL_VERSION,
            RevenueRecognition.leaders_revenue_eligible == True,  # noqa: E712
            RevenueRecognition.recognized_at >= start,
            RevenueRecognition.recognized_at < end,
        )
        .scalar()
    )
    return money(total or 0)


@dataclass(frozen=True)
class Ranked:
    user_id: int
    direct_commission: Decimal
    first_earned_at: datetime


def paid_direct_commission_filters():
    """Filters selecting commissions that may count toward the Leaders ranking."""
    return (
        AffiliateCommission.business_model_version == NEW_MODEL_VERSION,
        AffiliateCommission.level == 1,
        AffiliateCommission.status == CommissionStatus.PAID,
        AffiliateCommission.paid_date.isnot(None),
    )


def rank_members(db: Session, year: int, month: int, *, limit: int = LEADERS_MAX_MEMBERS) -> list[Ranked]:
    """PAID direct (level 1, NEW_V2) commission only. Ties: earlier first commission, then lower user id."""
    start, end = month_bounds(year, month)
    total = func.sum(AffiliateCommission.commission_amount)
    first = func.min(AffiliateCommission.transaction_date)
    rows = (
        db.query(AffiliateCommission.user_id, total.label("total"), first.label("first"))
        .filter(
            *paid_direct_commission_filters(),
            AffiliateCommission.transaction_date >= start,
            AffiliateCommission.transaction_date < end,
        )
        .group_by(AffiliateCommission.user_id)
        .having(total > 0)
        .order_by(total.desc(), first.asc(), AffiliateCommission.user_id.asc())
        .limit(limit)
        .all()
    )
    return [Ranked(int(r.user_id), money(r.total), r.first) for r in rows]


def allocate(pool: Decimal, ranked: list[Ranked]) -> list[tuple[Ranked, Decimal, Decimal]]:
    """(member, ratio, reward). Rewards are cut to the cent and sum exactly to the pool;
    the few undistributed cents go to rank 1. A zero pool or denominator yields zero rewards."""
    denominator = sum((r.direct_commission for r in ranked), Decimal("0"))
    if not ranked:
        return []
    if denominator <= 0 or pool <= 0:
        return [(r, Decimal("0"), Decimal("0.00")) for r in ranked]
    out = []
    for r in ranked:
        ratio = (r.direct_commission / denominator).quantize(Decimal("0.000000000001"))
        reward = (pool * r.direct_commission / denominator).quantize(_CENT, rounding=ROUND_DOWN)
        out.append([r, ratio, reward])
    remainder = pool - sum((x[2] for x in out), Decimal("0"))
    out[0][2] = out[0][2] + remainder
    return [tuple(x) for x in out]


def _live_period(db: Session, year: int, month: int) -> Optional[LeadersPeriod]:
    return (
        db.query(LeadersPeriod)
        .filter(
            LeadersPeriod.period_year == year,
            LeadersPeriod.period_month == month,
            LeadersPeriod.status.in_(("DRAFT", "APPROVED", "POSTED")),
        )
        .first()
    )


def preview(db: Session, year: int, month: int) -> dict:
    revenue = eligible_company_revenue(db, year, month)
    pool = money(revenue * LEADERS_POOL_RATE) if revenue > 0 else Decimal("0.00")
    ranked = rank_members(db, year, month)
    lines = allocate(pool, ranked)
    return {
        "period": f"{year:04d}-{month:02d}",
        "revenue_definition": REVENUE_DEFINITION,
        "ranking_definition": RANKING_DEFINITION,
        "eligible_company_revenue": revenue,
        "pool_rate": LEADERS_POOL_RATE,
        "pool_amount": pool,
        "max_members": LEADERS_MAX_MEMBERS,
        "qualifying_count": len(ranked),
        "total_qualifying_commission": money(sum((r.direct_commission for r in ranked), Decimal("0"))),
        "allocated_amount": money(sum((l[2] for l in lines), Decimal("0"))),
        "lines": [
            {"rank": i + 1, "user_id": r.user_id, "direct_commission": r.direct_commission, "ratio": ratio, "reward": reward}
            for i, (r, ratio, reward) in enumerate(lines)
        ],
    }


def prepare(db: Session, *, year: int, month: int, preparer_user_id: int, now: Optional[datetime] = None) -> LeadersPeriod:
    now = now or datetime.utcnow()
    _, end = month_bounds(year, month)
    if end > now:
        raise LeadersError("A Leaders month can only be prepared after the calendar month has ended")
    live = _live_period(db, year, month)
    if live is not None and live.status in ("APPROVED", "POSTED"):
        raise LeadersError(f"Period {year}-{month:02d} is already {live.status}")
    if live is not None:
        live.status = "SUPERSEDED"
        db.flush()
    data = preview(db, year, month)
    canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    period = LeadersPeriod(
        period_year=year, period_month=month, status="DRAFT", revenue_definition=REVENUE_DEFINITION,
        eligible_company_revenue=data["eligible_company_revenue"], pool_rate=data["pool_rate"],
        pool_amount=data["pool_amount"], max_members=data["max_members"], qualifying_count=data["qualifying_count"],
        total_qualifying_commission=data["total_qualifying_commission"], allocated_amount=data["allocated_amount"],
        snapshot_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(), prepared_by_user_id=preparer_user_id,
    )
    db.add(period)
    db.flush()
    for line in data["lines"]:
        db.add(LeadersAllocationLine(
            period_id=period.id, user_id=line["user_id"], rank=line["rank"],
            direct_commission_amount=line["direct_commission"], ratio=line["ratio"], reward_amount=line["reward"],
        ))
    db.flush()
    return period


def approve(db: Session, *, period_id: int, approver_user_id: int) -> LeadersPeriod:
    period = db.query(LeadersPeriod).filter(LeadersPeriod.id == period_id).with_for_update().one()
    if period.status != "DRAFT":
        raise LeadersError("Only a DRAFT period can be approved")
    if period.prepared_by_user_id is not None and int(period.prepared_by_user_id) == int(approver_user_id):
        raise LeadersError("Approver must differ from preparer (maker-checker)")
    period.status = "APPROVED"
    period.approved_by_user_id = approver_user_id
    db.flush()
    return period


def post(db: Session, *, period_id: int) -> LeadersPeriod:
    period = db.query(LeadersPeriod).filter(LeadersPeriod.id == period_id).with_for_update().one()
    if period.status == "POSTED":
        return period
    if period.status != "APPROVED":
        raise LeadersError("Only an APPROVED period can be posted")
    amount = money(period.allocated_amount)
    if amount > 0:
        _, end = month_bounds(period.period_year, period.period_month)
        entry = post_entry(
            db, source_type=SourceType.LEADERS_PERIOD, source_id=period.id, posting_type=PostingType.LEADERS_ALLOCATION,
            lines=[Line("5004", debit=amount, description="MyHigh5 Leaders monthly allocation"),
                   Line("2106", credit=amount, description="Leaders rewards payable (detail: leaders_allocation_lines)")],
            description=f"MyHigh5 Leaders {period.period_year}-{period.period_month:02d} allocation",
            entry_date=end,
        )
        period.journal_entry_id = entry.id
    period.status = "POSTED"
    period.posted_at = datetime.utcnow()
    db.flush()
    return period


def reverse(db: Session, *, period_id: int, reason: str) -> LeadersPeriod:
    """Audited correction path: allowed only while no reward of the period has been paid."""
    period = db.query(LeadersPeriod).filter(LeadersPeriod.id == period_id).with_for_update().one()
    if period.status != "POSTED":
        raise LeadersError("Only a POSTED period can be reversed")
    lines = db.query(LeadersAllocationLine).filter(LeadersAllocationLine.period_id == period.id).all()
    if any(l.payout_status == "PAID" for l in lines):
        raise LeadersError("Rewards already paid; use a next-period adjustment instead of reversing")
    if period.journal_entry_id is not None:
        original = find_entry(db, f"{NEW_MODEL_VERSION}:{SourceType.LEADERS_PERIOD}:{period.id}:{PostingType.LEADERS_ALLOCATION}")
        rev = reverse_entry(db, original, reason=reason)
        period.reversal_journal_entry_id = rev.id
    for l in lines:
        l.payout_status = "REVERSED"
    period.status = "REVERSED"
    period.notes = reason
    db.flush()
    return period


def record_external_payout(db: Session, *, line_id: int, reference: str) -> LeadersAllocationLine:
    """Record a reward paid outside the system (Dr 2106 / Cr 1001). Idempotent per line."""
    line = db.query(LeadersAllocationLine).filter(LeadersAllocationLine.id == line_id).with_for_update().one()
    period = db.query(LeadersPeriod).filter(LeadersPeriod.id == line.period_id).one()
    if period.status != "POSTED" or line.payout_status != "UNPAID" or money(line.reward_amount) <= 0:
        raise LeadersError("Only an unpaid reward of a POSTED period can be paid")
    post_entry(
        db, source_type=SourceType.LEADERS_PERIOD, source_id=period.id, posting_type="LEADERS_PAYOUT",
        key_suffix=f"line:{line.id}",
        lines=[Line("2106", debit=money(line.reward_amount), description=f"Leaders reward paid - User #{line.user_id}"),
               Line("1001", credit=money(line.reward_amount), description=f"Payout reference {reference}")],
        description=f"MyHigh5 Leaders reward payout line {line.id} ({reference})",
    )
    line.payout_status = "PAID"
    db.flush()
    return line
