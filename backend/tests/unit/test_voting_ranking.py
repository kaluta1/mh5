from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    ContestStage,
    ContestStageLevel,
    ContestStatus,
    Contestant,
    SeasonLevel,
)
from app.models.user import User
from app.models.voting import (
    ContestComment,
    ContestLike,
    ContestantReaction,
    ContestantShare,
    ContestantVoting,
    PageView,
    Vote,
    VoteStatus,
)
from app.models.comment import Comment
from app.services.voting_ranking import (
    RankingRow,
    VotingConflict,
    VotingValidationError,
    aggregate_rankings,
    _engagement,
    bucket_key_for_contest,
    cast_myhigh5_vote,
    invalidate_ranking_cache,
    points_for_position,
    rank_rows,
    reorder_myhigh5_votes,
    replace_fifth_myhigh5_vote,
)


def _user(db, suffix: str) -> User:
    user = User(email=f"{suffix}@example.test", hashed_password="not-used")
    db.add(user)
    db.flush()
    return user


def _scope(db):
    voter = _user(db, "voter")
    owners = [_user(db, f"owner-{index}") for index in range(1, 9)]
    contest = Contest(
        name="Canonical contest",
        contest_type="beauty",
        level="country",
        contest_mode="nomination",
        category_id=None,
    )
    db.add(contest)
    db.flush()
    season = ContestSeason(title="September 2026", level=SeasonLevel.COUNTRY)
    other_season = ContestSeason(title="October 2026", level=SeasonLevel.COUNTRY)
    db.add_all([season, other_season])
    db.flush()
    now = datetime.utcnow()
    stage = ContestStage(
        season_id=season.id,
        stage_level=ContestStageLevel.COUNTRY,
        status=ContestStatus.VOTING_ACTIVE,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
    )
    other_stage = ContestStage(
        season_id=other_season.id,
        stage_level=ContestStageLevel.COUNTRY,
        status=ContestStatus.VOTING_ACTIVE,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
    )
    db.add_all([stage, other_stage])
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()
    contestants = []
    for index, owner in enumerate(owners, start=1):
        contestant = Contestant(
            user_id=owner.id,
            season_id=season.id,
            title=f"Contestant {index}",
        )
        db.add(contestant)
        contestants.append(contestant)
    db.flush()
    return voter, owners, contest, season, other_season, stage, other_stage, contestants


def _cast(db, scope, index: int):
    voter, owners, contest, season, _, _, _, contestants = scope
    return cast_myhigh5_vote(
        db,
        voter_id=voter.id,
        contestant_id=contestants[index].id,
        nominator_user_id=owners[index].id,
        season_id=season.id,
        contest_id=contest.id,
        bucket_key=bucket_key_for_contest(contest),
    )


def test_valid_vote_is_scoped_and_server_scored(db):
    scope = _scope(db)
    vote = _cast(db, scope, 0)
    assert vote.position == 1
    assert vote.points == 5
    assert vote.season_id == scope[3].id
    assert vote.contest_id == scope[2].id


def test_duplicate_vote_returns_stable_conflict(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    with pytest.raises(VotingConflict, match="already voted") as error:
        _cast(db, scope, 0)
    assert error.value.code == "already_voted"


def test_database_unique_constraint_is_final_duplicate_authority(db):
    scope = _scope(db)
    first = _cast(db, scope, 0)
    db.flush()
    duplicate = ContestantVoting(
        user_id=first.user_id,
        contestant_id=first.contestant_id,
        contest_id=first.contest_id,
        season_id=first.season_id,
        vote_bucket_key=first.vote_bucket_key,
        position=2,
        points=4,
    )
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(duplicate)
            db.flush()


def test_five_slot_limit_is_rechecked_under_voter_lock(db):
    scope = _scope(db)
    for index in range(5):
        _cast(db, scope, index)
    with pytest.raises(VotingConflict) as error:
        _cast(db, scope, 5)
    assert error.value.code == "max_votes_reached"


def test_five_slot_limit_is_shared_by_same_category_bucket(db):
    scope = _scope(db)
    for index in range(5):
        _cast(db, scope, index)
    same_category_contest = Contest(
        name="Same category, another page",
        contest_type=scope[2].contest_type,
        level="country",
        contest_mode=scope[2].contest_mode,
        category_id=scope[2].category_id,
    )
    db.add(same_category_contest)
    db.flush()
    with pytest.raises(VotingConflict) as error:
        cast_myhigh5_vote(
            db,
            voter_id=scope[0].id,
            contestant_id=scope[-1][5].id,
            nominator_user_id=scope[1][5].id,
            season_id=scope[3].id,
            contest_id=same_category_contest.id,
            bucket_key=bucket_key_for_contest(same_category_contest),
        )
    assert error.value.code == "max_votes_reached"


def test_same_nominator_cannot_fill_two_slots(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    second = scope[-1][1]
    second.user_id = scope[1][0].id
    db.flush()
    with pytest.raises(VotingConflict, match="nominator"):
        cast_myhigh5_vote(
            db,
            voter_id=scope[0].id,
            contestant_id=second.id,
            nominator_user_id=second.user_id,
            season_id=scope[3].id,
            contest_id=scope[2].id,
            bucket_key=bucket_key_for_contest(scope[2]),
        )


@pytest.mark.parametrize("position,points", [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)])
def test_server_side_point_calculation(position, points):
    assert points_for_position(position) == points


@pytest.mark.parametrize("position", [0, 6, -1, 100])
def test_invalid_ranking_position_is_rejected(position):
    with pytest.raises(VotingValidationError):
        points_for_position(position)


def test_missing_voter_is_rejected(db):
    scope = _scope(db)
    with pytest.raises(VotingValidationError, match="Voter"):
        cast_myhigh5_vote(
            db,
            voter_id=999999,
            contestant_id=scope[-1][0].id,
            nominator_user_id=scope[1][0].id,
            season_id=scope[3].id,
            contest_id=scope[2].id,
            bucket_key=bucket_key_for_contest(scope[2]),
        )


def test_replace_fifth_vote_is_one_transactional_mutation(db):
    scope = _scope(db)
    for index in range(5):
        _cast(db, scope, index)
    replacement, removed_id = replace_fifth_myhigh5_vote(
        db,
        voter_id=scope[0].id,
        contestant_id=scope[-1][5].id,
        nominator_user_id=scope[1][5].id,
        season_id=scope[3].id,
        contest_id=scope[2].id,
        bucket_key=bucket_key_for_contest(scope[2]),
    )
    assert removed_id == scope[-1][4].id
    assert replacement.position == 5
    assert replacement.points == 1
    assert db.query(ContestantVoting).filter_by(user_id=scope[0].id).count() == 5


def test_replace_requires_five_votes(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    with pytest.raises(VotingValidationError, match="less than 5"):
        replace_fifth_myhigh5_vote(
            db,
            voter_id=scope[0].id,
            contestant_id=scope[-1][1].id,
            nominator_user_id=scope[1][1].id,
            season_id=scope[3].id,
            contest_id=scope[2].id,
            bucket_key=bucket_key_for_contest(scope[2]),
        )


def test_reorder_recalculates_all_points(db):
    scope = _scope(db)
    for index in range(3):
        _cast(db, scope, index)
    ordered = [scope[-1][2].id, scope[-1][0].id, scope[-1][1].id]
    votes = reorder_myhigh5_votes(
        db,
        voter_id=scope[0].id,
        season_id=scope[3].id,
        contest_id=scope[2].id,
        bucket_key=bucket_key_for_contest(scope[2]),
        ordered_contestant_ids=ordered,
    )
    assert [(vote.contestant_id, vote.position, vote.points) for vote in votes] == [
        (ordered[0], 1, 5),
        (ordered[1], 2, 4),
        (ordered[2], 3, 3),
    ]


def test_reorder_rejects_partial_or_cross_scope_set(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    _cast(db, scope, 1)
    with pytest.raises(VotingValidationError, match="exactly"):
        reorder_myhigh5_votes(
            db,
            voter_id=scope[0].id,
            season_id=scope[3].id,
            contest_id=scope[2].id,
            bucket_key=bucket_key_for_contest(scope[2]),
            ordered_contestant_ids=[scope[-1][0].id],
        )


def test_ranking_order_and_deterministic_tie():
    rows = rank_rows(
        [
            RankingRow(9, total_points=10, total_votes=2),
            RankingRow(3, total_points=10, total_votes=2),
            RankingRow(2, total_points=9, total_votes=9),
        ]
    )
    assert [row.contestant_id for row in rows] == [3, 9, 2]
    assert [row.rank for row in rows] == [1, 2, 3]


def test_engagement_breaks_equal_vote_totals_deterministically():
    rows = rank_rows(
        [
            RankingRow(1, total_points=5, total_votes=1, shares=2),
            RankingRow(2, total_points=5, total_votes=1, shares=3),
        ]
    )
    assert [row.contestant_id for row in rows] == [2, 1]


def test_engagement_is_batched_into_one_sql_round_trip(db):
    scope = _scope(db)
    contestant = scope[-1][0]
    user = scope[0]
    now = datetime.utcnow()
    db.add_all(
        [
            ContestantShare(
                contestant_id=contestant.id,
                shared_by_user_id=user.id,
                share_link="https://example.test/share",
                created_at=now,
            ),
            ContestLike(user_id=user.id, contestant_id=contestant.id, created_at=now),
            ContestantReaction(
                user_id=user.id,
                contestant_id=contestant.id,
                reaction_type="love",
                created_at=now,
            ),
            ContestComment(
                user_id=user.id,
                contestant_id=contestant.id,
                content="legacy",
                created_at=now,
            ),
            Comment(
                user_id=user.id,
                contestant_id=contestant.id,
                content="current",
                created_at=now,
            ),
            PageView(user_id=user.id, contestant_id=contestant.id, viewed_at=now),
        ]
    )
    db.flush()

    selects = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count_selects)
    try:
        totals = _engagement(
            db,
            [contestant.id],
            start_at=now - timedelta(seconds=1),
            end_at=now + timedelta(seconds=1),
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_selects)

    assert totals[contestant.id] == {
        "shares": 1,
        "likes": 2,
        "comments": 2,
        "views": 1,
    }
    assert len(selects) == 1


def test_top_high5_limit_is_applied_after_complete_ordering():
    rows = [RankingRow(i, total_points=i) for i in range(1, 10)]
    assert [row.contestant_id for row in rank_rows(rows, limit=5)] == [9, 8, 7, 6, 5]


def test_repeated_top_five_selection_is_idempotent():
    rows = [RankingRow(i, total_points=10) for i in range(1, 8)]
    first = rank_rows(rows, limit=5)
    second = rank_rows(reversed(rows), limit=5)
    assert first == second


def test_historical_votes_are_included_without_copying(db):
    scope = _scope(db)
    historical = Vote(
        voter_id=scope[0].id,
        contestant_id=scope[-1][0].id,
        stage_id=scope[5].id,
        rank_position=10,
        points=10,
        status=VoteStatus.ACTIVE,
    )
    db.add(historical)
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[scope[-1][0].id, scope[-1][1].id],
    )
    assert rows[0].contestant_id == scope[-1][0].id
    assert rows[0].total_points == 10
    assert rows[0].total_votes == 1


def test_current_and_historical_vote_facts_share_one_ranking_engine(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    db.add(
        Vote(
            voter_id=scope[1][7].id,
            contestant_id=scope[-1][1].id,
            stage_id=scope[5].id,
            rank_position=1,
            points=8,
            status=VoteStatus.ACTIVE,
        )
    )
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[scope[-1][0].id, scope[-1][1].id],
        contest_id=scope[2].id,
        bucket_key=bucket_key_for_contest(scope[2]),
    )
    assert [(row.contestant_id, row.total_points) for row in rows] == [
        (scope[-1][1].id, 8),
        (scope[-1][0].id, 5),
    ]


def test_ambiguous_historical_votes_are_not_assigned_to_one_contest(db):
    scope = _scope(db)
    other = Contest(
        name="Other linked contest",
        contest_type="music",
        level="country",
        contest_mode="nomination",
    )
    db.add(other)
    db.flush()
    db.add(
        ContestSeasonLink(
            contest_id=other.id, season_id=scope[3].id, is_active=True
        )
    )
    db.add(
        Vote(
            voter_id=scope[0].id,
            contestant_id=scope[-1][0].id,
            stage_id=scope[5].id,
            rank_position=1,
            points=50,
            status=VoteStatus.ACTIVE,
        )
    )
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[scope[-1][0].id],
        contest_id=scope[2].id,
    )
    assert rows[0].total_points == 0
    assert rows[0].total_votes == 0


def test_top_five_never_promotes_zero_vote_rows(db):
    scope = _scope(db)
    assert aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[candidate.id for candidate in scope[-1]],
        contest_id=scope[2].id,
        require_votes=True,
        limit=5,
    ) == []


def test_season_and_stage_isolation(db):
    scope = _scope(db)
    db.add_all(
        [
            Vote(
                voter_id=scope[0].id,
                contestant_id=scope[-1][0].id,
                stage_id=scope[5].id,
                rank_position=1,
                points=5,
                status=VoteStatus.ACTIVE,
            ),
            Vote(
                voter_id=scope[0].id,
                contestant_id=scope[-1][1].id,
                stage_id=scope[6].id,
                rank_position=1,
                points=10,
                status=VoteStatus.ACTIVE,
            ),
        ]
    )
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        stage_ids=[scope[5].id],
        contestant_ids=[scope[-1][0].id, scope[-1][1].id],
    )
    assert rows[0].contestant_id == scope[-1][0].id
    assert rows[1].total_points == 0


def test_current_season_isolation(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    db.add(
        ContestantVoting(
            user_id=scope[0].id,
            contestant_id=scope[-1][1].id,
            contest_id=scope[2].id,
            season_id=scope[4].id,
            vote_bucket_key=bucket_key_for_contest(scope[2]),
            position=1,
            points=99,
        )
    )
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[scope[-1][0].id, scope[-1][1].id],
        contest_id=scope[2].id,
        bucket_key=bucket_key_for_contest(scope[2]),
    )
    assert rows[0].contestant_id == scope[-1][0].id
    assert rows[1].total_points == 0


def test_contest_bucket_isolation(db):
    scope = _scope(db)
    other_contest = Contest(
        name="Other", contest_type="music", level="country", contest_mode="nomination"
    )
    db.add(other_contest)
    db.flush()
    db.add(
        ContestantVoting(
            user_id=scope[0].id,
            contestant_id=scope[-1][1].id,
            contest_id=other_contest.id,
            season_id=scope[3].id,
            vote_bucket_key=bucket_key_for_contest(other_contest),
            position=1,
            points=99,
        )
    )
    db.flush()
    rows = aggregate_rankings(
        db,
        season_ids=[scope[3].id],
        contestant_ids=[scope[-1][0].id, scope[-1][1].id],
        contest_id=scope[2].id,
        bucket_key=bucket_key_for_contest(scope[2]),
    )
    assert all(row.total_points == 0 for row in rows)


def test_cache_invalidation_is_scoped_and_fail_soft(monkeypatch):
    from app.core.cache import cache_service

    calls = []
    monkeypatch.setattr(cache_service, "delete_pattern", lambda key: calls.append(key))
    monkeypatch.setattr(cache_service, "invalidate_contest", lambda value: calls.append(value))
    invalidate_ranking_cache(season_id=12, contest_id=34)
    assert calls == ["cache:ranking:season:12:contest:34:*", 34]


def test_vote_route_requires_authentication(client):
    response = client.post("/api/v1/contestants/1/vote")
    assert response.status_code == 401


def test_legacy_contest_vote_route_is_not_registered(app):
    paths = {route.path for route in app.routes}
    assert "/api/v1/votes/{contest_id}" not in paths
