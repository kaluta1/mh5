#!/usr/bin/env python3
"""
Diagnostic script to verify the continental voting fix.

This script queries the database directly to:
1. Find contests with continental seasons and their promoted contestants
2. Compare old vs new logic for season resolution and roster counts
3. Report any discrepancies

Run from backend/ with:
    PYTHONPATH=. python scripts/diagnose_continental_fix.py
"""

import os
import sys

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, case, and_, or_, func
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.contests import (
    Contestant,
    ContestSeason,
    ContestSeasonLink,
    ContestantSeason,
    SeasonLevel,
)
from app.models.contest import Contest
from app.models.round import Round


def get_db_session():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def find_contests_with_continental_seasons(db):
    """Find all contests that have an active continental season link."""
    rows = (
        db.query(Contest, ContestSeason, ContestSeasonLink)
        .join(ContestSeasonLink, ContestSeasonLink.contest_id == Contest.id)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
            Contest.is_deleted == False,
        )
        .order_by(Contest.id, ContestSeason.id)
        .all()
    )
    return rows


def count_contestant_season_members(db, season_id):
    """Count active members in a ContestSeason."""
    return (
        db.query(ContestantSeason)
        .filter(
            ContestantSeason.season_id == season_id,
            ContestantSeason.is_active == True,
        )
        .count()
    )


def get_contestant_season_member_details(db, season_id):
    """Get details of active members in a ContestSeason."""
    members = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .filter(
            ContestantSeason.season_id == season_id,
            ContestantSeason.is_active == True,
            Contestant.is_deleted == False,
        )
        .all()
    )
    return members


def simulate_old_logic(db, contest, season, target_round_id):
    """
    Simulate the OLD buggy logic:
    1. Look for continental season ONLY with round_id == target_round_id
    2. If not found, fallback to naive active link (often country-level)
    3. Apply round_id filter on Contestant
    """
    # Old _season_pair_for_requested_ui_level logic (exact round only)
    old_pair = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeason.round_id == target_round_id,
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
        )
        .order_by(
            ContestSeasonLink.is_active.desc(),
            ContestSeasonLink.linked_at.desc(),
            ContestSeason.id.desc(),
        )
        .first()
    )

    if old_pair:
        resolved_season = old_pair[1]
        source = f"exact round {target_round_id}"
    else:
        # Old fallback: naive active link (first arbitrary active link)
        naive = (
            db.query(ContestSeasonLink)
            .filter(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.is_active == True,
            )
            .first()
        )
        if naive:
            resolved_season = (
                db.query(ContestSeason)
                .filter(
                    ContestSeason.id == naive.season_id,
                    ContestSeason.is_deleted == False,
                )
                .first()
            )
            source = f"naive fallback (level={resolved_season.level.value if resolved_season else 'none'})"
        else:
            resolved_season = None
            source = "none found"

    if resolved_season is None:
        return {"source": source, "count": 0, "members": []}

    # Old round filter applied
    members = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .filter(
            ContestantSeason.season_id == resolved_season.id,
            ContestantSeason.is_active == True,
            Contestant.is_deleted == False,
            Contestant.round_id == target_round_id,
            Contestant.season_id == contest.id,
        )
        .all()
    )

    return {
        "source": source,
        "season_level": (
            resolved_season.level.value
            if hasattr(resolved_season.level, "value")
            else str(resolved_season.level)
        ),
        "season_round_id": resolved_season.round_id,
        "count": len(members),
        "members": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "country": m.country,
                "continent": m.continent,
                "round_id": m.round_id,
                "season_id": m.season_id,
            }
            for m in members
        ],
    }


def simulate_new_logic(db, contest, season, target_round_id):
    """
    Simulate the NEW fixed logic:
    1. Look for continental season with round_id == target_round_id
    2. If not found, fallback to nearest continental season across all rounds
    3. Skip round_id filter on Contestant for pooled phases
    """
    # New _season_pair_for_requested_ui_level logic (exact round first)
    exact_pair = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeason.round_id == target_round_id,
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
        )
        .order_by(
            ContestSeasonLink.is_active.desc(),
            ContestSeasonLink.linked_at.desc(),
            ContestSeason.id.desc(),
        )
        .first()
    )

    if exact_pair:
        resolved_season = exact_pair[1]
        source = f"exact round {target_round_id}"
    else:
        # New fallback: nearest continental season across all rounds
        nearest = (
            db.query(ContestSeasonLink, ContestSeason)
            .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
            .filter(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeason.level == SeasonLevel.CONTINENT,
                ContestSeason.is_deleted == False,
            )
            .order_by(
                case(
                    (ContestSeason.round_id <= target_round_id, 0),
                    else_=1,
                ),
                ContestSeason.round_id.desc(),
                ContestSeason.id.desc(),
            )
            .first()
        )
        if nearest:
            resolved_season = nearest[1]
            source = f"nearest fallback (round {resolved_season.round_id})"
        else:
            resolved_season = None
            source = "none found"

    if resolved_season is None:
        return {"source": source, "count": 0, "members": []}

    # New logic: NO round_id filter for pooled phases
    members = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .filter(
            ContestantSeason.season_id == resolved_season.id,
            ContestantSeason.is_active == True,
            Contestant.is_deleted == False,
            Contestant.season_id == contest.id,
        )
        .all()
    )

    return {
        "source": source,
        "season_level": (
            resolved_season.level.value
            if hasattr(resolved_season.level, "value")
            else str(resolved_season.level)
        ),
        "season_round_id": resolved_season.round_id,
        "count": len(members),
        "members": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "country": m.country,
                "continent": m.continent,
                "round_id": m.round_id,
                "season_id": m.season_id,
            }
            for m in members
        ],
    }


def main():
    db = get_db_session()
    print("=" * 80)
    print("CONTINENTAL VOTING FIX DIAGNOSTIC")
    print("=" * 80)

    # Find all active rounds to use as target_round_id
    rounds = db.query(Round).filter(Round.status != "cancelled").order_by(Round.id.desc()).all()
    if not rounds:
        print("No active rounds found in database.")
        return

    print(f"\nFound {len(rounds)} active rounds: {[r.id for r in rounds]}")
    target_round_id = rounds[0].id
    print(f"Using latest round as target: {target_round_id}")

    rows = find_contests_with_continental_seasons(db)
    if not rows:
        print("\nNo contests with continental seasons found.")
        print("This could mean:")
        print("  - No continental promotions have been run yet")
        print("  - Continental seasons exist but are not linked to contests")
        return

    print(f"\nFound {len(rows)} contest(s) with continental season links:\n")

    for contest, season, link in rows:
        print("-" * 80)
        print(f"Contest: {contest.name} (id={contest.id})")
        print(f"  Continental season: id={season.id}, round_id={season.round_id}, level={season.level.value}")
        print(f"  Link active: {link.is_active}")

        total_members = count_contestant_season_members(db, season.id)
        print(f"  Total active ContestantSeason members: {total_members}")

        all_members = get_contestant_season_member_details(db, season.id)
        countries = set(m.country for m in all_members if m.country)
        continents = set(m.continent for m in all_members if m.continent)
        print(f"  Member countries: {sorted(countries) or 'N/A'}")
        print(f"  Member continents: {sorted(continents) or 'N/A'}")

        old_result = simulate_old_logic(db, contest, season, target_round_id)
        new_result = simulate_new_logic(db, contest, season, target_round_id)

        print(f"\n  OLD logic (buggy):")
        print(f"    Resolved season: {old_result['source']}")
        print(f"    Season level: {old_result.get('season_level', 'N/A')}")
        print(f"    Visible count: {old_result['count']}")
        if old_result['members']:
            old_countries = set(m['country'] for m in old_result['members'] if m['country'])
            print(f"    Visible countries: {sorted(old_countries)}")

        print(f"\n  NEW logic (fixed):")
        print(f"    Resolved season: {new_result['source']}")
        print(f"    Season level: {new_result.get('season_level', 'N/A')}")
        print(f"    Visible count: {new_result['count']}")
        if new_result['members']:
            new_countries = set(m['country'] for m in new_result['members'] if m['country'])
            print(f"    Visible countries: {sorted(new_countries)}")

        if old_result['count'] != new_result['count']:
            print(f"\n  *** DIFFERENCE DETECTED: {old_result['count']} vs {new_result['count']} ***")
            if old_result['count'] < new_result['count']:
                missing = [m for m in new_result['members'] if m['id'] not in {x['id'] for x in old_result['members']}]
                print(f"      Missing in old logic ({len(missing)} contestants):")
                for m in missing[:5]:
                    print(f"        - id={m['id']}, country={m['country']}, round_id={m['round_id']}")
                if len(missing) > 5:
                    print(f"        ... and {len(missing) - 5} more")
        else:
            print(f"\n  Counts match.")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
