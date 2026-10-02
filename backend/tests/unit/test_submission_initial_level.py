"""Initial competition level of a new submission (management rule, 2026-10-02).

    nomination     -> COUNTRY
    participation  -> CITY

The level follows from the contest's mode on the server. A request that names
any other level is rejected (422); higher levels are reached only through the
progression system. Missing geography is a clear validation error, never a
guessed location. Synthetic data only (SQLite).
"""
from __future__ import annotations

import pytest

from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
)
from app.services.submission_level import (
    SubmissionLevelError,
    enforce_initial_submission_level,
    initial_submission_level,
    require_submission_geography,
    requested_levels_from_payload,
)
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import _post, api_world, person  # noqa: F401  (fixture)
from tests.unit.test_phase8_participation_safety import admin_create, admin_scope

BASE = {"title": "Song", "description": "A song", "video_media_ids": None}


def seasons(db):
    return sorted((s.level.value, s.round_id) for s in db.query(ContestSeason).all())


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,level", [
    ("nomination", SeasonLevel.COUNTRY), ("Nomination ", SeasonLevel.COUNTRY),
    ("participation", SeasonLevel.CITY), (None, SeasonLevel.CITY), ("", SeasonLevel.CITY),
])
def test_initial_level_follows_the_contest_mode(mode, level):
    assert initial_submission_level(mode) == level
    assert enforce_initial_submission_level(mode) == level
    assert enforce_initial_submission_level(mode, [level.value]) == level      # naming it exactly is harmless


@pytest.mark.parametrize("mode,requested", [
    ("nomination", "city"), ("nomination", "regional"), ("nomination", "region"),
    ("nomination", "continental"), ("nomination", "continent"), ("nomination", "global"),
    ("participation", "country"), ("participation", "regional"), ("participation", "continental"),
    ("participation", "global"), ("participation", "GLOBAL "), ("participation", SeasonLevel.REGIONAL),
])
def test_any_other_explicit_level_is_rejected(mode, requested):
    with pytest.raises(SubmissionLevelError) as exc:
        enforce_initial_submission_level(mode, [requested])
    assert "always starts at" in str(exc.value)


def test_unknown_level_is_rejected_not_ignored():
    with pytest.raises(SubmissionLevelError):
        enforce_initial_submission_level("participation", ["galactic"])


def test_every_level_key_in_a_raw_body_is_captured():
    body = {"title": "x", "level": "regional", "contestLevel": "global", "season_level": "", "stage": None}
    assert requested_levels_from_payload(body) == ["regional", "global"]
    assert requested_levels_from_payload({"title": "x"}) == []


# ---------------------------------------------------------------------------
# API: new nomination -> Country, new participation -> City
# ---------------------------------------------------------------------------

def test_new_nomination_is_attached_to_the_country_season_of_its_round(client, db, api_world):
    c = api_world(mode="nomination")
    r = _post(client, person(db, 30), c, **BASE, nominee_age_declaration="ADULT")
    assert r.status_code == 200, r.text
    entry = db.query(Contestant).one()
    assert entry.entry_type == "nomination" and entry.round_id == r.json()["round_id"]
    assert seasons(db) == [("country", entry.round_id)]
    assert db.query(ContestSeason).filter(ContestSeason.level != SeasonLevel.COUNTRY).count() == 0


def test_new_participation_is_attached_to_the_city_season_of_its_round(client, db, api_world):
    c = api_world()
    r = _post(client, person(db, 30), c, **BASE)
    assert r.status_code == 200, r.text
    entry = db.query(Contestant).one()
    assert entry.entry_type == "participation" and (entry.city, entry.country) == ("Arusha", "Tanzania")
    assert seasons(db) == [("city", entry.round_id)]


def test_client_cannot_turn_a_participation_contest_into_a_nomination(client, db, api_world):
    """entry_type in the body is not trusted: the contest's mode decides."""
    c = api_world()
    r = _post(client, person(db, 30), c, **BASE, entry_type="nomination")
    assert r.status_code == 200, r.text
    assert db.query(Contestant).one().entry_type == "participation"
    assert seasons(db) == [("city", r.json()["round_id"])]


@pytest.mark.parametrize("key", ["level", "contest_level", "contestLevel", "season_level", "stage"])
@pytest.mark.parametrize("requested", ["country", "regional", "continental", "global"])
def test_participation_at_a_higher_level_is_rejected(client, db, api_world, key, requested):
    c = api_world()
    r = _post(client, person(db, 30), c, **BASE, **{key: requested})
    assert r.status_code == 422, r.text
    assert "always starts at City level" in r.json()["detail"]
    assert db.query(Contestant).count() == 0 and db.query(ContestSeason).count() == 0
    assert db.query(ContestantSeason).count() == 0


@pytest.mark.parametrize("requested", ["city", "regional", "continental", "global"])
def test_nomination_at_another_level_is_rejected(client, db, api_world, requested):
    c = api_world(mode="nomination")
    r = _post(client, person(db, 30), c, **BASE, nominee_age_declaration="ADULT", level=requested)
    assert r.status_code == 422, r.text
    assert "always starts at Country level" in r.json()["detail"]
    assert db.query(Contestant).count() == 0 and db.query(ContestSeason).count() == 0


def test_naming_the_initial_level_explicitly_is_accepted(client, db, api_world):
    r = _post(client, person(db, 30), api_world(), **BASE, level="city")
    assert r.status_code == 200, r.text
    n = _post(client, person(db, 30), api_world(mode="nomination"), **BASE, nominee_age_declaration="ADULT",
              contest_level="Country")
    assert n.status_code == 200, n.text


def test_participate_alias_enforces_the_same_rule(client, db, api_world):
    """/contests/{id}/participate is what the web app calls."""
    user = person(db, 30)
    c = api_world()
    body = {"title": "Song", "description": "A song"}
    bad = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(user), json={**body, "level": "regional"})
    assert bad.status_code == 422 and "always starts at City level" in bad.json()["detail"]
    assert db.query(Contestant).count() == 0
    ok = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(user), json=body)
    assert ok.status_code == 201, ok.text
    assert seasons(db) == [("city", ok.json()["round_id"])]


def test_season_id_in_the_url_cannot_be_used_to_enter_a_higher_stage(client, db, api_world):
    """Legacy form: POST /contestants/{season id}. A Regional/Global season is refused."""
    c = api_world()
    rnd_id = None
    made = {}
    for level in (SeasonLevel.REGIONAL, SeasonLevel.GLOBAL, SeasonLevel.CITY):
        s = ContestSeason(title=f"S {level.value}", level=level, round_id=rnd_id)
        db.add(s)
        db.flush()
        made[level] = s
    # Season ids must not collide with a contest id, or the contest path is taken.
    for s in made.values():
        while db.query(type(c)).filter(type(c).id == s.id).first() is not None:
            db.delete(s)
            db.flush()
            replacement = ContestSeason(title=s.title, level=s.level)
            db.add(replacement)
            db.flush()
            made[s.level] = s = replacement
        db.add(ContestSeasonLink(contest_id=c.id, season_id=s.id, is_active=True))
    db.commit()

    for level in (SeasonLevel.REGIONAL, SeasonLevel.GLOBAL):
        url = f"/api/v1/contestants/{made[level].id}"
        r = client.post(url, headers=auth(person(db, 30)), json=BASE)
        assert r.status_code == 422, r.text
        assert "always starts at City level" in r.json()["detail"]
    assert db.query(Contestant).count() == 0
    assert db.query(ContestantSeason).count() == 0


def test_resubmitting_returns_the_same_entry_without_duplicate_season_or_membership(client, db, api_world):
    user = person(db, 30)
    c = api_world()
    first = _post(client, user, c, **BASE)
    again = _post(client, user, c, **BASE)
    assert first.status_code == again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert db.query(Contestant).count() == 1
    assert db.query(ContestSeason).count() == 1
    memberships = db.query(ContestantSeason).all()
    assert len({(m.contestant_id, m.season_id) for m in memberships}) == len(memberships) <= 1
    other = _post(client, person(db, 30), c, **BASE)             # a second entrant reuses the City season
    assert other.status_code == 200 and db.query(ContestSeason).count() == 1


# ---------------------------------------------------------------------------
# Geography: required, never invented
# ---------------------------------------------------------------------------

def test_participation_without_a_city_is_a_clear_validation_error(client, db, api_world):
    r = _post(client, person(db, 30, city=None), api_world(), **BASE)
    assert r.status_code == 422, r.text
    assert "start at City level" in r.json()["detail"] and "no city" in r.json()["detail"]
    assert db.query(Contestant).count() == 0


def test_participation_without_a_country_is_a_clear_validation_error(client, db, api_world):
    r = _post(client, person(db, 30, country=None), api_world(), **BASE)
    assert r.status_code == 422 and "no country" in r.json()["detail"]
    assert db.query(Contestant).count() == 0


def test_nomination_without_a_country_is_a_clear_validation_error(client, db, api_world):
    r = _post(client, person(db, 30, country=None, city=None), api_world(mode="nomination"), **BASE,
              nominee_age_declaration="ADULT")
    assert r.status_code == 422, r.text
    assert "start at Country level" in r.json()["detail"]
    assert db.query(Contestant).count() == 0


def test_nomination_needs_a_country_but_not_a_city(client, db, api_world):
    r = _post(client, person(db, 30, city=None), api_world(mode="nomination"), **BASE,
              nominee_age_declaration="ADULT")
    assert r.status_code == 200, r.text
    entry = db.query(Contestant).one()
    assert entry.country == "Tanzania" and entry.city is None            # nothing invented


@pytest.mark.parametrize("mode,city,country,ok", [
    ("nomination", None, "Kenya", True), ("nomination", "Nairobi", None, False), ("nomination", None, "  ", False),
    ("participation", "Nairobi", "Kenya", True), ("participation", None, "Kenya", False),
    ("participation", "Nairobi", None, False), ("participation", " ", "", False),
])
def test_geography_requirement_per_mode(mode, city, country, ok):
    if ok:
        require_submission_geography(mode, city=city, country=country)
    else:
        with pytest.raises(SubmissionLevelError):
            require_submission_geography(mode, city=city, country=country)


# ---------------------------------------------------------------------------
# Admin creation follows the same rule; existing data is not touched
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,level,status_code", [
    ("participation", SeasonLevel.CITY, 201), ("nomination", SeasonLevel.COUNTRY, 201),
    ("participation", SeasonLevel.COUNTRY, 422), ("participation", SeasonLevel.REGIONAL, 422),
    ("participation", SeasonLevel.GLOBAL, 422), ("nomination", SeasonLevel.CITY, 422),
    ("nomination", SeasonLevel.REGIONAL, 422), ("nomination", SeasonLevel.CONTINENT, 422),
])
def test_admin_created_entry_must_start_at_the_initial_level(client, db, mode, level, status_code):
    cts, s = admin_scope(db, mode=mode)
    s.level = level
    db.commit()
    _, r = admin_create(client, db, person(db, 30), s)
    assert r.status_code == status_code, r.text
    assert db.query(Contestant).count() == (1 if status_code == 201 else 0)


def test_existing_higher_level_entries_and_memberships_are_left_as_they_are(client, db, api_world):
    """Historical data created under older behaviour keeps its recorded level."""
    c = api_world()
    regional = ContestSeason(title="old regional", level=SeasonLevel.REGIONAL)
    db.add(regional)
    db.flush()
    owner = person(db, 30)
    old = Contestant(user_id=owner.id, season_id=c.id, contest_id=c.id, title="old", description="d",
                     entry_type="participation", is_active=True, is_deleted=False, is_qualified=True)
    db.add(old)
    db.flush()
    db.add(ContestantSeason(contestant_id=old.id, season_id=regional.id, is_active=True))
    db.commit()
    before = (old.id, old.season_id, old.is_qualified, regional.level)

    assert _post(client, person(db, 30), c, **BASE).status_code == 200
    db.expire_all()
    kept = db.query(Contestant).filter(Contestant.id == before[0]).one()
    link = db.query(ContestantSeason).filter(ContestantSeason.contestant_id == kept.id).one()
    assert (kept.id, kept.season_id, kept.is_qualified, link.season.level) == before
    assert link.is_active is True and link.season_id == regional.id
