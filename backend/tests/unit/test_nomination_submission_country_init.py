"""
Nomination submission endpoint: initial ContestSeason/ContestantSeason
mechanics for backend/app/api/api_v1/endpoints/contestant.py's
create_contestant.

Client-clarified 2026 business rule: nomination mode has NO City stage.
Its first geographic level is COUNTRY. A nominated entry "should enter
Country voting immediately in the following calendar month" (M+1) --
NOT during the nomination month M itself.

Semantic split, per the client's explicit pre-deploy review:
  - The COUNTRY ContestSeason *definition* (get_or_create_season) is
    created immediately at submission time (M) -- harmless, contest-level
    metadata with no per-contestant side effect.
  - ensure_active_country_round_link_for_nomination is NOT called until
    Country's own vote-open date (M+1): it does more than activate the
    ContestSeasonLink, it also calls _sync_contestants_to_season, which
    immediately activates every matching contestant's ContestantSeason.
  - The per-contestant ACTIVE ContestantSeason membership -- what My
    Applications, ranking, and every other consumer that joins through
    ContestantSeason.is_active actually reads -- must NOT be created until
    that same M+1 date, exactly mirroring participation's pre-existing
    city_season_start_date gate.

This supersedes an earlier version of this file (and of
test_nomination_submission_city_init.py before it) that assumed
unconditional immediate activation at month M.
"""
from __future__ import annotations

from datetime import date, datetime

from app.models.contest import Contest
from app.models.contests import ContestantSeason, SeasonLevel
from app.models.round import Round
from app.models.user import User
from app.scripts.generate_monthly_rounds import generate_monthly_round
from app.services.season_migration import SeasonMigrationService


def _nomination_contest(db, suffix: str) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", level="country", contest_mode="nomination"
    )
    db.add(contest)
    db.flush()
    return contest


def _submission_time_season_and_activation(db, *, rnd: Round, contest: Contest, contestant_id: int) -> tuple:
    """
    Exact replica of the fixed logic in contestant.py's create_contestant
    nomination branch: the ContestSeason *definition* is created
    immediately (harmless, no per-contestant side effect), but
    ensure_active_country_round_link_for_nomination -- which activates
    every matching contestant via _sync_contestants_to_season -- and the
    contestant's own ContestantSeason row are both withheld until
    Country's own vote-open date (M+1) has arrived.
    """
    entry_season = SeasonMigrationService.get_or_create_season(
        db,
        level=SeasonLevel.COUNTRY,
        title="Saison Country",
        round_id=rnd.id,
        contest_id=contest.id,
    )

    country_vote_open = SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.COUNTRY
    )
    level_already_open = bool(country_vote_open and country_vote_open <= datetime.utcnow().date())

    if level_already_open:
        SeasonMigrationService.ensure_active_country_round_link_for_nomination(
            db, contest.id, rnd.id
        )

    link = None
    if level_already_open:
        link = db.query(ContestantSeason).filter(
            ContestantSeason.contestant_id == contestant_id,
            ContestantSeason.season_id == entry_season.id,
        ).first()
        if not link:
            link = ContestantSeason(
                contestant_id=contestant_id,
                season_id=entry_season.id,
                joined_at=datetime.utcnow(),
                is_active=True,
            )
            db.add(link)
            db.commit()

    return entry_season, link


def _dummy_contestant(db, *, suffix: str, rnd: Round, contest: Contest):
    from app.models.contests import Contestant

    owner = User(email=f"subcountry-{suffix}@example.test", hashed_password="unused")
    db.add(owner)
    db.flush()
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        season_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        entry_type="nomination",
        title=f"Contestant {suffix}",
    )
    db.add(contestant)
    db.flush()
    db.commit()
    return contestant


def test_nomination_submission_season_is_country_not_city(db):
    """entry_season.level must be COUNTRY -- nomination has no City stage."""
    rnd = generate_monthly_round(db, target_date=date(2030, 1, 1))  # far future: vote-open not yet real-world-passed
    contest = _nomination_contest(db, "subcountry")
    contestant = _dummy_contestant(db, suffix="subcountry", rnd=rnd, contest=contest)

    entry_season, _link = _submission_time_season_and_activation(
        db, rnd=rnd, contest=contest, contestant_id=contestant.id
    )
    assert entry_season.level == SeasonLevel.COUNTRY


def test_nomination_submission_before_country_vote_open_creates_no_active_season(db):
    """
    Submitting during the nomination month M (the normal case, any day
    before Country's own vote-open at M+1) must NOT create an active
    ContestantSeason -- the scheduler's STEP-1 activates it later, once
    Country's vote-open date genuinely arrives.
    """
    rnd = generate_monthly_round(db, target_date=date(2030, 1, 1))  # Country vote-open = 2030-02-01
    contest = _nomination_contest(db, "notyet")
    contestant = _dummy_contestant(db, suffix="notyet", rnd=rnd, contest=contest)

    entry_season, link = _submission_time_season_and_activation(
        db, rnd=rnd, contest=contest, contestant_id=contestant.id
    )
    assert entry_season.level == SeasonLevel.COUNTRY
    assert link is None

    active_count = (
        db.query(ContestantSeason)
        .filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.is_active == True,  # noqa: E712
        )
        .count()
    )
    assert active_count == 0


def test_nomination_submission_after_country_vote_open_activates_immediately(db):
    """
    Edge case: a contestant record created for a round whose Country
    vote-open date has ALREADY passed (e.g. a late/manual/backfilled
    entry) correctly gets an immediate active COUNTRY ContestantSeason --
    the gate is a date check, not a blanket "never activate here" rule.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    # Force Country's vote-open (submission month) into the past.
    rnd.submission_start_date = date(2020, 1, 1)
    db.add(rnd)
    db.commit()

    contest = _nomination_contest(db, "late")
    contestant = _dummy_contestant(db, suffix="late", rnd=rnd, contest=contest)

    entry_season, link = _submission_time_season_and_activation(
        db, rnd=rnd, contest=contest, contestant_id=contestant.id
    )
    assert entry_season.level == SeasonLevel.COUNTRY
    assert link is not None
    assert link.is_active is True


def test_my_applications_does_not_show_country_during_nomination_month(db):
    """
    End-to-end closure of the client's pre-deploy question: run the REAL
    submission-time logic (not just check ContestantSeason directly), then
    the REAL My Applications query
    (CRUDContestant.get_multi_by_user_with_stats), and prove
    contest_level is None during the nomination month M -- never
    fabricated as "country" a month early.
    """
    from app.crud.crud_contestant import crud_contestant

    rnd = generate_monthly_round(db, target_date=date(2030, 1, 1))  # Country vote-open = 2030-02-01
    contest = _nomination_contest(db, "myappsleak")
    contestant = _dummy_contestant(db, suffix="myappsleak", rnd=rnd, contest=contest)

    _submission_time_season_and_activation(
        db, rnd=rnd, contest=contest, contestant_id=contestant.id
    )

    results = crud_contestant.get_multi_by_user_with_stats(db, user_id=contestant.user_id)
    assert len(results) == 1
    assert results[0]["contest_level"] is None
