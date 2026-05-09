"""
Deactivate overlapping COUNTRY memberships when the same contestant is also active
in REGIONAL for the same nomination contest.

Default mode is dry-run (no DB writes).

Examples:
  python scripts/cleanup_country_regional_overlap.py --contest-id 17
  python scripts/cleanup_country_regional_overlap.py --contest-id 17 --apply
  python scripts/cleanup_country_regional_overlap.py --all-nomination
  python scripts/cleanup_country_regional_overlap.py --all-nomination --apply
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Set, Tuple

from sqlalchemy import and_

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, ContestantSeason, SeasonLevel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deactivate country memberships that overlap with regional memberships."
    )
    parser.add_argument("--contest-id", type=int, help="Single contest id to process")
    parser.add_argument(
        "--all-nomination",
        action="store_true",
        help="Process all nomination contests",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. If omitted, script runs in dry-run mode.",
    )
    return parser.parse_args()


def nomination_contest_ids(db, contest_id: int | None, all_nomination: bool) -> List[int]:
    if contest_id is not None:
        c = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
        if not c:
            raise ValueError(f"Contest {contest_id} not found")
        mode = str(getattr(c, "contest_mode", "") or "").split(".")[-1].strip().lower()
        if mode != "nomination":
            raise ValueError(f"Contest {contest_id} is not nomination mode")
        return [contest_id]

    if not all_nomination:
        raise ValueError("Pass --contest-id <id> or --all-nomination")

    rows = (
        db.query(Contest.id)
        .filter(Contest.is_deleted == False)
        .filter(Contest.contest_mode == "nomination")
        .order_by(Contest.id.asc())
        .all()
    )
    return [r[0] for r in rows]


def active_seasons_by_level(db, contest_id: int) -> Tuple[Set[int], Set[int]]:
    pairs = (
        db.query(ContestSeason.id, ContestSeason.level)
        .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True,
            ContestSeason.is_deleted == False,
            ContestSeason.level.in_([SeasonLevel.COUNTRY, SeasonLevel.REGIONAL]),
        )
        .all()
    )
    country_ids: Set[int] = set()
    regional_ids: Set[int] = set()
    for sid, lvl in pairs:
        level_str = str(lvl.value if hasattr(lvl, "value") else lvl).lower()
        if level_str == "country":
            country_ids.add(int(sid))
        elif level_str in ("regional", "region"):
            regional_ids.add(int(sid))
    return country_ids, regional_ids


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        contest_ids = nomination_contest_ids(db, args.contest_id, args.all_nomination)
        total_links_to_deactivate = 0
        contest_summaries: Dict[int, int] = {}

        for cid in contest_ids:
            country_season_ids, regional_season_ids = active_seasons_by_level(db, cid)
            if not country_season_ids or not regional_season_ids:
                continue

            regional_contestant_rows = (
                db.query(ContestantSeason.contestant_id)
                .filter(
                    ContestantSeason.season_id.in_(regional_season_ids),
                    ContestantSeason.is_active == True,
                )
                .distinct()
                .all()
            )
            regional_contestant_ids = {int(r[0]) for r in regional_contestant_rows}
            if not regional_contestant_ids:
                continue

            country_links = (
                db.query(ContestantSeason)
                .filter(
                    and_(
                        ContestantSeason.season_id.in_(country_season_ids),
                        ContestantSeason.is_active == True,
                        ContestantSeason.contestant_id.in_(regional_contestant_ids),
                    )
                )
                .all()
            )
            if not country_links:
                continue

            contest_summaries[cid] = len(country_links)
            total_links_to_deactivate += len(country_links)

            print(
                f"[contest {cid}] overlapping active country links: {len(country_links)} "
                f"(country seasons={sorted(country_season_ids)}, regional seasons={sorted(regional_season_ids)})"
            )
            for link in country_links:
                print(
                    f"  - contestant_id={link.contestant_id}, "
                    f"country_season_id={link.season_id}, is_active={link.is_active}"
                )
                if args.apply:
                    link.is_active = False

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"\n[{mode}] contests touched: {len(contest_summaries)}")
        print(f"[{mode}] country links to deactivate: {total_links_to_deactivate}")

        if args.apply:
            db.commit()
            print("[APPLY] committed successfully.")
        else:
            db.rollback()
            print("[DRY-RUN] no changes committed.")

        return 0
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

