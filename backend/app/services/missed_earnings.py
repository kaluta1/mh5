"""Missed earnings: what a member without APPROVED KYC would have earned, kept by MyHigh5.

Accounting. The sale (or the advertising revenue) is already credited in full to its revenue account by
the existing flow; a commission or an ad share is a separate expense with a member liability (2001). A
missed earning has neither: no expense, no liability, no balance. So that the retained amounts are
classified apart and auditable, one balanced reclassification moves the amount WITHIN revenue, from the
source's revenue account to RETAINED_REVENUE_ACCOUNT: Dr <source revenue> / Cr 4030. Total revenue is
unchanged (never recognized twice). It is posted when the source revenue itself is recognized (for a
KYC fee: at recognition, not at payment, because the fee is deferred revenue until then).

A refund of the source reverses the reclassification (exact mirror) and marks the record REVERSED.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.missed_earning import (CATEGORY_AD_CREATIVE, CATEGORY_AD_SPONSOR, CATEGORY_REFERRAL,
                                       STATUS_RECORDED, STATUS_REVERSED, MissedEarning)
from app.services import kyc_eligibility
from app.services.financial_integrity import money

RETAINED_REVENUE_ACCOUNT = "4030"
RETAINED_REVENUE_NAME = "Revenue retained - earnings not payable (earner's KYC not approved)"
SOURCE_MISSED = "MISSED_EARNING"
POSTING_RETAINED = "KYC_RETAINED"

KYC_MESSAGE = ("Only KYC-verified members can earn commissions. These amounts were missed because your "
               "verification was not approved when the earning events occurred. Complete KYC to become "
               "eligible for future commissions.")


def find(db: Session, *, user_id: int, category: str, source_type: str, source_id: int) -> Optional[MissedEarning]:
    return (db.query(MissedEarning)
            .filter(MissedEarning.user_id == int(user_id), MissedEarning.category == category,
                    MissedEarning.source_type == source_type, MissedEarning.source_id == int(source_id)).first())


def record(db: Session, *, user_id: int, category: str, source_type: str, source_id: int, amount, kyc_status: str,
           source_product: Optional[str] = None, source_user_id: Optional[int] = None, rate=None, base_amount=None,
           contestant_id: Optional[int] = None, origin_kind: Optional[str] = None,
           revenue_account: Optional[str] = None, event_at: Optional[datetime] = None) -> MissedEarning:
    """Insert-or-get the one record of this (member, category, source event). Never commits."""
    existing = find(db, user_id=user_id, category=category, source_type=source_type, source_id=source_id)
    if existing is not None:
        return existing
    row = MissedEarning(user_id=int(user_id), category=category, source_type=source_type, source_id=int(source_id),
                        source_product=(source_product or None) and str(source_product)[:50],
                        source_user_id=source_user_id, contestant_id=contestant_id, origin_kind=origin_kind,
                        rate=rate, base_amount=base_amount, amount=money(amount), currency="USD",
                        kyc_status=str(kyc_status or kyc_eligibility.NO_VERIFICATION)[:30],
                        event_at=event_at or datetime.utcnow(), revenue_account=revenue_account,
                        status=STATUS_RECORDED)
    savepoint = db.begin_nested()
    try:
        db.add(row)
        db.flush()
    except IntegrityError:
        savepoint.rollback()                     # a concurrent worker recorded it first: use that one
        return find(db, user_id=user_id, category=category, source_type=source_type, source_id=source_id)
    savepoint.commit()
    return row


def post_retained(db: Session, row: MissedEarning, revenue_account: Optional[str] = None):
    """Classify the retained amount apart (Dr source revenue / Cr 4030), once. Never commits."""
    from app.services.new_model_ledger import Line, post_entry

    if row.status != STATUS_RECORDED:
        return None
    account = revenue_account or row.revenue_account
    if not account:
        return None
    entry = post_entry(
        db, source_type=SOURCE_MISSED, source_id=row.id, posting_type=POSTING_RETAINED,
        lines=[Line(account, debit=money(row.amount),
                    description=f"Reclassify: {row.category.lower()} not payable (KYC {row.kyc_status})"),
               Line(RETAINED_REVENUE_ACCOUNT, credit=money(row.amount),
                    description=f"Revenue retained - member #{row.user_id} KYC not approved")],
        description=f"Missed earning #{row.id} ({row.category}, {row.source_type} {row.source_id}) retained by MyHigh5",
    )
    row.revenue_account, row.journal_entry_id = account, entry.id
    return entry


def reverse(db: Session, row: MissedEarning, *, reason: str) -> None:
    """The source was refunded/reversed: mirror the reclassification (if posted) and close the record."""
    from app.models.accounting import JournalEntry
    from app.services.new_model_ledger import is_reversed, reverse_entry

    if row.status == STATUS_REVERSED:
        return
    if row.journal_entry_id:
        entry = db.query(JournalEntry).filter(JournalEntry.id == row.journal_entry_id).one()
        if not is_reversed(db, entry):
            reverse_entry(db, entry, reason=reason)
    row.status, row.reversed_at, row.reversal_reason = STATUS_REVERSED, datetime.utcnow(), (reason or "")[:300]
    db.flush()


def reverse_for_source(db: Session, *, source_type: str, source_id: int, reason: str) -> int:
    rows = (db.query(MissedEarning).filter(MissedEarning.source_type == source_type,
                                           MissedEarning.source_id == int(source_id),
                                           MissedEarning.status == STATUS_RECORDED).with_for_update().all())
    for row in rows:
        reverse(db, row, reason=reason)
    return len(rows)


# ---------------------------------------------------------------- reporting

_SOURCE_LABELS = {
    "KYC_VERIFICATION": "KYC verification fee", "REFERRAL_POOL_ENTRY": "Referral Pool unit",
    "MARKETPLACE_MARKUP": "Marketplace purchase", "MEMBERSHIP": "Membership", "PLATFORM_SUBSCRIPTION": "Subscription",
    "SERVICE_FEE": "Platform service", "ORDINARY": "MyHigh5 advertising", "ADSENSE": "Google AdSense",
}


def as_dict(row: MissedEarning) -> dict:
    return {"id": row.id, "category": row.category, "source": _SOURCE_LABELS.get(row.source_product or "",
                                                                                  row.source_product or row.source_type),
            "source_product": row.source_product, "contest_entry_id": row.contestant_id,
            "original_submission_type": row.origin_kind,
            "percentage": (str((Decimal(str(row.rate)) * 100).quantize(Decimal("0.01"))) if row.rate is not None
                           else None),
            "amount": str(money(row.amount)), "currency": row.currency, "kyc_status_at_event": row.kyc_status,
            "date": row.event_at.isoformat(), "status": row.status, "payable": False}


def _query(db: Session, user_id: int, categories: tuple):
    return db.query(MissedEarning).filter(MissedEarning.user_id == int(user_id),
                                          MissedEarning.category.in_(categories))


def totals(db: Session, user_id: int, categories: tuple) -> dict:
    out = {c: Decimal("0.00") for c in categories}
    for category, total in (_query(db, user_id, categories).filter(MissedEarning.status == STATUS_RECORDED)
                            .with_entities(MissedEarning.category, func.sum(MissedEarning.amount))
                            .group_by(MissedEarning.category).all()):
        out[category] = money(total or 0)
    return {k: str(v) for k, v in out.items()}


def member_page(db: Session, user_id: int, *, categories: tuple, skip: int = 0, limit: int = 20) -> dict:
    """The member's own missed earnings (never payable, never in a balance), newest first."""
    q = _query(db, user_id, categories)
    rows = q.order_by(MissedEarning.event_at.desc(), MissedEarning.id.desc()).offset(skip).limit(limit).all()
    total = sum((Decimal(v) for v in totals(db, user_id, categories).values()), Decimal("0.00"))
    return {"total": str(money(total)), "currency": "USD", "count": q.count(), "skip": skip, "limit": limit,
            "kyc_status": kyc_eligibility.kyc_status(db, user_id), "kyc_url": "/dashboard/kyc",
            "message": KYC_MESSAGE, "items": [as_dict(r) for r in rows]}


def referral_page(db: Session, user_id: int, *, skip: int = 0, limit: int = 20) -> dict:
    return member_page(db, user_id, categories=(CATEGORY_REFERRAL,), skip=skip, limit=limit)


def ad_totals(db: Session, user_id: int) -> dict:
    t = totals(db, user_id, (CATEGORY_AD_CREATIVE, CATEGORY_AD_SPONSOR))
    return {"creative": t[CATEGORY_AD_CREATIVE], "sponsor": t[CATEGORY_AD_SPONSOR]}


def admin_overview(db: Session, *, skip: int = 0, limit: int = 50) -> dict:
    """Finance view: totals per category and the latest records (member ids only)."""
    by_category = {c: {"count": 0, "amount": "0.00"} for c in (CATEGORY_REFERRAL, CATEGORY_AD_CREATIVE,
                                                                CATEGORY_AD_SPONSOR)}
    for category, n, total in (db.query(MissedEarning.category, func.count(MissedEarning.id), func.sum(MissedEarning.amount))
                               .filter(MissedEarning.status == STATUS_RECORDED).group_by(MissedEarning.category).all()):
        by_category[category] = {"count": int(n), "amount": str(money(total or 0))}
    rows = (db.query(MissedEarning).order_by(MissedEarning.id.desc()).offset(skip).limit(limit).all())
    return {"by_category": by_category, "retained_revenue_account": RETAINED_REVENUE_ACCOUNT,
            "items": [dict(as_dict(r), user_id=r.user_id, source_type=r.source_type, source_id=r.source_id,
                           journal_entry_id=r.journal_entry_id) for r in rows]}
