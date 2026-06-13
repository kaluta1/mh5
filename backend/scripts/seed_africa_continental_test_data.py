#!/usr/bin/env python3
"""
Seed script for continental-level test data across major African countries.

Creates test users and contestants in Nigeria, Kenya, South Africa and Ghana,
links them to the continental season of a chosen contest, and sets both the
contestant snapshot and the user profile to continent=Africa so the
`continent=Africa` filter can be verified end-to-end.

Run from the repository root with:
    cd backend && PYTHONPATH=. python scripts/seed_africa_continental_test_data.py

Or with explicit arguments:
    PYTHONPATH=. python scripts/seed_africa_continental_test_data.py --contest-id 15 --round-id 3 --dry-run
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

# Ensure backend is on PYTHONPATH even when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.contest import Contest
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    ContestStage,
    ContestStageLevel,
    SeasonLevel,
)
from app.models.user import User


AFRICA_TEST_COUNTRIES = [
    {"name": "Nigeria", "slug": "nigeria"},
    {"name": "Kenya", "slug": "kenya"},
    {"name": "South Africa", "slug": "south-africa"},
    {"name": "Ghana", "slug": "ghana"},
]

DEFAULT_PASSWORD = "TestPass123!"


def get_db_session():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def ensure_continental_season(
    db,
    contest_id: int,
    round_id: Optional[int],
    dry_run: bool = False,
):
    """Find or create the active continental season for the given contest."""
    existing = (
        db.query(ContestSeasonLink, ContestSeason)
        .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True,
            ContestSeason.level == SeasonLevel.CONTINENT,
            ContestSeason.is_deleted == False,
        )
        .order_by(ContestSeason.id.desc())
        .first()
    )

    if existing:
        season = existing[1]
        print(f"[OK] Using existing continental season id={season.id} (round_id={season.round_id})")
        return season

    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
    if not contest:
        raise ValueError(f"Contest id={contest_id} not found or is deleted")

    if dry_run:
        print(f"[DRY-RUN] Would create continental season for contest_id={contest_id}, round_id={round_id}")
        return None

    now = datetime.utcnow()
    season = ContestSeason(
        round_id=round_id,
        title=f"{contest.name} - Continental Test Season",
        level=SeasonLevel.CONTINENT,
        is_deleted=False,
    )
    db.add(season)
    db.flush()

    link = ContestSeasonLink(
        contest_id=contest_id,
        season_id=season.id,
        is_active=True,
    )
    db.add(link)

    # A continental stage is useful for ranking/progression; it is not strictly
    # required for roster listing, but keeps the data graph consistent.
    stage = ContestStage(
        season_id=season.id,
        stage_level=ContestStageLevel.CONTINENTAL,
        start_date=now,
        end_date=now + timedelta(days=30),
        max_qualifiers=10,
        min_participants=2,
    )
    db.add(stage)

    db.commit()
    db.refresh(season)
    print(f"[OK] Created continental season id={season.id} (round_id={round_id}) linked to contest_id={contest_id}")
    return season


def seed_african_test_data(contest_id: int, round_id: Optional[int], dry_run: bool = False):
    db = get_db_session()
    try:
        season = ensure_continental_season(db, contest_id, round_id, dry_run=dry_run)
        if not season and dry_run:
            # Continue with a fake season id so the dry-run summary is meaningful.
            season_id = -1
            effective_round_id = round_id
        else:
            season_id = season.id
            # Align contestant.round_id with the season we are linking to.
            effective_round_id = season.round_id if season.round_id is not None else round_id

        created_users = []
        created_contestants = []

        for country_info in AFRICA_TEST_COUNTRIES:
            country_name = country_info["name"]
            slug = country_info["slug"]

            email = f"africa-test-{slug}@example.test"
            username = f"africa_test_{slug.replace('-', '_')}"

            existing_user = db.query(User).filter(
                (User.email == email) | (User.username == username)
            ).first()

            if existing_user:
                user = existing_user
                print(f"[WARN] User already exists for {country_name}: id={user.id}")
            elif dry_run:
                print(f"[DRY-RUN] Would create user for {country_name}: {email}")
                user = None
            else:
                user = User(
                    email=email,
                    username=username,
                    hashed_password=get_password_hash(DEFAULT_PASSWORD),
                    full_name=f"Test User {country_name}",
                    continent="Africa",
                    country=country_name,
                    city=f"Test City {country_name}",
                    is_active=True,
                    is_verified=True,
                    status="active",
                    preferred_language="en",
                )
                db.add(user)
                db.flush()
                db.refresh(user)
                created_users.append({"id": user.id, "country": country_name})
                print(f"[OK] Created user id={user.id} for {country_name}")

            if dry_run:
                print(f"[DRY-RUN] Would create contestant for {country_name} linked to season_id={season_id}")
                continue

            # Ensure a contestant exists for this user/season combination.
            existing_contestant = (
                db.query(Contestant)
                .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
                .filter(
                    Contestant.user_id == user.id,
                    ContestantSeason.season_id == season_id,
                    Contestant.is_deleted == False,
                )
                .first()
            )

            if existing_contestant:
                print(f"[WARN] Contestant already exists for {country_name}: id={existing_contestant.id}")
                # Make sure the geographic fields are correct even for pre-existing rows.
                needs_update = False
                if existing_contestant.country != country_name:
                    existing_contestant.country = country_name
                    needs_update = True
                if existing_contestant.continent != "Africa":
                    existing_contestant.continent = "Africa"
                    needs_update = True
                if user.country != country_name:
                    user.country = country_name
                    needs_update = True
                if user.continent != "Africa":
                    user.continent = "Africa"
                    needs_update = True
                if needs_update:
                    db.commit()
                    print(f"   Updated geographic fields to {country_name}/Africa")
                continue

            contestant = Contestant(
                user_id=user.id,
                season_id=season_id,
                round_id=effective_round_id,
                title=f"Test contestant from {country_name}",
                description=f"Auto-seeded continental-level test contestant from {country_name}",
                country=country_name,
                continent="Africa",
                city=f"Test City {country_name}",
                entry_type="participation",
                verification_status="verified",
                is_active=True,
                is_qualified=True,
                is_deleted=False,
            )
            db.add(contestant)
            db.flush()
            db.refresh(contestant)

            contestant_season = ContestantSeason(
                contestant_id=contestant.id,
                season_id=season_id,
                is_active=True,
            )
            db.add(contestant_season)
            db.commit()

            created_contestants.append({"id": contestant.id, "country": country_name})
            print(f"[OK] Created contestant id={contestant.id} for {country_name} in season_id={season_id}")

        if dry_run:
            print("\n[DRY-RUN] No changes were written to the database.")
            return

        # Final verification query.
        member_ids_subq = (
            db.query(ContestantSeason.contestant_id)
            .filter(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
            )
            .scalar_subquery()
        )
        roster = (
            db.query(Contestant, User)
            .join(User, User.id == Contestant.user_id)
            .filter(
                Contestant.id.in_(member_ids_subq),
                Contestant.is_deleted == False,
            )
            .all()
        )

        print("\n" + "=" * 70)
        print("SEED SUMMARY")
        print("=" * 70)
        print(f"Target contest_id: {contest_id}")
        print(f"Continental season_id: {season_id}")
        print(f"New users created: {len(created_users)}")
        print(f"New contestants created: {len(created_contestants)}")
        print(f"Total active members in continental season: {len(roster)}")
        print("\nCountry breakdown:")
        for contestant, user in roster:
            print(f"   - contestant_id={contestant.id} | user_id={user.id} | "
                  f"country={contestant.country or user.country} | "
                  f"continent={contestant.continent or user.continent}")
        print("=" * 70)

    except Exception as exc:
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {exc}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Seed continental-level African test contestants for filter verification."
    )
    parser.add_argument(
        "--contest-id",
        type=int,
        default=int(os.getenv("SEED_CONTEST_ID", "15")),
        help="Contest ID to link the continental season to (default: 15).",
    )
    parser.add_argument(
        "--round-id",
        type=int,
        default=int(os.getenv("SEED_ROUND_ID", "3")),
        help="Round ID to attach to the created continental season (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without touching the database.",
    )
    args = parser.parse_args()

    print("[SEED] African continental test data")
    print(f"   Database: {settings.DATABASE_URL.split('@')[-1]}")
    print(f"   Contest ID: {args.contest_id}, Round ID: {args.round_id}")
    if args.dry_run:
        print("   Mode: DRY-RUN (no writes)\n")

    seed_african_test_data(
        contest_id=args.contest_id,
        round_id=args.round_id,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
