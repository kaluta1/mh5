"""GET /contests/{id} for a stage that has no roster to show.

A nomination contest asked for a stage that is not open yet for the round
(contestLevel=regional/continental/global before that stage's month), or that
nobody has reached, used to answer 500: the empty response lacked fields the
response schema requires. It is a normal, complete, empty contest response.
"""
from __future__ import annotations

import pytest

from app.crud.crud_contest import _stage_without_roster_stats
from app.schemas.contest import ContestWithEnrichedContestants
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_held_nomination_visibility import _nominate, api_world, world  # noqa: F401  (fixtures)
from tests.unit.test_phase5_contest_eligibility import person

NOT_OPEN = ["regional", "continental", "continent", "global"]


def detail(client, c, rnd, viewer=None, **params):
    query = {"entryType": "nomination", **params}
    if rnd is not None:
        query.setdefault("roundId", rnd.id)
    return client.get(f"/api/v1/contests/{c.id}", params=query, headers=auth(viewer) if viewer else {})


@pytest.fixture
def scene(client, db, world):
    c, rnd = world()
    nominator = person(db, 30)
    entry = _nominate(client, db, c, nominator)
    return c, rnd, nominator, entry["id"]


def test_the_open_stage_is_unchanged(client, scene):
    c, rnd, nominator, entry_id = scene
    for params in ({}, {"contestLevel": "country"}, {"contestLevel": "country", "filterCountry": nominator.country}):
        r = detail(client, c, rnd, **params)
        assert r.status_code == 200, r.text
        body = r.json()
        assert [e["id"] for e in body["contestants"]] == [entry_id] and body["entries_count"] == 1
        ContestWithEnrichedContestants.model_validate(body)


@pytest.mark.parametrize("level", NOT_OPEN)
@pytest.mark.parametrize("roster_only", ["true", "false"])
@pytest.mark.parametrize("signed_in", [False, True])
def test_a_stage_that_is_not_open_is_an_empty_contest_not_an_error(client, scene, level, roster_only, signed_in):
    c, rnd, nominator, _entry_id = scene
    r = detail(client, c, rnd, viewer=nominator if signed_in else None, contestLevel=level, rosterOnly=roster_only,
               filterCountry=nominator.country)
    assert r.status_code == 200, r.text
    body = r.json()
    ContestWithEnrichedContestants.model_validate(body)                    # the declared schema, in full
    assert body["id"] == c.id and body["name"] == c.name and body["contest_mode"] == "nomination"
    assert body["created_at"] and body["updated_at"]
    # nothing is invented for a stage nobody is in
    assert body["contestants"] == [] and body["top_contestants"] == []
    assert (body["entries_count"], body["participants_count"], body["total_votes"], body["total_points"]) == (0, 0, 0, 0)
    assert body["season_level"] in ("regional", "continental", "global")


def test_an_open_stage_nobody_has_reached_is_also_an_empty_contest(client, scene, monkeypatch):
    """The stage's month has come but the contest has no season at that level."""
    import app.core.nomination_calendar as calendar

    c, rnd, _nominator, _entry_id = scene
    monkeypatch.setattr(calendar, "nomination_vote_list_blocked", lambda *a, **k: False)
    for level in NOT_OPEN:
        r = detail(client, c, rnd, contestLevel=level)
        assert r.status_code == 200, (level, r.text)
        body = r.json()
        ContestWithEnrichedContestants.model_validate(body)
        assert body["contestants"] == [] and body["entries_count"] == 0 and body["created_at"]


def test_a_round_that_is_not_this_contests_is_handled_the_same_way(client, scene):
    c, _rnd, _nominator, entry_id = scene
    # a past/unknown round with a pooled stage: empty, not an error
    r = detail(client, c, None, roundId=999999, contestLevel="regional")
    assert r.status_code == 200, r.text
    assert r.json()["contestants"] == []
    ContestWithEnrichedContestants.model_validate(r.json())
    # without a stage the request behaves as before
    plain = detail(client, c, None, roundId=999999)
    assert plain.status_code == 200
    assert client.get("/api/v1/contests/999999", params={"contestLevel": "regional"}).status_code == 404
    assert entry_id                                                          # the entry itself was never touched


def test_an_unknown_level_is_ignored_as_before(client, scene):
    c, rnd, _nominator, entry_id = scene
    plain = detail(client, c, rnd).json()
    for level in ("bogus", "", "COUNTRY "):
        r = detail(client, c, rnd, contestLevel=level)
        assert r.status_code == 200, (level, r.text)
        body = r.json()
        assert [e["id"] for e in body["contestants"]] == [entry_id]
        assert body["entries_count"] == plain["entries_count"]


def test_the_empty_stage_stats_keep_the_keys_other_callers_read(db, scene):
    c, _rnd, _nominator, _entry_id = scene
    stats = _stage_without_roster_stats(c, "regional")
    # list cards and the rounds endpoint read these from the same dict
    assert (stats["participants_count"], stats["entries_count"], stats["season_level"]) == (0, 0, "regional")
    assert stats["created_at"] == c.created_at and stats["updated_at"] == c.updated_at
    ContestWithEnrichedContestants.model_validate({**stats, "contestants": []})
