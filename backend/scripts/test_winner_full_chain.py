"""
End-to-end winner/migration chain test:
CITY -> COUNTRY -> REGIONAL -> CONTINENT -> GLOBAL

Validates tie-break order at each step:
1) stars(points)
2) shares
3) likes
4) comments
5) views
6) first contestant (lower contestant id)

Default mode is non-persistent (rollback at end).

Usage:
  cd backend
  python scripts/test_winner_full_chain.py
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import List, Dict, Tuple

import app.models  # noqa: F401

from app.db.session import SessionLocal
from app.models.user import User
from app.models.round import Round, RoundStatus
from app.models.contest import Contest, VotingRestriction, VerificationType, ParticipantType
from app.models.contests import ContestSeason, Contestant, ContestantSeason, ContestSeasonLink, SeasonLevel
from app.models.voting import ContestantVoting, ContestantShare, ContestLike, ContestComment, PageView
from app.services.season_migration import SeasonMigrationService


@contextmanager
def non_persistent_commits(db):
    original_commit = db.commit
    db.commit = db.flush  # type: ignore[assignment]
    try:
        yield
    finally:
        db.commit = original_commit  # type: ignore[assignment]


def mk_user(db, email: str, city: str, country: str, region: str, continent: str) -> User:
    u = User(
        email=email,
        hashed_password="x",
        is_active=True,
        full_name=email.split("@")[0],
        city=city,
        country=country,
        region=region,
        continent=continent,
        preferred_language="en",
    )
    db.add(u)
    db.flush()
    return u


def mk_round_contest_country_season(db, suffix: str) -> Tuple[Contest, ContestSeason]:
    r = Round(
        name=f"ChainTest Round {suffix}",
        status=RoundStatus.ACTIVE,
        is_submission_open=False,
        is_voting_open=True,
        city_season_start_date=date.today(),
        city_season_end_date=date.today(),
        country_season_start_date=date.today(),
        country_season_end_date=date.today(),
        regional_start_date=date.today(),
        regional_end_date=date.today(),
        continental_start_date=date.today(),
        continental_end_date=date.today(),
        global_start_date=date.today(),
        global_end_date=date.today(),
    )
    db.add(r)
    db.flush()

    c = Contest(
        name=f"ChainTest Contest {suffix}",
        contest_type="bongofreva",
        level="city",
        contest_mode="participation",
        is_active=True,
        is_submission_open=False,
        is_voting_open=True,
        voting_restriction=VotingRestriction.NONE,
        requires_kyc=False,
        verification_type=VerificationType.NONE,
        participant_type=ParticipantType.INDIVIDUAL,
    )
    db.add(c)
    db.flush()

    s = ContestSeason(
        title=f"ChainTest CITY Season {suffix}",
        level=SeasonLevel.CITY,
        is_deleted=False,
        round_id=r.id,
    )
    db.add(s)
    db.flush()

    db.add(
        ContestSeasonLink(
            contest_id=c.id,
            season_id=s.id,
            linked_at=datetime.now(timezone.utc),
            is_active=True,
        )
    )
    db.flush()
    return c, s


def add_votes(db, contestant_id: int, contest_id: int, season_id: int, voter_ids: List[int], points=5):
    for uid in voter_ids:
        db.add(
            ContestantVoting(
                user_id=uid,
                contestant_id=contestant_id,
                contest_id=contest_id,
                season_id=season_id,
                vote_bucket_key="cat:chain",
                vote_date=datetime.now(timezone.utc),
                position=1,
                points=points,
            )
        )
    db.flush()


def add_engagement(db, contestant: Contestant, user_ids: List[int], shares=0, likes=0, comments=0, views=0):
    if not user_ids:
        raise ValueError("user_ids cannot be empty")

    # Reuse helper users cyclically if engagement volume exceeds helper pool.
    def uid_at(pos: int) -> int:
        return user_ids[pos % len(user_ids)]

    i = 0
    for n in range(shares):
        db.add(
            ContestantShare(
                author_id=contestant.user_id,
                shared_by_user_id=uid_at(i),
                contestant_id=contestant.id,
                referral_code="chain",
                share_link=f"https://myhigh5.com/c/{contestant.id}?sh={n}",
                platform="test",
                user_id=contestant.user_id,
            )
        )
        i += 1
    for _ in range(likes):
        db.add(ContestLike(user_id=uid_at(i), contestant_id=contestant.id))
        i += 1
    for n in range(comments):
        db.add(
            ContestComment(
                user_id=uid_at(i),
                contestant_id=contestant.id,
                content=f"c{contestant.id}-{n}",
                is_approved=True,
            )
        )
        i += 1
    for n in range(views):
        db.add(
            PageView(
                user_id=uid_at(i),
                contestant_id=contestant.id,
                ip_address=f"10.9.{contestant.id % 255}.{(n + 1) % 255}",
                user_agent="chain-test",
                viewed_at=datetime.now(timezone.utc),
            )
        )
        i += 1
    db.flush()


def run_chain_test(persist: bool = False):
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    db = SessionLocal()
    try:
        ctx = contextmanager(lambda: (yield))() if persist else non_persistent_commits(db)
        with ctx:
            # 6 contestants across 2 cities (same country/region/continent) to test chain
            # city A: c1,c2,c3 ; city B: c4,c5,c6
            users = [
                mk_user(db, f"chain_u1_{suffix}@e.com", "CityA", "TZ", "EA", "AF"),
                mk_user(db, f"chain_u2_{suffix}@e.com", "CityA", "TZ", "EA", "AF"),
                mk_user(db, f"chain_u3_{suffix}@e.com", "CityA", "TZ", "EA", "AF"),
                mk_user(db, f"chain_u4_{suffix}@e.com", "CityB", "TZ", "EA", "AF"),
                mk_user(db, f"chain_u5_{suffix}@e.com", "CityB", "TZ", "EA", "AF"),
                mk_user(db, f"chain_u6_{suffix}@e.com", "CityB", "TZ", "EA", "AF"),
            ]
            voters = [
                mk_user(db, f"chain_v1_{suffix}@e.com", "X", "TZ", "EA", "AF"),
                mk_user(db, f"chain_v2_{suffix}@e.com", "X", "TZ", "EA", "AF"),
                mk_user(db, f"chain_v3_{suffix}@e.com", "X", "TZ", "EA", "AF"),
                mk_user(db, f"chain_v4_{suffix}@e.com", "X", "TZ", "EA", "AF"),
            ]
            support = [mk_user(db, f"chain_s{i}_{suffix}@e.com", "X", "TZ", "EA", "AF") for i in range(1, 180)]

            contest, city_season = mk_round_contest_country_season(db, suffix)

            contestants: List[Contestant] = []
            for i, u in enumerate(users, start=1):
                ct = Contestant(
                    user_id=u.id,
                    round_id=None,
                    season_id=contest.id,
                    title=f"Chain Contestant {i}",
                    entry_type="participation",
                    is_active=True,
                    is_qualified=True,
                    is_deleted=False,
                )
                db.add(ct)
                db.flush()
                db.add(
                    ContestantSeason(
                        contestant_id=ct.id,
                        season_id=city_season.id,
                        joined_at=datetime.now(timezone.utc),
                        is_active=True,
                    )
                )
                contestants.append(ct)
            db.flush()

            voter_ids = [v.id for v in voters]
            for ct in contestants:
                add_votes(db, ct.id, contest.id, city_season.id, voter_ids, points=5)  # same stars

            # Tie-break setup in CITY season:
            # city A: c1 wins by shares > c2 > c3
            # city B: c5 wins by views over c4 ; c6 lower
            plan: Dict[int, Dict[str, int]] = {
                contestants[0].id: {"shares": 5, "likes": 0, "comments": 0, "views": 0},     # c1
                contestants[1].id: {"shares": 4, "likes": 2, "comments": 0, "views": 0},     # c2
                contestants[2].id: {"shares": 4, "likes": 1, "comments": 0, "views": 0},     # c3
                contestants[3].id: {"shares": 4, "likes": 2, "comments": 1, "views": 50},    # c4
                contestants[4].id: {"shares": 4, "likes": 2, "comments": 1, "views": 100},   # c5
                contestants[5].id: {"shares": 3, "likes": 0, "comments": 0, "views": 0},     # c6
            }
            support_ids = [u.id for u in support]
            for ct in contestants:
                p = plan[ct.id]
                add_engagement(db, ct, support_ids, **p)

            # CITY -> COUNTRY
            r1 = SeasonMigrationService.promote_to_next_level(
                db, SeasonLevel.CITY, SeasonLevel.COUNTRY, contest.id, limit=5
            )
            if "error" in r1:
                raise RuntimeError(f"CITY->COUNTRY failed: {r1['error']}")
            promoted_country = r1.get("promoted_contestant_ids", [])
            # CITY -> COUNTRY is grouped per city. With limit=5 and 3 contestants per city,
            # all six are promoted; validate order INSIDE each city group.
            idx = {cid: i for i, cid in enumerate(promoted_country)}
            # CityA order expected: c1 > c2 > c3
            assert idx[contestants[0].id] < idx[contestants[1].id] < idx[contestants[2].id], (
                f"Unexpected CityA order in CITY->COUNTRY: {promoted_country}"
            )
            # CityB order expected: c5 > c4 > c6 (views tie-break between c5/c4)
            assert idx[contestants[4].id] < idx[contestants[3].id] < idx[contestants[5].id], (
                f"Unexpected CityB order in CITY->COUNTRY: {promoted_country}"
            )

            # COUNTRY -> REGIONAL
            r2 = SeasonMigrationService.promote_to_next_level(
                db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, limit=5
            )
            if "error" in r2:
                raise RuntimeError(f"COUNTRY->REGIONAL failed: {r2['error']}")

            # REGIONAL -> CONTINENT
            r3 = SeasonMigrationService.promote_to_next_level(
                db, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, contest.id, limit=5
            )
            if "error" in r3:
                raise RuntimeError(f"REGIONAL->CONTINENT failed: {r3['error']}")

            # CONTINENT -> GLOBAL (limit 3 by service/global behavior)
            r4 = SeasonMigrationService.promote_to_next_level(
                db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, contest.id, limit=3
            )
            if "error" in r4:
                raise RuntimeError(f"CONTINENT->GLOBAL failed: {r4['error']}")

            promoted_global = r4.get("promoted_contestant_ids", [])
            expected_top_global = [contestants[0].id, contestants[4].id, contestants[3].id]
            assert promoted_global == expected_top_global, (
                f"Unexpected GLOBAL winners.\nExpected: {expected_top_global}\nGot: {promoted_global}"
            )

            print("\n=== Full Chain Migration Test ===")
            print(f"CITY->COUNTRY promoted: {promoted_country}")
            print(f"CONTINENT->GLOBAL winners: {promoted_global}")
            print("PASS: full chain + tie-break rules validated.")

        if not persist:
            db.rollback()
            print("Rollback complete (non-persistent mode).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full chain winner/migration test")
    parser.add_argument("--persist", action="store_true", help="Persist inserted data.")
    args = parser.parse_args()
    run_chain_test(persist=args.persist)

