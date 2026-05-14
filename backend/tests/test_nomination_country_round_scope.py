"""Regression: nomination country tabs must widen SQL round scope consistently (see _preview_country_for_nomination_multi_round)."""
import pytest

from app.crud.crud_contest import _preview_country_for_nomination_multi_round


from typing import Optional


class _User:
    def __init__(self, country: Optional[str] = None, continent: Optional[str] = None):
        self.country = country
        self.continent = continent


@pytest.mark.parametrize(
    "filter_country,filter_continent,filter_region,user,season_level,expected",
    [
        ("Tanzania", None, None, None, "country", "Tanzania"),
        ("all", None, None, _User("Kenya"), "country", None),
        (None, None, None, _User("Tanzania"), "country", "Tanzania"),
        (None, None, None, _User("Tanzania"), "regional", None),
        (None, None, None, _User("Tanzania"), "continent", None),
        (None, None, None, _User("Tanzania"), "global", None),
        (None, None, None, None, "country", None),
        (None, "Africa", None, _User("Tanzania"), "country", "Tanzania"),
    ],
)
def test_preview_country_for_multi_round_widen(filter_country, filter_continent, filter_region, user, season_level, expected):
    assert (
        _preview_country_for_nomination_multi_round(
            filter_country, filter_continent, filter_region, user, season_level
        )
        == expected
    )
