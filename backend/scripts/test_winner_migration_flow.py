"""
Script to test winner determination + migration promotion order.

Business order validated by this script:
1) stars(points)
2) shares
3) likes
4) comments
5) views
6) first contestant (lower contestant id)

Default mode is NON-PERSISTENT:
- The script monkey-patches db.commit() -> db.flush()
- At the end it rolls back all inserted test data

Usage:
  cd backend
  python scripts/test_winner_migration_flow.py

Optional persistent mode (not recommended on production DB):
  python scripts/test_winner_migration_flow.py --persist
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime
from typing import Dict, List

# Ensure mappers are loaded
import app.models  # noqa: F401

from app.db.session import SessionLocal
from app.models.user import User
from app.models.round import Round, RoundStatus
from app.models.contest import Contest, VotingRestriction, VerificationType, ParticipantType
from app.models.contests import (
    ContestSeason,
    Contestant,
    ContestantSeason,
    ContestSeasonLink,
    SeasonLevel,
)
from app.models.voting import (
    ContestantVoting,
    ContestantShare,
    ContestLike,
    ContestComment,
    PageView,
)
from app.services.season_migration import SeasonMigrationService


@contextmanager
def non_persistent_commits(db):
    """
    Replace commit with flush so service code can run normally
    while keeping this script rollback-safe.
    """
    original_commit = db.commit
    db.commit = db.flush  # type: ignore[assignment]
    try:
        yield
    finally:
        db.commit = original_commit  # type: ignore[assignment]


def _create_user(db, idx: int, suffix: str) -> User:
    u = User(
        email=f"winner_test_user_{suffix}_{idx}@example.com",
        hashed_password="x",
        is_active=True,
        full_name=f"Winner Test User {idx}",
        country="TZ",
        city="Dar es Salaam",
        region="East Africa",
        continent="Africa",
        preferred_language="en",
    )
    db.add(u)
    db.flush()
    return u


def _create_contest_bundle(db, suffix: str):
    # Minimal round + contest + source season + active season link
    r = Round(
        name=f"Winner Test Round {suffix}",
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
        name=f"Winner Test Contest {suffix}",
        contest_type="bongofreva",
        level="country",
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

    src = ContestSeason(
        title=f"Test Country Season {suffix}",
        level=SeasonLevel.COUNTRY,
        is_deleted=False,
        round_id=r.id,
    )
    db.add(src)
    db.flush()

    db.add(
        ContestSeasonLink(
            contest_id=c.id,
            season_id=src.id,
            linked_at=datetime.utcnow(),
            is_active=True,
        )
    )
    db.flush()
    return c, src


def _add_votes(db, contestant_id: int, contest_id: int, season_id: int, voter_ids: List[int], points_each: int = 5):
    # Keep total stars equal across contestants for tie-break tests
    for uid in voter_ids:
        db.add(
            ContestantVoting(
                user_id=uid,
                contestant_id=contestant_id,
                contest_id=contest_id,
                season_id=season_id,
                vote_bucket_key="cat:test",
                vote_date=datetime.utcnow(),
                position=1,
                points=points_each,
            )
        )
    db.flush()


def _add_engagement(
    db,
    contestant: Contestant,
    support_user_ids: List[int],
    shares: int,
    likes: int,
    comments: int,
    views: int,
):
    if not support_user_ids:
        raise ValueError("support_user_ids cannot be empty")

    # Reuse helper users cyclically if we need more events than available IDs.
    def next_uid(pos: int) -> int:
        return support_user_ids[pos % len(support_user_ids)]

    idx = 0
    for i in range(shares):
        uid = next_uid(idx)
        idx += 1
        db.add(
            ContestantShare(
                author_id=contestant.user_id,
                shared_by_user_id=uid,
                contestant_id=contestant.id,
                referral_code="test",
                share_link=f"https://myhigh5.com/c/{contestant.id}?s={i}",
                platform="test",
                user_id=contestant.user_id,
            )
        )
    for i in range(likes):
        uid = next_uid(idx)
        idx += 1
        db.add(ContestLike(user_id=uid, contestant_id=contestant.id))
    for i in range(comments):
        uid = next_uid(idx)
        idx += 1
        db.add(
            ContestComment(
                user_id=uid,
                contestant_id=contestant.id,
                content=f"test comment {i} for contestant {contestant.id}",
                is_approved=True,
            )
        )
    for i in range(views):
        uid = next_uid(idx)
        idx += 1
        db.add(
            PageView(
                user_id=uid,
                contestant_id=contestant.id,
                ip_address=f"10.10.{contestant.id % 255}.{(i + 1) % 255}",
                user_agent="winner-test-script",
                viewed_at=datetime.utcnow(),
            )
        )
    db.flush()


def run_test(persist: bool = False):
    suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    db = SessionLocal()
    try:
        ctx = contextmanager(lambda: (yield))() if persist else non_persistent_commits(db)
        with ctx:
            # Create contestants and support users
            contestant_users = [_create_user(db, i, suffix) for i in range(1, 7)]
            voter_users = [_create_user(db, 100 + i, suffix) for i in range(1, 5)]  # 4 voters => 20 stars each
            support_users = [_create_user(db, 200 + i, suffix) for i in range(1, 120)]  # enough engagement rows

            contest, from_season = _create_contest_bundle(db, suffix)

            contestants: List[Contestant] = []
            for i, u in enumerate(contestant_users, start=1):
                ct = Contestant(
                    user_id=u.id,
                    round_id=None,
                    season_id=contest.id,
                    title=f"Contestant {i}",
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
                        season_id=from_season.id,
                        joined_at=datetime.utcnow(),
                        is_active=True,
                    )
                )
                contestants.append(ct)
            db.flush()

            voter_ids = [u.id for u in voter_users]
            for ct in contestants:
                _add_votes(db, ct.id, contest.id, from_season.id, voter_ids, points_each=5)

            # Engagement profile (all have same stars=20)
            # c1 wins on shares
            # c5 beats c4 on views after shares/likes/comments ties
            # c3 vs c6 fully tied on all metrics => lower id first
            engagement_plan: Dict[int, Dict[str, int]] = {
                contestants[0].id: {"shares": 5, "likes": 0, "comments": 0, "views": 0},    # c1
                contestants[1].id: {"shares": 4, "likes": 10, "comments": 0, "views": 0},   # c2
                contestants[2].id: {"shares": 4, "likes": 8, "comments": 0, "views": 0},    # c3
                contestants[3].id: {"shares": 4, "likes": 10, "comments": 2, "views": 50},  # c4
                contestants[4].id: {"shares": 4, "likes": 10, "comments": 2, "views": 100}, # c5
                contestants[5].id: {"shares": 4, "likes": 8, "comments": 0, "views": 0},    # c6 (tie with c3)
            }

            support_ids = [u.id for u in support_users]
            cursor = 0
            for ct in contestants:
                plan = engagement_plan[ct.id]
                needed = plan["shares"] + plan["likes"] + plan["comments"] + plan["views"]
                batch = support_ids[cursor: cursor + needed]
                cursor += needed
                _add_engagement(
                    db,
                    contestant=ct,
                    support_user_ids=batch,
                    shares=plan["shares"],
                    likes=plan["likes"],
                    comments=plan["comments"],
                    views=plan["views"],
                )

            result = SeasonMigrationService.promote_to_next_level(
                db=db,
                from_level=SeasonLevel.COUNTRY,
                to_level=SeasonLevel.REGIONAL,
                contest_id=contest.id,
                limit=6,  # include all contestants to verify full order
            )

            if "error" in result:
                raise RuntimeError(f"Promotion failed: {result['error']}")

            promoted_ids = result.get("promoted_contestant_ids", [])
            expected = [
                contestants[0].id,  # c1: best shares
                contestants[4].id,  # c5: same shares/likes/comments as c4, better views
                contestants[3].id,  # c4
                contestants[1].id,  # c2
                contestants[2].id,  # c3 (tie with c6 -> lower id wins)
                contestants[5].id,  # c6
            ]

            print("\n=== Winner/Migration Test ===")
            print(f"Contest ID: {contest.id}")
            print(f"From season ID: {from_season.id} (country)")
            print(f"Promoted IDs: {promoted_ids}")
            print(f"Expected IDs: {expected}")

            assert promoted_ids == expected, (
                "Promotion order mismatch.\n"
                f"Expected: {expected}\n"
                f"Got:      {promoted_ids}"
            )

            print("PASS: winner tie-break + migration promotion order matches business rules.")

        if not persist:
            db.rollback()
            print("Rollback complete (non-persistent mode).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test winner determination + migration flow")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist test data (default is rollback/non-persistent).",
    )
    args = parser.parse_args()
    run_test(persist=args.persist)

