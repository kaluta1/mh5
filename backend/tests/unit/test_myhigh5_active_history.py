"""Active MyHigh5 matches Top High5: current session per geography, past slices in History."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.api_v1.endpoints.contestant import _myhigh5_season_is_currently_live
from app.models.round import RoundStatus

AUGUST = datetime(2026, 8, 18, 12, 0, 0)


def _season(*, submission=None, country_start=None, country_end=None, status=RoundStatus.ACTIVE, name=""):
    rnd = SimpleNamespace(
        status=status,
        name=name or "",
        submission_start_date=submission,
        country_season_start_date=country_start,
        country_season_end_date=country_end,
        city_season_start_date=None,
        city_season_end_date=None,
        regional_start_date=None,
        regional_end_date=None,
        continental_start_date=None,
        continental_end_date=None,
        global_start_date=None,
        global_end_date=None,
        voting_start_date=None,
        voting_end_date=None,
    )
    return SimpleNamespace(id=1, is_deleted=False, round_id=10, round=rnd)


def _live(season, level, now=AUGUST):
    return _myhigh5_season_is_currently_live(
        MagicMock(),
        season=season,
        effective_level=level,
        contest_id=1,
        now=now,
    )


def test_may_country_votes_are_not_live_in_august():
    season = _season(country_start=date(2026, 5, 1), country_end=date(2026, 5, 31))
    assert _live(season, "country") is False


def test_current_country_window_is_live():
    season = _season(country_start=date(2026, 8, 1), country_end=date(2026, 8, 31))
    assert _live(season, "country") is True


def test_cancelled_round_is_not_live():
    season = _season(
        country_start=date(2026, 8, 1),
        country_end=date(2026, 8, 31),
        status=RoundStatus.CANCELLED,
    )
    assert _live(season, "country") is False


def test_may_cohort_in_august_matches_top_high5_calendar():
    """May nominations: country June, regional July, continental August, global September."""
    season = _season(submission=date(2026, 5, 1), name="Round May 2026")
    assert _live(season, "city") is False
    assert _live(season, "country") is False
    assert _live(season, "regional") is False
    assert _live(season, "continent") is True
    assert _live(season, "global") is False


def test_july_cohort_country_is_live_in_august():
    season = _season(submission=date(2026, 7, 1), name="Round July 2026")
    assert _live(season, "country") is True
    assert _live(season, "regional") is False
    assert _live(season, "continent") is False


def test_june_cohort_regional_is_live_in_august():
    season = _season(submission=date(2026, 6, 1), name="Round June 2026")
    assert _live(season, "country") is False
    assert _live(season, "regional") is True
    assert _live(season, "continent") is False
