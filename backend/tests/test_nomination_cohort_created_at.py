"""Cohort roster must match submission month (registration_date), not stale round_id."""
from datetime import date, datetime

from app.core.nomination_calendar import (
    cohort_submission_bounds,
    nomination_cohort_created_at_filters,
)


class _RoundStub:
    def __init__(self, start: date, end: date, name: str = "Round March 2026"):
        self.submission_start_date = start
        self.submission_end_date = end
        self.name = name
        self.voting_start_date = date(2026, 4, 1)


def test_cohort_submission_bounds_strict_march():
    rnd = _RoundStub(date(2026, 3, 1), date(2026, 3, 31))
    start, end = cohort_submission_bounds(rnd)
    assert start == date(2026, 3, 1)
    assert end == date(2026, 3, 31)


def test_cohort_submission_bounds_from_name_when_dates_missing():
    rnd = _RoundStub(None, None, name="Round March 2026")
    start, end = cohort_submission_bounds(rnd)
    assert start == date(2026, 3, 1)
    assert end == date(2026, 3, 31)


def test_nomination_cohort_created_at_filters_use_registration_date():
    rnd = _RoundStub(date(2026, 3, 1), date(2026, 3, 31))
    clauses = nomination_cohort_created_at_filters(rnd)
    assert len(clauses) == 3
    sql = " ".join(str(c) for c in clauses).lower()
    assert "registration_date" in sql


def test_april_registration_outside_march_window():
    rnd = _RoundStub(date(2026, 3, 1), date(2026, 3, 31))
    start, end = cohort_submission_bounds(rnd)
    april = datetime(2026, 4, 4, 12, 0, 0)
    assert not (start <= april.date() <= end)
