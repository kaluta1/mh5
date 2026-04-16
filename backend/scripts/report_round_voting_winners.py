#!/usr/bin/env python3
"""
Report voting leaders and migration counts for one round (read-only).

Uses the same ranking rules as production migration:
  stars (sum of vote points) -> shares -> likes -> comments -> views -> lower contestant id.

Run from the backend directory so imports resolve and .env is picked up:

  cd backend
  python scripts/report_round_voting_winners.py --list-rounds
  python scripts/report_round_voting_winners.py --round-id 3
  python scripts/report_round_voting_winners.py --round-name "March 2026"

Requires DATABASE_URL / SQL config in environment (same as the API).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, Contestant, ContestantSeason, SeasonLevel
from app.models.round import Round, round_contests
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService


def _next_season_level(level: SeasonLevel) -> Optional[SeasonLevel]:
    order = [
        SeasonLevel.CITY,
        SeasonLevel.COUNTRY,
        SeasonLevel.REGIONAL,
        SeasonLevel.CONTINENT,
        SeasonLevel.GLOBAL,
    ]
    try:
        i = order.index(level)
    except ValueError:
        return None
    return order[i + 1] if i + 1 < len(order) else None


def _location_field_for_promotion_from(current: SeasonLevel) -> Optional[str]:
    """When promoting FROM ``current``, grouping field matches season_migration.promote_to_next_level."""
    m = {
        SeasonLevel.CITY: "city",
        SeasonLevel.COUNTRY: "country",
        SeasonLevel.REGIONAL: "region",
        SeasonLevel.CONTINENT: "continent",
        SeasonLevel.GLOBAL: None,
    }
    return m.get(current)


def _find_round(db: Session, round_id: Optional[int], name_substring: Optional[str]) -> Optional[Round]:
    if round_id is not None:
        return db.query(Round).filter(Round.id == round_id).first()
    if name_substring:
        like = f"%{name_substring.strip()}%"
        return (
            db.query(Round)
            .filter(Round.name.ilike(like))
            .order_by(Round.id.desc())
            .first()
        )
    return None


def _contests_for_round(db: Session, round_obj: Round) -> List[Contest]:
    q = (
        db.query(Contest)
        .join(round_contests, Contest.id == round_contests.c.contest_id)
        .filter(round_contests.c.round_id == round_obj.id)
        .order_by(Contest.id)
    )
    return q.all()


def _resolve_voting_season(db: Session, contest: Contest, round_obj: Round) -> Optional[ContestSeason]:
    link = (
        db.query(ContestSeasonLink)
        .join(ContestSeason)
        .filter(
            and_(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.is_active == True,
                ContestSeason.round_id == round_obj.id,
                ContestSeason.is_deleted == False,
            )
        )
        .first()
    )
    if link:
        return link.season

    preferred = SeasonLevel.COUNTRY if contest.contest_mode == "nomination" else SeasonLevel.CITY
    return (
        db.query(ContestSeason)
        .filter(
            and_(
                ContestSeason.round_id == round_obj.id,
                ContestSeason.level == preferred,
                ContestSeason.is_deleted == False,
            )
        )
        .first()
    )


def _vote_points(
    db: Session, season_id: int, contest_id: int, contestant_ids: List[int]
) -> Tuple[Dict[int, int], Dict[int, int]]:
    if not contestant_ids:
        return {}, {}
    q = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
            func.count(ContestantVoting.id).label("vote_rows"),
        )
        .filter(
            and_(
                ContestantVoting.season_id == season_id,
                ContestantVoting.contest_id == contest_id,
                ContestantVoting.contestant_id.in_(contestant_ids),
            )
        )
        .group_by(ContestantVoting.contestant_id)
    )
    rows = q.all()
    if not rows:
        q2 = (
            db.query(
                ContestantVoting.contestant_id,
                func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
                func.count(ContestantVoting.id).label("vote_rows"),
            )
            .filter(
                and_(
                    ContestantVoting.contest_id == contest_id,
                    ContestantVoting.contestant_id.in_(contestant_ids),
                )
            )
            .group_by(ContestantVoting.contestant_id)
        )
        rows = q2.all()
    points = {r.contestant_id: int(r.total_points or 0) for r in rows}
    votes = {r.contestant_id: int(r.vote_rows or 0) for r in rows}
    return points, votes


def _count_active_in_season_for_contest(db: Session, contest_id: int, season_id: int) -> int:
    return (
        db.query(ContestantSeason)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
            )
        )
        .count()
    )


def _print_contestant_line(
    c: Contestant,
    stars: int,
    shares: int,
    likes: int,
    comments: int,
    views: int,
    vote_rows: int,
    rank: int,
    prefix: str = "",
) -> None:
    title = (c.title or "").replace("\n", " ")[:60]
    print(
        f"{prefix}  {rank:>3}. id={c.id} user={c.user_id} stars={stars} votes_rows={vote_rows} "
        f"sh={shares} lk={likes} cm={comments} vw={views} "
        f"city={c.city!r} country={c.country!r} title={title!r}"
    )


def _global_ranking(
    db: Session, season: ContestSeason, contest_id: int, limit: Optional[int] = 25
) -> None:
    contestants = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
            )
        )
        .all()
    )
    ids = [c.id for c in contestants]
    points, vote_rows = _vote_points(db, season.id, contest_id, ids)
    eng = SeasonMigrationService._engagement_by_contestant(db, ids)
    ranked = sorted(
        contestants,
        key=lambda c: (
            points.get(c.id, 0),
            eng.get(c.id, {}).get("shares", 0),
            eng.get(c.id, {}).get("likes", 0),
            eng.get(c.id, {}).get("comments", 0),
            eng.get(c.id, {}).get("views", 0),
            -(c.id or 0),
        ),
        reverse=True,
    )
    print(f"    Global leaderboard (qualified flag ignored; same sort as migration) — showing top {limit or 'all'}:")
    for i, c in enumerate(ranked[:limit] if limit else ranked, start=1):
        e = eng.get(c.id, {})
        _print_contestant_line(
            c,
            points.get(c.id, 0),
            e.get("shares", 0),
            e.get("likes", 0),
            e.get("comments", 0),
            e.get("views", 0),
            vote_rows.get(c.id, 0),
            i,
            prefix="",
        )


def _location_winners(
    db: Session,
    season: ContestSeason,
    contest_id: int,
    location_field: str,
    limit_per_location: int = 5,
) -> None:
    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        location_field,
        contest_id=contest_id,
        limit=limit_per_location,
        diagnostics=False,
    )
    if not grouped:
        print(f"    No grouped leaders for field={location_field!r} (no qualified contestants with location?)")
        return
    print(f"    Leaders per {location_field} (top {limit_per_location} each; promotion preview):")
    for loc in sorted(grouped.keys(), key=lambda x: (str(x).lower(), str(x))):
        print(f"      --- {location_field}={loc!r} ({len(grouped[loc])} selected) ---")
        ids = [c.id for c in grouped[loc]]
        points, vote_rows = _vote_points(db, season.id, contest_id, ids)
        eng = SeasonMigrationService._engagement_by_contestant(db, ids)
        ranked = sorted(
            grouped[loc],
            key=lambda c: (
                points.get(c.id, 0),
                eng.get(c.id, {}).get("shares", 0),
                eng.get(c.id, {}).get("likes", 0),
                eng.get(c.id, {}).get("comments", 0),
                eng.get(c.id, {}).get("views", 0),
                -(c.id or 0),
            ),
            reverse=True,
        )
        for i, c in enumerate(ranked, start=1):
            e = eng.get(c.id, {})
            _print_contestant_line(
                c,
                points.get(c.id, 0),
                e.get("shares", 0),
                e.get("likes", 0),
                e.get("comments", 0),
                e.get("views", 0),
                vote_rows.get(c.id, 0),
                i,
                prefix="      ",
            )


def _global_top_for_continent_promotion(db: Session, season: ContestSeason, contest_id: int, limit: int = 3) -> None:
    """FROM continent season -> global uses overall top N (not per-location)."""
    contestants = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True,
            )
        )
        .all()
    )
    ids = [c.id for c in contestants]
    points, vote_rows = _vote_points(db, season.id, contest_id, ids)
    eng = SeasonMigrationService._engagement_by_contestant(db, ids)
    ranked = sorted(
        contestants,
        key=lambda c: (
            points.get(c.id, 0),
            eng.get(c.id, {}).get("shares", 0),
            eng.get(c.id, {}).get("likes", 0),
            eng.get(c.id, {}).get("comments", 0),
            eng.get(c.id, {}).get("views", 0),
            -(c.id or 0),
        ),
        reverse=True,
    )
    print(f"    Overall top {limit} (GLOBAL promotion preview from CONTINENT season):")
    for i, c in enumerate(ranked[:limit], start=1):
        e = eng.get(c.id, {})
        _print_contestant_line(
            c,
            points.get(c.id, 0),
            e.get("shares", 0),
            e.get("likes", 0),
            e.get("comments", 0),
            e.get("views", 0),
            vote_rows.get(c.id, 0),
            i,
            prefix="      ",
        )


def list_rounds(db: Session) -> None:
    rows = db.query(Round).order_by(Round.id.desc()).limit(40).all()
    print("Recent rounds (id, name, status, voting_open):")
    for r in rows:
        print(f"  {r.id:>5}  {r.name!r}  status={r.status.value if r.status else ''}  is_voting_open={r.is_voting_open}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Round voting / migration report (read-only)")
    ap.add_argument("--list-rounds", action="store_true", help="Print recent rounds and exit")
    ap.add_argument("--round-id", type=int, default=None)
    ap.add_argument("--round-name", type=str, default=None, help="Substring match, e.g. March 2026")
    ap.add_argument("--leaderboard-limit", type=int, default=20, help="Rows for global leaderboard per contest")
    ap.add_argument("--per-location-limit", type=int, default=5, help="Top N per city/country/etc.")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.list_rounds:
            list_rounds(db)
            return 0

        round_obj = _find_round(db, args.round_id, args.round_name)
        if not round_obj:
            print("Round not found. Use --list-rounds or fix --round-id / --round-name.", file=sys.stderr)
            return 1

        contests = _contests_for_round(db, round_obj)
        print(f"Round id={round_obj.id} name={round_obj.name!r}")
        print(f"  status={round_obj.status.value if round_obj.status else ''}  submission_open={round_obj.is_submission_open}  voting_open={round_obj.is_voting_open}")
        print(f"  Contests linked via round_contests: {len(contests)}")

        by_category: Dict[str, List[Contest]] = defaultdict(list)
        for c in contests:
            cat = c.category.name if c.category else "Uncategorized"
            by_category[cat].append(c)

        for cat in sorted(by_category.keys(), key=str.lower):
            print(f"\n=== Category: {cat} ===")
            for contest in by_category[cat]:
                season = _resolve_voting_season(db, contest, round_obj)
                print(f"\n  Contest id={contest.id} name={contest.name!r} mode={contest.contest_mode!r} level={contest.level!r}")
                if not season:
                    print("    [skip] No voting season found for this round (no active ContestSeasonLink and no CITY/COUNTRY season).")
                    continue

                n_current = _count_active_in_season_for_contest(db, contest.id, season.id)
                next_lvl = _next_season_level(season.level)
                next_season = None
                n_next = 0
                if next_lvl:
                    next_season = (
                        db.query(ContestSeason)
                        .filter(
                            and_(
                                ContestSeason.round_id == round_obj.id,
                                ContestSeason.level == next_lvl,
                                ContestSeason.is_deleted == False,
                            )
                        )
                        .first()
                    )
                    if next_season:
                        n_next = _count_active_in_season_for_contest(db, contest.id, next_season.id)

                print(
                    f"    Active voting season: id={season.id} level={season.level.value!r} "
                    f"contestants_active_in_season={n_current}"
                )
                if next_lvl:
                    print(
                        f"    Next step: level={next_lvl.value!r} season_id={next_season.id if next_season else '—'} "
                        f"migrated_active_contestants={n_next}"
                    )
                else:
                    print("    Next step: — (already at GLOBAL or unknown)")

                loc_field = _location_field_for_promotion_from(season.level)
                if season.level == SeasonLevel.GLOBAL:
                    print("    At GLOBAL; no further location-based promotion in this pipeline.")
                elif season.level == SeasonLevel.CONTINENT:
                    # CONTINENT -> GLOBAL: overall top 3 (same as promote_to_next_level), not per-continent.
                    _global_top_for_continent_promotion(db, season, contest.id, limit=3)
                elif loc_field:
                    _location_winners(db, season, contest.id, loc_field, limit_per_location=args.per_location_limit)

                _global_ranking(db, season, contest.id, limit=args.leaderboard_limit)

        print("\nDone.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
