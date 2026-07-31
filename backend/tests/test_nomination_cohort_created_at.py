"""Cohort roster must match submission month, not just round_id."""
from datetime import date, datetime

import pytest

from app.core.nomination_calendar import nomination_cohort_created_at_filters


class _RoundStub:
    def __init__(self, start: date, end: date):
        self.submission_start_date = start
        self.submission_end_date = end
        self.name = "Round March 2026"


def test_nomination_cohort_created_at_filters_march_window():
    rnd = _RoundStub(date(2026, 3, 1), date(2026, 3, 31))
    clauses = nomination_cohort_created_at_filters(rnd)
    assert len(clauses) == 3


def test_nomination_cohort_created_at_filters_missing_dates():
    rnd = _RoundStub(None, None)
    assert nomination_cohort_created_at_filters(rnd) == []
