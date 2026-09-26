"""Phase 6: content classification, moderation and child-safety pipeline
(MyHigh5 Child/Teen Safety s.10, s.11, s.15, s.16, s.18).

All users, roles, entries and moderation decisions are SYNTHETIC. No external
moderation provider is called (the provider is stubbed in-process where a
configured provider is simulated).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

import pytest

from app.core.child_safety import (
    ChildSafetyResolution,
    CoverageDimension as CD,
    CoverageStatus as CS,
    ClassifierStatus,
    ContentRating,
    ContestEligibilityReason as R,
    ContestEntryKind,
    ModerationState,
    NomineeAgeDeclaration as D,
    SafetyConcern,
)
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.guardian import GuardianRelationship
from app.models.media import Media
from app.models.user import Permission, Role
from app.services import content_safety as cs
from app.services import contest_eligibility as ce
from app.services.content_moderation import FlagType
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import (  # noqa: F401
    APPROVED_CONTENT,
    TODAY,
    _post,
    adult_flag,
    api_world,
    contest,
    entry,
    flag,
    nominate,
    person,
    rule,
    submit,
)

NOW = datetime.utcnow()


def role_user(db, *perms, age=35):
    """A non-admin user whose role grants exactly `perms` (synthetic)."""
    role = Role(name=f"p6role_{uuid.uuid4().hex[:6]}")
    for name in perms:
        p = db.query(Permission).filter(Permission.name == name).first() or Permission(name=name)
        role.permissions.append(p)
    db.add(role)
    db.flush()
    u = person(db, age)
    u.role_id = role.id
    db.commit()
    db.refresh(u)
    return u


def moderator(db):
    return role_user(db, "moderate_content")


def cs_resolver(db):
    return role_user(db, "moderate_content", "child_safety_resolve")


def sanitized_image(db, owner, sanitized=True):
    m = Media(title="i", media_type="image", path="p", url=f"/api/v1/media/file/{owner.id}/{uuid.uuid4().hex}.jpg",
              user_id=owner.id, metadata_sanitized_at=NOW if sanitized else None)
    db.add(m)
    db.commit()
    return m


def classify(db, *, minor=False, adult=True, run=None, **kw):
    return cs.classify(db, title=kw.get("title", "My song"), description=kw.get("description", "Performance"),
                       image_media_ids=kw.get("images"), video_media_ids=kw.get("videos"),
                       moderation_results=kw.get("results", ()), extra_concerns=kw.get("extra", ()),
                       possibly_minor=minor, determined_adult=adult and not minor, run=run)


def completed(n=1):
    return cs.ClassifierRun(ClassifierStatus.COMPLETED, n, n)


def held_entry(db, user, content=None, **inputs):
    """Entry created through the real pipeline (content classified, record persisted)."""
    d = submit(db, user, content=content, **inputs)
    return entry(db, user, d, **{k: v for k, v in inputs.items() if k in ("description", "image_media_ids")})


# ===========================================================================
# CONTENT RATINGS
# ===========================================================================

def test_single_phase2_rating_vocabulary():
    assert [r.value for r in ContentRating] == ["GENERAL", "TEEN_13_PLUS", "TEEN_16_PLUS", "ADULT_18_PLUS",
                                                "PROHIBITED"]


@pytest.mark.parametrize("finding_flag, expected", [
    (FlagType.OFFENSIVE, ContentRating.TEEN_13_PLUS),
    (FlagType.WEAPONS, ContentRating.TEEN_13_PLUS),
    (FlagType.VIOLENCE, ContentRating.TEEN_16_PLUS),
    (FlagType.GORE, ContentRating.ADULT_18_PLUS),
    (FlagType.ADULT, ContentRating.ADULT_18_PLUS),   # adult subject only
    (FlagType.HATE, ContentRating.PROHIBITED),
])
def test_proposed_ratings(db, finding_flag, expected):
    g = classify(db, results=(flag(finding_flag),))
    assert g.proposed_rating == expected
    assert g.state == ModerationState.REVIEW_REQUIRED and not g.approved  # proposals are never final


@pytest.mark.parametrize("rating", [ContentRating.GENERAL, ContentRating.TEEN_13_PLUS, ContentRating.TEEN_16_PLUS,
                                    ContentRating.ADULT_18_PLUS])
def test_moderator_approves_with_final_rating_and_adult_entry_becomes_public(db, rating):
    adult = person(db, 30)
    row, safety = held_entry(db, adult)
    item = cs.moderation_for(db, row.id)
    assert item.state == "REVIEW_REQUIRED" and safety.exposure_status == "HELD"
    cs.moderate(db, item, action="APPROVE", actor=moderator(db), reason="REVIEWED_OK", rating=rating, today=TODAY)
    db.refresh(safety)
    assert item.rating == rating.value and safety.exposure_status == "PUBLIC"


def test_prohibited_never_public(db):
    adult = person(db, 30)
    row, safety = held_entry(db, adult)
    item = cs.moderation_for(db, row.id)
    mod = moderator(db)
    with pytest.raises(cs.ModerationError) as exc:
        cs.moderate(db, item, action="APPROVE", actor=mod, reason="X_OK", rating=ContentRating.PROHIBITED)
    assert exc.value.code == "PROHIBITED_RATING"
    db.rollback()
    cs.moderate(db, item, action="PROHIBIT", actor=mod, reason="POLICY_VIOLATION", today=TODAY)
    db.refresh(safety)
    assert item.state == "PROHIBITED" and safety.exposure_status == "HELD" and "CONTENT_PROHIBITED" in safety.reason_codes
    with pytest.raises(cs.ModerationError):
        cs.moderate(db, item, action="APPROVE", actor=mod, reason="X_OK", rating=ContentRating.GENERAL)


# ===========================================================================
# PUBLICATION / FAIL CLOSED
# ===========================================================================

def test_fully_classified_clean_adult_content_is_auto_approved_and_public(db):
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    g = classify(db, images=json.dumps([img.id]), run=completed(1))
    assert g.approved and g.automated and g.rating == ContentRating.GENERAL
    d = submit(db, adult, content=g)
    assert d.public and d.participation_eligible


@pytest.mark.parametrize("run", [None, cs.ClassifierRun(ClassifierStatus.UNAVAILABLE),
                                 cs.ClassifierRun(ClassifierStatus.PARTIAL, 2, 1),
                                 cs.ClassifierRun(ClassifierStatus.COMPLETED, 1, 0)])
def test_classifier_failure_or_gap_is_fail_closed(db, run):
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    g = classify(db, images=json.dumps([img.id]), run=run)
    assert g.state == ModerationState.REVIEW_REQUIRED and SafetyConcern.UNCLASSIFIED_MEDIA in g.findings
    assert not submit(db, adult, content=g).public


def test_external_links_are_never_auto_approved(db):
    g = classify(db, videos=json.dumps(["https://youtu.be/x"]), run=completed(1))
    assert not g.approved and g.coverage_map()[CD.MEDIA_CONTENT] == CS.NOT_SUPPORTED


def test_pending_and_escalated_gates_stay_private(db):
    adult = person(db, 30)
    for gate in (ce.ContentGate(ModerationState.PENDING), ce.ContentGate(ModerationState.PROHIBITED),
                 ce.ContentGate(ModerationState.CHILD_SAFETY_ESCALATED, child_safety_escalated=True)):
        d = submit(db, adult, content=gate)
        assert not d.public and d.participation_eligible


def test_age_eligibility_and_content_are_independent_gates(db):
    # content approved but participation fails (missing DOB) -> private
    d = submit(db, person(db, None), content=APPROVED_CONTENT)
    assert not d.public and not d.participation_eligible and R.AGE_REQUIRED in d.reasons
    # participation passes but content pending -> private
    d2 = submit(db, person(db, 30), content=ce.ContentGate(ModerationState.PENDING))
    assert not d2.public and d2.participation_eligible and R.CONTENT_REVIEW_REQUIRED in d2.reasons


# ===========================================================================
# MINORS
# ===========================================================================

@pytest.mark.parametrize("text, code", [
    ("Text me +255 712 345 678", SafetyConcern.PII_PHONE),
    ("mail me: kid (at) example (dot) com", SafetyConcern.PII_EMAIL),
    ("We live at -6.79235, 39.20833", SafetyConcern.PRECISE_LOCATION),
    ("see maps.app.goo.gl/abc123", SafetyConcern.PRECISE_LOCATION),
    ("I live at the blue house", SafetyConcern.HOME_ADDRESS),
    ("grade 8 at Uhuru", SafetyConcern.SCHOOL_INFORMATION),
    ("Mzizima Secondary School choir", SafetyConcern.SCHOOL_INFORMATION),
])
def test_minor_pii_location_school_findings_hold_and_block_approval(db, text, code):
    teen = person(db, 15)
    row, safety = held_entry(db, teen, description=text)
    item = cs.moderation_for(db, row.id)
    assert code.value in item.findings and safety.exposure_status == "HELD"
    with pytest.raises(cs.ModerationError) as exc:
        cs.moderate(db, item, action="APPROVE", actor=moderator(db), reason="X_OK", rating=ContentRating.GENERAL)
    assert exc.value.code == "UNRESOLVED_FINDINGS"


def test_minor_sexual_content_is_child_safety_escalation_not_adult_rating(db):
    teen = person(db, 16)
    g = classify(db, minor=True, results=(adult_flag(),))
    assert g.state == ModerationState.CHILD_SAFETY_ESCALATED and g.child_safety_escalated
    assert g.rating is None and SafetyConcern.SEXUAL_CONTENT not in g.findings
    row, safety = held_entry(db, teen, moderation_results=(adult_flag(),))
    assert safety.exposure_status == "CHILD_SAFETY_ESCALATED" and row.is_active is False
    item = cs.moderation_for(db, row.id)
    assert item.child_safety_escalated and item.state == "CHILD_SAFETY_ESCALATED"


def test_ordinary_moderation_and_admin_cannot_clear_child_safety(db):
    teen = person(db, 16)
    row, safety = held_entry(db, teen, moderation_results=(adult_flag(),))
    item = cs.moderation_for(db, row.id)
    for actor in (moderator(db), person(db, 45, admin=True), role_user(db, "all")):
        for action in ("APPROVE", "RESOLVE_ISSUE", "CLASSIFY", "HOLD"):
            with pytest.raises(cs.ModerationError) as exc:
                cs.moderate(db, item, action=action, actor=actor, reason="TRY", rating=ContentRating.GENERAL)
            assert exc.value.code == "CHILD_SAFETY_LOCKED"
            db.rollback()
        with pytest.raises(cs.ModerationError) as exc:
            cs.resolve_child_safety(db, item, resolution=ChildSafetyResolution.NO_CHILD_SAFETY_CONCERN, actor=actor,
                                    reason="TRY")
        assert exc.value.code == "FORBIDDEN"  # admin / 'all' wildcard do not imply the explicit permission
        db.rollback()
    db.refresh(item)
    assert item.child_safety_escalated and safety.exposure_status == "CHILD_SAFETY_ESCALATED"


def test_authorized_child_safety_resolution_is_audited_and_never_publishes(db):
    adult_subject = person(db, 30)  # even an adult-subject item escalated by a moderator
    row, safety = held_entry(db, adult_subject)
    item = cs.moderation_for(db, row.id)
    cs.moderate(db, item, action="ESCALATE_CHILD_SAFETY", actor=moderator(db), reason="POSSIBLE_MINOR", today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "CHILD_SAFETY_ESCALATED"
    resolver = cs_resolver(db)
    cs.resolve_child_safety(db, item, resolution=ChildSafetyResolution.NO_CHILD_SAFETY_CONCERN, actor=resolver,
                            reason="FALSE_POSITIVE_CONFIRMED", today=TODAY)
    db.refresh(safety)
    assert item.state == "REVIEW_REQUIRED" and not item.child_safety_escalated
    assert safety.exposure_status == "HELD"  # back to ordinary review, still private
    actions = [a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "content_moderation",
                                                             AuditTrail.record_id == item.id)]
    assert "CHILD_SAFETY_RESOLVED_NO_CHILD_SAFETY_CONCERN" in actions
    # A separate ordinary approval is still needed.
    cs.moderate(db, item, action="APPROVE", actor=moderator(db), reason="REVIEWED_OK", rating=ContentRating.GENERAL,
                today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "PUBLIC"


def test_confirmed_child_safety_is_terminal(db):
    teen = person(db, 16)
    row, safety = held_entry(db, teen, moderation_results=(adult_flag(),))
    item = cs.moderation_for(db, row.id)
    cs.resolve_child_safety(db, item, resolution=ChildSafetyResolution.CONFIRMED, actor=cs_resolver(db),
                            reason="CONFIRMED", today=TODAY)
    db.refresh(safety)
    assert item.state == "PROHIBITED" and item.rating == "PROHIBITED"
    assert safety.exposure_status == "CHILD_SAFETY_ESCALATED" and row.is_active is False
    with pytest.raises(cs.ModerationError) as exc:
        cs.moderate(db, item, action="APPROVE", actor=moderator(db), reason="TRY", rating=ContentRating.GENERAL)
    assert exc.value.code == "CHILD_SAFETY_LOCKED"


def test_minor_adult_rated_content_is_not_published(db):
    teen = person(db, 17)
    d = submit(db, teen, content=ce.ContentGate(ModerationState.APPROVED, rating=ContentRating.ADULT_18_PLUS))
    assert R.CONTENT_RATING_NOT_PERMITTED in d.reasons and not d.public


def test_contest_rating_ceiling_is_enforced(db):
    c = contest(db)
    rule(db, "contest", c.id, content_age_rating="TEEN_13_PLUS")
    d = submit(db, person(db, 30), c, content=ce.ContentGate(ModerationState.APPROVED, rating=ContentRating.TEEN_16_PLUS))
    assert R.CONTENT_RATING_NOT_PERMITTED in d.reasons and not d.public


def test_minors_are_never_auto_approved(db):
    teen = person(db, 15)
    img = sanitized_image(db, teen)
    g = classify(db, minor=True, images=json.dumps([img.id]), run=completed(1))
    assert g.state == ModerationState.REVIEW_REQUIRED and not g.automated


# ===========================================================================
# METADATA
# ===========================================================================

def test_unsanitized_hosted_image_is_a_finding_and_minor_video_stays_held(db):
    teen = person(db, 15)
    raw = sanitized_image(db, teen, sanitized=False)
    g = classify(db, minor=True, images=json.dumps([raw.id]))
    assert SafetyConcern.METADATA_UNVERIFIED in g.findings
    video = Media(title="v", media_type="video", path="p", url=f"/api/v1/media/file/{teen.id}/v.mp4", user_id=teen.id)
    db.add(video)
    db.commit()
    d = submit(db, teen, content=APPROVED_CONTENT, video_media_ids=json.dumps([video.url]))
    assert R.METADATA_UNRESOLVED in d.reasons and not d.public


def test_exif_gps_removed_by_upload_sanitizer():
    from io import BytesIO

    from PIL import Image

    from app.core.media_metadata import has_hidden_metadata, strip_image_metadata

    img = Image.new("RGB", (8, 8))
    ex = Image.Exif()
    ex[0x8825] = {1: "N", 2: (1.0, 2.0, 3.0)}
    buf = BytesIO()
    img.save(buf, "JPEG", exif=ex.tobytes())
    clean, ok = strip_image_metadata(buf.getvalue(), "image/jpeg")
    assert ok and not has_hidden_metadata(clean)


# ===========================================================================
# MODERATION PERMISSIONS / RE-EVALUATION
# ===========================================================================

def test_unauthorized_moderation_is_denied(client, db):
    adult = person(db, 30)
    row, _ = held_entry(db, adult)
    item = cs.moderation_for(db, row.id)
    member = person(db, 30)
    with pytest.raises(cs.ModerationError):
        cs.moderate(db, item, action="APPROVE", actor=member, reason="X_OK", rating=ContentRating.GENERAL)
    db.rollback()
    body = {"action": "APPROVE", "reason": "REVIEWED_OK", "rating": "GENERAL"}
    assert client.get("/api/v1/admin/content-moderation/queue", headers=auth(member)).status_code == 403
    assert client.post(f"/api/v1/admin/content-moderation/items/{item.id}/actions", headers=auth(member),
                       json=body).status_code == 403
    assert client.get("/api/v1/admin/content-moderation/queue").status_code in (401, 403)
    ok = client.post(f"/api/v1/admin/content-moderation/items/{item.id}/actions", headers=auth(moderator(db)),
                     json=body)
    assert ok.status_code == 200 and ok.json()["state"] == "APPROVED"


def test_child_safety_resolution_api_requires_explicit_permission(client, db):
    teen = person(db, 16)
    row, _ = held_entry(db, teen, moderation_results=(adult_flag(),))
    item = cs.moderation_for(db, row.id)
    body = {"resolution": "NO_CHILD_SAFETY_CONCERN", "reason": "FALSE_POSITIVE"}
    url = f"/api/v1/admin/content-moderation/items/{item.id}/child-safety-resolution"
    assert client.post(url, headers=auth(moderator(db)), json=body).status_code == 403
    assert client.post(url, headers=auth(person(db, 45, admin=True)), json=body).status_code == 403
    appr = client.post(f"/api/v1/admin/content-moderation/items/{item.id}/actions", headers=auth(moderator(db)),
                       json={"action": "APPROVE", "reason": "TRY", "rating": "GENERAL"})
    assert appr.status_code == 409 and appr.json()["detail"]["code"] == "CHILD_SAFETY_LOCKED"
    ok = client.post(url, headers=auth(cs_resolver(db)), json=body)
    assert ok.status_code == 200 and ok.json()["state"] == "REVIEW_REQUIRED"
    # free-text reasons are refused (structured codes only, nothing sensitive in the audit trail)
    assert client.post(f"/api/v1/admin/content-moderation/items/{item.id}/actions", headers=auth(moderator(db)),
                       json={"action": "HOLD", "reason": "call +255712345678"}).status_code == 422


def test_moderation_approval_never_bypasses_guardian_or_age(db):
    teen = person(db, 15)
    row, safety = held_entry(db, teen)
    item = cs.moderation_for(db, row.id)
    cs.moderate(db, item, action="APPROVE", actor=moderator(db), reason="REVIEWED_OK", rating=ContentRating.GENERAL,
                today=TODAY)
    db.refresh(safety)
    assert item.state == "APPROVED" and safety.exposure_status == "HELD"
    assert "GUARDIAN_CONSENT_REQUIRED" in safety.reason_codes
    nodob = person(db, None)
    row2, safety2 = held_entry(db, nodob)
    cs.moderate(db, cs.moderation_for(db, row2.id), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    db.refresh(safety2)
    assert safety2.exposure_status == "HELD" and "AGE_REQUIRED" in safety2.reason_codes


def test_moderation_change_triggers_full_reevaluation_and_suspends(db):
    adult = person(db, 30)
    row, safety = held_entry(db, adult)
    item = cs.moderation_for(db, row.id)
    mod = moderator(db)
    cs.moderate(db, item, action="APPROVE", actor=mod, reason="REVIEWED_OK", rating=ContentRating.GENERAL, today=TODAY)
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "PUBLIC" and row.is_active
    cs.moderate(db, item, action="HOLD", actor=mod, reason="NEW_REPORT", finding_codes=[SafetyConcern.VIOLENCE],
                today=TODAY)
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "HELD" and row.is_active is False
    actions = {a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "contest_entry_safety")}
    assert {"ENTRY_ACTIVATED", "ENTRY_SUSPENDED"} <= actions


def test_request_update_gives_member_update_required(client, db, api_world):
    c = api_world()
    adult = person(db, 30)
    resp = _post(client, adult, c, description="My address is 12 Uhuru Street")
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW"
    contestant = db.query(Contestant).one()
    item = cs.moderation_for(db, contestant.id)
    cs.moderate(db, item, action="REQUEST_UPDATE", actor=moderator(db), reason="REMOVE_ADDRESS", today=TODAY)
    view = client.get(f"/api/v1/contest-eligibility/entries/{contestant.id}", headers=auth(adult)).json()
    assert view["content_status"] == "UPDATE_REQUIRED" and "HOME_ADDRESS" not in json.dumps(view)


def test_editing_approved_content_discards_the_approval(client, db, api_world):
    c = api_world()
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    resp = _post(client, adult, c, image_media_ids=json.dumps([str(img.id)]), video_media_ids=None)
    assert resp.status_code == 200 and resp.json()["public_status"] == "PUBLIC", resp.text  # auto-approved
    contestant = db.query(Contestant).one()
    # The update path does not re-run media classification: the image is no longer covered.
    upd = client.put(f"/api/v1/contestants/{contestant.id}", headers=auth(adult),
                     json={"title": "New title", "description": "Changed description",
                           "image_media_ids": json.dumps([str(img.id)])})
    assert upd.status_code == 200, upd.text
    db.expire_all()
    item = cs.moderation_for(db, contestant.id)
    assert item.state == "REVIEW_REQUIRED" and item.coverage["MEDIA_CONTENT"] == "NOT_RUN"
    assert db.query(ContestEntrySafety).one().exposure_status == "HELD"


def test_minor_media_not_sent_to_provider_and_held(client, db, api_world, monkeypatch):
    from app.services.content_moderation import content_moderation_service

    calls = []
    monkeypatch.setattr(content_moderation_service, "moderate_image", lambda url: calls.append(url))
    c = api_world()
    teen = person(db, 15)
    img = sanitized_image(db, teen)
    resp = _post(client, teen, c, image_media_ids=json.dumps([str(img.id)]), video_media_ids=None)
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW" and calls == []
    item = cs.moderation_for(db, db.query(Contestant).one().id)
    assert item.classifier_status == "UNAVAILABLE" and item.state == "REVIEW_REQUIRED"


def test_provider_unavailable_is_held_not_rejected(client, db, api_world, monkeypatch):
    """Previously an unconfigured/erroring provider rejected the submission with a
    422; now the entry is kept private for human review (fail closed, not open)."""
    from app.services.content_moderation import ModerationResult, content_moderation_service

    monkeypatch.setattr(content_moderation_service, "moderate_video",
                        lambda url: ModerationResult(False, 0, [], {"error": "timeout", "fail_closed": True}))
    resp = _post(client, person(db, 30), api_world())
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW"
    assert cs.moderation_for(db, db.query(Contestant).one().id).classifier_status == "PARTIAL"


# ===========================================================================
# NOMINATIONS
# ===========================================================================

def test_claimed_nomination_still_waits_for_content_safety(client, db):
    nominator = person(db, 35)
    d = nominate(db, nominator, None, D.ADULT, content=None, description="A great song")
    row, safety = entry(db, nominator, d, ContestEntryKind.NOMINATION, declaration=D.ADULT)
    token = ce.issue_claim_token(db, safety, actor_id=nominator.id)
    nominee = person(db, 28, email_verified=True)
    r = client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                    json={"token": token, "decision": "ACCEPT"})
    assert r.status_code == 200
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    assert safety.rights_status == "CONFIRMED" and safety.exposure_status == "HELD"
    assert "CONTENT_REVIEW_REQUIRED" in safety.reason_codes
    cs.moderate(db, cs.moderation_for(db, row.id), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    db.expire_all()
    assert db.query(ContestEntrySafety).one().exposure_status == "PUBLIC"
    assert db.query(GuardianRelationship).count() == 0


def test_minor_nomination_with_safety_issue_stays_private(db):
    nominator = person(db, 35)
    d = nominate(db, nominator, None, D.MINOR, content=None, description="She studies at Mzizima Secondary School")
    assert SafetyConcern.SCHOOL_INFORMATION in d.safety_concerns and not d.public


# ===========================================================================
# HISTORICAL DATA
# ===========================================================================

def test_historical_entries_get_no_moderation_record_and_stay_public(db):
    legacy = Contestant(user_id=person(db, None).id, entry_type="nomination", title="Legacy", is_active=True,
                        is_deleted=False)
    db.add(legacy)
    db.commit()
    ce.reevaluate_open_entries(db, trigger="synthetic", today=TODAY)
    assert db.query(ContentModeration).count() == 0
    db.refresh(legacy)
    assert legacy.is_active and ce.entry_publicly_visible(db, legacy.id)


def test_phase5_public_entry_is_not_rewritten_but_held_entry_is_governed_prospectively(db):
    adult = person(db, 30)
    # A Phase 5 era public entry (no moderation row): stays public, nothing fabricated.
    d = submit(db, adult, content=APPROVED_CONTENT)
    row = Contestant(user_id=adult.id, title="p5", description="d", entry_type="participation", is_active=True,
                     is_deleted=False)
    db.add(row)
    db.flush()
    safety = ce.record_new_entry(db, row, d, kind=ContestEntryKind.PERSONAL_SUBMISSION, submitted_by=adult,
                                 contest_id=None, nominee_age_declaration=None, now=NOW)
    db.query(ContentModeration).filter(ContentModeration.contestant_id == row.id).delete()
    db.commit()
    ce.reevaluate_entry(db, safety, actor_id=None, trigger="synthetic", today=TODAY)
    assert safety.exposure_status == "PUBLIC" and cs.moderation_for(db, row.id) is None
    # A Phase 5 era HELD entry: when re-evaluated it gets a review record (never an approval).
    teen = person(db, 15)
    d2 = submit(db, teen, content=APPROVED_CONTENT)
    row2 = Contestant(user_id=teen.id, title="p5", description="d", entry_type="participation", is_active=False,
                      is_deleted=False)
    db.add(row2)
    db.flush()
    s2 = ce.record_new_entry(db, row2, d2, kind=ContestEntryKind.PERSONAL_SUBMISSION, submitted_by=teen,
                             contest_id=None, nominee_age_declaration=None, now=NOW)
    db.query(ContentModeration).filter(ContentModeration.contestant_id == row2.id).delete()
    db.commit()
    ce.reevaluate_entry(db, s2, actor_id=None, trigger="synthetic", today=TODAY)
    item = cs.moderation_for(db, row2.id)
    assert item is not None and item.state == "REVIEW_REQUIRED" and not item.automated_decision


# ===========================================================================
# MEMBER / ADMIN API SAFETY, LOGGING, REGRESSION
# ===========================================================================

def test_member_sees_only_safe_status(client, db, api_world):
    c = api_world()
    teen = person(db, 16)
    resp = _post(client, teen, c, description="call me +255 712 345 678")
    assert resp.status_code == 200
    safe = {k: resp.json()[k] for k in ("public_status", "eligibility_reasons", "message", "next_step")}
    body = json.dumps(safe)  # (the member's own title/description is echoed back to them unchanged)
    assert "PII" not in body and "PHONE" not in body and "finding" not in body.lower()
    contestant = db.query(Contestant).one()
    view = client.get(f"/api/v1/contest-eligibility/entries/{contestant.id}", headers=auth(teen)).json()
    assert view["content_status"] == "UNDER_REVIEW" and "PII" not in json.dumps(view)


def test_escalation_shown_to_member_only_as_generic_hold(client, db, api_world, monkeypatch):
    from app.core.config import settings
    from app.services.content_moderation import content_moderation_service

    monkeypatch.setattr(settings, "CONTENT_MODERATION_EXTERNAL_FOR_MINORS", True)
    monkeypatch.setattr(content_moderation_service, "moderate_video", lambda url: adult_flag())
    teen = person(db, 16)
    _post(client, teen, api_world())
    contestant = db.query(Contestant).one()
    view = client.get(f"/api/v1/contest-eligibility/entries/{contestant.id}", headers=auth(teen)).json()
    assert view["content_status"] == "CONTENT_HELD" and "CHILD" not in json.dumps(view)


def test_moderator_queue_shows_codes_and_history_only(client, db):
    teen = person(db, 16)
    row, _ = held_entry(db, teen, description="grade 8 at Uhuru, phone +255 712 345 678")
    mod = moderator(db)
    q = client.get("/api/v1/admin/content-moderation/queue", headers=auth(mod))
    assert q.status_code == 200 and len(q.json()) == 1
    item = q.json()[0]
    assert {"PII_PHONE", "SCHOOL_INFORMATION"} <= set(item["findings"])
    assert "712" not in json.dumps(q.json()) and "Uhuru" not in json.dumps(q.json())
    detail = client.get(f"/api/v1/admin/content-moderation/items/{item['id']}", headers=auth(mod)).json()
    assert detail["history"][0]["action"] == "CONTENT_ASSESSED" and detail["can_resolve_child_safety"] is False


def test_findings_text_never_logged_or_audited(db, caplog):
    caplog.set_level(logging.DEBUG)
    teen = person(db, 15)
    held_entry(db, teen, description="text me on +255 712 345 678 at 12 Uhuru Street")
    audit = json.dumps([[a.old_values, a.new_values] for a in db.query(AuditTrail)], default=str)
    for secret in ("712 345", "Uhuru Street", "text me"):
        assert secret not in audit and secret not in caplog.text


def test_held_content_is_not_votable_or_listed(db):
    adult = person(db, 30)
    row, safety = held_entry(db, adult)
    assert safety.exposure_status == "HELD" and row.is_active is False
    assert ce.entry_publicly_visible(db, row.id) is False
    assert db.query(Contestant.id).filter(Contestant.id == row.id, ce.public_entry_clause()).first() is None


def test_moderation_endpoints_are_rate_limited():
    from app.core.rate_limit import RATE_LIMITS

    assert RATE_LIMITS["/api/v1/admin/content-moderation"] == (120, 60)


# ===========================================================================
# HARDENING: PERMISSION POLICY
# ===========================================================================

def test_permission_matrix(db):
    plain = person(db, 30)
    unrelated = role_user(db, "view_users", "manage_users")
    dedicated_moderator_role = person(db, 30)
    mod_role = db.query(Role).filter(Role.name == "moderator").first() or Role(name="moderator")
    db.add(mod_role)
    db.flush()
    dedicated_moderator_role.role_id = mod_role.id
    db.commit()
    db.refresh(dedicated_moderator_role)
    explicit_moderator = moderator(db)
    admin = person(db, 45, admin=True)
    wildcard = role_user(db, "all")
    resolver_only = role_user(db, "child_safety_resolve")
    both = cs_resolver(db)
    table = {
        "plain": (plain, False, False), "unrelated": (unrelated, False, False),
        "moderator role": (dedicated_moderator_role, True, False), "moderate_content": (explicit_moderator, True, False),
        "admin": (admin, True, False), "all wildcard": (wildcard, True, False),
        "resolver only": (resolver_only, False, True), "moderator+resolver": (both, True, True),
    }
    for label, (user, can_mod, can_res) in table.items():
        assert cs.can_moderate(user) is can_mod, label
        assert cs.can_resolve_child_safety(user) is can_res, label
    assert "child_safety_resolve" not in {p.name for u in (plain, admin) for p in (u.role.permissions if u.role else [])}


def test_resolver_without_moderate_content_cannot_approve(db):
    adult = person(db, 30)
    row, _ = held_entry(db, adult, description="kill")  # held with a finding
    with pytest.raises(cs.ModerationError) as exc:
        cs.moderate(db, cs.moderation_for(db, row.id), action="APPROVE", actor=role_user(db, "child_safety_resolve"),
                    reason="X_OK", rating=ContentRating.GENERAL)
    assert exc.value.code == "FORBIDDEN"


def test_admin_ui_flags_reflect_permissions(client, db):
    teen = person(db, 16)
    row, _ = held_entry(db, teen, moderation_results=(adult_flag(),))
    item_id = cs.moderation_for(db, row.id).id
    mod_view = client.get(f"/api/v1/admin/content-moderation/items/{item_id}", headers=auth(moderator(db))).json()
    assert mod_view["child_safety_escalated"] is True
    assert mod_view["can_resolve_child_safety"] is False and mod_view["can_moderate"] is True
    res_view = client.get(f"/api/v1/admin/content-moderation/items/{item_id}",
                          headers=auth(role_user(db, "child_safety_resolve"))).json()
    assert res_view["can_resolve_child_safety"] is True and res_view["can_moderate"] is False
    assert client.get(f"/api/v1/admin/content-moderation/items/{item_id}",
                      headers=auth(role_user(db, "view_users"))).status_code == 403


# ===========================================================================
# HARDENING: COVERAGE-BASED AUTO-APPROVAL (A-I)
# ===========================================================================

def test_A_fully_covered_safe_content_auto_approves_and_is_public(db):
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    g = classify(db, images=json.dumps([img.id]), run=completed(1))
    assert g.approved and g.coverage_complete and not g.findings
    assert all(st in (CS.COMPLETED_NO_FINDING, CS.NOT_APPLICABLE) for st in g.coverage_map().values())
    assert submit(db, adult, content=g).public


def test_B_empty_findings_with_incomplete_coverage_is_review(db):
    adult = person(db, 30)
    video = Media(title="v", media_type="video", path="p", url=f"/api/v1/media/file/{adult.id}/v.mp4",
                  user_id=adult.id)
    db.add(video)
    db.commit()
    g = classify(db, videos=json.dumps([video.url]), run=completed(1))
    assert g.coverage_map()[CD.MEDIA_CONTENT] == CS.COMPLETED_NO_FINDING
    assert g.coverage_map()[CD.MEDIA_METADATA] == CS.NOT_SUPPORTED     # video metadata stripping is Phase 7
    assert not g.findings and not g.coverage_complete and not g.approved
    manual = ce.ContentGate(ModerationState.REVIEW_REQUIRED, coverage=((CD.TEXT_HARM, CS.NOT_RUN),))
    assert not manual.findings and not manual.coverage_complete


def test_C_provider_failure_is_review(db):
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    g = classify(db, images=json.dumps([img.id]), run=cs.ClassifierRun(ClassifierStatus.FAILED, 1, 0, 1))
    assert g.coverage_map()[CD.MEDIA_CONTENT] == CS.FAILED and g.classifier_status == ClassifierStatus.FAILED
    assert not g.approved


def test_D_unsupported_media_is_review(db):
    for videos in (json.dumps(["https://www.youtube.com/watch?v=x"]), json.dumps(["https://vimeo.com/1"])):
        g = classify(db, videos=videos, run=completed(1))
        assert g.coverage_map()[CD.MEDIA_CONTENT] == CS.NOT_SUPPORTED and not g.approved


def test_E_safe_text_only_with_complete_deterministic_coverage_auto_approves(db):
    adult = person(db, 30)
    g = classify(db, title="Morning song", description="An acoustic cover I recorded last summer")
    cov = g.coverage_map()
    assert cov[CD.TEXT_PERSONAL_INFORMATION] == cov[CD.TEXT_HARM] == cov[CD.TEXT_LANGUAGE] == CS.COMPLETED_NO_FINDING
    assert cov[CD.MEDIA_CONTENT] == cov[CD.MEDIA_METADATA] == CS.NOT_APPLICABLE
    assert g.approved and g.automated
    assert submit(db, adult, content=g).public


def test_F_text_only_with_failed_check_is_review(db, monkeypatch):
    from app.services.content_moderation import content_moderation_service

    def boom(text):
        raise RuntimeError("local rules unavailable")

    monkeypatch.setattr(content_moderation_service, "moderate_text", boom)
    g = classify(db, title="Morning song", description="An acoustic cover")
    assert g.coverage_map()[CD.TEXT_LANGUAGE] == CS.FAILED and not g.approved and not g.findings
    assert g.classifier_status == ClassifierStatus.FAILED


def test_F2_harmful_text_is_review(db):
    for text in ("come and see my sexy show", "I will kill you", "buy weed here"):
        g = classify(db, description=text)
        assert not g.approved and g.coverage_map()[CD.TEXT_HARM] == CS.COMPLETED_FINDING


def test_G_sanitized_fully_classified_hosted_image_auto_approves(db):
    adult = person(db, 30)
    img = sanitized_image(db, adult)
    g = classify(db, images=json.dumps([img.id]), run=completed(1))
    assert g.approved and g.coverage_map()[CD.MEDIA_METADATA] == CS.COMPLETED_NO_FINDING
    raw = sanitized_image(db, adult, sanitized=False)
    g2 = classify(db, images=json.dumps([raw.id]), run=completed(1))
    assert not g2.approved and g2.coverage_map()[CD.MEDIA_METADATA] == CS.COMPLETED_FINDING


def test_H_minor_content_never_auto_approves_even_when_fully_covered(db):
    teen = person(db, 15)
    img = sanitized_image(db, teen)
    for g in (classify(db, minor=True, title="Morning song", description="An acoustic cover"),
              classify(db, minor=True, images=json.dumps([img.id]), run=completed(1))):
        assert g.coverage_complete and not g.findings
        assert g.state == ModerationState.REVIEW_REQUIRED and not g.approved


def test_I_child_safety_never_auto_approves(db):
    g = classify(db, minor=True, title="my nudes")
    assert g.state == ModerationState.CHILD_SAFETY_ESCALATED and not g.approved
    adult_text = classify(db, title="my nudes")
    assert SafetyConcern.SEXUAL_CONTENT in adult_text.findings and not adult_text.approved
    assert SafetyConcern.CHILD_SEXUAL_CONTENT not in adult_text.findings


def test_coverage_is_persisted_and_shown_to_moderators(client, db):
    adult = person(db, 30)
    row, _ = held_entry(db, adult, description="kill")
    item = cs.moderation_for(db, row.id)
    assert item.coverage["TEXT_HARM"] == "COMPLETED_FINDING" and item.coverage["MEDIA_CONTENT"] == "NOT_APPLICABLE"
    q = client.get("/api/v1/admin/content-moderation/queue", headers=auth(moderator(db))).json()
    assert q[0]["coverage"]["TEXT_HARM"] == "COMPLETED_FINDING"
