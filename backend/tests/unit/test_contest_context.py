from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    ContestStage,
    ContestStageLevel,
    ContestStatus,
    Contestant,
    ContestantSeason,
    SeasonLevel,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.models.voting import ContestantVoting, Vote, VoteStatus
from app.services.contest_context import (
    AmbiguousContestContext,
    AttributionClass,
    ContestContextError,
    ContestContextNotFound,
    add_months,
    contest_context_service,
)
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"context-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _period(db, *, month: int = 8, contest_count: int = 1):
    start = date(2026, month, 1)
    rnd = Round(
        name=f"Round {start:%Y-%m}",
        status=RoundStatus.ACTIVE,
        submission_start_date=start,
        submission_end_date=add_months(start, 1) - timedelta(days=1),
    )
    db.add(rnd)
    db.flush()
    contests = []
    for index in range(contest_count):
        contest = Contest(
            name=f"Contest {index}",
            contest_type=f"type-{index}",
            contest_mode="nomination",
            level="country",
        )
        db.add(contest)
        db.flush()
        db.execute(
            round_contests.insert().values(round_id=rnd.id, contest_id=contest.id)
        )
        contests.append(contest)
    season = ContestSeason(
        round_id=rnd.id,
        title=f"Country {start:%Y-%m}",
        level=SeasonLevel.COUNTRY,
    )
    db.add(season)
    db.flush()
    for contest in contests:
        db.add(
            ContestSeasonLink(
                contest_id=contest.id, season_id=season.id, is_active=True
            )
        )
    stage = ContestStage(
        season_id=season.id,
        stage_level=ContestStageLevel.COUNTRY,
        status=ContestStatus.VOTING_ACTIVE,
        start_date=datetime(2026, month, 1),
        end_date=datetime(2026, month, 28, 23, 59, 59),
    )
    db.add(stage)
    owner = _user(db, f"owner-{month}-{contest_count}")
    voter = _user(db, f"voter-{month}-{contest_count}")
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,
        title="Candidate",
    )
    db.add(contestant)
    db.flush()
    db.add(
        ContestantSeason(
            contestant_id=contestant.id, season_id=season.id, is_active=True
        )
    )
    db.flush()
    vote = Vote(
        voter_id=voter.id,
        contestant_id=contestant.id,
        stage_id=stage.id,
        rank_position=1,
        points=5,
        vote_date=datetime(2026, month, 15),
        status=VoteStatus.ACTIVE,
    )
    db.add(vote)
    db.flush()
    return rnd, contests, season, stage, contestant, voter, vote


def test_current_submission_round_is_exact(db):
    august = _period(db)[0]
    resolved = contest_context_service.resolve_current_submission_round(
        db, today=date(2026, 8, 20)
    )
    assert resolved.id == august.id


def test_duplicate_current_round_is_rejected_not_silently_selected(db):
    _period(db)
    duplicate = Round(
        name="Duplicate August",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 8, 1),
    )
    db.add(duplicate)
    db.flush()
    with pytest.raises(AmbiguousContestContext) as error:
        contest_context_service.resolve_submission_round(db, date(2026, 8, 10))
    assert len(error.value.candidate_ids) == 2


def test_missing_current_round_is_explicit(db):
    with pytest.raises(ContestContextNotFound):
        contest_context_service.resolve_submission_round(db, date(2030, 1, 1))


def test_vote_cohort_uses_level_month_offset(db):
    august = _period(db, month=8)[0]
    resolved = contest_context_service.resolve_vote_round(
        db, SeasonLevel.COUNTRY, today=date(2026, 9, 8)
    )
    assert resolved.id == august.id


def test_contest_season_resolution_rejects_duplicate_links(db):
    rnd, contests, season, *_ = _period(db)
    duplicate = ContestSeason(
        round_id=rnd.id, title="Duplicate season", level=SeasonLevel.COUNTRY
    )
    db.add(duplicate)
    db.flush()
    db.add(
        ContestSeasonLink(
            contest_id=contests[0].id, season_id=duplicate.id, is_active=True
        )
    )
    db.flush()
    with pytest.raises(AmbiguousContestContext):
        contest_context_service.resolve_contest_season(
            db,
            contest_id=contests[0].id,
            round_id=rnd.id,
            level=SeasonLevel.COUNTRY,
        )


def test_period_resolution_proves_full_identity(db):
    rnd, contests, season, stage, *_ = _period(db)
    context = contest_context_service.resolve_period(
        db,
        contest_id=contests[0].id,
        round_id=rnd.id,
        season_id=season.id,
        stage_id=stage.id,
    )
    assert (context.contest_id, context.round_id, context.season_id, context.stage_id) == (
        contests[0].id,
        rnd.id,
        season.id,
        stage.id,
    )
    assert context.category_key == "type:type-0:mode:nomination"


def test_period_resolution_rejects_wrong_round(db):
    rnd, contests, season, stage, *_ = _period(db)
    with pytest.raises(ContestContextError, match="round"):
        contest_context_service.resolve_period(
            db,
            contest_id=contests[0].id,
            round_id=rnd.id + 999,
            season_id=season.id,
            stage_id=stage.id,
        )


def test_historical_vote_is_exact_with_one_contest_candidate(db):
    *_, vote = _period(db, contest_count=1)
    result = contest_context_service.resolve_historical_vote(db, vote)
    assert result.classification == AttributionClass.EXACT
    assert result.contest_id == result.candidate_contest_ids[0]


def test_historical_vote_is_ambiguous_with_shared_period(db):
    *_, vote = _period(db, contest_count=2)
    result = contest_context_service.resolve_historical_vote(db, vote)
    assert result.classification == AttributionClass.AMBIGUOUS
    assert result.contest_id is None
    assert len(result.candidate_contest_ids) == 2


def test_historical_vote_accepts_unique_temporal_contest_as_strong_evidence(db):
    _, contests, _, _, _, _, vote = _period(db, contest_count=2)
    contests[0].voting_start_date = date(2026, 8, 1)
    contests[0].voting_end_date = date(2026, 8, 31)
    contests[1].voting_start_date = date(2026, 9, 1)
    contests[1].voting_end_date = date(2026, 9, 30)
    db.flush()
    assert contests[0].voting_start_date <= vote.vote_date.date() <= contests[0].voting_end_date
    assert [
        (row.id, row.voting_start_date, row.voting_end_date)
        for row in db.query(Contest).filter(Contest.id.in_([c.id for c in contests])).all()
    ][0][1] == date(2026, 8, 1)
    assert {
        row.id
        for row in db.query(Contest).filter(Contest.id.in_([c.id for c in contests])).all()
        if row.voting_start_date <= vote.vote_date.date() <= row.voting_end_date
    } == {contests[0].id}
    assert db.query(Contest.id).filter(
        Contest.id.in_([c.id for c in contests]),
        Contest.voting_start_date <= vote.vote_date.date(),
        Contest.voting_end_date >= vote.vote_date.date(),
    ).all() == [(contests[0].id,)]
    result = contest_context_service.resolve_historical_vote(db, vote)
    assert result.classification == AttributionClass.STRONG, result
    assert result.contest_id == contests[0].id


def test_shared_period_roster_does_not_treat_vote_as_membership(db):
    _, contests, season, _, contestant, _, _ = _period(db, contest_count=2)
    roster = contest_context_service.resolve_period_roster(
        db, contest_id=contests[0].id, season_id=season.id
    )
    assert contestant.id not in roster.contestant_ids
    assert roster.evidence == "no contest-specific roster evidence"


def test_contextual_vote_is_exact_current_roster_evidence(db):
    _, contests, season, _, contestant, voter, _ = _period(db, contest_count=2)
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=contestant.id,
            contest_id=contests[0].id,
            season_id=season.id,
            vote_bucket_key="cat:test",
            position=1,
            points=5,
        )
    )
    db.flush()
    roster = contest_context_service.resolve_period_roster(
        db, contest_id=contests[0].id, season_id=season.id
    )
    assert roster.contestant_ids == (contestant.id,)


def test_exact_single_contest_period_uses_explicit_season_roster(db):
    _, contests, season, _, contestant, _, _ = _period(db, contest_count=1)
    roster = contest_context_service.resolve_period_roster(
        db, contest_id=contests[0].id, season_id=season.id
    )
    assert roster.contestant_ids == (contestant.id,)


def test_monthly_preflight_is_read_only_and_rejects_duplicates(db):
    _period(db)
    duplicate = Round(
        name="Duplicate August",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 8, 1),
    )
    db.add(duplicate)
    db.flush()
    before = db.query(Round).count()
    with pytest.raises(AmbiguousContestContext):
        contest_context_service.preflight_monthly_rounds(
            db, [date(2026, 8, 1), date(2026, 9, 1)]
        )
    assert db.query(Round).count() == before


def test_historical_resolution_never_mutates_vote(db):
    *_, vote = _period(db)
    original = (vote.contestant_id, vote.stage_id, vote.points, vote.vote_date)
    contest_context_service.resolve_historical_vote(db, vote)
    db.flush()
    assert (vote.contestant_id, vote.stage_id, vote.points, vote.vote_date) == original


def test_scheduler_lifecycle_fails_before_mutation_on_duplicate_month(db):
    original = _period(db)[0]
    original.submission_end_date = date(2020, 1, 1)
    original.is_submission_open = True
    duplicate = Round(
        name="Duplicate August",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 8, 1),
        submission_end_date=date(2020, 1, 1),
        is_submission_open=True,
    )
    db.add(duplicate)
    db.flush()
    with pytest.raises(AmbiguousContestContext):
        SeasonMigrationService.check_and_process_migrations(db)
    assert original.is_submission_open is True
    assert duplicate.is_submission_open is True


def test_promotion_requires_explicit_source_when_seasons_are_ambiguous(db):
    rnd, contests, _, _, _, _, _ = _period(db)
    duplicate = ContestSeason(
        round_id=rnd.id,
        title="Another country season",
        level=SeasonLevel.COUNTRY,
    )
    db.add(duplicate)
    db.flush()
    db.add(
        ContestSeasonLink(
            contest_id=contests[0].id,
            season_id=duplicate.id,
            is_active=True,
        )
    )
    db.flush()
    before_links = db.query(ContestSeasonLink).count()
    result = SeasonMigrationService.promote_to_next_level(
        db,
        SeasonLevel.COUNTRY,
        SeasonLevel.REGIONAL,
        contests[0].id,
    )
    assert "Ambiguous source season" in result["error"]
    assert db.query(ContestSeasonLink).count() == before_links
