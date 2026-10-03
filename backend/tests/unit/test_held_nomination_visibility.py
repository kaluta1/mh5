"""A nomination that is still on hold must never look "approved but missing".

Production case (application 1361, read-only audit 2026-10-03): a nomination
submitted in its submission month was correctly linked to its contest and
round, but was still HELD (unclaimed nominee, content awaiting review). It was
rightly absent from the public roster, yet the contest card counted it as a
participant and My Applications labelled it "Approved".

These tests pin the rules without weakening any gate:
  * a held entry is neither listed nor counted, for anyone;
  * its owner is told it is pending (never "approved");
  * once it is genuinely approved it is listed in its own contest, round and
    country only, and is still not votable before its voting window;
  * a failed roster request is an error, not an empty roster.

All users, contests, rounds and entries are SYNTHETIC.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from app.core.child_safety import ContentRating
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant, ContestantSeason
from app.models.round import Round
from app.models.voting import ContestantVoting
from app.services import content_safety as cs
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import (  # noqa: F401
    TODAY,
    _post,
    api_world,
    person,
)
from tests.unit.test_phase6_content_safety import moderator

HTML_DESCRIPTION = "<p><strong>A FREESTYLE</strong></p><p><br></p>"


def _next_month_start(d):
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1)


@pytest.fixture
def world(db, api_world, monkeypatch):
    """Contests with an open submission round on a real calendar: submission
    this month, Country voting from the first day of next month."""
    from app import crud

    rounds = {}

    def _round_for(db_, contest_id=None, *_a, **_k):
        return rounds.get(contest_id)

    def make(mode="nomination"):
        c = api_world(mode=mode)
        rnd = db.query(Round).filter(Round.contest_id == c.id).one()
        month = TODAY.replace(day=1)
        vote_open = _next_month_start(TODAY)
        rnd.submission_start_date = month
        rnd.submission_end_date = vote_open - timedelta(days=1)
        rnd.voting_start_date = vote_open
        rnd.voting_end_date = vote_open + timedelta(days=150)
        rnd.country_season_start_date = vote_open
        rnd.country_season_end_date = vote_open + timedelta(days=27)
        db.commit()
        rounds[c.id] = rnd
        # api_world's stubs only accept positional arguments; the read paths
        # call these with keywords.
        monkeypatch.setattr(crud.round, "get_active_round_for_contest", _round_for)
        monkeypatch.setattr(crud.round, "get_preferred_nomination_round_for_contest", _round_for)
        return c, rnd

    return make


def _nominate(client, db, c, nominator, **body):
    body.setdefault("nominee_age_declaration", "ADULT")
    body.setdefault("nominator_country", nominator.country)
    resp = _post(client, nominator, c, **body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _approve(client, db, submission):
    """The real path to publication: the nominee claims, a moderator approves."""
    nominee = person(db, 28, email_verified=True)
    claimed = client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                          json={"token": submission["nominee_claim_token"], "decision": "ACCEPT"})
    assert claimed.status_code == 200, claimed.text
    cs.moderate(db, cs.moderation_for(db, submission["id"]), action="APPROVE", actor=moderator(db),
                reason="REVIEWED_OK", rating=ContentRating.GENERAL, today=TODAY)
    db.expire_all()
    assert db.query(ContestEntrySafety).filter_by(contestant_id=submission["id"]).one().exposure_status == "PUBLIC"


def _detail(client, c, rnd, *, viewer=None, country="Tanzania"):
    params = {"roundId": rnd.id, "entryType": "nomination", "rosterOnly": "true"}
    if country:
        params["filterCountry"] = country
    resp = client.get(f"/api/v1/contests/{c.id}", params=params, headers=auth(viewer) if viewer else {})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(payload):
    return [row["id"] for row in payload["contestants"]]


def _my_entry(client, user, entry_id):
    rows = client.get("/api/v1/contestants/user/my-entries", headers=auth(user)).json()
    return next(r for r in rows if r["id"] == entry_id)


# ---------------------------------------------------------------------------
# held entry: correctly linked, not listed, not counted, owner told "pending"
# ---------------------------------------------------------------------------

def test_held_nomination_is_linked_correctly_but_neither_listed_nor_counted(client, db, world):
    c, rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator, description=HTML_DESCRIPTION)
    assert body["public_status"] == "PENDING_REVIEW"

    row = db.query(Contestant).filter(Contestant.id == body["id"]).one()
    # application -> contest / round / entry type / geography: all correct at creation
    assert (row.season_id, row.round_id, row.entry_type) == (c.id, rnd.id, "nomination")
    assert row.user_id == nominator.id and row.is_active is False
    # No stage membership during the submission month: that is the calendar, not a defect.
    assert db.query(ContestantSeason).filter(ContestantSeason.contestant_id == row.id).count() == 0

    for viewer in (None, person(db, 30), nominator):
        payload = _detail(client, c, rnd, viewer=viewer)
        assert _ids(payload) == []
        assert payload["entries_count"] == len(payload["contestants"]) == 0

    owner = _detail(client, c, rnd, viewer=nominator)
    assert owner["current_user_contesting"] is True
    assert owner["current_user_entry_status"] == "PENDING_REVIEW"
    stranger = _detail(client, c, rnd, viewer=person(db, 30))
    assert stranger["current_user_entry_status"] is None

    mine = _my_entry(client, nominator, row.id)
    # is_qualified defaults to true and is NOT a review outcome.
    assert mine["is_qualified"] is True and mine["public_status"] == "PENDING_REVIEW"


# ---------------------------------------------------------------------------
# approved entry: listed in its own contest / round / country, count == cards
# ---------------------------------------------------------------------------

def test_approved_nomination_is_listed_in_its_submission_round_and_country_only(client, db, world):
    c, rnd = world()
    nominator = person(db, 30, country="Tanzania")
    body = _nominate(client, db, c, nominator)
    _approve(client, db, body)

    # Still no ContestantSeason row (Country voting has not opened): the entry is
    # found through its own contest + round, with nothing to "repair".
    assert db.query(ContestantSeason).filter(ContestantSeason.contestant_id == body["id"]).count() == 0

    home = _detail(client, c, rnd, country="Tanzania")
    assert _ids(home) == [body["id"]]
    assert home["entries_count"] == len(home["contestants"]) == 1

    abroad = _detail(client, c, rnd, country="Uganda")
    assert _ids(abroad) == []

    owner = _detail(client, c, rnd, viewer=nominator)
    assert owner["current_user_entry_status"] == "PUBLIC"
    assert _my_entry(client, nominator, body["id"])["public_status"] == "PUBLIC"


def test_approved_nomination_is_not_vote_eligible_before_its_voting_window(client, db, world):
    c, rnd = world()
    assert rnd.voting_start_date > TODAY
    body = _nominate(client, db, c, person(db, 30))
    _approve(client, db, body)

    voter = person(db, 30)
    resp = client.post(f"/api/v1/contestants/{body['id']}/vote", headers=auth(voter))
    assert resp.status_code != 200, resp.text
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == body["id"]).count() == 0


def test_pending_and_prohibited_entries_stay_out_of_roster_and_count(client, db, world):
    c, rnd = world()
    pending = _nominate(client, db, c, person(db, 30))
    prohibited = _nominate(client, db, c, person(db, 30))
    cs.moderate(db, cs.moderation_for(db, prohibited["id"]), action="PROHIBIT", actor=moderator(db),
                reason="POLICY_VIOLATION", today=TODAY)
    approved = _nominate(client, db, c, person(db, 30))
    _approve(client, db, approved)

    payload = _detail(client, c, rnd)
    assert _ids(payload) == [approved["id"]]
    assert pending["id"] not in _ids(payload) and prohibited["id"] not in _ids(payload)
    assert payload["entries_count"] == len(payload["contestants"]) == 1


def test_nomination_and_participation_rosters_stay_separate(client, db, world):
    nomination_contest, nomination_round = world()
    nomination = _nominate(client, db, nomination_contest, person(db, 30))
    _approve(client, db, nomination)

    participation_contest, _participation_round = world("participation")
    entrant = person(db, 30)
    participation = _post(client, entrant, participation_contest, title="Morning song",
                          description="An acoustic cover", video_media_ids=None)
    assert participation.status_code == 200 and participation.json()["public_status"] == "PUBLIC"
    participation_id = participation.json()["id"]

    assert db.query(Contestant).get(nomination["id"]).entry_type == "nomination"
    assert db.query(Contestant).get(participation_id).entry_type == "participation"
    assert _ids(_detail(client, nomination_contest, nomination_round)) == [nomination["id"]]
    listed = client.get(f"/api/v1/contestants/contest/{participation_contest.id}").json()
    assert [r["id"] for r in listed] == [participation_id]
    assert nomination["id"] not in [r["id"] for r in listed]


def test_retried_submission_is_idempotent(client, db, world):
    c, _rnd = world()
    nominator = person(db, 30)
    video = json.dumps([f"https://youtu.be/{uuid.uuid4().hex[:8]}"])
    first = _nominate(client, db, c, nominator, video_media_ids=video)
    again = _nominate(client, db, c, nominator, video_media_ids=video)
    assert again["id"] == first["id"]
    assert db.query(Contestant).filter(Contestant.user_id == nominator.id).count() == 1
    assert db.query(ContestEntrySafety).filter_by(contestant_id=first["id"]).count() == 1


def test_month_boundary_entry_belongs_to_its_own_submission_round(client, db, world):
    """An entry is listed for the round it was submitted in, never the neighbouring month."""
    c, current = world()
    previous = Round(name="previous month", contest_id=c.id,
                     submission_start_date=(current.submission_start_date - timedelta(days=1)).replace(day=1),
                     submission_end_date=current.submission_start_date - timedelta(days=1),
                     voting_start_date=current.submission_start_date,
                     voting_end_date=current.submission_start_date + timedelta(days=150))
    db.add(previous)
    db.commit()

    body = _nominate(client, db, c, person(db, 30))
    _approve(client, db, body)
    assert db.query(Contestant).get(body["id"]).round_id == current.id

    assert _ids(_detail(client, c, current)) == [body["id"]]
    assert _ids(_detail(client, c, previous)) == []


# ---------------------------------------------------------------------------
# a failed roster request is an ERROR, never an empty roster
# ---------------------------------------------------------------------------

def test_roster_failure_is_reported_as_an_error_not_an_empty_list(client, db, world, monkeypatch):
    c, _rnd = world()
    assert client.get(f"/api/v1/contestants/contest/{c.id}").json() == []   # genuinely empty: 200 []

    from app.services import viewer_access

    def boom(*_a, **_k):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(viewer_access, "listing_clause", boom)
    failed = client.get(f"/api/v1/contestants/contest/{c.id}")
    assert failed.status_code == 500
    assert failed.json() != []
    assert "synthetic database failure" not in failed.text      # no internals leaked


# ---------------------------------------------------------------------------
# REJECTED: the administrator's "reject" decision (verification_status)
# ---------------------------------------------------------------------------

def _reject(client, db, entry_id):
    """The real rejection path: an administrator rejects the entry."""
    admin = person(db, 40, admin=True)
    resp = client.post(f"/api/v1/admin/contestants/{entry_id}/reject", headers=auth(admin))
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(Contestant).get(entry_id).verification_status == "rejected"


def test_rejected_nomination_is_not_listed_not_counted_and_not_labelled_approved(client, db, world):
    c, rnd = world()
    kept = _nominate(client, db, c, person(db, 30))
    _approve(client, db, kept)
    nominator = person(db, 30)
    rejected = _nominate(client, db, c, nominator)
    _approve(client, db, rejected)          # it was public before being rejected
    assert sorted(_ids(_detail(client, c, rnd))) == sorted([kept["id"], rejected["id"]])

    _reject(client, db, rejected["id"])

    row = db.query(Contestant).get(rejected["id"])
    # is_qualified is still true: it must not be what makes an entry visible.
    assert row.is_qualified is True

    for viewer in (None, person(db, 30), nominator):
        payload = _detail(client, c, rnd, viewer=viewer)
        assert _ids(payload) == [kept["id"]]
        assert payload["entries_count"] == len(payload["contestants"]) == 1

    listed = client.get(f"/api/v1/contestants/contest/{c.id}", params={"roundId": rnd.id}).json()
    assert [r["id"] for r in listed] == [kept["id"]]

    # A stranger cannot open or vote for it; the owner still sees their own entry.
    stranger = person(db, 30)
    assert client.get(f"/api/v1/contestants/{rejected['id']}", headers=auth(stranger)).status_code == 404
    assert client.post(f"/api/v1/contestants/{rejected['id']}/vote", headers=auth(stranger)).status_code != 200
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == rejected["id"]).count() == 0
    assert client.get(f"/api/v1/contestants/{rejected['id']}", headers=auth(nominator)).status_code == 200

    mine = _my_entry(client, nominator, rejected["id"])
    assert mine["is_qualified"] is True
    assert mine["public_status"] == "REJECTED"
    assert _detail(client, c, rnd, viewer=nominator)["current_user_entry_status"] == "REJECTED"


def test_rejected_pending_and_prohibited_are_three_distinct_states(client, db, world):
    c, rnd = world()
    pending_owner, prohibited_owner, rejected_owner = person(db, 30), person(db, 30), person(db, 30)
    pending = _nominate(client, db, c, pending_owner)
    prohibited = _nominate(client, db, c, prohibited_owner)
    cs.moderate(db, cs.moderation_for(db, prohibited["id"]), action="PROHIBIT", actor=moderator(db),
                reason="POLICY_VIOLATION", today=TODAY)
    rejected = _nominate(client, db, c, rejected_owner)
    _approve(client, db, rejected)
    _reject(client, db, rejected["id"])
    db.expire_all()

    def state(entry_id):
        row = db.query(Contestant).get(entry_id)
        safety = db.query(ContestEntrySafety).filter_by(contestant_id=entry_id).one()
        return row.verification_status, safety.exposure_status, cs.moderation_for(db, entry_id).state

    assert state(pending["id"]) == ("pending", "HELD", "REVIEW_REQUIRED")
    assert state(prohibited["id"])[2] == "PROHIBITED" and state(prohibited["id"])[0] != "rejected"
    assert state(rejected["id"])[0] == "rejected" and state(rejected["id"])[2] == "APPROVED"

    assert _my_entry(client, pending_owner, pending["id"])["public_status"] == "PENDING_REVIEW"
    assert _my_entry(client, prohibited_owner, prohibited["id"])["public_status"] == "PENDING_REVIEW"
    assert _my_entry(client, rejected_owner, rejected["id"])["public_status"] == "REJECTED"

    payload = _detail(client, c, rnd)
    assert _ids(payload) == [] and payload["entries_count"] == 0


def test_rejection_alone_hides_a_legacy_entry_that_has_no_review_record(client, db, world):
    """Entries created before review records existed are public by default;
    an administrator's rejection must still take them out of the roster."""
    c, rnd = world()
    owner = person(db, 30)
    legacy = Contestant(user_id=owner.id, season_id=c.id, round_id=rnd.id, title="Legacy", description="d",
                        entry_type="nomination", country=owner.country, nominator_country=owner.country,
                        is_active=True, is_deleted=False, is_qualified=True)
    db.add(legacy)
    db.commit()
    assert _ids(_detail(client, c, rnd)) == [legacy.id]

    _reject(client, db, legacy.id)
    payload = _detail(client, c, rnd)
    assert _ids(payload) == [] and payload["entries_count"] == 0
    assert _my_entry(client, owner, legacy.id)["public_status"] == "REJECTED"
