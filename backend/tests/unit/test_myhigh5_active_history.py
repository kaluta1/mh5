"""Active MyHigh5 tab should not include closed geography windows (e.g. May country in August)."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.api_v1.endpoints.contestant import _myhigh5_season_is_currently_live
from app.models.round import RoundStatus


def _season(*, start, end, status=RoundStatus.ACTIVE):
    rnd = SimpleNamespace(
        status=status,
        country_season_start_date=start,
        country_season_end_date=end,
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


def test_may_country_votes_are_not_live_in_august():
    season = _season(start=date(2026, 5, 1), end=date(2026, 5, 31))
    now = datetime(2026, 8, 18, 12, 0, 0)
    assert (
        _myhigh5_season_is_currently_live(
            MagicMock(),
            season=season,
            effective_level="country",
            contest_id=1,
            now=now,
        )
        is False
    )


def test_current_country_window_is_live():
    season = _season(start=date(2026, 8, 1), end=date(2026, 8, 31))
    now = datetime(2026, 8, 18, 12, 0, 0)
    assert (
        _myhigh5_season_is_currently_live(
            MagicMock(),
            season=season,
            effective_level="country",
            contest_id=1,
            now=now,
        )
        is True
    )


def test_cancelled_round_is_not_live():
    season = _season(start=date(2026, 8, 1), end=date(2026, 8, 31), status=RoundStatus.CANCELLED)
    now = datetime(2026, 8, 18, 12, 0, 0)
    assert (
        _myhigh5_season_is_currently_live(
            MagicMock(),
            season=season,
            effective_level="country",
            contest_id=1,
            now=now,
        )
        is False
    )
