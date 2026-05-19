"""
One active contest per (category, contest_mode) — nomination vs participation pairs.

Product rule:
- Each category (category_id or contest_type slug) should have at most one
  active nomination contest and one active participation contest.
- Duplicates (e.g. two rows both contest_mode=nomination) break Nominate vs
  Participations tabs and regional vote category lists.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_contest_mode(mode: Any) -> str:
    if mode is None:
        return "participation"
    value = mode.value if hasattr(mode, "value") else mode
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return "participation"
    low = text.lower()
    if low in ("nomination", "nominate"):
        return "nomination"
    if low in ("participation", "participant", "participate"):
        return "participation"
    token = text.split(".")[-1].strip().lower()
    if token in {"nomination", "nominate"}:
        return "nomination"
    if token in {"participation", "participant", "participate"}:
        return "participation"
    if "nomination" in low and "participation" not in low:
        return "nomination"
    return "participation"


def category_scope_key(contest: Any) -> str:
    """Stable key for dedupe / audit (category_id preferred)."""
    cid = getattr(contest, "category_id", None)
    if cid:
        return f"cat:{int(cid)}"
    ctype = (getattr(contest, "contest_type", None) or "").strip().lower()
    return f"ty:{ctype or 'unknown'}"


def _level_rank_for_mode(contest: Any, mode: str) -> Tuple[int, int, int]:
    """Higher is better when picking canonical row among duplicates."""
    lv = (getattr(contest, "level", None) or "").strip().lower()
    want = "country" if mode == "nomination" else "city"
    level_match = 1 if lv == want else 0
    pc = int(getattr(contest, "participant_count", 0) or 0)
    cid = int(getattr(contest, "id", 0) or 0)
    return (level_match, pc, cid)


def dedupe_contests_one_per_category_mode(
    contests: List[Any],
    *,
    contest_mode_filter: Optional[str] = None,
) -> List[Any]:
    """
    When listing for Nominate or Participations tab, keep one contest per category per mode.
    If DB has two nomination rows for Gospel, keep the best canonical one and log a warning.
    """
    if not contests:
        return contests
    mode_filter = normalize_contest_mode(contest_mode_filter) if contest_mode_filter else None
    if mode_filter is None:
        return contests

    best: Dict[str, Any] = {}
    dropped: List[int] = []

    for c in contests:
        mode = normalize_contest_mode(getattr(c, "contest_mode", "participation"))
        if mode != mode_filter:
            continue
        key = f"{category_scope_key(c)}:{mode}"
        prev = best.get(key)
        if prev is None:
            best[key] = c
            continue
        if _level_rank_for_mode(c, mode) > _level_rank_for_mode(prev, mode):
            dropped.append(int(getattr(prev, "id", 0) or 0))
            best[key] = c
        else:
            dropped.append(int(getattr(c, "id", 0) or 0))

    if dropped:
        logger.warning(
            "Dropped duplicate contest rows for mode=%s (same category): ids=%s — "
            "run scripts/fix_contest_category_duplicates.py --apply",
            mode_filter,
            dropped,
        )
    return list(best.values())


def find_active_duplicate_groups(db, *, contest_id: Optional[int] = None) -> List[dict]:
    """Audit: groups with 2+ active contests sharing category scope + contest_mode."""
    from app.models.contest import Contest

    q = db.query(Contest).filter(
        Contest.is_deleted == False,
        Contest.is_active == True,
    )
    if contest_id is not None:
        q = q.filter(Contest.id == contest_id)

    rows = q.order_by(Contest.id.asc()).all()
    groups: Dict[str, List[Any]] = {}
    for c in rows:
        mode = normalize_contest_mode(c.contest_mode)
        key = f"{category_scope_key(c)}:{mode}"
        groups.setdefault(key, []).append(c)

    out = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        out.append(
            {
                "key": key,
                "mode": key.split(":")[-1],
                "category_scope": ":".join(key.split(":")[:-1]),
                "contest_ids": [c.id for c in members],
                "details": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "contest_mode": normalize_contest_mode(c.contest_mode),
                        "level": c.level,
                        "contest_type": c.contest_type,
                        "category_id": c.category_id,
                        "participant_count": getattr(c, "participant_count", 0),
                    }
                    for c in members
                ],
            }
        )
    return out


def suggest_participation_contestant_id(members: List[Any]) -> Optional[int]:
    """Which duplicate row should be participation (city / participate copy)."""
    for c in members:
        lv = (getattr(c, "level", None) or "").lower()
        desc = (getattr(c, "description", None) or "").lower()
        if lv == "city":
            return c.id
        if "participate" in desc and "city" in desc:
            return c.id
        if "in your city" in desc:
            return c.id
    if len(members) == 2:
        sorted_rows = sorted(
            members,
            key=lambda r: (
                int(getattr(r, "participant_count", 0) or 0),
                int(getattr(r, "id", 0) or 0),
            ),
        )
        return sorted_rows[0].id
    return None


def repair_category_mode_duplicates(db, *, apply: bool = False) -> List[dict]:
    """
    Fix pairs where both rows are nomination (or both participation).
    - Two nominations → lower-priority row → participation + city
    - Two participations → lower-priority row → nomination + country (rare)
    """
    from app.models.contest import Contest

    actions: List[dict] = []
    groups = find_active_duplicate_groups(db)

    for g in groups:
        mode = g["mode"]
        members = (
            db.query(Contest)
            .filter(Contest.id.in_(g["contest_ids"]))
            .all()
        )
        if len(members) < 2:
            continue

        if mode == "nomination":
            move_id = suggest_participation_contestant_id(members)
            if move_id is None:
                continue
            actions.append(
                {
                    "contest_id": move_id,
                    "set_contest_mode": "participation",
                    "set_level": "city",
                    "reason": "duplicate nomination for same category; city/participate copy",
                }
            )
        elif mode == "participation" and len(members) == 2:
            sorted_rows = sorted(
                members,
                key=lambda r: (
                    int(getattr(r, "participant_count", 0) or 0),
                    int(getattr(r, "id", 0) or 0),
                ),
            )
            move_id = sorted_rows[0].id
            actions.append(
                {
                    "contest_id": move_id,
                    "set_contest_mode": "nomination",
                    "set_level": "country",
                    "reason": "duplicate participation for same category",
                }
            )

    if apply:
        for act in actions:
            row = db.query(Contest).filter(Contest.id == act["contest_id"]).first()
            if not row:
                continue
            row.contest_mode = act["set_contest_mode"]
            row.level = act["set_level"]
            db.add(row)
        if actions:
            db.commit()

    return actions


def assert_unique_category_mode(
    db,
    *,
    category_id: Optional[int],
    contest_type: str,
    contest_mode: str,
    exclude_contest_id: Optional[int] = None,
) -> None:
    """Raise ValueError if another active contest exists for same category + mode."""
    from app.models.contest import Contest

    mode = normalize_contest_mode(contest_mode)
    q = db.query(Contest).filter(
        Contest.is_deleted == False,
        Contest.is_active == True,
    )
    if exclude_contest_id is not None:
        q = q.filter(Contest.id != exclude_contest_id)

    if category_id and category_id > 0:
        q = q.filter(Contest.category_id == category_id)
    else:
        q = q.filter(
            Contest.category_id.is_(None),
            Contest.contest_type == contest_type,
        )

    for existing in q.all():
        if normalize_contest_mode(existing.contest_mode) == mode:
            raise ValueError(
                f"An active {mode} contest already exists for this category "
                f"(contest id={existing.id}, name={existing.name!r}). "
                f"Use Participations tab for participation or edit the existing row."
            )
