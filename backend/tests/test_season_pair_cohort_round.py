"""Pooled vote levels must not reuse another calendar round's season."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.crud.crud_contest import _season_pair_for_requested_ui_level
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink
from app.models.round import Round


def test_pooled_level_returns_none_when_no_season_for_target_round():
    """June continental must stay empty; do not fall back to March season."""
    db = MagicMock()

    def query_side_effect(*entities):
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        q.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect

    link, season = _season_pair_for_requested_ui_level(db, 177, 26, "continental")

    assert link is None
    assert season is None


def test_country_level_still_queries_exact_round():
    db = MagicMock()
    fake_season = SimpleNamespace(id=1, level=SimpleNamespace(value="country"), round_id=21)
    fake_link = SimpleNamespace(season_id=1)
    round_row = SimpleNamespace(
        id=21,
        name="Round March 2026",
        submission_start_date=date(2026, 3, 1),
        submission_end_date=date(2026, 3, 31),
    )

    def query_side_effect(*entities):
        q = MagicMock()
        if entities == (Round,):
            q.filter.return_value.first.return_value = round_row
        elif entities == (ContestSeason,):
            q.filter.return_value.first.return_value = None
        elif entities == (Contest,):
            q.filter.return_value.first.return_value = None
        elif entities and entities[0] is ContestSeasonLink:
            q.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
                fake_link,
                fake_season,
            )
        else:
            q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = query_side_effect

    link, season = _season_pair_for_requested_ui_level(db, 177, 21, "country")

    assert link is fake_link
    assert season is fake_season
