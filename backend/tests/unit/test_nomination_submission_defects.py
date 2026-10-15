"""Nomination submission defects (Comedy audit, 2026-10-15).

1. The rule-based relevance score rejected ordinary nominations ("Please vote
   for X") with a 422 carrying French suggestions. It is now a non-blocking
   signal; these tests run the REAL checker (it is not stubbed here).
2. A nomination in a sibling contest of the same category returned 201 with the
   nominator's older nomination and moved that row onto the new contest, without
   creating the new nominee. It now answers 409 and changes nothing.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models.contest import Contest
from app.models.contests import Contestant
from app.models.round import Round, round_contests
from app.services.content_moderation import ModerationResult
from app.services.content_relevance import content_relevance_service
from app.services.contest_category_integrity import contest_ids_for_category
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import TODAY, category, person

COMEDY_DESCRIPTION = "Nominate your favorite comedian from your country to participate in this contest."


@pytest.fixture
def world(db, monkeypatch):
    """Contests sharing one open calendar round. Moderation providers and the
    submission-window service are stubbed; the relevance checker is NOT."""
    from app import crud
    from app.services.content_moderation import content_moderation_service
    from app.services.contest_status import contest_status_service

    approved = ModerationResult(True, 1.0, [], {})
    monkeypatch.setattr(content_moderation_service, "is_configured", lambda: True)  # in-process stub only
    monkeypatch.setattr(content_moderation_service, "moderate_text", lambda text: approved)
    monkeypatch.setattr(content_moderation_service, "moderate_image", lambda url: approved)
    monkeypatch.setattr(content_moderation_service, "moderate_video", lambda url: approved)
    monkeypatch.setattr(contest_status_service, "check_submission_allowed", lambda db_, cid: (True, None))
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_ENABLED", False)  # no network in tests

    month = TODAY.replace(day=1)
    rnd = Round(name="Shared round", submission_start_date=month, submission_end_date=month + timedelta(days=40))
    db.add(rnd)
    db.commit()
    monkeypatch.setattr(crud.round, "get_active_round_for_contest", lambda db_, cid: rnd)
    monkeypatch.setattr(crud.round, "get_preferred_nomination_round_for_contest", lambda db_, cid: rnd)

    def make(mode="nomination", contest_type="comedy", category_id=None, name="Comedy Contest",
             description=COMEDY_DESCRIPTION, level=None):
        c = Contest(name=name, description=description, contest_type=contest_type,
                    level=level or ("country" if mode == "nomination" else "city"),
                    contest_mode=mode, requires_kyc=False, category_id=category_id)
        db.add(c)
        db.commit()
        db.refresh(c)
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=c.id))
        db.commit()
        return c

    return SimpleNamespace(make=make, round=rnd)


def video(link=None):
    # The web app sends a list holding one JSON-encoded list (participation-form.tsx).
    return [json.dumps([link or f"https://www.youtube.com/watch?v={uuid.uuid4().hex[:11]}"])]


def nominate(client, user, c, title, description, link=None):
    body = {"title": title, "description": description, "video_media_ids": video(link),
            "nominator_country": user.country, "entry_type": "nomination", "nominee_age_declaration": "ADULT"}
    return client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(user), json=body)


def snapshot(db):
    db.expire_all()
    return sorted((r.id, r.title, r.season_id, r.round_id, r.entry_type) for r in db.query(Contestant).all())


# ---------------------------------------------------------------------------
# Defect 1: relevance score never refuses a submission
# ---------------------------------------------------------------------------

LOW_SCORING_NOMINATIONS = [
    ("Eric Omondi", "<p>Please vote for Eric Omondi, the funniest man in Kenya</p>"),
    ("Mammito", "<p>Vote for me, she is the best</p>"),
    ("Anne Kansiime", "<p>Please vote for her https://youtu.be/X-s_AHxiLI4</p>"),
]


@pytest.mark.parametrize("title,description", LOW_SCORING_NOMINATIONS)
def test_these_texts_score_below_the_threshold_with_the_real_checker(title, description):
    """Guard: the API tests below would prove nothing if these texts scored high."""
    result = content_relevance_service.check_relevance(
        contestant_title=title, contestant_description=description,
        contest_title="Comedy Contest", contest_description=COMEDY_DESCRIPTION, contest_type="comedy")
    assert result.is_relevant is False


@pytest.mark.parametrize("title,description", LOW_SCORING_NOMINATIONS)
def test_low_relevance_comedy_nomination_is_created(client, db, world, title, description):
    c = world.make()
    r = nominate(client, person(db, 30), c, title, description, link="https://youtu.be/X-s_AHxiLI4")
    assert r.status_code == 201, r.text
    assert r.json()["created"] is True
    assert snapshot(db) == [(r.json()["id"], title, c.id, world.round.id, "nomination")]


@pytest.mark.parametrize("contest_type,name", [
    ("dj", "DJ Contest"), ("handsome", "Handsome Contest"), ("bongo-flavor-singer", "Bongo Flava Song Contest"),
    ("beauty", "Beauty Contest"), ("famous-person", "Famous Person Contest"),
])
def test_low_relevance_nomination_in_other_categories_is_created(client, db, world, contest_type, name):
    c = world.make(contest_type=contest_type, name=name, description="Nominate your favourite.")
    r = nominate(client, person(db, 30), c, "Eric Omondi", "<p>Please vote for him</p>")
    assert r.status_code == 201, r.text
    assert len(snapshot(db)) == 1


def test_low_relevance_participation_is_created(client, db, world):
    c = world.make(mode="participation")
    body = {"title": "My set", "description": "<p>Please vote for me</p>", "image_media_ids": ["https://example.com/a.jpg"]}
    r = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(person(db, 30)), json=body)
    assert r.status_code == 201, r.text


def test_relevance_messages_are_english():
    result = content_relevance_service.check_relevance(
        contestant_title="Abc", contestant_description="xx https://example.org vote for me",
        contest_title="Comedy Contest", contest_description=COMEDY_DESCRIPTION, contest_type="comedy")
    text = " ".join(result.suggestions + result.reasons)
    assert result.suggestions
    for french in ("Ajoutez", "Votre", "Évitez", "titre", "concours", "Aucune"):
        assert french not in text


def test_youtu_be_link_in_description_is_not_penalised():
    suspicious = content_relevance_service._contains_suspicious_links
    assert not suspicious("comedian https://youtu.be/abc")
    assert not suspicious("comedian https://www.youtube.com/watch?v=abc")
    assert suspicious("comedian https://example.org/abc")


def test_comedy_has_its_own_keywords():
    result = content_relevance_service.check_relevance(
        contestant_title="Alex Muhangi", contestant_description="Funny stand-up comedian, makes everyone laugh",
        contest_title="Comedy Contest", contest_description=COMEDY_DESCRIPTION, contest_type="comedy")
    assert any("comedian" in r for r in result.reasons)


def test_text_moderation_still_rejects(client, db, world, monkeypatch):
    """Making relevance non-blocking does not weaken moderation."""
    from app.services.content_moderation import ContentFlag, FlagType, Severity, content_moderation_service

    flagged = ModerationResult(False, 0.99, [ContentFlag(FlagType.HATE, Severity.HIGH, 0.99, "hate")], {})
    monkeypatch.setattr(content_moderation_service, "moderate_text", lambda text: flagged)
    r = nominate(client, person(db, 30), world.make(), "Eric Omondi", "<p>Comedian</p>")
    assert r.status_code == 422 and "Text content rejected" in r.json()["detail"]
    assert snapshot(db) == []


def test_duplicate_video_is_still_refused(client, db, world):
    c = world.make()
    link = "https://www.youtube.com/watch?v=dupdupdup01"
    assert nominate(client, person(db, 30), c, "Comedian One", "<p>Comedian</p>", link=link).status_code == 201
    r = nominate(client, person(db, 30), c, "Comedian Two", "<p>Comedian</p>", link=link)
    assert r.status_code == 409 and "already been submitted" in r.json()["detail"]
    assert len(snapshot(db)) == 1


# ---------------------------------------------------------------------------
# Defect 2: sibling-contest nominations
# ---------------------------------------------------------------------------

def test_same_contest_second_nominee_is_created(client, db, world):
    c = world.make()
    user = person(db, 30)
    r1 = nominate(client, user, c, "Comedian One", "<p>Comedian One, stand-up comedian</p>")
    r2 = nominate(client, user, c, "Comedian Two", "<p>Comedian Two, stand-up comedian</p>")
    assert (r1.status_code, r2.status_code) == (201, 201)
    assert r1.json()["created"] is r2.json()["created"] is True
    assert [t for _, t, *_ in snapshot(db)] == ["Comedian One", "Comedian Two"]


@pytest.mark.parametrize("categorised", [False, True], ids=["null-category-comedy", "category-id"])
def test_sibling_contest_nomination_is_a_conflict_and_changes_nothing(client, db, world, categorised):
    cat_id = category(db).id if categorised else None
    first = world.make(category_id=cat_id, name="Comedy Contest")
    second = world.make(category_id=cat_id, name="Comedy Contest (duplicate)")
    user = person(db, 30)
    r1 = nominate(client, user, first, "Comedian One", "<p>Comedian One, stand-up comedian</p>")
    assert r1.status_code == 201
    before = snapshot(db)

    r2 = nominate(client, user, second, "Comedian Two", "<p>Comedian Two, stand-up comedian</p>")
    assert r2.status_code == 409, r2.text
    detail = r2.json()["detail"]
    assert "already nominated" in detail and '"Comedian One"' in detail and '"Comedy Contest"' in detail
    assert "was not saved" in detail and "not changed" in detail
    assert snapshot(db) == before                     # not moved, no new row, round unchanged
    assert before[0][2] == first.id


def test_other_users_can_still_nominate_in_the_sibling_contest(client, db, world):
    first, second = world.make(), world.make()
    assert nominate(client, person(db, 30), first, "Comedian One", "<p>Comedian</p>").status_code == 201
    assert nominate(client, person(db, 30), second, "Comedian Two", "<p>Comedian</p>").status_code == 201


def test_participation_contest_of_the_same_category_is_not_a_sibling(client, db, world):
    """Scoped by mode: a legacy nomination-typed row on the Comedy participation
    contest no longer blocks (or gets moved by) a Comedy nomination."""
    participation = world.make(mode="participation")
    nomination = world.make()
    user = person(db, 30)
    legacy = Contestant(user_id=user.id, season_id=participation.id, round_id=world.round.id, entry_type="nomination",
                        title="Legacy row", description="legacy", registration_date=TODAY)
    db.add(legacy)
    db.commit()
    r = nominate(client, user, nomination, "Comedian Two", "<p>Comedian</p>")
    assert r.status_code == 201, r.text
    db.refresh(legacy)
    assert (legacy.season_id, legacy.round_id) == (participation.id, world.round.id)


def test_other_round_is_not_a_conflict(client, db, world):
    first, second = world.make(), world.make()
    user = person(db, 30)
    old = Contestant(user_id=user.id, season_id=first.id, round_id=None, entry_type="nomination",
                     title="Older round", description="x", registration_date=TODAY)
    db.add(old)
    db.commit()
    assert nominate(client, user, second, "Comedian Two", "<p>Comedian</p>").status_code == 201


def test_resubmitting_the_same_nomination_returns_it_with_200_not_201(client, db, world):
    c = world.make()
    user = person(db, 30)
    link = "https://www.youtube.com/watch?v=samesame001"
    r1 = nominate(client, user, c, "Comedian One", "<p>Comedian</p>", link=link)
    r2 = nominate(client, user, c, "Comedian One", "<p>Comedian</p>", link=link)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r2.json()["created"] is False and r2.json()["id"] == r1.json()["id"]
    assert len(snapshot(db)) == 1


def test_resubmitting_a_participation_returns_it_with_200_not_201(client, db, world):
    c = world.make(mode="participation")
    user = person(db, 30)
    body = {"title": "My set", "description": "<p>Comedy set</p>", "image_media_ids": ["https://example.com/a.jpg"]}
    r1 = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(user), json=body)
    r2 = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(user), json=body)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["created"] is True and r2.json()["created"] is False


def test_contest_ids_for_category_mode_filter(db, world):
    nom, part = world.make(), world.make(mode="participation")
    odd = world.make(mode="Nomination ")                          # normalised like elsewhere
    both = set(contest_ids_for_category(db, category_id=None, contest_type="comedy"))
    assert both == {nom.id, part.id, odd.id}                      # default unchanged
    assert set(contest_ids_for_category(db, category_id=None, contest_type="comedy", contest_mode="nomination")) == {nom.id, odd.id}
    assert contest_ids_for_category(db, category_id=None, contest_type="comedy", contest_mode="participation") == [part.id]
