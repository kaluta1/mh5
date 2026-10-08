"""The automatic text keyword rules do not apply to a nomination.

Management decision (2026-10-08): words such as "kill", "gun", "weed" or
"school", and a run of digits read as a phone number, held nominations for a
review that nobody carried out (production case: contestant 1374, held with
VIOLENCE). For a nomination those rules are no longer applied; inappropriate
nominations are handled by member reports. What stays: the child-safety text
rule, the media classifier, every moderator and administrator decision, and
all of the rules for personal participation entries.

All users, contests, rounds and entries are SYNTHETIC.
"""
from __future__ import annotations

import pytest

from app.models.accounting import AuditTrail
from app.models.contests import Contestant
from app.services import content_safety as cs
from app.services import contest_eligibility as ce
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_held_nomination_visibility import (  # noqa: F401
    _is_hidden_everywhere,
    _is_public_everywhere,
    _moderation,
    _nominate,
    _safety,
    world,
)
from tests.unit.test_phase5_contest_eligibility import TODAY, _post, api_world, person  # noqa: F401
from tests.unit.test_phase6_content_safety import moderator

KEYWORD_TEXT = "Killer freestyle from my school days, the video is 7613480056349396230"
PIPELINE = {c.value for c in ce._PIPELINE_FINDINGS}


# ===========================================================================
# 1. New nominations
# ===========================================================================

def test_keywords_in_the_text_do_not_hold_a_nomination(client, db, world):
    """The text dimensions are recorded as not run, never as checked and clean."""
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30), description=KEYWORD_TEXT)
    safety, moderation = _safety(db, body["id"]), _moderation(db, body["id"])
    assert body["public_status"] == "PUBLIC" and safety.exposure_status == "PUBLIC"
    assert "SAFETY_REVIEW_REQUIRED" not in (safety.reason_codes or [])
    assert set(moderation.findings) <= PIPELINE
    assert moderation.state == "REVIEW_REQUIRED" and moderation.decided_by_user_id is None
    assert {moderation.coverage[d] for d in ("TEXT_HARM", "TEXT_LANGUAGE", "TEXT_PERSONAL_INFORMATION")} == {"NOT_RUN"}
    assert db.query(Contestant).get(body["id"]).verification_status == "verified"
    assert _is_public_everywhere(client, db, c, rnd, body["id"])


def test_a_spam_or_forbidden_word_flag_from_text_moderation_does_not_hold_a_nomination(client, db, world):
    """The local text moderation result (capitals, forbidden words) reaches the
    classifier by a second route; that route is closed for nominations too."""
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30), title="BEST FREESTYLE EVER",
                     description="WATCH THIS AMAZING PERFORMANCE RIGHT NOW")
    assert _safety(db, body["id"]).exposure_status == "PUBLIC"
    assert set(_moderation(db, body["id"]).findings) <= PIPELINE


def test_the_same_keywords_still_hold_a_participation_entry(client, db, world):
    c, rnd = world(mode="participation")
    resp = _post(client, person(db, 30), c, description=KEYWORD_TEXT)
    assert resp.status_code == 200, resp.text
    safety = _safety(db, resp.json()["id"])
    assert safety.exposure_status == "HELD" and "SAFETY_REVIEW_REQUIRED" in safety.reason_codes
    assert {"VIOLENCE", "SCHOOL_INFORMATION", "PII_PHONE"} <= set(_moderation(db, resp.json()["id"]).findings)


def test_sexual_wording_about_a_possibly_minor_nominee_is_still_escalated(client, db, world):
    """The child-safety text rule is the one text rule a nomination keeps."""
    c, rnd = world()
    body = _nominate(client, db, c, person(db, 30), description="a sexy dance", nominee_age_declaration="MINOR")
    assert _safety(db, body["id"]).exposure_status == "CHILD_SAFETY_ESCALATED"
    assert "CHILD_SEXUAL_CONTENT" in _moderation(db, body["id"]).findings
    assert _is_hidden_everywhere(client, db, c, rnd, body["id"])


def test_classify_without_keyword_rules_never_auto_approves(db):
    text = dict(title="Guns and weed", description="call 0712345678", image_media_ids=None, video_media_ids=None,
                possibly_minor=False, determined_adult=True)
    gate = cs.classify(db, keyword_rules=False, **text)
    assert not gate.findings and gate.state.value == "REVIEW_REQUIRED" and not gate.coverage_complete
    assert {"WEAPONS", "VIOLENCE", "DANGEROUS_BEHAVIOR", "PII_PHONE"} & {f.value for f in cs.classify(db, **text).findings}


# ===========================================================================
# 2. Nominations already held under the previous rules
# ===========================================================================

def _held_under_the_old_rules(client, db, c, nominator, monkeypatch, **body):
    """A nomination as the previous rules stored it: held by a keyword finding."""
    with monkeypatch.context() as old_rules:
        old_rules.setattr(ce, "keyword_rules_apply", lambda kind: True)
        old_rules.setattr(cs, "CLASSIFIER_VERSION", "p6-rules-2")
        out = _nominate(client, db, c, nominator, **body)
    safety = _safety(db, out["id"])
    assert safety.exposure_status == "HELD" and "SAFETY_REVIEW_REQUIRED" in safety.reason_codes
    assert _moderation(db, out["id"]).classifier_version == "p6-rules-2"
    return out["id"]


@pytest.mark.parametrize("via", ["bulk", "single"])
def test_nomination_held_by_a_keyword_is_released_by_admin_reevaluation(client, db, world, monkeypatch, via):
    c, rnd = world()
    entry_id = _held_under_the_old_rules(client, db, c, person(db, 30), monkeypatch, description=KEYWORD_TEXT)
    assert _is_hidden_everywhere(client, db, c, rnd, entry_id)

    admin = person(db, 40, admin=True)
    if via == "bulk":
        resp = client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin))
    else:
        resp = client.post(f"/api/v1/admin/contest-eligibility/entries/{_safety(db, entry_id).id}/review",
                           headers=auth(admin), json={"action": "REEVALUATE", "note": "keyword rules retired"})
    assert resp.status_code == 200, resp.text

    safety, moderation = _safety(db, entry_id), _moderation(db, entry_id)
    assert safety.exposure_status == "PUBLIC" and safety.activated_at is not None
    assert set(safety.safety_concerns or []) <= PIPELINE
    assert moderation.classifier_version == cs.CLASSIFIER_VERSION and moderation.state == "REVIEW_REQUIRED"
    assert moderation.decided_by_user_id is None and moderation.rating is None      # not an approval
    assert db.query(Contestant).get(entry_id).verification_status == "verified"
    audit = [a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "content_moderation",
                                                           AuditTrail.record_id == moderation.id).all()]
    assert audit.count("CONTENT_REASSESSED_RULE_CHANGE") == 1
    assert _is_public_everywhere(client, db, c, rnd, entry_id)
    # A second run assesses nothing again.
    assert ce.reassess_nomination_content(db, safety, actor_id=None, trigger="TEST", today=TODAY) is False


@pytest.mark.parametrize("action", ["HOLD", "REQUEST_UPDATE", "PROHIBIT", "ESCALATE_CHILD_SAFETY"])
def test_reassessment_never_replaces_a_moderator_decision(client, db, world, monkeypatch, action):
    c, rnd = world()
    entry_id = _held_under_the_old_rules(client, db, c, person(db, 30), monkeypatch, description=KEYWORD_TEXT)
    cs.moderate(db, _moderation(db, entry_id), action=action, actor=moderator(db), reason="REVIEW_DECISION",
                today=TODAY)
    before = _moderation(db, entry_id)
    snapshot = (before.state, before.findings, before.classifier_version, before.decided_by_user_id)
    assert ce.reassess_nomination_content(db, _safety(db, entry_id), actor_id=None, trigger="TEST",
                                          today=TODAY) is False
    ce.reevaluate_open_entries(db, trigger="TEST", today=TODAY)
    after = _moderation(db, entry_id)
    assert snapshot == (after.state, after.findings, after.classifier_version, after.decided_by_user_id)
    assert _is_hidden_everywhere(client, db, c, rnd, entry_id)


def test_reassessment_keeps_a_finding_the_word_rules_do_not_explain(client, db, world, monkeypatch):
    """A finding that did not come from the text (media classifier, synthetic
    signal) is not dropped with the keyword ones: the entry stays held."""
    c, rnd = world()
    entry_id = _held_under_the_old_rules(client, db, c, person(db, 30), monkeypatch, description=KEYWORD_TEXT)
    moderation = _moderation(db, entry_id)
    moderation.findings = sorted(set(moderation.findings) | {"HATE"})
    db.commit()
    assert ce.reassess_nomination_content(db, _safety(db, entry_id), actor_id=None, trigger="TEST",
                                          today=TODAY) is True
    findings = _moderation(db, entry_id).findings
    assert "HATE" in findings and "VIOLENCE" not in findings
    assert _safety(db, entry_id).exposure_status == "HELD"
    assert _is_hidden_everywhere(client, db, c, rnd, entry_id)


def test_reassessment_leaves_an_entry_with_a_media_classifier_finding_alone(client, db, world, monkeypatch):
    c, rnd = world()
    entry_id = _held_under_the_old_rules(client, db, c, person(db, 30), monkeypatch, description=KEYWORD_TEXT)
    moderation = _moderation(db, entry_id)
    moderation.coverage = {**moderation.coverage, "MEDIA_CONTENT": "COMPLETED_FINDING"}
    db.commit()
    assert ce.reassess_nomination_content(db, _safety(db, entry_id), actor_id=None, trigger="TEST",
                                          today=TODAY) is False
    assert _moderation(db, entry_id).classifier_version == "p6-rules-2"
    assert _safety(db, entry_id).exposure_status == "HELD"


def test_reassessment_does_not_touch_a_participation_entry(client, db, world):
    c, rnd = world(mode="participation")
    entry_id = _post(client, person(db, 30), c, description=KEYWORD_TEXT).json()["id"]
    moderation = _moderation(db, entry_id)
    moderation.classifier_version = "p6-rules-2"
    db.commit()
    ce.reevaluate_open_entries(db, trigger="TEST", today=TODAY)
    assert _moderation(db, entry_id).classifier_version == "p6-rules-2"
    assert _safety(db, entry_id).exposure_status == "HELD"
