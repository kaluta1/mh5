"""Pooled vote levels must not reuse another calendar round's season."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.crud.crud_contest import _season_pair_for_requested_ui_level


def test_pooled_level_returns_none_when_no_season_for_target_round():
    """June continental must stay empty; do not fall back to March season."""
    db = MagicMock()
    # Exact-round queries return nothing (active then inactive passes).
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = None

    link, season = _season_pair_for_requested_ui_level(db, 177, 26, "continental")

    assert link is None
    assert season is None


def test_country_level_still_queries_exact_round():
    db = MagicMock()
    fake_season = SimpleNamespace(id=1, level=SimpleNamespace(value="country"), round_id=21)
    fake_link = SimpleNamespace(season_id=1)
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = (
        fake_link,
        fake_season,
    )

    link, season = _season_pair_for_requested_ui_level(db, 177, 21, "country")

    assert link is fake_link
    assert season is fake_season
