#!/usr/bin/env python3
"""
Preview top qualifiers for NOMINATION contests in a round (read-only).

Uses the same selection rules as SeasonMigrationService.promote_to_next_level:
  - Non-global: get_top_contestants_by_location (points, then shares/likes/comments/views, then id)
  - Global: single ranked list over all qualified contestants in the source season

Does NOT write to the database or call promote_to_next_level.

Usage (from repo backend/):
  set PYTHONPATH=.
  python scripts/preview_nomination_winners_round.py --round-id 3
  python scripts/preview_nomination_winners_round.py --round-name "March"
  python scripts/preview_nomination_winners_round.py --round-id 3 --compact
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select

from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, Contestant, ContestantSeason, SeasonLevel
from app.models.round import Round, round_contests
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService


def _contestant_label(c: Contestant) -> str:
    if c.title:
        return c.title.strip()
    u = c.user
    if u is None:
        return f"contestant#{c.id}"
    return (u.full_name or u.username or u.email or f"user#{u.id}")[:80]


def _points_map(
    db,
    season_id: int,
    contestant_ids: List[int],
    contest_id: int,
) -> Dict[int, int]:
    if not contestant_ids:
        return {}
    q = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
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
    if rows:
        return {r.contestant_id: int(r.total_points or 0) for r in rows}
    # Legacy fallback (matches get_top_contestants_by_location)
    rows2 = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
        )
        .filter(
            and_(
                ContestantVoting.contest_id == contest_id,
                ContestantVoting.contestant_id.in_(contestant_ids),
            )
        )
        .group_by(ContestantVoting.contestant_id)
        .all()
    )
    return {r.contestant_id: int(r.total_points or 0) for r in rows2}


def _preview_global_top(
    db,
    *,
    season_id: int,
    contest_id: int,
    limit: int,
) -> List[Contestant]:
    """Match promote_to_next_level GLOBAL branch; filter contestants to this contest."""
    season_contestants = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True,
                Contestant.season_id == contest_id,
            )
        )
        .all()
    )
    ids = [c.id for c in season_contestants]
    if not ids:
        return []
    vote_rows = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
        )
        .filter(
            and_(
                ContestantVoting.season_id == season_id,
                ContestantVoting.contestant_id.in_(ids),
            )
        )
        .group_by(ContestantVoting.contestant_id)
        .all()
    )
    points_dict = {r.contestant_id: int(r.total_points or 0) for r in vote_rows}
    engagement = SeasonMigrationService._engagement_by_contestant(db, ids)
    ranked = sorted(
        season_contestants,
        key=lambda c: (
            points_dict.get(c.id, 0),
            engagement.get(c.id, {}).get("shares", 0),
            engagement.get(c.id, {}).get("likes", 0),
            engagement.get(c.id, {}).get("comments", 0),
            engagement.get(c.id, {}).get("views", 0),
            -(c.id or 0),
        ),
        reverse=True,
    )
    return ranked[:limit]


def _next_level(current: SeasonLevel) -> Optional[SeasonLevel]:
    order = [
        SeasonLevel.CITY,
        SeasonLevel.COUNTRY,
        SeasonLevel.REGIONAL,
        SeasonLevel.CONTINENT,
        SeasonLevel.GLOBAL,
    ]
    try:
        i = order.index(current)
    except ValueError:
        return None
    if i >= len(order) - 1:
        return None
    return order[i + 1]


def _location_field_for_promotion_to(to_level: SeasonLevel) -> Optional[str]:
    """Grouping field on SOURCE season (same map as promote_to_next_level)."""
    m = {
        SeasonLevel.COUNTRY: "city",
        SeasonLevel.REGIONAL: "country",
        SeasonLevel.CONTINENT: "region",
        SeasonLevel.GLOBAL: "continent",
    }
    return m.get(to_level)


def preview_next_migration(
    db,
    *,
    contest_id: int,
    season_id: int,
    current_level: SeasonLevel,
    limit: int,
) -> Tuple[Optional[SeasonLevel], Optional[str], Dict[str, List[Contestant]] | List[Contestant]]:
    nxt = _next_level(current_level)
    if nxt is None:
        return None, None, []
    if nxt == SeasonLevel.GLOBAL:
        winners = _preview_global_top(db, season_id=season_id, contest_id=contest_id, limit=limit)
        return nxt, "global_top", winners
    loc = _location_field_for_promotion_to(nxt)
    if not loc:
        return nxt, loc, {}
    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season_id,
        loc,
        contest_id=contest_id,
        limit=limit,
        stage_id=None,
        diagnostics=False,
    )
    return nxt, loc, grouped


def _run_one_nomination_preview(
    *,
    contest_id: int,
    round_id: int,
    limit: int,
    compact: bool,
) -> Tuple[int, int, int, List[str]]:
    """
    Returns (empty_inc, errors_inc, at_global_inc, lines) for one contest.
    Uses a fresh DB session (safe for thread pool workers).
    """
    from app.db.session import SessionLocal

    lines: List[str] = []
    empty_inc = 0
    errors_inc = 0
    at_global_inc = 0

    db = SessionLocal()
    try:
        c = db.query(Contest).filter(Contest.id == contest_id).first()
        if not c or c.contest_mode != "nomination":
            errors_inc = 1
            lines.append(f"[SKIP] contest_id={contest_id} — not found or not nomination")
            return empty_inc, errors_inc, at_global_inc, lines

        link = (
            db.query(ContestSeasonLink, ContestSeason)
            .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
            .filter(
                ContestSeasonLink.contest_id == c.id,
                ContestSeasonLink.is_active == True,
                ContestSeason.round_id == round_id,
            )
            .first()
        )
        if not link:
            errors_inc = 1
            lines.append(
                f"[SKIP] contest_id={c.id} {c.name!r} — no active ContestSeasonLink for this round"
            )
            return empty_inc, errors_inc, at_global_inc, lines

        _, season = link
        lvl = season.level

        if lvl == SeasonLevel.GLOBAL:
            at_global_inc = 1
            if compact:
                lines.append(
                    f"[GLOBAL] id={c.id} {c.name[:50]!r} season={season.id} (already at global)"
                )
            else:
                lines.append(
                    f"\n### contest_id={c.id} {c.name!r} — already at GLOBAL (season {season.id})"
                )
            return empty_inc, errors_inc, at_global_inc, lines

        nxt, loc_or_mode, payload = preview_next_migration(
            db,
            contest_id=c.id,
            season_id=season.id,
            current_level=lvl,
            limit=limit,
        )
        if nxt is None:
            errors_inc = 1
            lines.append(f"[SKIP] contest_id={c.id} — could not resolve next level from {lvl}")
            return empty_inc, errors_inc, at_global_inc, lines

        if isinstance(payload, dict):
            total_pick = sum(len(v) for v in payload.values())
            if total_pick == 0:
                empty_inc = 1
            if compact:
                lines.append(
                    f"id={c.id}\t{lvl.value}->{nxt.value}\tgroups={len(payload)}\t"
                    f"promoted={total_pick}\t{c.name[:45]!r}"
                )
                return empty_inc, errors_inc, at_global_inc, lines
            lines.append(
                f"\n### contest_id={c.id} {c.name!r}\n"
                f"    Active season: id={season.id} level={lvl.value}\n"
                f"    Next step if promoted now: -> {nxt.value} "
                f"(grouping field on contestants: {loc_or_mode})"
            )
            if not payload:
                lines.append(
                    "    (no qualified contestants with required location / no votes — empty preview)"
                )
                return empty_inc, errors_inc, at_global_inc, lines
            for group_key in sorted(payload.keys(), key=lambda x: (str(x) or "").lower()):
                winners = payload[group_key]
                lines.append(f"\n    --- {loc_or_mode}={group_key!r} — top {len(winners)} ---")
                ids = [x.id for x in winners]
                pts = _points_map(db, season.id, ids, c.id)
                eng = SeasonMigrationService._engagement_by_contestant(db, ids)
                for rank, ct in enumerate(winners, start=1):
                    lines.append(
                        f"       {rank}. id={ct.id} {_contestant_label(ct)!r} "
                        f"stars={pts.get(ct.id, 0)} "
                        f"sh={eng.get(ct.id, {}).get('shares', 0)} "
                        f"lk={eng.get(ct.id, {}).get('likes', 0)} "
                        f"cm={eng.get(ct.id, {}).get('comments', 0)} "
                        f"vw={eng.get(ct.id, {}).get('views', 0)}"
                    )
            return empty_inc, errors_inc, at_global_inc, lines

        winners = payload
        if compact:
            lines.append(
                f"id={c.id}\t{lvl.value}->{nxt.value}\tGLOBAL_LIST\t"
                f"promoted={len(winners)}\t{c.name[:45]!r}"
            )
            return empty_inc, errors_inc, at_global_inc, lines
        lines.append(
            f"\n### contest_id={c.id} {c.name!r}\n"
            f"    Active season: id={season.id} level={lvl.value}\n"
            f"    Next step: -> GLOBAL (single ranking, top {limit})"
        )
        if not winners:
            empty_inc = 1
            lines.append("    (empty — no qualified contestants)")
        else:
            ids = [x.id for x in winners]
            pts = _points_map(db, season.id, ids, c.id)
            eng = SeasonMigrationService._engagement_by_contestant(db, ids)
            for rank, ct in enumerate(winners, start=1):
                lines.append(
                    f"       {rank}. id={ct.id} {_contestant_label(ct)!r} "
                    f"stars={pts.get(ct.id, 0)} "
                    f"sh={eng.get(ct.id, {}).get('shares', 0)} "
                    f"lk={eng.get(ct.id, {}).get('likes', 0)}"
                )
        return empty_inc, errors_inc, at_global_inc, lines
    finally:
        db.close()


def resolve_round(db, round_id: Optional[int], round_name: Optional[str]) -> Round:
    if round_id is not None:
        r = db.query(Round).filter(Round.id == round_id).first()
        if not r:
            sys.exit(f"Round id={round_id} not found")
        return r
    if round_name:
        r = db.query(Round).filter(Round.name.ilike(f"%{round_name.strip()}%")).first()
        if not r:
            sys.exit(f"No round matching name {round_name!r}")
        return r
    sys.exit("Provide --round-id or --round-name")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview nomination migration winners (read-only)")
    parser.add_argument("--round-id", type=int, default=None)
    parser.add_argument("--round-name", type=str, default=None, help='e.g. "March"')
    parser.add_argument("--limit", type=int, default=5, help="Top N per group (default 5)")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="One line per contest (counts only)",
    )
    parser.add_argument(
        "--contest-id",
        type=int,
        default=None,
        help="Only this nomination contest id (for quick checks)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Parallel DB workers for multiple contests (default 6; use 1 to run sequentially)",
    )
    args = parser.parse_args()

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        rnd = resolve_round(db, args.round_id, args.round_name)
        contest_ids = [
            r[0]
            for r in db.execute(
                select(round_contests.c.contest_id).where(round_contests.c.round_id == rnd.id)
            ).fetchall()
        ]
        cq = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids))
            .filter(Contest.contest_mode == "nomination")
        )
        if args.contest_id is not None:
            cq = cq.filter(Contest.id == args.contest_id)
        contests = cq.order_by(Contest.id).all()

        print(f"Round: id={rnd.id} name={rnd.name!r}")
        print(
            "Nomination pipeline: COUNTRY -> REGIONAL -> CONTINENT -> GLOBAL "
            f"(top {args.limit} per geo bucket; global = top {args.limit} overall)"
        )
        print(f"Nomination contests in round: {len(contests)}")
        if len(contests) > 1:
            print(f"Parallel workers: {max(1, args.workers)}")
        print("-" * 80)

        empty = 0
        at_global = 0
        errors = 0
        ordered_lines: List[Tuple[int, List[str]]] = []
        ids_in_order = [c.id for c in contests]

        workers = max(1, args.workers)
        if len(contests) == 1:
            e, err, ag, ls = _run_one_nomination_preview(
                contest_id=ids_in_order[0],
                round_id=rnd.id,
                limit=args.limit,
                compact=args.compact,
            )
            empty += e
            errors += err
            at_global += ag
            for line in ls:
                print(line)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(
                        _run_one_nomination_preview,
                        contest_id=cid,
                        round_id=rnd.id,
                        limit=args.limit,
                        compact=args.compact,
                    ): cid
                    for cid in ids_in_order
                }
                for fut in as_completed(futs):
                    cid = futs[fut]
                    e, err, ag, ls = fut.result()
                    empty += e
                    errors += err
                    at_global += ag
                    ordered_lines.append((cid, ls))
            for cid, ls in sorted(ordered_lines, key=lambda x: x[0]):
                for line in ls:
                    print(line)

        print("-" * 80)
        print(
            f"Summary: contests={len(contests)} empty_preview~={empty} "
            f"at_global={at_global} missing_link_or_error~={errors}"
        )
        print("Note: Preview uses current DB votes on the active season only. "
              "After a real migration, the next stage starts fresh until new votes arrive.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
