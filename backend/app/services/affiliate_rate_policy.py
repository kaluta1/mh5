"""Direct-affiliate rate qualification: the ONE place for 20% / 40%, 10,000 and six months.

Client rule (Shafi Abeid, confirmed 2026-09-28):
  * Standard direct sponsor rate: 20%.
  * A member qualifies for a PERMANENT 40% when at least 10,000 of their DIRECT referrals
    complete KYC verification within six months of the member's original registration.
    Referrals completing KYC after that deadline do not count.
  * The 40% REPLACES the 20% (never added to it) and applies only to the revenue
    categories in ``DYNAMIC_RATE_REVENUE_CATEGORIES``. Every other category keeps its
    approved revenue-policy rate unchanged (see new_model_revenue / revenue_policies).

Counting (deterministic, from authoritative data only):
  * direct referral = users.sponsor_id == member, not the member themself, AND sponsor_source
    is PERSONAL_REFERRAL (validated personal code at registration) or JOIN_CODE (validated
    personal code via /affiliates/join, first assignment only). FAIL CLOSED: a NULL/empty
    source is never counted. It predates the provenance column (added 2026-09-23 without a
    backfill) and is ambiguous: from 2026-04-22 until 2026-09-10 the admin user-details
    endpoint silently persisted a fallback sponsor (the founding account "mlenzi123") on any
    unsponsored user it displayed, also fabricating affiliate_tree/affiliation rows, so no
    stored record can prove which NULL-source relationships came from a personal code.
    Referral Pool assignments never count: REFERRAL_POOL rows are excluded by source, and any
    user with a referral_pool_assignments row is excluded whatever its current source.
    Indirect referrals are never walked.
  * KYC verified = the referral's kyc_verifications row is APPROVED and its processed_at
    (the approval time) is inside the window. Paying for KYC, or the partial
    identity-only step, is not verification. An admin identity override without an
    approved KYC record does not count.
  * the sponsor relationship must also exist by the deadline
    (sponsor_assigned_at, or the referral's registration when it was not stamped).

Window: [member.created_at, member.created_at + 6 calendar months], deadline inclusive.
Calendar months follow the application's convention (contest_context.add_months: the
same day-of-month, clamped to the month's last day), keeping the time of day.

Permanence: the first time the rule is met, an affiliate_rate_qualifications row is written
(once; never updated or deleted by the application). From then on the member's rate is 40%
whatever happens to the underlying referrals. Nothing is backfilled or applied retroactively.

Safety: qualification never changes age, guardian, messaging, delivery or financial
eligibility state. It is a rate lookup only; payouts stay gated by financial_eligibility.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_model import AffiliateRateQualification, ReferralPoolAssignment
from app.models.kyc import KYCStatus, KYCVerification
from app.models.user import User
from app.services.contest_context import add_months

logger = logging.getLogger(__name__)

RULE_VERSION = "DIRECT_40_AFTER_10K_KYC_IN_6M_V1"
STANDARD_DIRECT_RATE = Decimal("0.20")
QUALIFIED_DIRECT_RATE = Decimal("0.40")
QUALIFICATION_DIRECT_REFERRALS = 10000
QUALIFICATION_WINDOW_MONTHS = 6

AD_SLOT_PURCHASE = "AD_SLOT_PURCHASE"
# Only these revenue categories use the dynamic 20%/40% rate. Everything else is unchanged.
DYNAMIC_RATE_REVENUE_CATEGORIES = frozenset({AD_SLOT_PURCHASE})

# The only sponsor provenance that proves a DIRECT/personal referral (NULL/empty never counts).
_DIRECT_SOURCES = ("PERSONAL_REFERRAL", "JOIN_CODE")


@dataclass(frozen=True)
class DirectRateStatus:
    user_id: int
    rate: Decimal
    permanently_qualified: bool
    qualified_at: Optional[datetime]
    qualifying_referral_count: int
    required_referral_count: int
    window_start: datetime
    window_deadline: datetime


def add_calendar_months(value: datetime, months: int) -> datetime:
    d = add_months(value.date(), months)
    return value.replace(year=d.year, month=d.month, day=d.day)


def qualification_window(member: User) -> tuple[datetime, datetime]:
    start = member.created_at
    return start, add_calendar_months(start, QUALIFICATION_WINDOW_MONTHS)


def _qualifying_times(db: Session, member: User, deadline: datetime) -> list[datetime]:
    """Per qualifying direct referral: the moment it satisfied every condition (sorted)."""
    pool_assigned = db.query(ReferralPoolAssignment.referred_user_id)
    rows = (
        db.query(User.created_at, User.sponsor_assigned_at, KYCVerification.processed_at)
        .join(KYCVerification, KYCVerification.user_id == User.id)
        .filter(
            User.sponsor_id == member.id,
            User.id != member.id,
            User.sponsor_source.in_(_DIRECT_SOURCES),
            ~User.id.in_(pool_assigned),
            KYCVerification.status == KYCStatus.APPROVED,
            KYCVerification.processed_at.isnot(None),
            KYCVerification.processed_at <= deadline,
        )
        .all()
    )
    times = []
    for created_at, assigned_at, kyc_at in rows:
        attached_at = assigned_at or created_at
        if attached_at is None or attached_at > deadline:
            continue
        times.append(max(attached_at, kyc_at))
    times.sort()
    return times


def _record(db: Session, member_id: int) -> Optional[AffiliateRateQualification]:
    return db.query(AffiliateRateQualification).filter(AffiliateRateQualification.user_id == member_id).first()


def _status_from_record(member: User, row: AffiliateRateQualification) -> DirectRateStatus:
    return DirectRateStatus(
        user_id=member.id, rate=Decimal(str(row.qualified_rate)), permanently_qualified=True,
        qualified_at=row.qualified_at, qualifying_referral_count=int(row.qualifying_referral_count),
        required_referral_count=int(row.required_referral_count),
        window_start=row.window_start, window_deadline=row.window_deadline,
    )


def evaluate(db: Session, member: User, *, record: bool = True) -> DirectRateStatus:
    """Current qualification status. With ``record`` the first qualification is persisted.

    Never commits; the caller's transaction owns the write.
    """
    existing = _record(db, member.id)
    if existing is not None:
        return _status_from_record(member, existing)

    start, deadline = qualification_window(member)
    times = _qualifying_times(db, member, deadline)
    count = len(times)
    qualified_at = times[QUALIFICATION_DIRECT_REFERRALS - 1] if count >= QUALIFICATION_DIRECT_REFERRALS else None
    if qualified_at is None:
        return DirectRateStatus(
            user_id=member.id, rate=STANDARD_DIRECT_RATE, permanently_qualified=False, qualified_at=None,
            qualifying_referral_count=count, required_referral_count=QUALIFICATION_DIRECT_REFERRALS,
            window_start=start, window_deadline=deadline,
        )

    row = AffiliateRateQualification(
        user_id=member.id, rule_version=RULE_VERSION, qualified_rate=QUALIFIED_DIRECT_RATE,
        qualified_at=qualified_at, window_start=start, window_deadline=deadline,
        qualifying_referral_count=count, required_referral_count=QUALIFICATION_DIRECT_REFERRALS,
    )
    if record:
        savepoint = db.begin_nested()
        try:
            db.add(row)
            db.flush()
            savepoint.commit()
            logger.info("Member %s permanently qualified for the %s direct rate", member.id, QUALIFIED_DIRECT_RATE)
        except IntegrityError:
            savepoint.rollback()  # a concurrent evaluation recorded it first
            concurrent = _record(db, member.id)
            if concurrent is not None:
                return _status_from_record(member, concurrent)
            raise
    return _status_from_record(member, row)


def direct_rate_for_category(db: Session, sponsor: User, revenue_category: str) -> Optional[Decimal]:
    """The dynamic direct rate for a category that uses it; None = use the approved revenue policy."""
    if revenue_category not in DYNAMIC_RATE_REVENUE_CATEGORIES:
        return None
    return evaluate(db, sponsor).rate


def record_for_sponsor_of(db: Session, referral_user_id: int) -> None:
    """Hook after a referral's KYC approval: persist the sponsor's qualification the moment it is met.

    Best effort and isolated: it can never break or roll back the KYC approval itself.
    """
    try:
        referral = db.query(User).filter(User.id == referral_user_id).first()
        if referral is None or not referral.sponsor_id:
            return
        sponsor = db.query(User).filter(User.id == referral.sponsor_id).first()
        if sponsor is None or sponsor.id == referral.id:
            return
        with db.begin_nested():
            evaluate(db, sponsor, record=True)
    except Exception:  # noqa: BLE001 - qualification must never block KYC
        logger.exception("Affiliate rate qualification check failed for sponsor of user %s", referral_user_id)


def qualifying_referral_count(db: Session, member: User) -> int:
    _start, deadline = qualification_window(member)
    return len(_qualifying_times(db, member, deadline))


__all__ = [
    "AD_SLOT_PURCHASE", "DYNAMIC_RATE_REVENUE_CATEGORIES", "DirectRateStatus", "QUALIFICATION_DIRECT_REFERRALS",
    "QUALIFICATION_WINDOW_MONTHS", "QUALIFIED_DIRECT_RATE", "RULE_VERSION", "STANDARD_DIRECT_RATE",
    "add_calendar_months", "direct_rate_for_category", "evaluate", "qualification_window",
    "qualifying_referral_count", "record_for_sponsor_of",
]
