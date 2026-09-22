"""
Client-clarified 2026 business rule: participation mode's canonical
lifecycle is

    M     Submission
    M+1   City     (= voting_start_date -- no separate "Start Voting" month)
    M+2   Country
    M+3   Regional
    M+4   Continental
    M+5   Global

exercised through the real, primary round generator
(app.scripts.generate_monthly_rounds.generate_monthly_round), the same
path production uses every month.

Nomination mode's own (different, City-less) calendar is covered by
test_nomination_migration_calendar.py and test_lifecycle_scheduler_unification.py.
"""
from __future__ import annotations

from datetime import date

from app.scripts.generate_monthly_rounds import generate_monthly_round


def test_participation_september_submission_calendar(db):
    """REQUIRED TEST A. September 2026 submission cohort."""
    rnd = generate_monthly_round(db, target_date=date(2026, 9, 1))

    assert rnd.submission_start_date == date(2026, 9, 1)
    assert rnd.submission_end_date == date(2026, 9, 30)
    assert rnd.city_season_start_date == date(2026, 10, 1)
    assert rnd.city_season_end_date == date(2026, 10, 31)
    assert rnd.country_season_start_date == date(2026, 11, 1)
    assert rnd.country_season_end_date == date(2026, 11, 30)
    assert rnd.regional_start_date == date(2026, 12, 1)
    assert rnd.regional_end_date == date(2026, 12, 31)
    assert rnd.continental_start_date == date(2027, 1, 1)
    assert rnd.continental_end_date == date(2027, 1, 31)
    assert rnd.global_start_date == date(2027, 2, 1)
    assert rnd.global_end_date == date(2027, 2, 28)


def test_participation_year_rollover_calendar(db):
    """REQUIRED TEST C. December 2026 submission cohort crosses the New Year."""
    rnd = generate_monthly_round(db, target_date=date(2026, 12, 1))

    assert rnd.submission_start_date == date(2026, 12, 1)
    assert rnd.city_season_start_date == date(2027, 1, 1)
    assert rnd.city_season_end_date == date(2027, 1, 31)
    assert rnd.country_season_start_date == date(2027, 2, 1)
    assert rnd.country_season_end_date == date(2027, 2, 28)
    assert rnd.regional_start_date == date(2027, 3, 1)
    assert rnd.regional_end_date == date(2027, 3, 31)
    assert rnd.continental_start_date == date(2027, 4, 1)
    assert rnd.continental_end_date == date(2027, 4, 30)
    assert rnd.global_start_date == date(2027, 5, 1)
    assert rnd.global_end_date == date(2027, 5, 31)


def test_no_artificial_start_voting_season(db):
    """
    REQUIRED TEST E. There is no separate "Start Voting" calendar phase for
    participation mode: voting_start_date IS City's own start date, not an
    earlier, independent M+1 slot with City pushed out to M+2.
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 9, 1))
    assert rnd.voting_start_date == rnd.city_season_start_date == date(2026, 10, 1)
    # voting_end_date spans the whole round (through Global), a pre-existing,
    # deliberate convention used by sync_round_calendar_flags / the
    # scheduler's STEP 0 to know when the entire round is finished — not a
    # second, competing "City window end" value.
    assert rnd.voting_end_date == rnd.global_end_date == date(2027, 2, 28)


def test_participation_first_voting_level_is_city(db):
    """REQUIRED TEST F. Participation's first voting level is CITY, opening
    exactly at voting_start_date -- never Country, and never a month later
    than City's own canonical M+1 slot."""
    rnd = generate_monthly_round(db, target_date=date(2026, 9, 1))
    assert rnd.voting_start_date == date(2026, 10, 1)
    assert rnd.city_season_start_date == date(2026, 10, 1)
    assert rnd.country_season_start_date == date(2026, 11, 1)  # not eligible until M+2
