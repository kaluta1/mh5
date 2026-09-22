"""
Client-clarified 2026 business rule: nomination mode's canonical lifecycle
is its own, independent, City-less calendar:

    M     Nomination
    M+1   Country
    M+2   Regional
    M+3   Continental
    M+4   Global

computed by SeasonMigrationService._nomination_vote_open_date_for_level
(and friends) from a Round's own submission month — never from the Round's
shared city_season_*/country_season_*/etc. columns, which
app.scripts.generate_monthly_rounds.generate_monthly_round only ever
populates with PARTICIPATION's schedule (see test_participation_lifecycle_calendar.py).

The underlying month-offset arithmetic is already exhaustively covered,
parametrized, for a March 2026 cohort by test_nomination_migration_calendar.py.
This file adds the client's two explicitly-named literal cohort examples
(September, and a December year-rollover) for direct traceability.
"""
from __future__ import annotations

from datetime import date

from app.models.contests import SeasonLevel
from app.scripts.generate_monthly_rounds import generate_monthly_round
from app.services.season_migration import SeasonMigrationService


def test_nomination_september_cohort_vote_open_calendar(db):
    """REQUIRED TEST B. September 2026 nomination cohort."""
    rnd = generate_monthly_round(db, target_date=date(2026, 9, 1))

    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.COUNTRY
    ) == date(2026, 10, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.REGIONAL
    ) == date(2026, 11, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.CONTINENT
    ) == date(2026, 12, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.GLOBAL
    ) == date(2027, 1, 1)


def test_nomination_year_rollover_cohort_vote_open_calendar(db):
    """REQUIRED TEST D. December 2026 nomination cohort crosses the New Year."""
    rnd = generate_monthly_round(db, target_date=date(2026, 12, 1))

    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.COUNTRY
    ) == date(2027, 1, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.REGIONAL
    ) == date(2027, 2, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.CONTINENT
    ) == date(2027, 3, 1)
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.GLOBAL
    ) == date(2027, 4, 1)


def test_nomination_has_no_city_level_date(db):
    """
    REQUIRED (supports Test E / NOMINATION_HAS_CITY=NO). Nomination's
    calendar helper returns None for CITY -- there is no nomination City
    offset, by construction (the offsets table has no CITY entry).
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 9, 1))
    assert SeasonMigrationService._nomination_vote_open_date_for_level(
        rnd, SeasonLevel.CITY
    ) is None
    assert SeasonMigrationService._nomination_min_start_for_level(
        rnd, SeasonLevel.CITY
    ) is None
