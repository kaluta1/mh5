#!/usr/bin/env python3
"""
Print Top N "winners" per country for each nomination contest in a given round,
using the same scoring rules as season migration / Top High5 (MyHigh5 points in
that COUNTRY season + engagement tie-break).

Example:
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-id 3
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-name "Round March 2026" --limit 5
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-id 3 --contest-id 15 --country Tanzania
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


def _resolve_round(db, round_id: int | None, round_name: str | None) -> Round:
    if round_id is not None:
        rnd = db.query(Round).filter(Round.id == round_id).first()
    elif round_name:
        rnd = db.query(Round).filter(Round.name == round_name).first()
    else:
        raise SystemExit("Provide --round-id or --round-name")
    if not rnd:
        raise SystemExit("Round not found")
    return rnd


def _contest_ids_for_round(db, round_id: int) -> List[int]:
    rows = db.execute(
        select(round_contests.c.contest_id).where(round_contests.c.round_id == round_id)
    ).fetchall()
    return [row[0] for row in rows]


def _country_season_for_contest(
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
    row = q.first()
    return row


def _country_variants(raw: str) -> set[str]:
    raw = (raw or "").strip().lower()
    variants = {raw}
    alias_map = {
        "tanzania": "tz",
        "tz": "tanzania",
        "uganda": "ug",
        "ug": "uganda",
        "kenya": "ke",
        "ke": "kenya",
    }
    if raw in alias_map:
        variants.add(alias_map[raw])
    return variants


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print Top-N per-country winners per nomination contest for one round."
    )
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument("--limit", type=int, default=5, help="Top N per country (default 5)")
    parser.add_argument("--contest-id", type=int, help="Only one contest/category")
    parser.add_argument(
        "--country",
        help="Only print groups matching this country label (aliases: Tanzania, TZ, …)",
    )
    parser.add_argument(
        "--active-links-only",
        action="store_true",
        help="Restrict to ContestantSeason rows marked active=True (default: include inactive links)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object (good for piping)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name)
        contest_ids = _contest_ids_for_round(db, rnd.id)
        if args.contest_id is not None:
            if args.contest_id not in contest_ids:
                raise SystemExit(
                    f"Contest {args.contest_id} is not linked to round {rnd.id}"
                )
            contest_ids = [args.contest_id]

        contests = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids or [-1]))
            .filter(Contest.contest_mode == "nomination")
            .order_by(Contest.id.asc())
            .all()
        )

        country_filter_variants = _country_variants(args.country) if args.country else None

        payload: Dict[str, Any] = {
            "round_id": rnd.id,
            "round_name": rnd.name,
            "limit_per_country": args.limit,
            "contests": [],
        }

        for contest in contests:
            link_row = _country_season_for_contest(db, contest.id, rnd.id)
            if not link_row:
                payload["contests"].append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "category_id": contest.category_id,
                        "error": "No COUNTRY season link for this round",
                        "countries": {},
                    }
                )
                continue

            _, country_season = link_row

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

            contest_out: Dict[str, Any] = {
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
                "countries": {},
            }

            for country_key, winners in sorted(
                grouped.items(), key=lambda kv: (kv[0] or "").lower()
            ):
                if country_filter_variants:
                    canon = SeasonMigrationService._canonical_country_label(country_key) or ""
                    raw_l = (country_key or "").strip().lower()
                    if raw_l not in country_filter_variants and canon.strip().lower() not in country_filter_variants:
                        continue

                cid_list = [c.id for c in winners]
                points_map = _points_by_contestant(
                    db, country_season.id, contest.id, cid_list
                )
                engagement = SeasonMigrationService._engagement_by_contestant(db, cid_list)

                rows = []
                for rank, c in enumerate(winners, start=1):
                    e = engagement.get(c.id, {})
                    rows.append(
                        {
                            "rank": rank,
                            "contestant_id": c.id,
                            "title": (c.title or "")[:120],
                            "country_on_profile": (c.country or c.nominator_country or ""),
                            "stars_points": points_map.get(c.id, 0),
                            "shares": e.get("shares", 0),
                            "likes": e.get("likes", 0),
                            "comments": e.get("comments", 0),
                            "views": e.get("views", 0),
                        }
                    )

                contest_out["countries"][country_key or "UNKNOWN"] = rows

            payload["contests"].append(contest_out)

        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"Round: {rnd.name} (id={rnd.id})")
            print(f"Top {args.limit} per country · nomination contests only")
            print()
            for cblock in payload["contests"]:
                print(
                    f"=== Contest {cblock['contest_id']}: {cblock['contest_name']} "
                    f"(category_id={cblock.get('category_id')}) ==="
                )
                if "error" in cblock:
                    print(f"  ERROR: {cblock['error']}")
                    print()
                    continue
                print(
                    f"  COUNTRY season_id={cblock['country_season_id']} "
                    f"link_active={cblock.get('country_link_active')}"
                )
                countries = cblock.get("countries") or {}
                if not countries:
                    print("  (no country groups / no qualifiers for this contest)")
                    print()
                    continue
                for country, rows in sorted(countries.items(), key=lambda x: x[0].lower()):
                    print(f"  --- {country} ({len(rows)} shown) ---")
                    for row in rows:
                        print(
                            f"    {row['rank']}. id={row['contestant_id']} "
                            f"stars={row['stars_points']} "
                            f"shares={row['shares']} likes={row['likes']} "
                            f"comments={row['comments']} views={row['views']} "
                            f"| {row['title']!r} "
                            f"[profile_country={row['country_on_profile']!r}]"
                        )
                    print()
                print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
