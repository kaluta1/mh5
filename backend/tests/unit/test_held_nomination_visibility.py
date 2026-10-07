"""Nomination publication, and what still keeps an entry out of a contest.

Management rule (2026-10-04): a valid NOMINATION is published as soon as it is
submitted. An unclaimed nominee, pending rights, content waiting for its first
human review, a minor nominee without guardian consent and a missing date of
birth are recorded as facts but no longer hold publication. Nothing is
fabricated: the claim, rights, guardian and moderation records keep their real
state.

What still hides a nomination: a nominee who declined, prohibited or flagged
content, a moderator's hold, an administrator's block or rejection,
child-safety escalation, and a contest's own explicit rules. Personal
participation entries keep their previous behaviour. Publication is not
voting: stage timing still decides when votes open.

(History: the production case that started this - application 1361 - was a
held nomination labelled "Approved" by the UI. The owner-status and count
rules from that fix are still pinned here, on entries that are really held.)

All users, contests, rounds and entries are SYNTHETIC.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from app.core.child_safety import ContentRating, NomineeAgeDeclaration as D
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant, ContestantSeason
from app.models.guardian import GuardianRelationship
from app.models.round import Round
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services import content_safety as cs
from app.services import contest_eligibility as ce
from app.services import participation_safety as ps
from app.services.content_moderation import FlagType
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import (  # noqa: F401
    TODAY,
    _post,
    api_world,
    category,
    contest,
    flag,
    nominate,
    person,
    rule,
)
from tests.unit.test_phase6_content_safety import moderator

HTML_DESCRIPTION = "<p><strong>A FREESTYLE</strong></p><p><br></p>"
ADVISORY = {"NOMINEE_UNCLAIMED", "RIGHTS_CONFIRMATION_REQUIRED", "CONTENT_REVIEW_REQUIRED"}


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

    def make(mode="nomination", **extra):
        c = api_world(mode=mode, **extra)
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


def _safety(db, entry_id) -> ContestEntrySafety:
    db.expire_all()
    return db.query(ContestEntrySafety).filter_by(contestant_id=entry_id).one()


def _moderation(db, entry_id) -> ContentModeration:
    db.expire_all()
    return db.query(ContentModeration).filter_by(contestant_id=entry_id).one()


def _is_public_everywhere(client, db, c, rnd, entry_id):
    """Roster, count, anonymous detail and the participation decision agree."""
    payload = _detail(client, c, rnd)
    listed = client.get(f"/api/v1/contestants/contest/{c.id}", params={"roundId": rnd.id}).json()
    decision = ps.participation_decision(db, db.query(Contestant).get(entry_id))
    return (entry_id in _ids(payload) and payload["entries_count"] == len(payload["contestants"])
            and entry_id in [r["id"] for r in listed]
            and client.get(f"/api/v1/contestants/{entry_id}").status_code == 200
            and decision.eligible)


def _is_hidden_everywhere(client, db, c, rnd, entry_id):
    payload = _detail(client, c, rnd)
    listed = client.get(f"/api/v1/contestants/contest/{c.id}", params={"roundId": rnd.id}).json()
    decision = ps.participation_decision(db, db.query(Contestant).get(entry_id))
    return (entry_id not in _ids(payload) and payload["entries_count"] == len(payload["contestants"])
            and entry_id not in [r["id"] for r in listed]
            and client.get(f"/api/v1/contestants/{entry_id}").status_code == 404
            and not decision.eligible)


# ===========================================================================
# 1. Immediate publication of a nomination
# ===========================================================================

def test_nomination_with_an_external_video_is_published_immediately(client, db, world):
    c, rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator, description=HTML_DESCRIPTION)

    assert body["public_status"] == "PUBLIC" and body["message"] == "Submission created successfully."
    row = db.query(Contestant).get(body["id"])
    assert (row.season_id, row.round_id, row.entry_type, row.is_active) == (c.id, rnd.id, "nomination", True)

    # Facts are kept as they are; nothing is fabricated.
    safety = _safety(db, row.id)
    assert safety.exposure_status == "PUBLIC" and safety.activated_at is not None
    assert safety.nominee_user_id is None and safety.claimed_at is None            # still unclaimed
    assert safety.rights_status == "PENDING"                                       # still pending
    assert ADVISORY <= set(safety.reason_codes)
    moderation = _moderation(db, row.id)
    assert moderation.state == "REVIEW_REQUIRED" and moderation.rating is None     # still awaiting review
    assert moderation.decided_by_user_id is None and moderation.automated_decision is False
    assert db.query(GuardianRelationship).count() == 0

    # The claim link is still offered, as an option for the nominee.
    assert body["nominee_claim_token"] and safety.claim_token_hash

    # No stage membership before the stage opens.
    assert db.query(ContestantSeason).filter(ContestantSeason.contestant_id == row.id).count() == 0

    assert _is_public_everywhere(client, db, c, rnd, row.id)
    for viewer in (None, person(db, 30), nominator):
        payload = _detail(client, c, rnd, viewer=viewer)
        assert _ids(payload) == [row.id] and payload["entries_count"] == 1

    # The owner is told it is live, never "pending review".
    assert _detail(client, c, rnd, viewer=nominator)["current_user_entry_status"] == "PUBLIC"
    assert _my_entry(client, nominator, row.id)["public_status"] == "PUBLIC"


@pytest.mark.parametrize("declaration, recorded", [
    ("MINOR", {"NOMINEE_DECLARED_MINOR", "GUARDIAN_CONSENT_REQUIRED"}),
    ("UNKNOWN", {"NOMINEE_AGE_UNDETERMINED"}),
    (None, {"NOMINEE_AGE_UNDETERMINED"}),
])
def test_minor_or_unknown_age_nominee_does_not_hold_publication(client, db, world, declaration, recorded):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30), nominee_age_declaration=declaration)
    assert body["public_status"] == "PUBLIC"
    safety = _safety(db, body["id"])
    assert safety.exposure_status == "PUBLIC" and recorded <= set(safety.reason_codes)
    # Guardian consent is not fabricated: none exists, and none is recorded.
    assert safety.guardian_relationship_id is None and db.query(GuardianRelationship).count() == 0
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_nominator_without_a_date_of_birth_can_still_publish_a_nomination(client, db, world):
    c, rnd = world()
    nominator = person(db, None)
    body = _nominate(client, db, c, nominator)
    assert body["public_status"] == "PUBLIC"
    assert "AGE_REQUIRED" in _safety(db, body["id"]).reason_codes       # the fact is kept
    assert db.query(User).get(nominator.id).date_of_birth is None       # no date of birth is invented
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_minor_nominator_can_publish_a_nomination_without_fabricated_consent(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 16))
    assert body["public_status"] == "PUBLIC"
    assert db.query(GuardianRelationship).count() == 0
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_public_nomination_is_listed_in_its_own_round_and_country_only(client, db, world):
    c, current = world()
    previous = Round(name="previous month", contest_id=c.id,
                     submission_start_date=(current.submission_start_date - timedelta(days=1)).replace(day=1),
                     submission_end_date=current.submission_start_date - timedelta(days=1),
                     voting_start_date=current.submission_start_date,
                     voting_end_date=current.submission_start_date + timedelta(days=150))
    db.add(previous)
    db.commit()
    body = _nominate(client, db, c, person(db, 30, country="Tanzania"))
    assert _ids(_detail(client, c, current, country="Tanzania")) == [body["id"]]
    assert _ids(_detail(client, c, current, country="Uganda")) == []
    assert _ids(_detail(client, c, previous)) == []


def test_retried_submission_is_idempotent(client, db, world):
    c, _rnd = world()
    nominator = person(db, 30)
    video = json.dumps([f"https://youtu.be/{uuid.uuid4().hex[:8]}"])
    first = _nominate(client, db, c, nominator, video_media_ids=video)
    again = _nominate(client, db, c, nominator, video_media_ids=video)
    assert again["id"] == first["id"]
    assert db.query(Contestant).filter(Contestant.user_id == nominator.id).count() == 1
    assert db.query(ContestEntrySafety).filter_by(contestant_id=first["id"]).count() == 1


# ===========================================================================
# 2. Publication is not voting
# ===========================================================================

def test_public_nomination_is_not_votable_before_its_stage_opens(client, db, world):
    c, rnd = world()
    assert rnd.voting_start_date > TODAY
    body = _nominate(client, db, c, person(db, 30))
    row = db.query(Contestant).get(body["id"])
    voter = person(db, 30)

    resp = client.post(f"/api/v1/contestants/{row.id}/vote", headers=auth(voter))
    assert resp.status_code != 200, resp.text
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == row.id).count() == 0
    # Not because of safety: the safety gate accepts it. Stage timing is what closes voting.
    assert ps.can_receive_vote(db, row, voter).eligible is True
    assert ps.participation_decision(db, row).eligible is True


def test_pending_first_review_does_not_exclude_a_nomination_from_ranking_or_voting_gates(client, db, world):
    """PUBLIC nomination does not imply moderation APPROVED - and the ranking /
    voting safety gates must not assume it does."""
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    row = db.query(Contestant).get(body["id"])
    assert _moderation(db, row.id).state == "REVIEW_REQUIRED"
    decision = ps.participation_decision(db, row)
    assert decision.eligible is True and ps.Reason.CONTENT_NOT_APPROVED not in decision.reasons
    assert ps.can_appear_in_ranking(db, row).eligible is True
    assert ps.can_progress(db, row, today=TODAY).eligible is True


# ===========================================================================
# 3. What still hides a nomination (after publication too)
# ===========================================================================

@pytest.mark.parametrize("action", ["HOLD", "REQUEST_UPDATE", "PROHIBIT", "ESCALATE_CHILD_SAFETY"])
def test_a_moderator_action_overrides_provisional_publication(client, db, world, action):
    c, rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    assert _is_public_everywhere(client, db, c, rnd, body["id"])

    cs.moderate(db, _moderation(db, body["id"]), action=action, actor=moderator(db), reason="REVIEW_DECISION",
                today=TODAY)
    assert _safety(db, body["id"]).exposure_status != "PUBLIC"
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])
    assert _detail(client, c, rnd, viewer=nominator)["current_user_entry_status"] == "PENDING_REVIEW"
    # Re-evaluating never brings it back by itself.
    ce.reevaluate_entry(db, _safety(db, body["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


def test_moderator_approval_keeps_it_public_with_a_real_rating(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    cs.moderate(db, _moderation(db, body["id"]), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    moderation = _moderation(db, body["id"])
    assert moderation.state == "APPROVED" and moderation.rating == "GENERAL" and moderation.decided_by_user_id
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_rejected_nomination_stays_hidden_and_never_reappears(client, db, world):
    c, rnd = world()
    kept = _nominate(client, db, c, person(db, 30))
    nominator = person(db, 30)
    rejected = _nominate(client, db, c, nominator)
    assert sorted(_ids(_detail(client, c, rnd))) == sorted([kept["id"], rejected["id"]])

    admin = person(db, 40, admin=True)
    assert client.post(f"/api/v1/admin/contestants/{rejected['id']}/reject",
                       headers=auth(admin)).status_code == 200
    assert _is_hidden_everywhere(client, db, c, rnd, rejected["id"])
    assert _ids(_detail(client, c, rnd)) == [kept["id"]]

    # The immediate-publication policy must not bring a rejected entry back.
    ce.reevaluate_entry(db, _safety(db, rejected["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin)).status_code == 200
    assert _is_hidden_everywhere(client, db, c, rnd, rejected["id"])
    stranger = person(db, 30)
    assert client.post(f"/api/v1/contestants/{rejected['id']}/vote", headers=auth(stranger)).status_code != 200
    mine = _my_entry(client, nominator, rejected["id"])
    assert mine["is_qualified"] is True and mine["public_status"] == "REJECTED"
    assert _detail(client, c, rnd, viewer=nominator)["current_user_entry_status"] == "REJECTED"


def test_admin_block_hides_it_and_reevaluation_does_not_undo_it(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    admin = person(db, 40, admin=True)
    ce.admin_review(db, _safety(db, body["id"]), action="BLOCK", admin_id=admin.id, note="synthetic block",
                    today=TODAY)
    assert _safety(db, body["id"]).exposure_status == "BLOCKED"
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])
    ce.reevaluate_entry(db, _safety(db, body["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert _safety(db, body["id"]).exposure_status == "BLOCKED"
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


def test_prohibited_text_is_still_refused_at_submission(client, db, world, monkeypatch):
    from app.services.content_moderation import content_moderation_service

    c, _rnd = world()
    monkeypatch.setattr(content_moderation_service, "moderate_text", lambda text: flag(FlagType.HATE))
    resp = _post(client, person(db, 30), c, nominee_age_declaration="ADULT")
    assert resp.status_code == 422
    assert db.query(Contestant).count() == 0


def test_a_contests_own_adult_only_rule_still_holds_a_minor_nomination(db):
    cat = category(db)
    c = contest(db, "nomination", category_id=cat.id)
    rule(db, "category", cat.id, adult_only=True, minor_participation_allowed=False)
    held = nominate(db, person(db, 30), c, D.MINOR)
    assert not held.public and "ADULT_ONLY_CATEGORY" in [r.value for r in held.reasons]
    # The same contest still publishes an adult nomination at once.
    assert nominate(db, person(db, 30), c, D.ADULT).public


# ===========================================================================
# 4. Claim: optional, factual, and a refusal is honoured
# ===========================================================================

def test_nominee_can_still_claim_a_public_nomination(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    nominee = person(db, 28, email_verified=True)
    resp = client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                       json={"token": body["nominee_claim_token"], "decision": "ACCEPT"})
    assert resp.status_code == 200, resp.text
    safety = _safety(db, body["id"])
    assert safety.nominee_user_id == nominee.id and safety.claimed_at is not None
    assert safety.rights_status == "CONFIRMED"            # a real event confirmed it
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_nominee_who_declines_hides_the_nomination(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    assert _is_public_everywhere(client, db, c, rnd, body["id"])
    nominee = person(db, 28, email_verified=True)
    resp = client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                       json={"token": body["nominee_claim_token"], "decision": "DECLINE"})
    assert resp.status_code == 200, resp.text
    safety = _safety(db, body["id"])
    assert safety.rights_status == "DISPUTED" and safety.claim_declined_at is not None
    assert safety.exposure_status == "HELD"               # "not yet claimed" is fine; "refused" is not
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


# ===========================================================================
# 5. Personal participation is unchanged
# ===========================================================================

def test_participation_with_an_external_video_still_waits_for_review(client, db, world):
    c, rnd = world("participation")
    entrant = person(db, 30)
    resp = _post(client, entrant, c)                       # YouTube link
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW"
    entry_id = resp.json()["id"]
    safety = _safety(db, entry_id)
    assert safety.exposure_status == "HELD" and "CONTENT_REVIEW_REQUIRED" in safety.reason_codes
    assert db.query(Contestant).get(entry_id).is_active is False
    assert client.get(f"/api/v1/contestants/contest/{c.id}").json() == []
    assert client.get(f"/api/v1/contestants/{entry_id}").status_code == 404
    assert ps.participation_decision(db, db.query(Contestant).get(entry_id)).eligible is False
    # The owner is told the truth, and is_qualified is not what decides it.
    mine = _my_entry(client, entrant, entry_id)
    assert mine["is_qualified"] is True and mine["public_status"] == "PENDING_REVIEW"
    # A moderator's approval is still what publishes it.
    cs.moderate(db, _moderation(db, entry_id), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    assert _safety(db, entry_id).exposure_status == "PUBLIC"


def test_participation_still_requires_a_date_of_birth_and_guardian_consent(client, db, world):
    c, _rnd = world("participation")
    no_dob = _post(client, person(db, None), c, title="Morning song", description="An acoustic cover",
                   video_media_ids=None)
    assert no_dob.status_code == 200
    assert no_dob.json()["public_status"] == "PENDING_REVIEW" and no_dob.json()["next_step"] == "ADD_DATE_OF_BIRTH"
    c2, _ = world("participation")
    minor = _post(client, person(db, 16), c2, title="Morning song", description="An acoustic cover",
                  video_media_ids=None)
    assert minor.status_code == 200 and minor.json()["public_status"] == "PENDING_REVIEW"
    assert "GUARDIAN_CONSENT_REQUIRED" in _safety(db, minor.json()["id"]).reason_codes


def test_safe_adult_participation_is_still_public_and_rosters_stay_separate(client, db, world):
    nomination_contest, nomination_round = world()
    nomination = _nominate(client, db, nomination_contest, person(db, 30))
    participation_contest, _r = world("participation")
    participation = _post(client, person(db, 30), participation_contest, title="Morning song",
                          description="An acoustic cover", video_media_ids=None)
    assert participation.status_code == 200 and participation.json()["public_status"] == "PUBLIC"
    participation_id = participation.json()["id"]
    assert db.query(Contestant).get(nomination["id"]).entry_type == "nomination"
    assert db.query(Contestant).get(participation_id).entry_type == "participation"
    assert _ids(_detail(client, nomination_contest, nomination_round)) == [nomination["id"]]
    listed = client.get(f"/api/v1/contestants/contest/{participation_contest.id}").json()
    assert [r["id"] for r in listed] == [participation_id]


# ===========================================================================
# 6. An existing held nomination (the application 1361 case)
# ===========================================================================

def test_existing_held_nomination_becomes_public_through_reevaluation_only(client, db, world, monkeypatch):
    """A nomination stored as HELD under the previous rule (unclaimed, rights
    pending, external video awaiting review) is published by the ordinary
    service re-evaluation - with no claim, rights, consent or moderation event
    invented, and without becoming votable early."""
    c, rnd = world()
    nominator = person(db, 30)
    with monkeypatch.context() as previous_rule:
        previous_rule.setattr(ce, "_nomination_publication_policy",
                              lambda unmet, holds, **_k: (tuple(unmet), tuple(holds), ()))
        body = _nominate(client, db, c, nominator)
    entry_id = body["id"]
    safety = _safety(db, entry_id)
    assert body["public_status"] == "PENDING_REVIEW" and safety.exposure_status == "HELD"
    assert db.query(Contestant).get(entry_id).is_active is False
    assert _is_hidden_everywhere(client, db, c, rnd, entry_id)
    before_moderation = _moderation(db, entry_id)
    snapshot = (before_moderation.state, before_moderation.rating, before_moderation.decided_by_user_id,
                safety.rights_status, safety.nominee_user_id, safety.claimed_at, safety.claim_token_hash,
                safety.guardian_relationship_id)

    admin = person(db, 40, admin=True)
    resp = client.post(f"/api/v1/admin/contest-eligibility/entries/{safety.id}/review", headers=auth(admin),
                       json={"action": "REEVALUATE", "note": "apply nomination publication policy"})
    assert resp.status_code == 200, resp.text

    safety = _safety(db, entry_id)
    row = db.query(Contestant).get(entry_id)
    assert safety.exposure_status == "PUBLIC" and safety.activated_at is not None and row.is_active is True
    assert row.entry_type == "nomination" and (row.season_id, row.round_id) == (c.id, rnd.id)
    after_moderation = _moderation(db, entry_id)
    assert snapshot == (after_moderation.state, after_moderation.rating, after_moderation.decided_by_user_id,
                        safety.rights_status, safety.nominee_user_id, safety.claimed_at, safety.claim_token_hash,
                        safety.guardian_relationship_id)
    assert after_moderation.state == "REVIEW_REQUIRED" and safety.rights_status == "PENDING"
    actions = [a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "contest_entry_safety",
                                                             AuditTrail.record_id == safety.id).all()]
    assert "ENTRY_ACTIVATED" in actions
    assert not [a for a in actions if "CLAIM_ACCEPTED" in a or "RIGHTS" in a]

    assert _is_public_everywhere(client, db, c, rnd, entry_id)
    payload = _detail(client, c, rnd)
    assert _ids(payload) == [entry_id] and payload["entries_count"] == 1
    assert _my_entry(client, nominator, entry_id)["public_status"] == "PUBLIC"
    # Still not votable before the stage opens, and no early stage membership.
    assert client.post(f"/api/v1/contestants/{entry_id}/vote", headers=auth(person(db, 30))).status_code != 200
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == entry_id).count() == 0
    assert db.query(ContestantSeason).filter(ContestantSeason.contestant_id == entry_id).count() == 0


# ===========================================================================
# 7. Owner-facing state on the contest list card
# ===========================================================================

def _card(client, c, rnd, *, viewer=None, mode="nomination"):
    """The card payload exactly as the contests list page requests it."""
    resp = client.get("/api/v1/rounds/", params={"roundId": rnd.id, "contestMode": mode, "filterCountry": "Tanzania",
                                                 "contestLimit": 50},
                      headers=auth(viewer) if viewer else {})
    assert resp.status_code == 200, resp.text
    round_row = next(r for r in resp.json() if r["id"] == rnd.id)
    return next(x for x in round_row["contests"] if x["id"] == c.id)


def _link_round(db, c, rnd):
    """The list endpoint finds a round's contests through round_contests."""
    from app.models.round import round_contests

    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=c.id))
    db.commit()


def test_list_card_shows_a_new_nomination_as_public_and_counted(client, db, world):
    c, rnd = world()
    _link_round(db, c, rnd)
    nominator = person(db, 30)
    _nominate(client, db, c, nominator)
    owner_card = _card(client, c, rnd, viewer=nominator)
    assert owner_card["current_user_contesting"] is True
    assert owner_card["current_user_entry_status"] == "PUBLIC" and owner_card["participants_count"] == 1
    for viewer in (None, person(db, 30)):
        card = _card(client, c, rnd, viewer=viewer)
        assert not card.get("current_user_contesting") and card.get("current_user_entry_status") is None
        assert card["participants_count"] == 1


def test_list_card_reports_held_and_rejected_states_without_counting_them(client, db, world):
    c, rnd = world()
    _link_round(db, c, rnd)
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    cs.moderate(db, _moderation(db, body["id"]), action="HOLD", actor=moderator(db), reason="REVIEW_DECISION",
                today=TODAY)
    card = _card(client, c, rnd, viewer=nominator)
    assert card["current_user_entry_status"] == "PENDING_REVIEW" and (card.get("participants_count") or 0) == 0

    admin = person(db, 40, admin=True)
    client.post(f"/api/v1/admin/contestants/{body['id']}/reject", headers=auth(admin))
    card = _card(client, c, rnd, viewer=nominator)
    assert card["current_user_entry_status"] == "REJECTED" and (card.get("participants_count") or 0) == 0


def test_list_card_reports_the_state_of_a_held_participation_entry(client, db, world):
    c, rnd = world("participation")
    _link_round(db, c, rnd)
    entrant = person(db, 30)
    resp = _post(client, entrant, c)                                  # YouTube link -> held for review
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW"
    card = _card(client, c, rnd, viewer=entrant, mode="participation")
    assert card["current_user_contesting"] is True and card["current_user_entry_status"] == "PENDING_REVIEW"


# ===========================================================================
# 8. Dead link at submission, and errors are not empty rosters
# ===========================================================================

def test_definitively_dead_link_is_refused_at_submission_but_a_timeout_is_not(client, db, world, monkeypatch):
    import requests

    from app.core.config import settings
    from app.services import creative_link_check as clc

    c, _rnd = world()
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_ENABLED", True)
    monkeypatch.setattr(clc, "_http_status", lambda url: 404)
    dead = _post(client, person(db, 30), c, nominee_age_declaration="ADULT",
                 video_media_ids=json.dumps(["https://youtu.be/AAAAAAAAAAA"]))
    assert dead.status_code == 422 and "not available" in dead.json()["detail"]
    assert db.query(Contestant).count() == 0

    def slow(url):
        raise requests.Timeout("slow")

    monkeypatch.setattr(clc, "_http_status", slow)
    ok = _post(client, person(db, 30), c, nominee_age_declaration="ADULT",
               video_media_ids=json.dumps(["https://youtu.be/BBBBBBBBBBB"]))
    assert ok.status_code == 200 and ok.json()["public_status"] == "PUBLIC"


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


# ===========================================================================
# 9. Publication is not voting: stage timing and stage membership still decide
# ===========================================================================

def _join_country_stage(db, c, row):
    """Normal stage membership: the entry is an active member of its contest's Country season."""
    from app.models.contests import ContestSeason, ContestSeasonLink

    season = db.query(ContestSeason).one()
    db.add(ContestSeasonLink(contest_id=c.id, season_id=season.id, is_active=True))
    db.add(ContestantSeason(contestant_id=row.id, season_id=season.id, is_active=True))
    db.commit()


def _open_country_stage(db, rnd):
    """Make the round last month's cohort, so its Country vote is open today."""
    this_month = TODAY.replace(day=1)
    rnd.submission_start_date = (this_month - timedelta(days=1)).replace(day=1)
    rnd.submission_end_date = this_month - timedelta(days=1)
    rnd.voting_start_date = this_month
    rnd.country_season_start_date = this_month
    db.commit()


def _vote(client, voter, row, c, rnd):
    return client.post(f"/api/v1/contestants/{row.id}/vote?contest_id={c.id}&round_id={rnd.id}",
                       headers=auth(voter))


def _votes(db, row):
    return db.query(ContestantVoting).filter(ContestantVoting.contestant_id == row.id).count()


def test_public_nomination_is_votable_only_in_its_open_stage_with_stage_membership(client, db, world):
    c, rnd = world()
    _link_round(db, c, rnd)
    nominator = person(db, 30)
    row = db.query(Contestant).get(_nominate(client, db, c, nominator)["id"])
    assert _is_public_everywhere(client, db, c, rnd, row.id)
    voter = person(db, 30)

    # (a) Published, but not a member of an open stage: no vote.
    assert _vote(client, voter, row, c, rnd).status_code == 400
    _join_country_stage(db, c, row)
    early = _vote(client, voter, row, c, rnd)
    assert early.status_code == 400 and "starts on" in early.json()["detail"]
    assert _votes(db, row) == 0

    # (b) The Country stage opens: the same public nomination can now be voted on,
    # while its first human review is still pending.
    _open_country_stage(db, rnd)
    assert _moderation(db, row.id).state == "REVIEW_REQUIRED"
    voted = _vote(client, voter, row, c, rnd)
    assert voted.status_code == 201, voted.text
    assert voted.json()["season_level"] == "country" and _votes(db, row) == 1
    # The nominator still cannot vote for their own nomination.
    assert _vote(client, nominator, row, c, rnd).status_code == 400
    assert _votes(db, row) == 1


@pytest.mark.parametrize("removal", ["rejected", "blocked", "prohibited", "creative_unavailable"])
def test_removed_nomination_cannot_be_voted_on_even_in_an_open_stage(client, db, world, removal):
    c, rnd = world()
    _link_round(db, c, rnd)
    row = db.query(Contestant).get(_nominate(client, db, c, person(db, 30))["id"])
    _join_country_stage(db, c, row)
    _open_country_stage(db, rnd)
    admin = person(db, 40, admin=True)

    if removal == "rejected":
        assert client.post(f"/api/v1/admin/contestants/{row.id}/reject", headers=auth(admin)).status_code == 200
    elif removal == "blocked":
        ce.admin_review(db, _safety(db, row.id), action="BLOCK", admin_id=admin.id, note="synthetic block",
                        today=TODAY)
    elif removal == "prohibited":
        cs.moderate(db, _moderation(db, row.id), action="PROHIBIT", actor=moderator(db), reason="REVIEW_DECISION",
                    today=TODAY)
    else:
        row.verification_status = "creative_unavailable"
        db.commit()

    resp = _vote(client, person(db, 30), row, c, rnd)
    assert resp.status_code == 404, resp.text   # the generic "not found": no reason is disclosed
    assert _votes(db, row) == 0
    assert _is_hidden_everywhere(client, db, c, rnd, row.id)


# ===========================================================================
# 9. Approval state: a published nomination is not "Pending review" for admins
# ===========================================================================
#
# Regression (2026-10-07): a nomination was public for everyone, yet its
# contestants.verification_status stayed "pending", so Admin > Contestants
# listed every new nomination as "Pending review" with an Approve button.

def _approval(db, entry_id) -> str:
    db.expire_all()
    return db.query(Contestant).get(entry_id).verification_status


def _admin_rows(client, admin, **params):
    resp = client.get("/api/v1/admin/contestants", params=params, headers=auth(admin))
    assert resp.status_code == 200, resp.text
    return {row["id"]: row for row in resp.json()}


def test_published_nomination_is_approved_not_pending_review(client, db, world):
    c, rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)

    assert body["public_status"] == "PUBLIC"
    row = db.query(Contestant).get(body["id"])
    assert (row.verification_status, row.is_active, row.entry_type) == ("verified", True, "nomination")
    assert _safety(db, row.id).exposure_status == "PUBLIC"
    assert _is_public_everywhere(client, db, c, rnd, row.id)

    # What the administrator sees: approved, and nothing waiting for approval.
    admin = person(db, 40, admin=True)
    assert _admin_rows(client, admin)[row.id]["verification_status"] == "verified"
    assert row.id not in _admin_rows(client, admin, status_filter="pending")
    assert row.id in _admin_rows(client, admin, status_filter="verified")
    from app.api.api_v1.endpoints.admin import get_contest_stats

    assert get_contest_stats(db, c.id) == (1, 1, 0)        # total, approved, pending


@pytest.mark.parametrize("age, declaration", [(30, "MINOR"), (30, "UNKNOWN"), (30, None), (None, "ADULT"), (16, "ADULT")])
def test_every_normal_nomination_is_approved_whatever_the_ages(client, db, world, age, declaration):
    c, _rnd = world()
    body = _nominate(client, db, c, person(db, age), nominee_age_declaration=declaration)
    assert body["public_status"] == "PUBLIC" and _approval(db, body["id"]) == "verified"


def test_retried_or_duplicate_submission_creates_no_pending_entry(client, db, world):
    c, _rnd = world(category_id=category(db).id)
    nominator = person(db, 30)
    video = json.dumps([f"https://www.youtube.com/watch?v={uuid.uuid4().hex[:11]}"])
    first = _nominate(client, db, c, nominator, video_media_ids=video)
    again = _nominate(client, db, c, nominator, video_media_ids=video)
    assert again["id"] == first["id"] and _approval(db, first["id"]) == "verified"
    # The same creative from another member is refused, not parked for review.
    other = _post(client, person(db, 30), c, nominee_age_declaration="ADULT", video_media_ids=video)
    assert other.status_code == 409, other.text
    assert db.query(Contestant).count() == 1
    assert db.query(Contestant).filter(Contestant.verification_status == "pending").count() == 0


def test_held_nomination_stays_pending_until_it_is_published(client, db, world, monkeypatch):
    """A nomination that IS on hold really is waiting: it stays "pending", and
    becomes approved at the moment a re-evaluation publishes it."""
    c, rnd = world()
    with monkeypatch.context() as previous_rule:
        previous_rule.setattr(ce, "_nomination_publication_policy",
                              lambda unmet, holds, **_k: (tuple(unmet), tuple(holds), ()))
        body = _nominate(client, db, c, person(db, 30))
    assert body["public_status"] == "PENDING_REVIEW" and _approval(db, body["id"]) == "pending"

    ce.reevaluate_entry(db, _safety(db, body["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert _safety(db, body["id"]).exposure_status == "PUBLIC" and _approval(db, body["id"]) == "verified"
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_existing_public_nomination_left_pending_is_approved_on_reevaluation(client, db, world):
    """Nominations published before this fix still carry "pending"."""
    c, _rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    row = db.query(Contestant).get(body["id"])
    row.verification_status = "pending"
    db.commit()

    admin = person(db, 40, admin=True)
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin)).status_code == 200
    assert _approval(db, body["id"]) == "verified" and _safety(db, body["id"]).exposure_status == "PUBLIC"


@pytest.mark.parametrize("status", ["rejected", "creative_unavailable"])
def test_automatic_approval_never_overrides_a_removal(client, db, world, status):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    row = db.query(Contestant).get(body["id"])
    row.verification_status = status
    db.commit()
    ce.reevaluate_entry(db, _safety(db, body["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert _approval(db, body["id"]) == status
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


def test_declined_nomination_is_hidden_and_not_reapproved(client, db, world):
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30))
    nominee = person(db, 28, email_verified=True)
    assert client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                       json={"token": body["nominee_claim_token"], "decision": "DECLINE"}).status_code == 200
    assert _safety(db, body["id"]).exposure_status == "HELD"
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


def test_participation_approval_state_is_unchanged(client, db, world):
    """Only nominations are approved automatically."""
    c, _rnd = world("participation")
    public = _post(client, person(db, 30), c, title="Morning song", description="An acoustic cover",
                   video_media_ids=None)
    assert public.status_code == 200 and public.json()["public_status"] == "PUBLIC"
    assert _approval(db, public.json()["id"]) == "pending"
    c2, _ = world("participation")
    held = _post(client, person(db, 30), c2)                 # external video: waits for a moderator
    assert held.status_code == 200 and held.json()["public_status"] == "PENDING_REVIEW"
    assert _approval(db, held.json()["id"]) == "pending"
    cs.moderate(db, _moderation(db, held.json()["id"]), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    assert _safety(db, held.json()["id"]).exposure_status == "PUBLIC"
    assert _approval(db, held.json()["id"]) == "pending"
