"""Nomination stage calendar: March nominate → April country vote → May regional → June continental."""
from datetime import date

import pytest

from app.models.round import Round, RoundStatus
from app.models.contests import SeasonLevel
from app.services.season_migration import SeasonMigrationService


def _march_round() -> Round:
    return Round(
        id=1,
        name="Round March 2026",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 3, 1),
        submission_end_date=date(2026, 3, 31),
        voting_start_date=date(2026, 4, 1),
        voting_end_date=date(2026, 8, 31),
        city_season_start_date=date(2026, 4, 1),
        city_season_end_date=date(2026, 4, 30),
        country_season_start_date=date(2026, 5, 1),
        country_season_end_date=date(2026, 5, 31),
        regional_start_date=date(2026, 6, 1),
        regional_end_date=date(2026, 6, 30),
        continental_start_date=date(2026, 7, 1),
        continental_end_date=date(2026, 7, 31),
    )


@pytest.mark.parametrize(
    "level,expected",
    [
        (SeasonLevel.COUNTRY, date(2026, 3, 1)),
        (SeasonLevel.REGIONAL, date(2026, 5, 1)),
        (SeasonLevel.CONTINENT, date(2026, 6, 1)),
        (SeasonLevel.GLOBAL, date(2026, 7, 1)),
    ],
)
def test_nomination_min_start_march_round(level, expected):
    rnd = _march_round()
    assert SeasonMigrationService._nomination_min_start_for_level(rnd, level) == expected


@pytest.mark.parametrize(
    "today,ready",
    [
        (date(2026, 3, 1), True),
        (date(2026, 2, 28), False),
        (date(2026, 4, 15), True),
    ],
)
def test_nomination_country_init_ready(today, ready):
    rnd = _march_round()
    assert SeasonMigrationService._nomination_country_init_ready(rnd, today) is ready


@pytest.mark.parametrize(
    "today,due",
    [
        (date(2026, 4, 30), False),
        (date(2026, 5, 1), True),
        (date(2026, 5, 31), True),
        (date(2026, 6, 1), True),
    ],
)
def test_nomination_country_to_regional_promotion_due(today, due):
    rnd = _march_round()
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.COUNTRY,
            SeasonLevel.REGIONAL,
            "nomination",
            today,
        )
        is due
    )


@pytest.mark.parametrize(
    "today,due",
    [
        (date(2026, 5, 31), False),
        (date(2026, 6, 1), True),
    ],
)
def test_nomination_regional_to_continental_promotion_due(today, due):
    rnd = _march_round()
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.REGIONAL,
            SeasonLevel.CONTINENT,
            "nomination",
            today,
        )
        is due
    )


def test_nomination_country_vote_window_march_cohort():
    rnd = _march_round()
    assert SeasonMigrationService._nomination_vote_open_date_for_level(rnd, SeasonLevel.COUNTRY) == date(
        2026, 4, 1
    )
    assert SeasonMigrationService._nomination_vote_close_date_for_level(rnd, SeasonLevel.COUNTRY) == date(
        2026, 4, 30
    )
    assert SeasonMigrationService.nomination_stage_voting_open(rnd, SeasonLevel.COUNTRY, date(2026, 4, 15))
    assert not SeasonMigrationService.nomination_stage_voting_open(rnd, SeasonLevel.COUNTRY, date(2026, 5, 1))


def test_june_cohort_country_only_in_july():
    """June nominees vote at country in July; regional promotion waits until August 1."""
    rnd = Round(
        id=2,
        name="Round June 2026",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 6, 1),
        submission_end_date=date(2026, 6, 30),
        voting_start_date=date(2026, 7, 1),
        voting_end_date=date(2026, 11, 30),
    )
    assert SeasonMigrationService.nomination_stage_voting_open(
        rnd, SeasonLevel.COUNTRY, date(2026, 7, 15)
    )
    assert not SeasonMigrationService.nomination_stage_voting_open(
        rnd, SeasonLevel.REGIONAL, date(2026, 7, 15)
    )
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.COUNTRY,
            SeasonLevel.REGIONAL,
            "nomination",
            date(2026, 7, 31),
        )
        is False
    )
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.COUNTRY,
            SeasonLevel.REGIONAL,
            "nomination",
            date(2026, 8, 1),
        )
        is True
    )


def test_june_cohort_regional_list_blocked_in_july():
    """Regional Vote list must be empty before August for June cohort."""
    from unittest.mock import patch

    from app.core.nomination_calendar import nomination_vote_list_blocked
    from app.models.round import Round, RoundStatus

    rnd = Round(
        id=2,
        name="Round June 2026",
        status=RoundStatus.ACTIVE,
        submission_start_date=date(2026, 6, 1),
        submission_end_date=date(2026, 6, 30),
    )
    with patch("app.core.nomination_calendar.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 15)
        assert nomination_vote_list_blocked(rnd, "nomination", "regional") is True
        mock_date.today.return_value = date(2026, 8, 1)
        assert nomination_vote_list_blocked(rnd, "nomination", "regional") is False


def test_participation_uses_round_stage_dates_not_nomination_calendar():
    rnd = _march_round()
    # Participation country→regional follows DB columns (June), not nomination May.
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.COUNTRY,
            SeasonLevel.REGIONAL,
            "participation",
            date(2026, 5, 1),
        )
        is False
    )
    assert (
        SeasonMigrationService._promotion_due_for_contest(
            rnd,
            SeasonLevel.COUNTRY,
            SeasonLevel.REGIONAL,
            "participation",
            date(2026, 6, 1),
        )
        is True
    )
