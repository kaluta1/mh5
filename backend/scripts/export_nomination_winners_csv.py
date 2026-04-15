#!/usr/bin/env python3
"""
Export nomination contests: per-group rankings, stars + engagement, migration flags (CSV).

Read-only. Uses the same ordering as SeasonMigrationService (stars -> shares -> likes ->
comments -> views -> lower contestant id).

VPS usage (example):
  cd /path/to/mh5-1/backend
  source venv/bin/activate
  export PYTHONPATH=/path/to/mh5-1/backend
  # Ensure .env (or environment) points at the production DATABASE_URL
  python scripts/export_nomination_winners_csv.py --round-id 3 --output /tmp/nomination_round3.csv

  # Everyone in each country (e.g. 10) with metrics; migrates_next_stage=Y for top 5:
  python scripts/export_nomination_winners_csv.py --round-id 3 --output out.csv --full-group-ranks

  # Single contest:
  python scripts/export_nomination_winners_csv.py --round-id 3 --contest-id 4 --output beauty.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select

from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, Contestant, ContestantSeason, SeasonLevel
from app.models.round import Round, round_contests
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService

CSV_FIELDS = [
    "round_id",
    "round_name",
    "contest_id",
    "contest_name",
    "from_level",
    "to_level",
    "group_field",
    "group_value",
    "rank_in_group",
    "rank_overall_in_contest",
    "migrates_next_stage",
    "promotion_limit",
    "contestant_id",
    "contestant_title",
    "user_id",
    "full_name",
    "email",
    "city",
    "country",
    "region",
    "continent",
    "stars_points",
    "shares",
    "likes",
    "comments",
    "views",
]


def _points_map(db, season_id: int, contestant_ids: List[int], contest_id: int) -> Dict[int, int]:
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


def _overall_rank_map(db, season_id: int, contest_id: int) -> Dict[int, int]:
    """Single global ordering for all qualified contestants on this season (same key as migration)."""
    cts = (
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
    ids = [c.id for c in cts]
    if not ids:
        return {}
    pts = _points_map(db, season_id, ids, contest_id)
    eng = SeasonMigrationService._engagement_by_contestant(db, ids)
    ranked = sorted(
        cts,
        key=lambda c: (
            pts.get(c.id, 0),
            eng.get(c.id, {}).get("shares", 0),
            eng.get(c.id, {}).get("likes", 0),
            eng.get(c.id, {}).get("comments", 0),
            eng.get(c.id, {}).get("views", 0),
            -(c.id or 0),
        ),
        reverse=True,
    )
    return {c.id: i + 1 for i, c in enumerate(ranked)}


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
    m = {
        SeasonLevel.COUNTRY: "city",
        SeasonLevel.REGIONAL: "country",
        SeasonLevel.CONTINENT: "region",
        SeasonLevel.GLOBAL: "continent",
    }
    return m.get(to_level)


def _global_ranked_list(db, season_id: int, contest_id: int, limit: Optional[int]) -> List[Contestant]:
    cts = (
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
    ids = [c.id for c in cts]
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
        cts,
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
    if limit is None:
        return ranked
    return ranked[:limit]


def _export_rows_for_contest(
    db,
    *,
    rnd: Round,
    contest: Contest,
    promotion_limit: int,
    full_group_ranks: bool,
    omit_email: bool,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    link = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeasonLink.is_active == True,
            ContestSeason.round_id == rnd.id,
        )
        .first()
    )
    if not link:
        return rows
    _, season = link
    lvl = season.level
    nxt = _next_level(lvl)
    if nxt is None:
        return rows

    overall = _overall_rank_map(db, season.id, contest.id)

    if nxt == SeasonLevel.GLOBAL:
        lim = None if full_group_ranks else promotion_limit
        ranked = _global_ranked_list(db, season.id, contest.id, lim)
        ids = [c.id for c in ranked]
        pts = _points_map(db, season.id, ids, contest.id)
        eng = SeasonMigrationService._engagement_by_contestant(db, ids) if ids else {}
        for rank, ct in enumerate(ranked, start=1):
            u = ct.user
            email = "" if omit_email else (getattr(u, "email", None) or "" if u else "")
            full_name = (u.full_name or u.username or "") if u else ""
            e = eng.get(ct.id, {})
            rows.append(
                {
                    "round_id": rnd.id,
                    "round_name": rnd.name,
                    "contest_id": contest.id,
                    "contest_name": contest.name,
                    "from_level": lvl.value,
                    "to_level": nxt.value,
                    "group_field": "global",
                    "group_value": "",
                    "rank_in_group": rank,
                    "rank_overall_in_contest": overall.get(ct.id, ""),
                    "migrates_next_stage": "Y" if rank <= promotion_limit else "N",
                    "promotion_limit": promotion_limit,
                    "contestant_id": ct.id,
                    "contestant_title": (ct.title or "").replace("\n", " ")[:500],
                    "user_id": ct.user_id,
                    "full_name": full_name.replace("\n", " ")[:255],
                    "email": email.replace("\n", " ")[:255],
                    "city": ct.city or "",
                    "country": ct.country or "",
                    "region": ct.region or "",
                    "continent": ct.continent or "",
                    "stars_points": pts.get(ct.id, 0),
                    "shares": e.get("shares", 0),
                    "likes": e.get("likes", 0),
                    "comments": e.get("comments", 0),
                    "views": e.get("views", 0),
                }
            )
        return rows

    loc = _location_field_for_promotion_to(nxt)
    if not loc:
        return rows

    per_limit = None if full_group_ranks else promotion_limit
    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        loc,
        contest_id=contest.id,
        limit=per_limit,
        stage_id=None,
        diagnostics=False,
    )
    for group_value in sorted(grouped.keys(), key=lambda x: (str(x) or "").lower()):
        winners = grouped[group_value]
        ids = [c.id for c in winners]
        pts = _points_map(db, season.id, ids, contest.id)
        eng = SeasonMigrationService._engagement_by_contestant(db, ids) if ids else {}
        for rank, ct in enumerate(winners, start=1):
            u = ct.user
            email = "" if omit_email else (getattr(u, "email", None) or "" if u else "")
            full_name = (u.full_name or u.username or "") if u else ""
            e = eng.get(ct.id, {})
            rows.append(
                {
                    "round_id": rnd.id,
                    "round_name": rnd.name,
                    "contest_id": contest.id,
                    "contest_name": contest.name,
                    "from_level": lvl.value,
                    "to_level": nxt.value,
                    "group_field": loc,
                    "group_value": str(group_value) if group_value is not None else "",
                    "rank_in_group": rank,
                    "rank_overall_in_contest": overall.get(ct.id, ""),
                    "migrates_next_stage": "Y" if rank <= promotion_limit else "N",
                    "promotion_limit": promotion_limit,
                    "contestant_id": ct.id,
                    "contestant_title": (ct.title or "").replace("\n", " ")[:500],
                    "user_id": ct.user_id,
                    "full_name": full_name.replace("\n", " ")[:255],
                    "email": email.replace("\n", " ")[:255],
                    "city": ct.city or "",
                    "country": ct.country or "",
                    "region": ct.region or "",
                    "continent": ct.continent or "",
                    "stars_points": pts.get(ct.id, 0),
                    "shares": e.get("shares", 0),
                    "likes": e.get("likes", 0),
                    "comments": e.get("comments", 0),
                    "views": e.get("views", 0),
                }
            )
    return rows


def _worker(
    contest_id: int,
    round_id: int,
    promotion_limit: int,
    full_group_ranks: bool,
    omit_email: bool,
) -> Tuple[int, List[Dict[str, Any]]]:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        rnd = db.query(Round).filter(Round.id == round_id).first()
        if not rnd:
            return contest_id, []
        c = db.query(Contest).filter(Contest.id == contest_id).first()
        if not c or c.contest_mode != "nomination":
            return contest_id, []
        rows = _export_rows_for_contest(
            db,
            rnd=rnd,
            contest=c,
            promotion_limit=promotion_limit,
            full_group_ranks=full_group_ranks,
            omit_email=omit_email,
        )
        return contest_id, rows
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
    parser = argparse.ArgumentParser(description="CSV export: nomination migration preview (read-only)")
    parser.add_argument("--round-id", type=int, default=None)
    parser.add_argument("--round-name", type=str, default=None)
    parser.add_argument("--contest-id", type=int, default=None)
    parser.add_argument("--output", "-o", required=True, help="Output .csv path")
    parser.add_argument("--promotion-limit", type=int, default=5, help="Top N per group that would migrate")
    parser.add_argument(
        "--full-group-ranks",
        action="store_true",
        help="Export every contestant in each geo group (sorted), not only top N",
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--no-email", action="store_true", help="Blank the email column")
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
        ids_in_order = [c.id for c in contests]
    finally:
        db.close()

    all_rows: List[Dict[str, Any]] = []
    workers = max(1, args.workers)

    if len(ids_in_order) == 1:
        _, rs = _worker(
            ids_in_order[0],
            rnd.id,
            args.promotion_limit,
            args.full_group_ranks,
            args.no_email,
        )
        all_rows.extend(rs)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    _worker,
                    cid,
                    rnd.id,
                    args.promotion_limit,
                    args.full_group_ranks,
                    args.no_email,
                ): cid
                for cid in ids_in_order
            }
            by_cid: Dict[int, List[Dict[str, Any]]] = {}
            for fut in as_completed(futs):
                cid, rs = fut.result()
                by_cid[cid] = rs
        for cid in sorted(by_cid.keys()):
            all_rows.extend(by_cid[cid])

    # Stable sort: contest, group, rank
    def sort_key(r: Dict[str, Any]):
        return (
            int(r["contest_id"]),
            str(r.get("group_field") or ""),
            str(r.get("group_value") or ""),
            int(r.get("rank_in_group") or 0),
        )

    all_rows.sort(key=sort_key)

    out_fields = CSV_FIELDS.copy()
    if args.no_email:
        for r in all_rows:
            r["email"] = ""

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {args.output!r} (round_id={rnd.id}, contests={len(ids_in_order)})")


if __name__ == "__main__":
    main()
