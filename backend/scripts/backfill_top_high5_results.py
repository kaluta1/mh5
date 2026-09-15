#!/usr/bin/env python3
"""
Backfill top_high5_results for stages that closed before the freeze hook
existed (SeasonMigrationService._freeze_top_high5_results). Per the Top
High5 functional spec's own worked example (May 2026 nomination cohort):
June Country, July Regional, and August Continental had all already closed
-- migration for them already ran correctly, but nothing froze their
results. September Global has not closed yet as of this writing and needs
no backfill; the new GLOBAL finalization step handles it automatically.

Dry-run by default; pass --apply to write.

Reconstruction method differs by level, and this matters -- an earlier
version of this script recomputed rankings from CURRENT votes for every
level and, tested against a real staging copy of production, that diverged
badly from what actually got promoted (votes keep accumulating after the
fact, so "top 5 by today's votes" is often not "who was actually top 5 when
this stage closed"). Per the functional spec's own section 24 guidance
("reconstruct using the creatives that were actually migrated"):

- COUNTRY and REGIONAL: reconstructed from the ACTUAL destination season's
  membership (ContestantSeason rows, ordered by joined_at, which
  promote_to_next_level stamps in real rank order at promotion time -- see
  season_migration.py's promotion loop), grouped back to this level's own
  jurisdiction via each contestant's own city/country/region field (unchanged
  by promotion). This is exact, not a recomputation, because at these hops
  "top N per jurisdiction" IS "who advanced" -- the two sets are the same by
  construction (see season_migration.py's location_field_map).
- CONTINENT: prefer the same destination-membership method as COUNTRY/
  REGIONAL (see _groups_for_continent) -- a 2026-09-15 production audit
  found real GLOBAL-destination evidence, <=5 per continent, for every
  contest checked, contradicting this script's original assumption that
  Continental->Global pooling usually leaves a continent's own membership
  empty. Falls back to recomputing per-continent rankings from
  currently-visible votes (the same call the live freeze hook uses) only
  for a jurisdiction with genuinely no destination evidence at all, which
  can still diverge from the real historical result if continent-level
  votes changed since the stage actually closed -- there is no better
  signal available for that specific case without a point-in-time
  snapshot, which was never taken. Treat any CONTINENT `migrated` flag
  produced by the recompute fallback as lower-confidence than the
  membership-based result; going-forward data (frozen live, in
  promote_to_next_level's own transaction) doesn't have this limitation
  regardless of level. A jurisdiction with membership evidence but more
  than 5 real candidates still falls back to the recompute+cap here,
  matching prior behavior -- the separate, stricter historical repair
  utility (scripts/repair_continent_top_high5.py) refuses outright in that
  case instead of guessing.

A stage only qualifies for backfill if the contest has already moved past
it (a link exists at the next level for that specific contest+round), so
this never touches a stage that's still actively voting.

Examples:
  PYTHONPATH=. python scripts/backfill_top_high5_results.py --round-id 3 --level country
  PYTHONPATH=. python scripts/backfill_top_high5_results.py --round-name-contains May --level country --apply
  PYTHONPATH=. python scripts/backfill_top_high5_results.py --round-id 3 --level regional --apply
  PYTHONPATH=. python scripts/backfill_top_high5_results.py --round-id 3 --level continent --apply
"""
from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import func as sa_func, select

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, round_contests
from app.services.contestant_contest_resolution import contestant_belongs_to_contest_clause
from app.services.season_migration import SeasonMigrationService

_LEVEL_MAP = {
    "country": SeasonLevel.COUNTRY,
    "regional": SeasonLevel.REGIONAL,
    "continent": SeasonLevel.CONTINENT,
}
_NEXT_LEVEL = {
    SeasonLevel.COUNTRY: SeasonLevel.REGIONAL,
    SeasonLevel.REGIONAL: SeasonLevel.CONTINENT,
    SeasonLevel.CONTINENT: SeasonLevel.GLOBAL,
}
# Jurisdiction field on Contestant to group by, keyed by the level being
# backfilled -- e.g. level=country groups by contestant.country, matching
# location_field_map's 'country' grouping for the COUNTRY->REGIONAL hop.
_JURISDICTION_FIELD = {
    SeasonLevel.COUNTRY: "country",
    SeasonLevel.REGIONAL: "region",
    SeasonLevel.CONTINENT: "continent",
}


def _contest_linked_season_for_level(db, contest_id: int, round_id: int, level: SeasonLevel):
    """
    Contest-SCOPED season lookup for one (contest, round, level) -- unlike
    SeasonMigrationService._pick_contest_season_for_level, this never falls
    back to an unrelated contest's shared season for the round: contest
    seasons are shared by many contests, so "some season exists at this
    level for the round" does not mean "this contest reached it". Returns
    None when this contest genuinely has no link (active or inactive) at
    this level for this round -- exactly what "not yet closed" must mean.
    """
    for active_only in (True, False):
        q = (
            db.query(ContestSeason)
            .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
            .filter(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeason.round_id == round_id,
                ContestSeason.level == level,
                ContestSeason.is_deleted == False,
            )
        )
        if active_only:
            q = q.filter(ContestSeasonLink.is_active == True)
        row = q.order_by(ContestSeason.id.desc()).first()
        if row:
            return row
    return None


def _groups_from_actual_migration(
    db,
    contest: Contest,
    dest_season: ContestSeason,
    jurisdiction_field: str,
    *,
    cap: "int | None" = 5,
):
    """
    COUNTRY/REGIONAL (and, where evidence exists, CONTINENT) reconstruction:
    the destination season's own active membership for this contest, in real
    promotion order (joined_at), grouped back to this level's jurisdiction
    and capped at 5 per group. Exact, not a guess -- these contestants are
    who actually migrated.

    `cap`: defaults to 5 (existing, unchanged behavior for every current
    caller). Pass `cap=None` to get the full, uncapped membership per
    jurisdiction instead -- used by the separate historical repair utility
    (scripts/repair_continent_top_high5.py), which must be able to tell "more
    than 5 real candidates" apart from "exactly 5" rather than have that
    distinction silently hidden by truncation.
    """
    members = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .filter(
            ContestantSeason.season_id == dest_season.id,
            ContestantSeason.is_active == True,
            contestant_belongs_to_contest_clause(contest.id),
        )
        .order_by(ContestantSeason.joined_at.asc())
        .all()
    )
    groups: dict[str, list] = {}
    for m in members:
        key = (getattr(m, jurisdiction_field, None) or "").strip()
        if not key:
            continue
        groups.setdefault(key, []).append(m)
    if cap is None:
        return groups
    return {k: v[:cap] for k, v in groups.items()}


def _groups_from_recomputed_ranking(db, contest: Contest, source_season: ContestSeason, location_field: str):
    """CONTINENT fallback: no destination evidence to read (see
    _groups_for_continent), so recompute from currently-visible votes, same
    call the live freeze hook uses -- best available signal, not an exact
    reconstruction."""
    return SeasonMigrationService.get_top_contestants_by_location(
        db,
        source_season.id,
        location_field,
        contest_id=contest.id,
        limit=5,
        diagnostics=False,
        qualified_only=False,
        strict_season_scope=True,
        require_votes=False,
    )


def _groups_for_continent(
    db, contest: Contest, source_season: ContestSeason, dest_season: ContestSeason, jurisdiction_field: str
):
    """
    CONTINENT reconstruction: prefer the same exact, destination-membership
    method already proven for COUNTRY/REGIONAL whenever the GLOBAL
    destination season actually has evidence for this contest -- a
    2026-09-15 production audit (see KALUTASOCIETY memory: Top High5
    reconciliation audit) found this evidence exists and is <=5 per
    continent for every real case checked, contradicting this script's
    original assumption that Continental->Global pooling usually leaves a
    continent's own membership empty. Falls back to the current-vote
    recompute only when there is genuinely no destination evidence at all
    for a given jurisdiction (empty group) -- never as a first choice, and
    never for a jurisdiction that has evidence but more than 5 members
    (still handled by the existing recompute+cap fallback here, matching
    prior behavior; the separate repair utility is stricter and refuses
    outright rather than guessing in that case).

    Returns (grouped, method_label) for reporting.
    """
    from_membership = _groups_from_actual_migration(db, contest, dest_season, jurisdiction_field)
    if from_membership:
        recomputed = _groups_from_recomputed_ranking(db, contest, source_season, jurisdiction_field)
        # Fill in any jurisdiction with real evidence missing from the
        # membership-based pass (e.g. a continent whose own top 5 never
        # reached this destination season) using the recompute fallback,
        # without ever overriding a jurisdiction membership already proved.
        for jurisdiction, ranked in recomputed.items():
            from_membership.setdefault(jurisdiction, ranked)
        return from_membership, "actual destination membership (recompute fallback for jurisdictions with no evidence)"
    return _groups_from_recomputed_ranking(db, contest, source_season, jurisdiction_field), (
        "recomputed from current votes (no destination evidence for any jurisdiction)"
    )


def _resolve_round(db, round_id, round_name, round_name_contains) -> Round:
    if round_id is not None:
        rnd = db.query(Round).filter(Round.id == round_id).first()
    elif round_name_contains:
        pat = round_name_contains.strip().lower()
        if not pat:
            raise SystemExit("--round-name-contains is empty")
        rnd = (
            db.query(Round)
            .filter(sa_func.lower(Round.name).contains(pat))
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill frozen Top High5 results for already-closed stages.",
    )
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument("--round-name-contains")
    parser.add_argument("--level", choices=("country", "regional", "continent"), required=True)
    parser.add_argument(
        "--contest-id",
        type=int,
        help="Only this contest (default: every nomination contest in the round)",
    )
    parser.add_argument("--apply", action="store_true", help="Write rows (default: dry-run report only)")
    args = parser.parse_args()

    level = _LEVEL_MAP[args.level]
    next_level = _NEXT_LEVEL[level]
    jurisdiction_field = _JURISDICTION_FIELD[level]

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name, args.round_name_contains)
        contest_ids = [
            row[0]
            for row in db.execute(
                select(round_contests.c.contest_id).where(round_contests.c.round_id == rnd.id)
            ).fetchall()
        ]
        if args.contest_id is not None:
            contest_ids = [args.contest_id]

        contests = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids or [-1]))
            .filter(Contest.contest_mode == "nomination")
            .order_by(Contest.id.asc())
            .all()
        )

        total_written = 0
        total_skipped_already = 0
        total_no_source_season = 0
        total_not_yet_closed = 0
        report_rows = []
        methods_used: set[str] = set()

        for contest in contests:
            source_season = _contest_linked_season_for_level(db, contest.id, rnd.id, level)
            if not source_season:
                total_no_source_season += 1
                continue

            # Only backfill a stage that has actually closed: a link at the
            # next level must already exist for this contest+round (proof
            # the contest has moved on). A still-open stage is left alone --
            # the real freeze hook handles it once it closes.
            dest_season = _contest_linked_season_for_level(db, contest.id, rnd.id, next_level)
            if not dest_season:
                total_not_yet_closed += 1
                continue

            already = (
                db.query(TopHigh5Result.id)
                .filter(
                    TopHigh5Result.contest_id == contest.id,
                    TopHigh5Result.level == level,
                    TopHigh5Result.round_id == rnd.id,
                )
                .first()
            )
            if already:
                total_skipped_already += 1
                continue

            if level == SeasonLevel.CONTINENT:
                grouped, method_used = _groups_for_continent(
                    db, contest, source_season, dest_season, jurisdiction_field
                )
                methods_used.add(method_used)
            else:
                grouped = _groups_from_actual_migration(db, contest, dest_season, jurisdiction_field)

            for jurisdiction, ranked in grouped.items():
                if not ranked:
                    continue
                report_rows.append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "jurisdiction": jurisdiction,
                        "contestant_ids_in_rank_order": [c.id for c in ranked],
                    }
                )
                if args.apply:
                    written = SeasonMigrationService._freeze_top_high5_results(
                        db,
                        level=level,
                        jurisdiction=jurisdiction,
                        contest=contest,
                        from_season=source_season,
                        to_season=dest_season,
                        ranked_contestants=ranked,
                    )
                    total_written += written

        if args.apply and total_written:
            db.commit()

        print(f"Round: {rnd.name} (id={rnd.id}), level={level.value}")
        if level == SeasonLevel.CONTINENT:
            method_desc = "; ".join(sorted(methods_used)) if methods_used else "n/a (no contests reached this stage)"
        else:
            method_desc = "actual destination membership"
        print(f"Reconstruction method: {method_desc}")
        print(f"Contests scanned: {len(contests)}")
        print(f"  no source season for this level: {total_no_source_season}")
        print(f"  stage not yet closed (no higher-level link found): {total_not_yet_closed}")
        print(f"  already frozen (skipped): {total_skipped_already}")
        action = "written" if args.apply else "that WOULD be written (dry-run)"
        print(f"  groups {action}: {len(report_rows)}")
        for row in report_rows:
            print(
                f"    contest={row['contest_id']} ({row['contest_name']}) "
                f"jurisdiction={row['jurisdiction']!r} "
                f"rank_order={row['contestant_ids_in_rank_order']}"
            )
        if args.apply:
            print(f"Rows committed: {total_written}")
        else:
            print("Dry run only -- pass --apply to write these rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
