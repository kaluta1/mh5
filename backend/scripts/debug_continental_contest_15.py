#!/usr/bin/env python3
"""
Debug script for continental contest display issue.
Run from backend/ with:
    PYTHONPATH=. python scripts/debug_continental_contest_15.py
"""
import os
import sys

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
from app.models.user import User


def get_db_session():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def main():
    db = get_db_session()
    print("=" * 80)
    print("DEBUG: Continental Contest Issue (Contest ID = 15)")
    print("=" * 80)

    # 1. Find the contest
    contest = db.query(Contest).filter(Contest.id == 15, Contest.is_deleted == False).first()
    if not contest:
        print("\n❌ Contest 15 not found!")
        return
    print(f"\n📋 Contest: {contest.name} (id={contest.id})")
    print(f"   level={contest.level} | contest_mode={getattr(contest, 'contest_mode', 'N/A')}")

    # 2. Find all active seasons linked to this contest
    print("\n📊 Active ContestSeason links for this contest:")
    season_links = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == 15,
            ContestSeason.is_deleted == False,
        )
        .order_by(ContestSeasonLink.is_active.desc(), ContestSeason.id.desc())
        .all()
    )
    if not season_links:
        print("   ❌ NO seasons linked to this contest!")
        return

    for link, season in season_links:
        print(f"   - season_id={season.id} | level={season.level.value} | "
              f"round_id={season.round_id} | link_active={link.is_active}")

    # 3. Find the CONTINENTAL season specifically
    continental_link = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == 15,
            ContestSeasonLink.is_active == True,
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
        )
        .first()
    )

    if not continental_link:
        print("\n❌ NO active continental season found for contest 15!")
        print("   This means regional winners were NEVER promoted to continental.")
        print("   The code fix alone cannot help — the migration must be run first.")
        return

    continental_season = continental_link[1]
    print(f"\n🌍 Found continental season: id={continental_season.id}, round_id={continental_season.round_id}")

    # 4. Find active ContestantSeason members for this continental season
    members = (
        db.query(ContestantSeason, Contestant, User)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .outerjoin(User, User.id == Contestant.user_id)
        .filter(
            ContestantSeason.season_id == continental_season.id,
            ContestantSeason.is_active == True,
            Contestant.is_deleted == False,
        )
        .all()
    )

    print(f"\n👥 Active ContestantSeason members in continental season: {len(members)}")
    if not members:
        print("   ❌ ZERO members! Regional winners were not linked to continental season.")
        print("   The migration that promotes regional → continental did not run or failed.")
        return

    countries = {}
    for cs, c, u in members:
        country = getattr(c, 'country', None) or 'UNKNOWN'
        countries[country] = countries.get(country, 0) + 1
        print(f"   - contestant_id={c.id} | country={country} | "
              f"region={getattr(c, 'region', 'N/A')} | "
              f"continent={getattr(c, 'continent', 'N/A')} | "
              f"season_id={c.season_id} | "
              f"user={getattr(u, 'username', 'N/A')}")

    print(f"\n📈 Country breakdown in continental season:")
    for country, count in sorted(countries.items(), key=lambda x: -x[1]):
        print(f"   {country}: {count}")

    # 5. Simulate OLD buggy query (season_id == contest.id)
    print("\n🔴 OLD BUGGY QUERY (Contestant.season_id == 15):")
    old_buggy = (
        db.query(Contestant)
        .filter(
            Contestant.season_id == 15,
            Contestant.is_deleted == False,
        )
        .all()
    )
    old_countries = {}
    for c in old_buggy:
        country = getattr(c, 'country', None) or 'UNKNOWN'
        old_countries[country] = old_countries.get(country, 0) + 1
    print(f"   Returns {len(old_buggy)} contestants")
    for country, count in sorted(old_countries.items(), key=lambda x: -x[1]):
        print(f"     {country}: {count}")

    # 6. Simulate NEW fixed query (ContestantSeason membership)
    print("\n🟢 NEW FIXED QUERY (ContestantSeason membership):")
    member_ids = [m[0].contestant_id for m in members]
    if member_ids:
        new_fixed = (
            db.query(Contestant)
            .filter(
                Contestant.id.in_(member_ids),
                Contestant.is_deleted == False,
            )
            .all()
        )
        new_countries = {}
        for c in new_fixed:
            country = getattr(c, 'country', None) or 'UNKNOWN'
            new_countries[country] = new_countries.get(country, 0) + 1
        print(f"   Returns {len(new_fixed)} contestants")
        for country, count in sorted(new_countries.items(), key=lambda x: -x[1]):
            print(f"     {country}: {count}")
    else:
        print("   Returns 0 contestants (no member IDs)")

    # 7. Check if round_id=3 is being passed and what it filters
    print("\n🔍 Checking contestants with round_id=3 (from URL parameter):")
    round_3 = (
        db.query(Contestant)
        .filter(
            Contestant.id.in_(member_ids),
            Contestant.round_id == 3,
            Contestant.is_deleted == False,
        )
        .all()
    )
    print(f"   ContestantSeason members with round_id=3: {len(round_3)}")

    print("\n   ContestantSeason members with round_id != 3 or NULL:")
    round_not_3 = (
        db.query(Contestant)
        .filter(
            Contestant.id.in_(member_ids),
            or_(Contestant.round_id != 3, Contestant.round_id.is_(None)),
            Contestant.is_deleted == False,
        )
        .all()
    )
    print(f"   Count: {len(round_not_3)}")
    for c in round_not_3[:10]:
        print(f"     id={c.id} | country={getattr(c, 'country', 'N/A')} | round_id={c.round_id}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

    # Summary
    if len(members) > 0 and len(old_buggy) < len(members):
        print(f"\n✅ CONCLUSION: The fix IS needed.")
        print(f"   Old query returns {len(old_buggy)} contestants.")
        print(f"   New query should return {len(members)} contestants.")
        print(f"   Missing countries: {set(new_countries.keys()) - set(old_countries.keys())}")
    elif len(members) == 0:
        print(f"\n❌ CONCLUSION: No ContestantSeason links exist.")
        print("   The regional → continental migration never ran or failed.")
    else:
        print(f"\n⚠️ CONCLUSION: Old and new queries return the same count.")
        print("   This means all members already have season_id == 15, OR")
        print("   the promotion created new rows instead of linking existing ones.")


if __name__ == "__main__":
    main()
