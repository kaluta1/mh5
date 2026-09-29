"""Deploying corrected progression logic must not rewrite historical cohorts.

Production pre-check for 92ea83c (2026-09-29, read-only): the new personal
COUNTRY->REGIONAL collector picked up every participation contest still linked
at COUNTRY, including March 2026 (round 3), whose Regional month ended on
2026-06-30. promote_to_next_level then ran _ensure_source_season_links, which
would have REACTIVATED 17 memberships deactivated at the May promotion, CREATED
1 membership and set is_qualified on 1 entry -- historical state rewritten
although nobody could be promoted (no votes at that stage).

Rule under test: a personal-calendar hop is only due while its DESTINATION
stage's voting month has not ended (round stage columns, the authoritative
calendar). Entering a stage that is already over has no business meaning, so a
cohort past that point is historical and is never touched; a cohort that merely
missed a scheduler run still catches up during the destination month.
Synthetic data only (SQLite).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel, TopHigh5Result
from app.models.round import round_contests
from app.services.season_migration import SeasonMigrationService
from tests.unit.test_month_end_progression_hardening import (  # noqa: F401  (fixtures)
    _quiet_scheduler_prints,
    active_at,
    add_votes,
    clock,
    entry,
    run_pass,
    season_for,
    state,
    wide_round,
)
from tests.unit.test_phase5_contest_eligibility import contest
from tests.unit.test_phase8_participation_safety import season


def march_historical_cohort(db):
    """Round 3 as found in production: participation contest still linked at COUNTRY,
    Regional month (June) long over, memberships deactivated by the May promotion."""
    rnd = wide_round(db, date(2026, 3, 1))           # City Apr, Country May, Regional Jun, ...
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    country = season(db, rnd, ct, SeasonLevel.COUNTRY)          # active ContestSeasonLink at COUNTRY
    inactive = [entry(db, ct, rnd, k=k, origin="nomination") for k in range(1, 18)]
    for c in inactive:
        db.add(ContestantSeason(contestant_id=c.id, season_id=country.id, is_active=False,
                                joined_at=datetime(2026, 5, 1, 23, 55)))
    no_membership = entry(db, ct, rnd, k=18, origin="participation")
    unqualified = entry(db, ct, rnd, k=19, origin="nomination")
    unqualified.is_qualified = False
    db.add(ContestantSeason(contestant_id=unqualified.id, season_id=country.id, is_active=False,
                            joined_at=datetime(2026, 5, 1, 23, 55)))
    db.commit()
    return rnd, ct, country


def fingerprint(db):
    """Memberships, links, TopHigh5, provenance, vote count + per-entry qualification/activity."""
    return state(db), sorted((c.id, c.is_qualified, c.is_active) for c in db.query(Contestant).all()),         sorted((s.id, s.round_id, str(s.level)) for s in db.query(ContestSeason).all())


def test_A_B_march_cohort_is_not_rewritten_by_any_pass(db, clock):
    march_historical_cohort(db)
    before = fingerprint(db)
    run_pass(db, clock, datetime(2026, 9, 29, 10, 0))          # first hourly pass after deploy
    assert fingerprint(db) == before
    for i in range(5):                                          # five more hourly passes
        run_pass(db, clock, datetime(2026, 9, 29, 11 + i, 0))
    assert fingerprint(db) == before
    run_pass(db, clock, datetime(2026, 10, 1, 0, 5))           # monthly (day-1) pass
    run_pass(db, clock, datetime(2026, 10, 1, 7, 0))           # restart-equivalent rerun
    assert fingerprint(db) == before


def test_C_ambiguous_personal_looking_historical_record_untouched(db, clock):
    rnd, ct, country = march_historical_cohort(db)
    lone = entry(db, ct, rnd, k=20, origin="participation")
    db.add(ContestantSeason(contestant_id=lone.id, season_id=country.id, is_active=True,
                            joined_at=datetime(2026, 5, 1)))
    db.commit()
    add_votes(db, lone, country, ct, 3, datetime(2026, 5, 15))  # it even has Country votes
    before = fingerprint(db)
    run_pass(db, clock, datetime(2026, 10, 1, 0, 5))
    assert fingerprint(db) == before
    assert season_for(db, rnd, SeasonLevel.REGIONAL) is None
    assert db.query(TopHigh5Result).count() == 0


def _current_personal_cohort(db, at_level: SeasonLevel, submission: date):
    rnd = wide_round(db, submission)
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    src = season(db, rnd, ct, at_level)
    entries = [entry(db, ct, rnd, k=k, origin="participation") for k in range(1, 7)]
    for c in entries:
        db.add(ContestantSeason(contestant_id=c.id, season_id=src.id, is_active=True,
                                joined_at=datetime(2026, 9, 1)))
    db.commit()
    for c in entries:
        add_votes(db, c, src, ct, int(c.title.rsplit("-k", 1)[1]), datetime(2026, 9, 15))
    return rnd, ct, entries


TOP5 = {3, 4, 5, 6, 2}


@pytest.mark.parametrize("frm,to,submission", [
    (SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, date(2026, 7, 1)),     # D: Country Sep -> Regional Oct
    (SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, date(2026, 6, 1)),   # E: Regional Sep -> Continental Oct
    (SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, date(2026, 5, 1)),     # F: Continental Sep -> Global Oct
])
def test_D_E_F_current_personal_hops_on_oct_1(db, clock, frm, to, submission):
    rnd, ct, entries = _current_personal_cohort(db, frm, submission)
    run_pass(db, clock, datetime(2026, 9, 30, 23, 59, 59))
    assert active_at(db, rnd, to, ct) == set()
    run_pass(db, clock, datetime(2026, 10, 1, 0, 5))
    assert active_at(db, rnd, to, ct) == {e.title for e in entries if int(e.title.rsplit("-k", 1)[1]) in TOP5}


def test_current_cohort_that_missed_runs_still_catches_up_within_destination_month(db, clock):
    rnd, ct, entries = _current_personal_cohort(db, SeasonLevel.COUNTRY, date(2026, 7, 1))
    run_pass(db, clock, datetime(2026, 10, 20, 9, 0))          # scheduler down until Oct 20
    assert len(active_at(db, rnd, SeasonLevel.REGIONAL, ct)) == 5


def test_I_cohort_whose_destination_month_is_over_is_historical(db, clock):
    rnd, ct, entries = _current_personal_cohort(db, SeasonLevel.COUNTRY, date(2026, 7, 1))
    before = fingerprint(db)
    run_pass(db, clock, datetime(2026, 11, 1, 0, 5))           # Regional (October) already over
    assert fingerprint(db) == before


@pytest.mark.parametrize("frm,to,today,expected", [
    (SeasonLevel.CITY, SeasonLevel.COUNTRY, date(2026, 10, 1), True),
    (SeasonLevel.CITY, SeasonLevel.COUNTRY, date(2026, 10, 31), True),
    (SeasonLevel.CITY, SeasonLevel.COUNTRY, date(2026, 11, 1), False),
    (SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, date(2026, 11, 1), True),
    (SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, date(2026, 12, 1), False),
])
def test_due_predicate_requires_open_destination_stage(db, frm, to, today, expected):
    rnd = wide_round(db, date(2026, 8, 1))           # City Sep, Country Oct, Regional Nov
    assert SeasonMigrationService._promotion_due_for_contest(rnd, frm, to, "participation", today) is expected


def test_due_predicate_fails_closed_without_destination_calendar(db):
    rnd = wide_round(db, date(2026, 8, 1))
    rnd.regional_end_date = None
    assert SeasonMigrationService._promotion_due_for_contest(
        rnd, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, "participation", date(2026, 11, 1)) is False


def test_G_nomination_catchup_is_unchanged(db):
    rnd = wide_round(db, date(2026, 3, 1))
    # Nomination keeps its own calendar and its existing catch-up behaviour.
    assert SeasonMigrationService._promotion_due_for_contest(
        rnd, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, "nomination", date(2026, 9, 29)) is True


def test_april_legacy_rows_exact_production_shape_untouched(db, clock):
    """Production round 4 (April 2026): 4 nomination-origin rows whose legacy
    season_id points at a participation contest (contest_id NULL), with no
    Country membership and is_qualified not set. 92ea83c would have inserted an
    active Country membership and set is_qualified=True for each of them."""
    rnd = wide_round(db, date(2026, 4, 1))            # Country Jun, Regional Jul (over)
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    season(db, rnd, ct, SeasonLevel.COUNTRY)
    for k in range(1, 5):
        c = entry(db, ct, rnd, k=k, origin="nomination")
        c.contest_id = None
        c.is_qualified = False
    db.commit()
    before = fingerprint(db)
    for when in (datetime(2026, 9, 29, 10), datetime(2026, 9, 30, 23, 59, 59), datetime(2026, 10, 1, 0, 5),
                 datetime(2026, 10, 1, 0, 50), datetime(2026, 10, 2, 1)):
        run_pass(db, clock, when)
    assert fingerprint(db) == before
