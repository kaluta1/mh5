"""
Regression tests for two rounds.py resolvers: _contest_card_level_for_round
and _contest_eligible_at_ui_level.

Client-clarified 2026 business rule: nomination mode has NO City stage and
keeps its own independent, faster calendar (Nomination M -> Country M+1 ->
Regional M+2 -> Continental M+3 -> Global M+4); participation's first level
is CITY (M+1). Nomination's COUNTRY ContestSeason/link may exist and be
browsable from the submission month (M) itself -- only actual vote casting
is separately gated to M+1 elsewhere (see test_nomination_migration_calendar.py).

Supersedes an earlier version of this file that asserted a (since-rejected)
"nomination also starts at City, M+2" premise from a short-lived unified-
calendar experiment.
"""
from __future__ import annotations

from datetime import date

from app.api.api_v1.endpoints.rounds import (
    _contest_card_level_for_round,
    _contest_eligible_at_ui_level,
)
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, SeasonLevel
from app.scripts.generate_monthly_rounds import generate_monthly_round


def _nomination_contest(db, suffix: str) -> Contest:
    contest = Contest(name=f"Contest {suffix}", contest_type="t", level="country", contest_mode="nomination")
    db.add(contest)
    db.flush()
    return contest


def _active_link(db, *, rnd, contest: Contest, level: SeasonLevel, suffix: str) -> None:
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=level)
    db.add(season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.commit()


def test_contest_card_level_defaults_to_country_with_no_higher_link(db):
    """A nomination contest with no active link at GLOBAL/CONTINENT/REGIONAL
    falls through to "country" (nomination's first real geographic level)."""
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    contest = _nomination_contest(db, "nolink")
    assert _contest_card_level_for_round(db, rnd, contest, "nomination") == "country"


def test_contest_card_level_reflects_active_regional_link(db):
    """Once promoted, an active REGIONAL link (past its own min_start) takes
    priority over the country fallback."""
    import app.api.api_v1.endpoints.rounds as rounds_module
    from unittest.mock import patch

    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))  # Regional min_start = 2026-09-01 (M+2)
    contest = _nomination_contest(db, "regionallink")
    _active_link(db, rnd=rnd, contest=contest, level=SeasonLevel.REGIONAL, suffix="regionallink")

    class OnRegionalOpen(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 5)

    with patch.object(rounds_module, "date", OnRegionalOpen):
        assert _contest_card_level_for_round(db, rnd, contest, "nomination") == "regional"


def test_contest_card_level_participation_always_city(db):
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))
    contest = Contest(name="Participation X", contest_type="t", level="city", contest_mode="participation")
    db.add(contest)
    db.commit()
    assert _contest_card_level_for_round(db, rnd, contest, "participation") == "city"


def test_country_chip_eligible_from_nomination_month(db):
    """
    Nomination's COUNTRY chip/tab is eligible (browsable) from the round's
    own submission month (M) itself -- roster visibility starts immediately;
    only actual vote casting is separately gated to M+1 by the nomination
    vote calendar (see test_nomination_migration_calendar.py).
    """
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))  # submission month = July
    contest = _nomination_contest(db, "chipgate")

    import app.api.api_v1.endpoints.rounds as rounds_module
    from unittest.mock import patch

    class BeforeMonth(date):
        @classmethod
        def today(cls):
            return date(2026, 6, 15)  # before the round's own submission month

    with patch.object(rounds_module, "date", BeforeMonth):
        assert (
            _contest_eligible_at_ui_level(db, rnd, contest, "nomination", "country") is False
        )

    class WithinMonth(date):
        @classmethod
        def today(cls):
            return date(2026, 7, 5)  # within submission month M itself

    with patch.object(rounds_module, "date", WithinMonth):
        assert (
            _contest_eligible_at_ui_level(db, rnd, contest, "nomination", "country") is True
        )


def test_regional_chip_not_eligible_before_vote_open(db):
    """Pooled chips (regional/continental/global) stay gated to their own
    nomination vote-open date, unlike country."""
    rnd = generate_monthly_round(db, target_date=date(2026, 7, 1))  # Regional vote-open = 2026-09-01 (M+2)
    contest = _nomination_contest(db, "regionalchip")

    import app.api.api_v1.endpoints.rounds as rounds_module
    from unittest.mock import patch

    class Early(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 15)  # after country opens, before regional's vote-open

    with patch.object(rounds_module, "date", Early):
        assert (
            _contest_eligible_at_ui_level(db, rnd, contest, "nomination", "regional") is False
        )
