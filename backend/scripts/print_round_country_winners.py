#!/usr/bin/env python3
"""
Top High5 per country, per category (each nomination contest on the round):

  Default `--limit 5` = up to five winners per country per contest, ranked by the
  same rules as season migration / Top High5 (votes in that COUNTRY—or REGIONAL—
  season scope + engagement tie-break).

Levels:
  country  — ContestSeason.level=COUNTRY; groups by nominee country (default).
  regional — ContestSeason.level=REGIONAL; groups by nominee region label.

Example:
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-id 3
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-name "Round March 2026" --limit 5
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-name-contains March \\
    --limit 5 -o ~/top_high5_per_country_per_category.json
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-name-contains "March" --level regional --limit 10 --json --output march_regional.json
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-id 3 --contest-id 15 --country Tanzania
  PYTHONPATH=. python scripts/print_round_country_winners.py --round-id 3 --contest-name Adventure --east-africa-only
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


def _linked_season_for_contest(
    db, contest_id: int, round_id: int, season_level: SeasonLevel
) -> Optional[Tuple[ContestSeasonLink, ContestSeason]]:
    q = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeason.round_id == round_id,
            ContestSeason.level == season_level,
            ContestSeason.is_deleted == False,
        )
        .order_by(ContestSeasonLink.is_active.desc(), ContestSeasonLink.linked_at.desc())
    )
    row = q.first()
    return row


def _country_season_for_contest(
    db, contest_id: int, round_id: int
) -> Optional[Tuple[ContestSeasonLink, ContestSeason]]:
    return _linked_season_for_contest(db, contest_id, round_id, SeasonLevel.COUNTRY)


def _east_africa_key(country_group_label: str) -> Optional[str]:
    """Normalize grouped country label to bloc key if in EA pool."""
    k = SeasonMigrationService._country_key(country_group_label)
    if not k or k not in SeasonMigrationService.EAST_AFRICA_COUNTRY_KEYS:
        return None
    return k


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
        "rwanda": "rw",
        "rw": "rwanda",
        "burundi": "bi",
        "bi": "burundi",
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


def _points_by_contestant_contest_wide(
    db, contest_id: int, contestant_ids: List[int]
) -> Dict[int, int]:
    """Sum star points for this contest across all season_id values (diagnostic / reporting)."""
    if not contestant_ids:
        return {}
    rows = (
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
    return {r.contestant_id: int(r.total_points or 0) for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Top High5-style export: Top N nominees per country (or region) per nomination contest."
    )
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument(
        "--round-name-contains",
        help="Pick latest round whose name contains this substring (case-insensitive), e.g. March",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Top N per country per contest (High5 ⇒ 5); same for regional groups when --level regional.",
    )
    parser.add_argument("--contest-id", type=int, help="Only one contest/category")
    parser.add_argument(
        "--contest-name",
        help="Single nomination contest whose name contains this text (case-insensitive), e.g. Adventure",
    )
    parser.add_argument(
        "--east-africa-only",
        action="store_true",
        help="Only Tanzania, Kenya, Uganda, Rwanda, Burundi (+ common codes)",
    )
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
    parser.add_argument(
        "--level",
        choices=("country", "regional"),
        default="country",
        help="Season link to use: country (default) or regional macro groups",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Write the same payload as --json to this UTF-8 file path (JSON)",
    )
    parser.add_argument(
        "--include-contest-vote-totals",
        action="store_true",
        help="Add stars_points_contest_wide: summed votes for contest_id ignoring season_id (see JSON explainer)",
    )
    args = parser.parse_args()

    if args.contest_id is not None and args.contest_name:
        raise SystemExit("Use either --contest-id or --contest-name, not both.")

    selectors = sum(
        1 for x in (args.round_id, args.round_name, args.round_name_contains) if x
    )
    if selectors > 1:
        raise SystemExit(
            "Use only one of: --round-id, --round-name, --round-name-contains."
        )

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name, args.round_name_contains)
        contest_ids = _contest_ids_for_round(db, rnd.id)
        if args.contest_id is not None:
            if args.contest_id not in contest_ids:
                raise SystemExit(
                    f"Contest {args.contest_id} is not linked to round {rnd.id}"
                )
            contest_ids = [args.contest_id]
        elif args.contest_name:
            pat = args.contest_name.strip().lower()
            if not pat:
                raise SystemExit("--contest-name is empty")
            rows = (
                db.query(Contest.id, Contest.name)
                .filter(
                    Contest.id.in_(contest_ids or [-1]),
                    Contest.contest_mode == "nomination",
                    Contest.is_deleted == False,
                    func.lower(Contest.name).contains(pat),
                )
                .all()
            )
            if len(rows) == 0:
                raise SystemExit(
                    f"No nomination contest on round {rnd.id} matches name substring {pat!r}"
                )
            if len(rows) > 1:
                labs = [(r.id, r.name) for r in rows[:12]]
                extra = (
                    f" (+{len(rows)-12} more)" if len(rows) > 12 else ""
                )
                raise SystemExit(
                    "Multiple contests match {!r}: {}{}. Use --contest-id.".format(
                        pat, labs, extra
                    )
                )
            contest_ids = [rows[0].id]

        contests = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids or [-1]))
            .filter(Contest.contest_mode == "nomination")
            .order_by(Contest.id.asc())
            .all()
        )

        country_filter_variants = _country_variants(args.country) if args.country else None

        seasonal = SeasonLevel.REGIONAL if args.level == "regional" else SeasonLevel.COUNTRY
        location_field = "region" if args.level == "regional" else "country"
        groups_json_key = "regions" if args.level == "regional" else "countries"

        payload: Dict[str, Any] = {
            "round_id": rnd.id,
            "round_name": rnd.name,
            "level": args.level,
            "limit_per_group": args.limit,
            "limit_per_country": args.limit,
            "east_africa_only": bool(args.east_africa_only),
            "contests": [],
        }
        if args.include_contest_vote_totals:
            payload["stars_points_explainer"] = (
                "stars_points = SUM(ContestantVoting.points) WHERE season_id is this contest's "
                "country/regional season AND contest_id matches (official stage scope). "
                "stars_points_contest_wide = same sum but ANY season_id for that contest_id — "
                "useful when votes were stored under a different season_id so official shows 0."
            )

        for contest in contests:
            link_row = _linked_season_for_contest(db, contest.id, rnd.id, seasonal)
            if not link_row:
                level_label = "REGIONAL" if args.level == "regional" else "COUNTRY"
                payload["contests"].append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "category_id": contest.category_id,
                        "error": f"No {level_label} season link for this round",
                        groups_json_key: {},
                    }
                )
                continue

            _, geo_season = link_row

            grouped = SeasonMigrationService.get_top_contestants_by_location(
                db,
                geo_season.id,
                location_field,
                contest_id=contest.id,
                limit=args.limit,
                diagnostics=False,
                active_links_only=args.active_links_only,
                qualified_only=False,
                strict_season_scope=True,
            )

            link_active_col = (
                "regional_link_active"
                if args.level == "regional"
                else "country_link_active"
            )
            season_id_col = (
                "regional_season_id"
                if args.level == "regional"
                else "country_season_id"
            )
            contest_out: Dict[str, Any] = {
                "contest_id": contest.id,
                "contest_name": contest.name,
                "category_id": contest.category_id,
                season_id_col: geo_season.id,
                link_active_col: bool(
                    db.query(ContestSeasonLink.is_active)
                    .filter(
                        ContestSeasonLink.contest_id == contest.id,
                        ContestSeasonLink.season_id == geo_season.id,
                    )
                    .scalar()
                ),
                groups_json_key: {},
            }

            east_africa_regions = frozenset(
                ("east africa", "eastern africa")
            )

            def _skip_group(label: Optional[str]) -> bool:
                if args.level != "country":
                    if args.east_africa_only:
                        lk = (label or "").strip().lower()
                        if lk not in east_africa_regions:
                            return True
                    return False
                if args.east_africa_only:
                    if _east_africa_key(label or "") is None:
                        return True
                if country_filter_variants:
                    canon = SeasonMigrationService._canonical_country_label(label) or ""
                    raw_l = (label or "").strip().lower()
                    if (
                        raw_l not in country_filter_variants
                        and canon.strip().lower() not in country_filter_variants
                    ):
                        return True
                return False

            for group_key, winners in sorted(
                grouped.items(), key=lambda kv: (kv[0] or "").lower()
            ):
                if _skip_group(group_key):
                    continue

                cid_list = [c.id for c in winners]
                points_map = _points_by_contestant(
                    db, geo_season.id, contest.id, cid_list
                )
                wide_map = (
                    _points_by_contestant_contest_wide(db, contest.id, cid_list)
                    if args.include_contest_vote_totals
                    else {}
                )
                engagement = SeasonMigrationService._engagement_by_contestant(db, cid_list)

                rows = []
                for rank, c in enumerate(winners, start=1):
                    e = engagement.get(c.id, {})
                    row_out: Dict[str, Any] = {
                        "rank": rank,
                        "contestant_id": c.id,
                        "title": (c.title or "")[:120],
                        "country_on_profile": (c.country or c.nominator_country or ""),
                        "region_on_profile": (c.region or ""),
                        "stars_points": points_map.get(c.id, 0),
                        "shares": e.get("shares", 0),
                        "likes": e.get("likes", 0),
                        "comments": e.get("comments", 0),
                        "views": e.get("views", 0),
                    }
                    if args.include_contest_vote_totals:
                        row_out["stars_points_contest_wide"] = wide_map.get(c.id, 0)
                    rows.append(row_out)

                contest_out[groups_json_key][group_key or "UNKNOWN"] = rows

            payload["contests"].append(contest_out)

        text = json.dumps(payload, indent=2, default=str)
        out_path = (args.output or "").strip()
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
                f.write("\n")
            print(f"Wrote {out_path}")

        if args.json:
            print(text)
        elif out_path:
            pass
        else:
            per_what = "region" if args.level == "regional" else "country"
            print(f"Round: {rnd.name} (id={rnd.id})")
            print(
                f"Top {args.limit} per {per_what} · {args.level} season · nomination contests only",
                end="",
            )
            if args.east_africa_only:
                if args.level == "regional":
                    print(" · East Africa / Eastern Africa regions only")
                else:
                    print(" · East Africa countries only")
            else:
                print()
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
                sid = cblock.get("country_season_id") or cblock.get(
                    "regional_season_id"
                )
                lk = (
                    "country_link_active"
                    if "country_link_active" in cblock
                    else "regional_link_active"
                )
                print(f"  season_id={sid} link_active={cblock.get(lk)} ({args.level})")
                groups = cblock.get(groups_json_key) or {}
                if not groups:
                    msg = (
                        "no regional groups"
                        if args.level == "regional"
                        else "no country groups"
                    )
                    print(f"  ({msg} / no qualifiers for this contest)")
                    print()
                    continue
                for gname, grow in sorted(groups.items(), key=lambda x: x[0].lower()):
                    print(f"  --- {gname} ({len(grow)} shown) ---")
                    for row in grow:
                        loc = ""
                        if args.level == "regional" and row.get("region_on_profile"):
                            loc = f" region={row['region_on_profile']!r}"
                        wide_s = ""
                        if "stars_points_contest_wide" in row:
                            wide_s = f" stars_wide={row['stars_points_contest_wide']}"
                        print(
                            f"    {row['rank']}. id={row['contestant_id']} "
                            f"stars={row['stars_points']}{wide_s} "
                            f"shares={row['shares']} likes={row['likes']} "
                            f"comments={row['comments']} views={row['views']} "
                            f"| {row['title']!r} "
                            f"[profile_country={row['country_on_profile']!r}]{loc}"
                        )
                    print()
                print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
