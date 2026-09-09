"""Bounded, cycle-safe traversal for the canonical ``users.sponsor_id`` hierarchy."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.user import User


MAX_AFFILIATE_LEVELS = 10
MAX_CYCLE_CHECK_DEPTH = 100


class AffiliateHierarchyError(ValueError):
    pass


@dataclass(frozen=True)
class SponsorHop:
    user: User
    level: int
    eligible: bool


@dataclass(frozen=True)
class SponsorChain:
    hops: tuple[SponsorHop, ...]
    stopped_reason: str


def walk_sponsor_chain(
    db: Session,
    source_user_id: int,
    *,
    max_levels: int = MAX_AFFILIATE_LEVELS,
) -> SponsorChain:
    """Walk at most ten ancestors and terminate safely on malformed historical data."""
    bounded_levels = min(max(int(max_levels), 0), MAX_AFFILIATE_LEVELS)
    source = db.query(User).filter(User.id == source_user_id).first()
    if not source:
        return SponsorChain((), "source_missing")

    current_sponsor_id = source.sponsor_id
    visited = {int(source_user_id)}
    hops: list[SponsorHop] = []

    for level in range(1, bounded_levels + 1):
        if not current_sponsor_id:
            return SponsorChain(tuple(hops), "root")
        sponsor_id = int(current_sponsor_id)
        if sponsor_id in visited:
            return SponsorChain(tuple(hops), "cycle")
        visited.add(sponsor_id)

        sponsor = db.query(User).filter(User.id == sponsor_id).first()
        if not sponsor:
            return SponsorChain(tuple(hops), "missing_sponsor")

        eligible = sponsor.is_active is not False and sponsor.is_deleted is not True
        hops.append(SponsorHop(user=sponsor, level=level, eligible=eligible))
        current_sponsor_id = sponsor.sponsor_id

    return SponsorChain(tuple(hops), "max_levels")


def validate_sponsor_assignment(db: Session, *, user_id: int, sponsor_id: int) -> User:
    """Reject self-referral, reassignment, deleted sponsors, and descendant cycles."""
    if int(user_id) == int(sponsor_id):
        raise AffiliateHierarchyError("Self-referral is not allowed")

    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    sponsor = db.query(User).filter(User.id == sponsor_id).first()
    if not user or not sponsor:
        raise AffiliateHierarchyError("User or sponsor does not exist")
    if user.sponsor_id is not None and int(user.sponsor_id) != int(sponsor_id):
        raise AffiliateHierarchyError("Sponsor reassignment is not allowed")
    if not sponsor.is_active or sponsor.is_deleted:
        raise AffiliateHierarchyError("Sponsor is inactive")

    cursor: User | None = sponsor
    visited: set[int] = set()
    for _ in range(MAX_CYCLE_CHECK_DEPTH):
        if cursor.id == user_id:
            raise AffiliateHierarchyError("Sponsor assignment would create a referral cycle")
        if cursor.id in visited:
            raise AffiliateHierarchyError("Sponsor hierarchy already contains a cycle")
        visited.add(cursor.id)
        if not cursor.sponsor_id:
            return user
        cursor = db.query(User).filter(User.id == cursor.sponsor_id).first()
        if cursor is None:
            raise AffiliateHierarchyError("Sponsor hierarchy contains a missing parent")

    raise AffiliateHierarchyError("Sponsor hierarchy exceeds the safety depth")
