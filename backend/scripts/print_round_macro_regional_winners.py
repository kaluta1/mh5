#!/usr/bin/env python3
"""
For each nomination contest linked to the round (= each category):

  • top_per_country — top N nominees per country (same rules as migration / Top High5).
  • macro_regions — same winners grouped under macro blocs (REGIONAL_VOTING_POOLS:
    east/west/north/central/southern Africa). Keys are always present; buckets may be [].

Uses the COUNTRY season only — no REGIONAL ContestSeasonLink needed.

Example:
  PYTHONPATH=. python scripts/print_round_macro_regional_winners.py \\
    --round-name-contains March -o ~/march_macro_regions.json

  PYTHONPATH=. python scripts/print_round_macro_regional_winners.py \\
    --round-id 3 --limit 10 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import and_, func, select

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, SeasonLevel
from app.models.round import Round, round_contests
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService

MACRO_REGION_LABELS: Dict[str, str] = {
    "east_africa": "East Africa",
    "west_africa": "West Africa",
    "southern_africa": "Southern Africa",
    "north_africa": "North Africa",
    "central_africa": "Central Africa",
}
MACRO_ORDER: Tuple[str, ...] = tuple(MACRO_REGION_LABELS.keys()) + ("_outside_pools",)


def _empty_macro_regions() -> Dict[str, List[Any]]:
    return {pid: [] for pid in MACRO_ORDER}


def _resolve_round(
    db,
    round_id: int | None,
    round_name: str | None,
    round_name_contains: str | None,
) -> Round:
    if round_id is not None:
        rnd = db.query(Round).filter(Round.id == round_id).first()
    elif round_name_contains:
        pat = round_name_contains.strip().lower()
        if not pat:
            raise SystemExit("--round-name-contains is empty")
        rnd = (
            db.query(Round)
            .filter(func.lower(Round.name).contains(pat))
            .order_by(Round.id.desc())
            .first()
        )
    elif round_name:
        rnd = db.query(Round).filter(Round.name == round_name).first()
    else:
        raise SystemExit("Provide --round-id or --round-name or --round-name-contains")
    if not rnd:
        raise SystemExit("Round not found")
    return rnd


def _contest_ids_for_round(db, round_id: int) -> List[int]:
    rows = db.execute(
        select(round_contests.c.contest_id).where(round_contests.c.round_id == round_id)
    ).fetchall()
    return [row[0] for row in rows]


def _country_season_row(
    db, contest_id: int, round_id: int
) -> Optional[Tuple[ContestSeasonLink, ContestSeason]]:
    q = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeason.round_id == round_id,
            ContestSeason.level == SeasonLevel.COUNTRY,
            ContestSeason.is_deleted == False,
        )
        .order_by(ContestSeasonLink.is_active.desc(), ContestSeasonLink.linked_at.desc())
    )
    return q.first()


def _points_by_contestant(
    db, season_id: int, contest_id: int, contestant_ids: List[int]
) -> Dict[int, int]:
    if not contestant_ids:
        return {}
    rows = (
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
        .all()
    )
    return {r.contestant_id: int(r.total_points or 0) for r in rows}


def _pool_for_country_label(country_key: Optional[str]) -> str:
    """Macro pool id or _outside_pools."""
    if not country_key:
        return "_outside_pools"
    pid = SeasonMigrationService.regional_pool_id_for_raw_country(country_key)
    if pid:
        return pid
    return "_outside_pools"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="March-round style export: Top-N per country, folded into macro African regional pools.",
    )
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument("--round-name-contains")
    parser.add_argument("--limit", type=int, default=5, help="Top N per country (default 5)")
    parser.add_argument("--contest-id", type=int)
    parser.add_argument(
        "--contest-name",
        help="Contest name substring (case-insensitive); must match exactly one nomination contest.",
    )
    parser.add_argument(
        "--active-links-only",
        action="store_true",
        help="Restrict ContestantSeason to active rows",
    )
    parser.add_argument(
        "--east-africa-only",
        action="store_true",
        help="Only include east_africa pool (drops other macro regions)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output", metavar="PATH", help="Write JSON to this UTF-8 path")

    args = parser.parse_args()

    if args.contest_id is not None and args.contest_name:
        raise SystemExit("Use either --contest-id or --contest-name, not both.")

    flags = sum(1 for x in (args.round_id, args.round_name, args.round_name_contains) if x)
    if flags > 1:
        raise SystemExit("Use only one of: --round-id, --round-name, --round-name-contains")

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name, args.round_name_contains)
        contest_ids = _contest_ids_for_round(db, rnd.id)

        if args.contest_id is not None:
            if args.contest_id not in contest_ids:
                raise SystemExit(f"Contest {args.contest_id} is not linked to round {rnd.id}")
            contest_ids = [args.contest_id]
        elif args.contest_name:
            pat = args.contest_name.strip().lower()
            if not pat:
                raise SystemExit("--contest-name is empty")
            rows_nm = (
                db.query(Contest.id, Contest.name)
                .filter(
                    Contest.id.in_(contest_ids or [-1]),
                    Contest.contest_mode == "nomination",
                    Contest.is_deleted == False,
                    func.lower(Contest.name).contains(pat),
                )
                .all()
            )
            if len(rows_nm) == 0:
                raise SystemExit(
                    f"No nomination contest on round {rnd.id} matches name substring {pat!r}"
                )
            if len(rows_nm) > 1:
                labs = [(r.id, r.name) for r in rows_nm[:12]]
                extra = f" (+{len(rows_nm) - 12} more)" if len(rows_nm) > 12 else ""
                raise SystemExit(
                    f"Multiple contests match {pat!r}: {labs}{extra}. Use --contest-id."
                )
            contest_ids = [rows_nm[0].id]

        contests = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids or [-1]))
            .filter(Contest.contest_mode == "nomination")
            .order_by(Contest.id.asc())
            .all()
        )

        payload: Dict[str, Any] = {
            "round_id": rnd.id,
            "round_name": rnd.name,
            "grouping": "macro_regional_pools",
            "macro_region_labels": {**MACRO_REGION_LABELS, "_outside_pools": "Outside configured pools"},
            "limit_per_country": args.limit,
            "east_africa_only": bool(args.east_africa_only),
            "contests": [],
        }

        for contest in contests:
            row = _country_season_row(db, contest.id, rnd.id)
            if not row:
                payload["contests"].append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "category_id": contest.category_id,
                        "error": "No COUNTRY season link for this round",
                        "top_per_country": [],
                        "macro_regions": _empty_macro_regions(),
                    }
                )
                continue

            _, country_season = row
            grouped = SeasonMigrationService.get_top_contestants_by_location(
                db,
                country_season.id,
                "country",
                contest_id=contest.id,
                limit=args.limit,
                diagnostics=False,
                active_links_only=args.active_links_only,
                qualified_only=False,
                strict_season_scope=True,
            )

            macro: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in MACRO_ORDER}
            top_per_country: List[Dict[str, Any]] = []

            for country_label, winners in sorted(
                grouped.items(), key=lambda kv: (kv[0] or "").lower()
            ):
                pid = _pool_for_country_label(country_label)
                if args.east_africa_only and pid != "east_africa":
                    continue

                cid_list = [c.id for c in winners]
                pts = _points_by_contestant(db, country_season.id, contest.id, cid_list)
                eng = SeasonMigrationService._engagement_by_contestant(db, cid_list)

                country_rows = []
                for rank, c in enumerate(winners, start=1):
                    e = eng.get(c.id, {})
                    country_rows.append(
                        {
                            "rank_within_country": rank,
                            "contestant_id": c.id,
                            "title": (c.title or "")[:160],
                            "country_on_profile": (c.country or c.nominator_country or ""),
                            "macro_region_id": pid,
                            "macro_region_label": MACRO_REGION_LABELS.get(pid, "Outside pools"),
                            "stars_points": pts.get(c.id, 0),
                            "shares": e.get("shares", 0),
                            "likes": e.get("likes", 0),
                            "comments": e.get("comments", 0),
                            "views": e.get("views", 0),
                        }
                    )

                bucket = {
                    "country_group": country_label or "UNKNOWN",
                    "macro_region_id": pid,
                    "macro_region_label": MACRO_REGION_LABELS.get(pid, "Outside pools"),
                    "winner_count": len(country_rows),
                    "winners": country_rows,
                }
                macro[pid].append(bucket)
                top_per_country.append(bucket)

            macro_out = {pid: macro[pid] for pid in MACRO_ORDER}
            contest_payload = {
                "contest_id": contest.id,
                "contest_name": contest.name,
                "category_id": contest.category_id,
                "country_season_id": country_season.id,
                "country_link_active": bool(
                    db.query(ContestSeasonLink.is_active)
                    .filter(
                        ContestSeasonLink.contest_id == contest.id,
                        ContestSeasonLink.season_id == country_season.id,
                    )
                    .scalar()
                ),
                "top_per_country": top_per_country,
                "macro_regions": macro_out,
                "macro_region_summary": {
                    pid: {
                        "country_buckets": len(macro[pid]),
                        "total_winners": sum(b.get("winner_count", 0) for b in macro[pid]),
                    }
                    for pid in MACRO_ORDER
                },
            }
            payload["contests"].append(contest_payload)

        text = json.dumps(payload, indent=2, default=str)
        outp = (args.output or "").strip()
        if outp:
            with open(outp, "w", encoding="utf-8") as f:
                f.write(text)
                f.write("\n")
            print(f"Wrote {outp}")

        if args.json:
            print(text)
        elif not outp:
            print(text)
    finally:
        db.close()


if __name__ == "__main__":
    main()
