"""Contest-entry attribution for advertising revenue sharing.

* Original submission type: decided ONCE per entry from verified evidence and stored immutably in
  adv_entry_origins. Evidence, in order:
    1. the Phase 5 entry-safety record (contest_entry_safety.entry_kind, written at submission);
    2. otherwise the contest's own mode (contest.contest_mode, the value create_contestant derives the
       type from) AND the entry's entry_type must agree.
  Anything else (no safety record and no contest link, or the two disagree - e.g. an older
  admin-created nomination whose entry_type kept the 'participation' default) is REVIEW: its
  revenue is held for an administrator, never guessed.
* Creative: ad_revenue_policy.contest_page_owner (a nomination pays only the confirmed nominee,
  never the nominator; unclaimed -> nobody yet).
* Direct sponsor at the earning event: snapshot of ad_revenue_policy.valid_direct_sponsor.
* Contest level: the entry's active season link at the earning event.

Nothing here posts money.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvEntryOrigin
from app.services import ad_revenue_policy as policy

RULE_VERSION = "CONTEST_PAGE_V1"          # personal 20% + sponsor 1%; nomination 10% + sponsor 1%
PERSONAL, NOMINATION = "PERSONAL_SUBMISSION", "NOMINATION"
_MODE_TO_KIND = {"participation": PERSONAL, "nomination": NOMINATION}


@dataclass(frozen=True)
class Attribution:
    contestant_id: int
    origin_kind: Optional[str]           # None while the origin is under review
    creative_user_id: Optional[int]
    sponsor_user_id: Optional[int]
    sponsor_status: str                  # VALID | NONE | INELIGIBLE | UNRESOLVED
    contest_level: Optional[str]
    season_id: Optional[int]
    rule_version: str = RULE_VERSION


def _evidence(db: Session, contestant) -> tuple[Optional[str], dict]:
    from app.models.contest import Contest
    from app.models.contest_eligibility import ContestEntrySafety

    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant.id).first()
    entry_type = (getattr(contestant, "entry_type", None) or "").strip().lower()
    mode = None
    if getattr(contestant, "contest_id", None):
        contest = db.query(Contest).filter(Contest.id == contestant.contest_id).first()
        mode = (getattr(contest, "contest_mode", None) or "").strip().lower() if contest else None
    evidence = {"safety_entry_kind": safety.entry_kind if safety else None, "contest_mode": mode,
                "entry_type": entry_type or None}
    if safety is not None and safety.entry_kind in (PERSONAL, NOMINATION):
        if mode in _MODE_TO_KIND and _MODE_TO_KIND[mode] != safety.entry_kind:
            evidence["conflict"] = "safety record and contest mode disagree"
            return None, evidence
        evidence["basis"] = "contest_entry_safety"
        return safety.entry_kind, evidence
    if mode in _MODE_TO_KIND and _MODE_TO_KIND.get(entry_type) == _MODE_TO_KIND[mode]:
        evidence["basis"] = "contest_mode+entry_type"
        return _MODE_TO_KIND[mode], evidence
    evidence["conflict"] = ("no contest link" if mode not in _MODE_TO_KIND
                            else "contest mode and entry_type disagree")
    return None, evidence


def origin_for(db: Session, contestant) -> AdvEntryOrigin:
    """The entry's stored origin, created on first use. A RESOLVED origin is never re-derived."""
    row = db.query(AdvEntryOrigin).filter(AdvEntryOrigin.contestant_id == contestant.id).first()
    if row is not None:
        return row
    kind, evidence = _evidence(db, contestant)
    row = AdvEntryOrigin(contestant_id=contestant.id, origin_kind=kind, status="RESOLVED" if kind else "REVIEW",
                         evidence=evidence, resolved_at=datetime.utcnow() if kind else None)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:                      # created concurrently: use the stored one
        row = db.query(AdvEntryOrigin).filter(AdvEntryOrigin.contestant_id == contestant.id).one()
    return row


def resolve_review(db: Session, *, contestant_id: int, origin_kind: str, actor_id: int, note: str) -> AdvEntryOrigin:
    """Administrator decision for an origin under review (once). Audited by the caller."""
    if origin_kind not in (PERSONAL, NOMINATION):
        raise ValueError("origin_kind must be PERSONAL_SUBMISSION or NOMINATION")
    if not (note or "").strip():
        raise ValueError("A note with the evidence is required")
    row = (db.query(AdvEntryOrigin).filter(AdvEntryOrigin.contestant_id == contestant_id)
           .with_for_update().first())
    if row is None or row.status != "REVIEW":
        raise ValueError("Only an origin under review can be resolved")
    row.origin_kind, row.status = origin_kind, "RESOLVED"
    row.resolved_by_user_id, row.resolved_at = actor_id, datetime.utcnow()
    row.evidence = {**(row.evidence or {}), "admin_note": note.strip()[:300]}
    db.flush()
    return row


def _level(db: Session, contestant_id: int) -> tuple[Optional[str], Optional[int]]:
    from app.models.contests import ContestantSeason, ContestSeason

    row = (db.query(ContestSeason.level, ContestSeason.id)
           .join(ContestantSeason, ContestantSeason.season_id == ContestSeason.id)
           .filter(ContestantSeason.contestant_id == contestant_id, ContestantSeason.is_active.is_(True))
           .order_by(ContestantSeason.id.desc()).first())
    if row is None:
        return None, None
    level = row[0].value if hasattr(row[0], "value") else (str(row[0]) if row[0] is not None else None)
    return level, int(row[1])


def _sponsor(db: Session, creative_user_id: Optional[int]) -> tuple[Optional[int], str]:
    from app.models.user import User

    if creative_user_id is None:
        return None, "UNRESOLVED"              # nominee account not linked yet: never invented
    user = db.query(User).filter(User.id == creative_user_id).first()
    if user is None or not user.sponsor_id:
        return None, "NONE"
    sponsor = policy.valid_direct_sponsor(db, creative_user_id)
    if sponsor is None:
        return int(user.sponsor_id), "INELIGIBLE"
    return int(sponsor.id), "VALID"


def attribute(db: Session, contestant) -> Attribution:
    """Snapshot for one earning event on this entry's page."""
    origin = origin_for(db, contestant)
    level, season_id = _level(db, contestant.id)
    if origin.status != "RESOLVED":
        return Attribution(contestant.id, None, None, None, "UNRESOLVED", level, season_id)
    page_class = policy.ContestPageClass.PERSONAL if origin.origin_kind == PERSONAL else policy.ContestPageClass.NOMINATION
    creative = policy.contest_page_owner(db, contestant, page_class)
    sponsor_id, sponsor_status = _sponsor(db, creative)
    return Attribution(contestant.id, origin.origin_kind, creative, sponsor_id, sponsor_status, level, season_id)


def creative_rate(origin_kind: Optional[str]):
    if origin_kind == PERSONAL:
        return policy.PERSONAL_OWNER_RATE
    if origin_kind == NOMINATION:
        return policy.NOMINATION_OWNER_RATE
    return None


# ---------------------------------------------------------------- administrator review of historical origins

def scan_origins(db: Session, *, limit: int = 500) -> dict:
    """Decide the stored origin of active entries that have none yet, from verified evidence only
    (same rule as at the first earning event). Entries without proof become REVIEW and stay held until an
    administrator resolves them. Never guesses, never changes a stored origin, posts no money."""
    from app.models.contests import Contestant

    rows = (db.query(Contestant)
            .outerjoin(AdvEntryOrigin, AdvEntryOrigin.contestant_id == Contestant.id)
            .filter(AdvEntryOrigin.id.is_(None), Contestant.is_active.is_(True), Contestant.is_deleted.is_(False))
            .order_by(Contestant.id.asc()).limit(max(1, min(int(limit), 2000))).all())
    counts = {"RESOLVED": 0, "REVIEW": 0}
    for contestant in rows:
        counts[origin_for(db, contestant).status] += 1
    remaining = (db.query(Contestant.id).outerjoin(AdvEntryOrigin, AdvEntryOrigin.contestant_id == Contestant.id)
                 .filter(AdvEntryOrigin.id.is_(None), Contestant.is_active.is_(True),
                         Contestant.is_deleted.is_(False)).count())
    return {"scanned": len(rows), "resolved_from_evidence": counts["RESOLVED"], "sent_to_review": counts["REVIEW"],
            "remaining_unscanned": int(remaining)}


def origin_overview(db: Session) -> dict:
    from sqlalchemy import func

    from app.models.contests import Contestant

    by_status = dict(db.query(AdvEntryOrigin.status, func.count(AdvEntryOrigin.id)).group_by(AdvEntryOrigin.status).all())
    by_kind = dict(db.query(AdvEntryOrigin.origin_kind, func.count(AdvEntryOrigin.id))
                   .filter(AdvEntryOrigin.status == "RESOLVED").group_by(AdvEntryOrigin.origin_kind).all())
    active = db.query(func.count(Contestant.id)).filter(Contestant.is_active.is_(True),
                                                         Contestant.is_deleted.is_(False)).scalar()
    unscanned = (db.query(Contestant.id).outerjoin(AdvEntryOrigin, AdvEntryOrigin.contestant_id == Contestant.id)
                 .filter(AdvEntryOrigin.id.is_(None), Contestant.is_active.is_(True),
                         Contestant.is_deleted.is_(False)).count())
    return {"active_entries": int(active or 0), "unscanned": int(unscanned),
            "resolved": int(by_status.get("RESOLVED", 0)), "under_review": int(by_status.get("REVIEW", 0)),
            "resolved_by_kind": {str(k): int(v) for k, v in by_kind.items()}}


def review_page(db: Session, *, skip: int = 0, limit: int = 50) -> list:
    """Entries under review with the facts an administrator needs to decide (no guess is offered)."""
    from app.models.contest import Contest
    from app.models.contests import Contestant

    rows = (db.query(AdvEntryOrigin, Contestant)
            .join(Contestant, Contestant.id == AdvEntryOrigin.contestant_id)
            .filter(AdvEntryOrigin.status == "REVIEW").order_by(AdvEntryOrigin.id.asc())
            .offset(max(0, skip)).limit(max(1, min(limit, 200))).all())
    out = []
    for origin, c in rows:
        contest = db.query(Contest).filter(Contest.id == c.contest_id).first() if c.contest_id else None
        out.append({"contestant_id": c.id, "title": c.title, "owner_user_id": c.user_id, "entry_type": c.entry_type,
                    "contest_id": c.contest_id, "contest_name": getattr(contest, "name", None) if contest else None,
                    "contest_mode": getattr(contest, "contest_mode", None) if contest else None,
                    "nominator_country": getattr(c, "nominator_country", None),
                    "registration_date": c.registration_date.isoformat() if c.registration_date else None,
                    "evidence": origin.evidence})
    return out
