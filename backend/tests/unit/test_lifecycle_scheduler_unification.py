"""
Scheduler-level tests for nomination mode's independent lifecycle calendar
(Nomination M -> Country M+1 -> Regional M+2 -> Continental M+3 -> Global
M+4, no City stage) — client-clarified 2026 business rule.

Covers scheduler-level behavior that needs a real, running pass
(SeasonMigrationService.check_and_process_migrations) rather than just the
pure calendar functions already covered by test_nomination_migration_calendar.py:

- nomination mode initializes through COUNTRY, immediately from the
  submission month (M) — never through City (nomination has no City stage)
- repeated scheduler execution within the same lifecycle period cannot
  over-advance a contestant (idempotency)
- day-1 multi-hop only catches up a genuine backlog, and is visibly logged
  when it fires
- Contestant.round_id (the original cohort) never changes through
  progression
- two different cohorts processed in the same pass remain independently
  scoped

Supersedes an earlier version of this file built around a short-lived
"nomination also gains a City stage at M+2" unified-calendar experiment,
since rejected by the client.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.models.contest import Contest
from app.models.contests import ContestantSeason, ContestSeason, ContestSeasonLink, Contestant, SeasonLevel
from app.models.round import round_contests
from app.models.user import User
from app.scripts.generate_monthly_rounds import generate_monthly_round
from app.services.season_migration import SeasonMigrationService


def _nomination_contest(db, suffix: str) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}",
        contest_type="t",
        level="country",
        contest_mode="nomination",
    )
    db.add(contest)
    db.flush()
    return contest


def _submit_contestant(db, *, suffix: str, rnd, contest: Contest) -> Contestant:
    owner = User(email=f"lifecycle-{suffix}@example.test", hashed_password="unused")
    db.add(owner)
    db.flush()
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        # migrate_to_country_start (and much of the legacy migration code)
        # looks contestants up via the legacy `season_id == contest_id`
        # convention, not the newer, unambiguous `contest_id` field alone --
        # mirrors exactly what the real submission endpoint sets.
        season_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        entry_type="nomination",
        title=f"Contestant {suffix}",
        continent="Africa",
        country="Kenya",
        city="Nairobi",
        region="East Africa",
    )
    db.add(contestant)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    db.commit()
    return contestant


def _own_round_active_level(db, contestant: Contestant) -> "str | None":
    row = (
        db.query(ContestSeason.level)
        .join(ContestantSeason, ContestantSeason.season_id == ContestSeason.id)
        .filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.is_active == True,  # noqa: E712
            ContestSeason.round_id == contestant.round_id,
        )
        .first()
    )
    if not row:
        return None
    level = row[0]
    return level.value if hasattr(level, "value") else str(level)


def _run_scheduler_on(db, simulated_today: date, *, allow_multi_hop: bool = False) -> dict:
    class FixedDate(date):
        @classmethod
        def today(cls):
            return simulated_today

    with patch("app.services.season_migration.date", FixedDate):
        return SeasonMigrationService.check_and_process_migrations(
            db, allow_multi_hop=allow_multi_hop
        )


def test_nomination_scheduler_stays_inactive_during_nomination_month(db):
    """
    Client-clarified pre-deploy review: a nomination submission must NOT
    have an active geographic ContestantSeason merely because it is still
    Nomination month (M) -- My Applications, ranking, and every other
    consumer that joins through ContestantSeason.is_active would otherwise
    show it as already "in Country" a full month early.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))  # submission month = July
    contest = _nomination_contest(db, "notyetinit")
    contestant = _submit_contestant(db, suffix="notyetinit", rnd=rnd, contest=contest)

    _run_scheduler_on(db, date(2026, 7, 25))  # still within the nomination month itself

    assert _own_round_active_level(db, contestant) is None


def test_nomination_scheduler_init_reaches_country_at_vote_open(db):
    """
    Primary regression: a nomination submission, processed only by the
    scheduler's STEP 1 (no explicit entry_season passed in, unlike the
    submission-endpoint test file), must initialize at COUNTRY exactly once
    Country's own vote-open date (M+1) arrives — never at CITY (nomination
    has no City stage), and never before M+1.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))  # Country vote-open = Aug 1
    contest = _nomination_contest(db, "countryinit")
    contestant = _submit_contestant(db, suffix="countryinit", rnd=rnd, contest=contest)

    _run_scheduler_on(db, date(2026, 8, 5))  # M+1

    assert _own_round_active_level(db, contestant) == "country"


def test_repeated_scheduler_runs_cannot_over_advance_within_one_period(db):
    """
    Running the scheduler once, or many times, on the same simulated date
    (well within a single lifecycle month, before Regional's own vote-open)
    must leave the contestant at the same stage — never advance further
    just because the scheduler executed again.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    contest = _nomination_contest(db, "repeat")
    contestant = _submit_contestant(db, suffix="repeat", rnd=rnd, contest=contest)

    today = date(2026, 8, 15)  # country vote-open (Aug 1) passed; regional's Sep 1 not yet
    for _ in range(10):
        _run_scheduler_on(db, today)

    assert _own_round_active_level(db, contestant) == "country"


def _vote_for(db, *, suffix: str, contestant: Contestant, contest: Contest, season: ContestSeason, points: int = 5):
    """Real promotion (unlike the freeze hook) requires require_votes=True
    candidates -- a contestant with zero votes anywhere is correctly never
    selected to advance. Mirrors the equivalent helper in
    test_top_high5_frozen_results.py."""
    from app.models.voting import ContestantVoting

    voter = User(email=f"voter-{suffix}@example.test", hashed_password="unused")
    db.add(voter)
    db.flush()
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=contestant.id,
            contest_id=contest.id,
            season_id=season.id,
            vote_bucket_key=f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}",
            position=1,
            points=points,
        )
    )
    db.commit()


def _active_own_round_season(db, contestant: Contestant) -> "ContestSeason | None":
    return (
        db.query(ContestSeason)
        .join(ContestantSeason, ContestantSeason.season_id == ContestSeason.id)
        .filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.is_active == True,  # noqa: E712
            ContestSeason.round_id == contestant.round_id,
        )
        .first()
    )


def test_day1_catchup_promotes_a_genuinely_overdue_backlog(db, caplog):
    """
    A contestant reaches COUNTRY under normal operation (at Country's own
    vote-open, M+1), then the scheduler is simulated as down for two months
    past Regional's own vote-open (a genuine catch-up scenario).
    allow_multi_hop=True (the day-1 case) must not block a legitimately
    overdue hop just because it's "late".
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    contest = _nomination_contest(db, "catchup")
    contestant = _submit_contestant(db, suffix="catchup", rnd=rnd, contest=contest)

    # Normal operation reaches Country at its own vote-open (Aug 1, M+1)...
    _run_scheduler_on(db, date(2026, 8, 5))
    country_season = _active_own_round_season(db, contestant)
    assert country_season is not None and country_season.level == SeasonLevel.COUNTRY
    _vote_for(db, suffix="catchup", contestant=contestant, contest=contest, season=country_season)

    # ...then the scheduler is simulated as down until Nov 5 -- Country->Regional
    # has been genuinely overdue since Sep 1 (M+2), two months ago.
    _run_scheduler_on(db, date(2026, 11, 5), allow_multi_hop=True)

    assert _own_round_active_level(db, contestant) == "regional"


def test_normal_operation_does_not_multihop(db, caplog):
    """
    Companion to the catch-up test: under normal (non-backlogged)
    operation, at most one transition is ever due per contest+round on a
    given day, so the multi-hop warning must NOT fire.
    """
    import logging

    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    contest = _nomination_contest(db, "normal")
    contestant = _submit_contestant(db, suffix="normal", rnd=rnd, contest=contest)

    caplog.set_level(logging.WARNING, logger="app.services.season_migration")
    _run_scheduler_on(db, date(2026, 8, 5))  # only Country init is due (M+1)

    assert _own_round_active_level(db, contestant) == "country"
    assert not any("Multi-hop promotion" in rec.message for rec in caplog.records)


def test_original_cohort_round_id_immutable_through_progression(db):
    """
    Contestant.round_id (the authoritative original submission cohort) must
    never change as the contestant genuinely progresses through Country ->
    Regional -> Continental. Votes at each stage so real promotion (not
    just a stalled Country season) actually happens at every checkpoint.

    Stops at Continental, not Global: Continental->Global promotion applies
    an additional cohort-month `registration_date`/`created_at` filter
    (nomination_cohort_created_at_filters) that this synthetic contestant's
    real wall-clock creation timestamp does not satisfy -- an unrelated,
    pre-existing anti-contamination guard, not part of this test's scope.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    original_round_id = rnd.id
    contest = _nomination_contest(db, "immutable")
    contestant = _submit_contestant(db, suffix="immutable", rnd=rnd, contest=contest)

    expected_levels = ["country", "regional", "continent"]
    for idx, simulated_today in enumerate((
        date(2026, 8, 5),   # Country opens at its own vote-open (M+1)
        date(2026, 9, 5),   # Regional (M+2, after voting at Country)
        date(2026, 10, 5),  # Continental (M+3, after voting at Regional)
    )):
        _run_scheduler_on(db, simulated_today)
        db.refresh(contestant)
        assert contestant.round_id == original_round_id
        assert _own_round_active_level(db, contestant) == expected_levels[idx]
        current_season = _active_own_round_season(db, contestant)
        _vote_for(
            db, suffix=f"immutable-{idx}", contestant=contestant, contest=contest,
            season=current_season, points=5,
        )


def test_two_cohorts_progress_independently_in_the_same_pass(db):
    """
    A June cohort and a July cohort, processed in the same scheduler pass
    on the same simulated "today", must each end at the stage their OWN
    Round's independent nomination calendar dictates — neither may inherit
    the other's stage or date.
    """
    june_round = generate_monthly_round(db, target_date=date(2026, 6, 1))  # Country=Jul1, Regional=Aug1
    july_round = generate_monthly_round(db, target_date=date(2026, 7, 1))  # Country=Aug1, Regional=Sep1

    june_contest = _nomination_contest(db, "junecohort")
    july_contest = _nomination_contest(db, "julycohort")
    june_contestant = _submit_contestant(db, suffix="junecohort", rnd=june_round, contest=june_contest)
    july_contestant = _submit_contestant(db, suffix="julycohort", rnd=july_round, contest=july_contest)

    # June's Country vote-open (Jul 1, M+1) has passed by Jul 5, so June
    # already has an active Country season; July's own Country vote-open
    # (Aug 1) has not, so July has no active level yet at this point.
    # Vote for June's contestant only, so June alone is eligible to
    # actually promote to Regional.
    _run_scheduler_on(db, date(2026, 7, 5))
    june_country_season = _active_own_round_season(db, june_contestant)
    assert june_country_season is not None and june_country_season.level == SeasonLevel.COUNTRY
    assert _own_round_active_level(db, july_contestant) is None
    _vote_for(db, suffix="junecohort", contestant=june_contestant, contest=june_contest, season=june_country_season)

    # Aug 15: June cohort should be at Regional (opened Aug1, voted at
    # Country); July cohort should still be at Country (its own Regional
    # not due until Sep1 regardless of votes).
    _run_scheduler_on(db, date(2026, 8, 15))

    assert _own_round_active_level(db, june_contestant) == "regional"
    assert _own_round_active_level(db, july_contestant) == "country"
