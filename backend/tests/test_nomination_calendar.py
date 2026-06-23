"""Tests for official nomination start and vote list blocking."""
from datetime import date

from app.core.nomination_calendar import (
    OFFICIAL_NOMINATION_START,
    is_official_nomination_cohort_round,
    nomination_vote_list_blocked,
)


class _Round:
    def __init__(self, name: str, submission_start_date: date):
        self.name = name
        self.submission_start_date = submission_start_date


def test_official_start_is_march_2026():
    assert OFFICIAL_NOMINATION_START == date(2026, 3, 1)


def test_february_round_not_official():
    r = _Round("Round February 2026", date(2026, 2, 1))
    assert is_official_nomination_cohort_round(r) is False
    assert nomination_vote_list_blocked(r, "nomination", "global") is True


def test_march_round_official():
    r = _Round("Round March 2026", date(2026, 3, 1))
    assert is_official_nomination_cohort_round(r) is True
    assert nomination_vote_list_blocked(r, "nomination", "continental") is False
