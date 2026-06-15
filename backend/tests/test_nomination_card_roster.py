"""Nomination list card count must use same roster query as contest detail."""
import pytest

from app.crud.crud_contest import CRUDContest


@pytest.mark.parametrize(
    "country,region,continent,ui_level,expected",
    [
        ("Tanzania", None, None, None, True),
        (None, "East Africa", None, None, True),
        (None, None, "Africa", None, True),
        (None, None, None, "country", True),
        (None, None, None, "regional", True),
        (None, None, None, "continental", True),
        ("all", None, None, None, False),
        (None, None, None, None, False),
        (None, None, "all", None, False),
    ],
)
def test_nomination_card_uses_exact_roster(country, region, continent, ui_level, expected):
    assert (
        CRUDContest.nomination_card_uses_exact_roster(
            country, region, continent, ui_level
        )
        is expected
    )
