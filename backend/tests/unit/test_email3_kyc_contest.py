"""EMAIL-3: KYC and contest entry status emails.

The emails follow committed application state; they never drive it. These
tests exercise the REAL business paths (submission endpoint, moderation,
administrator review, re-evaluation, dead-link checker, Kaluta webhook
processing, KYC CRUD) and look at what reached the EMAIL-1 outbox.

Everything is SYNTHETIC. No KYC provider and no video provider is contacted;
emails go to the in-memory FakeEmailProvider.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.child_safety import ContentRating
from app.core.config import settings
from app.core.public_urls import public_site_base
from app.crud import crud_kyc
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant, ContestantSeason
from app.models.email import EmailDelivery
from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider
from app.models.verification import UserVerification
from app.models.voting import ContestantVoting
from app.services import content_safety as cs
from app.services import contest_eligibility as ce
from app.services import contest_notifications, kyc_notifications
from app.services import creative_link_check as clc
from app.services import email_settings_service as svc
from app.services import email_templates as tpl
from app.services import kyc_provider_dispatch as dispatch
from app.services.email import email_service
from app.services.email_events import EMAIL_EVENTS, EmailEvent, get_event
from app.services.email_render import RENDERERS, RenderError, render
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_creative_link_check import NOW as LINK_NOW
from tests.unit.test_creative_link_check import _entry as legacy_entry
from tests.unit.test_creative_link_check import _round as link_round
from tests.unit.test_creative_link_check import provider as link_provider  # noqa: F401  (fixture)
from tests.unit.test_held_nomination_visibility import (  # noqa: F401  (world/api_world are fixtures)
    _moderation, _nominate, _safety, api_world, world,
)
from tests.unit.test_phase5_contest_eligibility import TODAY, _post, contest, person
from tests.unit.test_phase6_content_safety import cs_resolver, moderator

APP = Path(__file__).resolve().parents[2] / "app"
ENTRIES_URL = "/dashboard/my-applications"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def rows(db, event=None):
    q = db.query(EmailDelivery).order_by(EmailDelivery.id)
    return [r for r in q.all() if event is None or r.event_key == event]


def events(db):
    return [r.event_key for r in rows(db)]


def keys(db):
    return [r.idempotency_key for r in rows(db)]


def participate(client, db, c, user, *, safe=True):
    """A participation: text-only (auto-approvable) or with an external video (waits for review)."""
    extra = {"title": "Morning song", "description": "An acoustic cover", "video_media_ids": None} if safe else {}
    resp = _post(client, user, c, **extra)
    assert resp.status_code == 200, resp.text
    return resp.json()


def verification(db, user, status=KYCStatus.PENDING, attempts=1) -> KYCVerification:
    row = KYCVerification(user_id=user.id, status=status, provider=VerificationProvider.KALUTA,
                          reference_id=f"ref-{uuid.uuid4().hex[:10]}", attempts_count=attempts)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def kaluta(event, v, **session):
    return {"event": event, "session": {"id": f"sess-{v.id}", "external_id": v.reference_id,
                                        "metadata": {"user_id": v.user_id}, **session}}


SENSITIVE = ("Jane", "Doe", "1990-01-01", "P1234567", "document number", "passport", "SECRET-PROVIDER-REASON",
             "face_match", "provider", "selfie")


# ===========================================================================
# REGISTRY: nothing added, nothing renamed
# ===========================================================================

def test_registry_is_unchanged_and_only_the_audited_events_are_wired():
    assert len(EMAIL_EVENTS) == 54                  # 53 of EMAIL-1 + PAYOUT.WALLET_CONFIRMATION (dual cashout)
    wired_now = {k for k, d in EMAIL_EVENTS.items() if d.trigger_implemented and (k.startswith("KYC.") or k.startswith("CONTEST."))}
    assert wired_now == {
        "KYC.APPROVED", "KYC.REJECTED", "KYC.ACTION_REQUIRED",
        "CONTEST.NOMINATION_PUBLISHED", "CONTEST.NOMINATION_ACTION_REQUIRED", "CONTEST.NOMINATION_REMOVED",
        "CONTEST.PARTICIPATION_PENDING_REVIEW", "CONTEST.PARTICIPATION_PUBLISHED",
        "CONTEST.PARTICIPATION_ACTION_REQUIRED", "CONTEST.PARTICIPATION_REJECTED", "CONTEST.CREATIVE_UNAVAILABLE"}
    for key in wired_now:
        assert EMAIL_EVENTS[key].default_enabled and key in RENDERERS
    # deferred or blocked: registered, switchable, not emitted
    for key in ("KYC.SUBMITTED", "KYC.EXPIRED", "CONTEST.NOMINATION_RESTORED", "CONTEST.NOMINEE_CLAIM_INVITATION",
                "CONTEST.NOMINEE_CLAIMED", "CONTEST.VOTING_OPEN", "CONTEST.VOTING_CLOSING", "CONTEST.ADVANCED",
                "CONTEST.NOT_ADVANCED", "CONTEST.RESULT_PUBLISHED", "CONTEST.WINNER",
                "AUTH.ACCOUNT_SUSPENDED", "AUTH.ACCOUNT_RESTORED"):
        assert not EMAIL_EVENTS[key].trigger_implemented and key not in RENDERERS
    # EMAIL-4 / EMAIL-5 untouched: no billing, affiliate or payout event became live here
    live_money = {k for k, d in EMAIL_EVENTS.items() if d.trigger_implemented
                  and k.split(".")[0] in ("BILLING", "AFFILIATE", "PAYOUT")}
    # as before EMAIL-3, plus the payout wallet confirmation link added by the dual cashout
    assert live_money == {"BILLING.PAYMENT_CONFIRMED", "AFFILIATE.INVITATION", "PAYOUT.WALLET_CONFIRMATION"}


def test_business_modules_never_talk_to_a_provider():
    for name in ("services/contest_notifications.py", "services/kyc_notifications.py", "services/email_event_texts.py"):
        source = (APP / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import resend|from resend)", source, re.M)
        assert "email_providers" not in source and "requests" not in source and "process_outbox" not in source
    for name in ("services/contest_notifications.py", "services/kyc_notifications.py"):
        assert "email_service.enqueue(" in (APP / name).read_text(encoding="utf-8")


# ===========================================================================
# KYC
# ===========================================================================

def test_identity_accepted_asks_for_the_remaining_step_once(db, email_outbox):
    user = person(db, 30)
    v = verification(db, user)
    payload = kaluta("session.approved", v, status="approved",
                     identity={"first_name": "Jane", "last_name": "Doe", "nationality": "TZ",
                               "document_number": "P1234567", "date_of_birth": "1990-01-01"})
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=payload) is True
    db.refresh(v)
    assert v.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert events(db) == ["KYC.ACTION_REQUIRED"]
    delivery = rows(db)[0]
    assert (delivery.user_id, delivery.idempotency_key) == (user.id, f"kyc.action_required:{v.id}:1")

    # the provider delivers the webhook again, and a status poll reaches the same state
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=payload) is True
    kyc_notifications.notify_status(db, v.id)
    assert events(db) == ["KYC.ACTION_REQUIRED"]

    mail = email_outbox[0]
    assert mail["to"] == user.email and f"{public_site_base()}/dashboard/kyc" in mail["html"]
    for secret in SENSITIVE:
        assert secret.lower() not in (mail["subject"] + mail["html"] + mail["text"]).lower()


def test_automatic_approval_is_announced_once_whatever_path_reports_it(db, email_outbox, monkeypatch):
    """The main approval path (proof of address validated automatically) used to
    send nothing; only an administrator's approval did."""
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    user = person(db, 30)
    v = verification(db, user, status=KYCStatus.PENDING_PROOF_OF_ADDRESS)
    crud_kyc.kyc_verification.finalize_proof_of_address_auto(db, verification_id=v.id)
    kyc_notifications.notify_status(db, v.id)                    # what the proof-of-address endpoint does next
    db.refresh(v)
    assert v.status == KYCStatus.APPROVED and events(db) == ["KYC.APPROVED"]
    assert rows(db)[0].idempotency_key == f"kyc.approved:{v.id}:1"   # the same key the admin endpoint uses

    kyc_notifications.notify_status(db, v.id)                    # reported again
    assert events(db) == ["KYC.APPROVED"]
    assert len(email_outbox) == 1 and email_outbox[0]["to"] == user.email

    # Kaluta validating the address itself reaches APPROVED in one webhook: one approval email, no "step left"
    other = person(db, 31)
    v2 = verification(db, other)
    payload = kaluta("session.approved", v2, status="approved", checks_required={"proof_of_address": True},
                     scores={"document": 90, "face": 90, "poa": 90})
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=payload) is True
    db.refresh(v2)
    assert v2.status == KYCStatus.APPROVED
    assert [r.event_key for r in rows(db) if r.user_id == other.id] == ["KYC.APPROVED"]


def test_the_endpoints_notify_only_after_the_committed_transition():
    source = (APP / "api/api_v1/endpoints/kyc.py").read_text(encoding="utf-8")
    finalize = source.index("crud_kyc.kyc_verification.finalize_proof_of_address_auto(db, verification_id=verification.id)")
    assert 0 < source.index("kyc_notifications.notify_status(db, verification.id)", finalize) - finalize < 400
    assert source.count("kyc_notifications.notify_status(") == 3     # proof of address + Shufti accepted + Shufti declined
    assert "kyc_notifications" not in (APP / "crud/crud_kyc.py").read_text(encoding="utf-8")


def test_provider_rejection_is_announced_without_the_providers_reason(db, email_outbox):
    user = person(db, 30)
    v = verification(db, user)
    payload = kaluta("session.rejected", v, status="rejected",
                     rejection_reason="SECRET-PROVIDER-REASON: document number P1234567 does not match face_match 0.31")
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=payload) is True
    db.refresh(v)
    assert v.status == KYCStatus.REJECTED and "SECRET-PROVIDER-REASON" in (v.rejection_reason or "")   # kept in the record
    assert events(db) == ["KYC.REJECTED"]
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=payload) is True       # duplicate webhook
    assert events(db) == ["KYC.REJECTED"]
    mail = email_outbox[0]
    whole = (mail["subject"] + mail["html"] + mail["text"]).lower()
    for secret in SENSITIVE:
        assert secret.lower() not in whole
    assert "reason:" not in whole


def test_admin_decisions_keep_their_email_and_never_double_up(client, db, email_outbox, monkeypatch):
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    admin = person(db, 40, admin=True)
    approved_user, rejected_user = person(db, 30), person(db, 30)
    v1, v2 = verification(db, approved_user), verification(db, rejected_user)
    assert client.post(f"/api/v1/kyc/admin/verification/{v1.id}/approve", headers=auth(admin)).status_code == 200
    kyc_notifications.notify_status(db, v1.id)
    assert client.post(f"/api/v1/kyc/admin/verification/{v2.id}/reject", headers=auth(admin),
                       data={"reason": "The photo is too dark to read"}).status_code == 200
    kyc_notifications.notify_status(db, v2.id)
    assert sorted(events(db)) == ["KYC.APPROVED", "KYC.REJECTED"]
    rejected_mail = next(m for m in email_outbox if m["to"] == rejected_user.email)
    assert "The photo is too dark to read" in rejected_mail["html"]        # the administrator's own, member-facing reason


@pytest.mark.parametrize("event, status", [("session.expired", KYCStatus.EXPIRED),
                                           ("session.created", KYCStatus.PENDING),
                                           ("session.processing", KYCStatus.PENDING)])
def test_internal_and_session_states_send_nothing(db, email_outbox, event, status):
    user = person(db, 30)
    v = verification(db, user)
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta(event, v)) is True
    db.refresh(v)
    assert v.status == status and rows(db) == []
    for quiet in (KYCStatus.IN_PROGRESS, KYCStatus.REQUIRES_REVIEW, KYCStatus.EXPIRED, KYCStatus.PENDING):
        v.status = quiet
        db.commit()
        kyc_notifications.notify_status(db, v.id)
    kyc_notifications.notify_status(db, None)
    kyc_notifications.notify_status(db, 999999)
    assert rows(db) == []


def test_a_kyc_transition_that_does_not_commit_sends_nothing(db, email_outbox, monkeypatch):
    user = person(db, 30)
    v = verification(db, user)

    def fails_before_commit(*args, **kwargs):
        raise RuntimeError("database refused the update")
    monkeypatch.setattr(crud_kyc.kyc_verification, "apply_shufti_identity_accepted", fails_before_commit)
    with pytest.raises(RuntimeError):
        dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta("session.approved", v, status="approved"))
    db.rollback()
    db.refresh(v)
    assert v.status == KYCStatus.PENDING and rows(db) == []

    # a caller that only THINKS the status changed (uncommitted, then rolled back) sends nothing either
    v.status = KYCStatus.APPROVED
    db.flush()
    db.rollback()
    kyc_notifications.notify_status(db, v.id)
    assert rows(db) == []


def test_kyc_email_respects_switches_and_never_blocks_the_decision(db, email_outbox, monkeypatch):
    # event switched off
    svc.set_event_enabled(db, get_event(EmailEvent.KYC_REJECTED), False, actor_id=None)
    db.commit()
    user = person(db, 30)
    v = verification(db, user)
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta("session.rejected", v)) is True
    db.refresh(v)
    assert v.status == KYCStatus.REJECTED
    off = rows(db)[0]
    assert (off.status, off.failure_category) == ("SUPPRESSED", "event_disabled")

    # master switch off: KYC email is not "critical", so it is suppressed too
    settings_row = svc.get_settings_for_update(db)
    settings_row.email_enabled = False
    db.commit()
    v2 = verification(db, person(db, 30))
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta("session.approved", v2, status="approved"))
    db.refresh(v2)
    assert v2.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert (rows(db)[1].status, rows(db)[1].failure_category) == ("SUPPRESSED", "master_disabled")

    # emergency stop
    settings_row.email_enabled, settings_row.emergency_stop = True, True
    db.commit()
    v3 = verification(db, person(db, 30))
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta("session.rejected", v3))
    assert rows(db)[2].failure_category == "emergency_stop"
    assert len(email_outbox) == 0

    # the email subsystem itself failing never undoes or blocks the KYC decision
    settings_row.emergency_stop = False
    db.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("email subsystem down")
    monkeypatch.setattr(email_service, "enqueue", boom)
    v4 = verification(db, person(db, 30))
    assert dispatch.process_kaluta_webhook_event(db, crud_kyc=crud_kyc, payload=kaluta("session.rejected", v4)) is True
    db.refresh(v4)
    assert v4.status == KYCStatus.REJECTED and len(rows(db)) == 3


def test_kyc_email_goes_only_to_an_active_account_and_reflects_the_state_when_sent(db, email_outbox):
    gone = person(db, 30)
    v = verification(db, gone, status=KYCStatus.REJECTED)
    gone.is_active = False
    db.commit()
    kyc_notifications.notify_status(db, v.id)
    assert rows(db) == []

    # "one step left" is not sent if the verification has moved on before the outbox runs
    user = person(db, 30)
    v2 = verification(db, user, status=KYCStatus.PENDING_PROOF_OF_ADDRESS)
    kyc_notifications.notify_status(db, v2.id)
    v2.status = KYCStatus.APPROVED
    db.commit()
    assert len(email_outbox) == 0
    stale = rows(db)[0]
    assert (stale.status, stale.failure_category, stale.failure_code) == ("FAILED", "render_error", "state_changed")


# ===========================================================================
# CONTEST: nomination
# ===========================================================================

def test_a_nomination_is_announced_as_published_at_once(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    assert body["public_status"] == "PUBLIC"
    safety = _safety(db, body["id"])
    assert safety.exposure_status == "PUBLIC" and safety.nominee_user_id is None      # unclaimed, and public
    assert events(db) == ["CONTEST.NOMINATION_PUBLISHED"]
    delivery = rows(db)[0]
    assert (delivery.user_id, delivery.idempotency_key) == (nominator.id, f"contest.entry.published:{body['id']}")

    mail = email_outbox[0]
    assert mail["to"] == nominator.email
    whole = (mail["subject"] + " " + mail["html"] + " " + mail["text"]).lower()
    for wrong in ("waiting for approval", "awaiting approval", "pending", "under review", "being checked",
                  "will be reviewed", "approved"):
        assert wrong not in whole
    assert "published" in mail["subject"].lower() and "now public" in whole
    assert c.name in mail["html"] and "My song" in mail["html"]
    assert f'href="{public_site_base()}{ENTRIES_URL}"' in mail["html"]
    # publication is not voting: the email promises neither votes nor a result
    assert "voting opens when" in whole and "you can vote" not in whole and "winner" not in whole
    # the claim link is the nominee's credential: it is returned once by the API and never emailed here
    assert body["nominee_claim_token"] and body["nominee_claim_token"] not in mail["html"] + mail["text"]
    assert "claim" not in whole


def test_one_published_email_per_entry_whatever_repeats(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    video = json.dumps([f"https://youtu.be/{uuid.uuid4().hex[:8]}"])
    first = _nominate(client, db, c, nominator, video_media_ids=video)
    again = _nominate(client, db, c, nominator, video_media_ids=video)      # the client retries the submission
    assert again["id"] == first["id"]
    admin = person(db, 40, admin=True)
    ce.reevaluate_entry(db, _safety(db, first["id"]), actor_id=None, trigger="TEST", today=TODAY)
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin)).status_code == 200
    contest_notifications.entry_created(db, first["id"])
    contest_notifications.entries_published(db, [first["id"], first["id"]])
    assert events(db) == ["CONTEST.NOMINATION_PUBLISHED"] and len(email_outbox) == 1


def test_a_held_nomination_is_announced_only_when_it_really_becomes_public(client, db, world, email_outbox, monkeypatch):
    c, _rnd = world()
    nominator = person(db, 30)
    with monkeypatch.context() as previous_rule:
        previous_rule.setattr(ce, "_nomination_publication_policy",
                              lambda unmet, holds, **_k: (tuple(unmet), tuple(holds), ()))
        body = _nominate(client, db, c, nominator)
    assert _safety(db, body["id"]).exposure_status == "HELD"
    assert rows(db) == []                               # held at submission: nothing claims it is public, or "in review"
    contest_notifications.entries_published(db, [body["id"]])   # a caller that is wrong about the state
    assert rows(db) == []

    admin = person(db, 40, admin=True)
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin)).status_code == 200
    assert _safety(db, body["id"]).exposure_status == "PUBLIC"
    assert events(db) == ["CONTEST.NOMINATION_PUBLISHED"]
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate", headers=auth(admin)).status_code == 200
    assert events(db) == ["CONTEST.NOMINATION_PUBLISHED"]       # the next pass announces nothing again


def test_admin_block_and_rejection_are_announced_once(client, db, world, email_outbox):
    c, _rnd = world()
    admin = person(db, 40, admin=True)
    blocked_owner, rejected_owner = person(db, 30), person(db, 30)
    blocked = _nominate(client, db, c, blocked_owner)
    rejected = _nominate(client, db, c, rejected_owner)
    email_outbox.drain()                                         # the two "published" emails go out first

    ce.admin_review(db, _safety(db, blocked["id"]), action="BLOCK", admin_id=admin.id,
                    note="INTERNAL NOTE not for the member", today=TODAY)
    ce.admin_review(db, _safety(db, blocked["id"]), action="BLOCK", admin_id=admin.id, note="again", today=TODAY)
    for _ in range(2):
        assert client.post(f"/api/v1/admin/contestants/{rejected['id']}/reject", headers=auth(admin)).status_code == 200
    assert client.put(f"/api/v1/admin/contestants/{rejected['id']}/status?status=rejected",
                      headers=auth(admin)).status_code == 200
    removed = rows(db, "CONTEST.NOMINATION_REMOVED")
    assert sorted(r.user_id for r in removed) == sorted([blocked_owner.id, rejected_owner.id])
    mails = [m for m in email_outbox if "removed" in m["subject"].lower()]
    assert len(mails) == 2
    for mail in mails:
        assert "INTERNAL NOTE" not in mail["html"] + mail["text"]

    # approving (legacy "verified") is not a publication and announces nothing
    other = _nominate(client, db, c, person(db, 30))
    before = len(rows(db))
    assert client.post(f"/api/v1/admin/contestants/{other['id']}/approve", headers=auth(admin)).status_code == 200
    assert client.put(f"/api/v1/admin/contestants/{other['id']}/status?status=verified",
                      headers=auth(admin)).status_code == 200
    assert len(rows(db)) == before


def test_states_that_are_deliberately_not_emailed(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    # the nominee declines: the entry is hidden; nobody is emailed about it here
    declined = _nominate(client, db, c, nominator)
    nominee = person(db, 28, email_verified=True)
    assert client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(nominee),
                       json={"token": declined["nominee_claim_token"], "decision": "DECLINE"}).status_code == 200
    assert _safety(db, declined["id"]).exposure_status == "HELD"
    # another nominee accepts
    claimed = _nominate(client, db, c, person(db, 30))
    claimant = person(db, 29, email_verified=True)
    assert client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(claimant),
                       json={"token": claimed["nominee_claim_token"], "decision": "ACCEPT"}).status_code == 200
    # a child-safety escalation is never announced by email
    escalated = _nominate(client, db, c, person(db, 30))
    ce.escalate_entry(db, _safety(db, escalated["id"]), actor_id=None, action="TEST_ESCALATION")
    admin = person(db, 40, admin=True)
    ce.admin_review(db, _safety(db, escalated["id"]), action="BLOCK", admin_id=admin.id, note="x", today=TODAY)
    assert _safety(db, escalated["id"]).exposure_status == "CHILD_SAFETY_ESCALATED"
    contest_notifications.entry_removed(db, escalated["id"])
    contest_notifications.entry_update_requested(db, escalated["id"])

    assert set(events(db)) == {"CONTEST.NOMINATION_PUBLISHED"} and len(rows(db)) == 3
    assert {r.user_id for r in rows(db)} .isdisjoint({nominee.id, claimant.id, admin.id})   # only the nominators


# ===========================================================================
# CONTEST: participation (a different lifecycle from nomination)
# ===========================================================================

def test_participation_and_nomination_send_their_own_events(client, db, world, email_outbox):
    nomination_contest, _ = world()
    participation_contest, _ = world("participation")
    nominator, entrant = person(db, 30), person(db, 30)
    nomination = _nominate(client, db, nomination_contest, nominator)
    entry = participate(client, db, participation_contest, entrant, safe=True)
    assert entry["public_status"] == "PUBLIC"
    by_user = {r.user_id: r.event_key for r in rows(db)}
    assert by_user == {nominator.id: "CONTEST.NOMINATION_PUBLISHED", entrant.id: "CONTEST.PARTICIPATION_PUBLISHED"}
    assert db.query(Contestant).get(nomination["id"]).entry_type == "nomination"
    assert db.query(Contestant).get(entry["id"]).entry_type == "participation"
    subjects = {m["to"]: m["subject"] for m in email_outbox}
    assert "nomination" in subjects[nominator.email].lower() and "nomination" not in subjects[entrant.email].lower()


def test_participation_that_waits_for_review_then_is_approved(client, db, world, email_outbox):
    c, _rnd = world("participation")
    entrant = person(db, 30)
    entry = participate(client, db, c, entrant, safe=False)                 # external video: a moderator decides
    assert entry["public_status"] == "PENDING_REVIEW"
    safety = _safety(db, entry["id"])
    assert safety.exposure_status == "HELD" and "CONTENT_REVIEW_REQUIRED" in safety.reason_codes   # rule unchanged
    assert events(db) == ["CONTEST.PARTICIPATION_PENDING_REVIEW"]
    pending = email_outbox[0]
    assert "not public yet" in pending["html"] and "now public" not in pending["html"]

    cs.moderate(db, _moderation(db, entry["id"]), action="APPROVE", actor=moderator(db), reason="REVIEWED_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    assert _safety(db, entry["id"]).exposure_status == "PUBLIC"
    assert events(db) == ["CONTEST.PARTICIPATION_PENDING_REVIEW", "CONTEST.PARTICIPATION_PUBLISHED"]
    ce.reevaluate_open_entries(db, trigger="TEST", today=TODAY)
    ce.reevaluate_for_user(db, entrant.id, trigger="TEST", today=TODAY)
    assert events(db).count("CONTEST.PARTICIPATION_PUBLISHED") == 1
    assert email_outbox[-1]["to"] == entrant.email and "now public" in email_outbox[-1]["html"]


def test_a_moderators_update_request_is_announced_per_request(client, db, world, email_outbox):
    c, _rnd = world("participation")
    entrant = person(db, 30)
    entry = participate(client, db, c, entrant, safe=False)
    mod = moderator(db)
    t0 = datetime.utcnow().replace(microsecond=0)
    cs.moderate(db, _moderation(db, entry["id"]), action="REQUEST_UPDATE", actor=mod,
                reason="MODERATOR INTERNAL REASON", now=t0, today=TODAY)
    assert _moderation(db, entry["id"]).update_required is True
    assert events(db) == ["CONTEST.PARTICIPATION_PENDING_REVIEW", "CONTEST.PARTICIPATION_ACTION_REQUIRED"]
    contest_notifications.entry_update_requested(db, entry["id"])            # reported twice
    assert events(db).count("CONTEST.PARTICIPATION_ACTION_REQUIRED") == 1
    mail = email_outbox[-1]
    assert "update" in mail["subject"].lower() and "MODERATOR INTERNAL REASON" not in mail["html"] + mail["text"]

    # a HOLD is not an update request; a NEW request later is a new email
    cs.moderate(db, _moderation(db, entry["id"]), action="HOLD", actor=mod, reason="x",
                now=t0 + timedelta(minutes=5), today=TODAY)
    assert events(db).count("CONTEST.PARTICIPATION_ACTION_REQUIRED") == 1
    cs.moderate(db, _moderation(db, entry["id"]), action="REQUEST_UPDATE", actor=mod, reason="x",
                now=t0 + timedelta(minutes=10), today=TODAY)
    assert events(db).count("CONTEST.PARTICIPATION_ACTION_REQUIRED") == 2

    # the same action on a nomination uses the nomination event
    nc, _ = world()
    nomination = _nominate(client, db, nc, person(db, 30))
    cs.moderate(db, _moderation(db, nomination["id"]), action="REQUEST_UPDATE", actor=mod, reason="x", today=TODAY)
    assert events(db)[-1] == "CONTEST.NOMINATION_ACTION_REQUIRED"


def test_rejected_participation_uses_the_participation_event(client, db, world, email_outbox):
    c, _rnd = world("participation")
    entrant = person(db, 30)
    entry = participate(client, db, c, entrant, safe=True)
    admin = person(db, 40, admin=True)
    assert client.post(f"/api/v1/admin/contestants/{entry['id']}/reject", headers=auth(admin)).status_code == 200
    assert events(db) == ["CONTEST.PARTICIPATION_PUBLISHED", "CONTEST.PARTICIPATION_REJECTED"]
    assert rows(db)[-1].user_id == entrant.id


# ===========================================================================
# CONTEST: dead video link
# ===========================================================================

def test_dead_link_removal_is_announced_once(db, link_provider, email_outbox):
    c = contest(db, "nomination")
    rnd = link_round(db, c)
    owner = person(db, 30)
    entry = legacy_entry(db, c, rnd, owner=owner)                 # a pre-Phase-5 entry without a safety record
    link_provider.default = 404
    assert clc.run_link_recheck(db, now=LINK_NOW)["suspected"] == 1
    assert rows(db) == []                                         # a suspicion is not a removal
    assert clc.run_link_recheck(db, now=LINK_NOW + timedelta(hours=1))["removed"] == 0
    assert rows(db) == []
    assert clc.run_link_recheck(db, now=LINK_NOW + timedelta(hours=13))["removed"] == 1
    db.refresh(entry)
    assert entry.verification_status == "creative_unavailable"
    assert events(db) == ["CONTEST.CREATIVE_UNAVAILABLE"] and rows(db)[0].user_id == owner.id
    for hours in (14, 40, 80):                                    # later scheduler passes
        clc.run_link_recheck(db, now=LINK_NOW + timedelta(hours=hours))
    contest_notifications.creative_unavailable(db, [entry.id])
    assert events(db) == ["CONTEST.CREATIVE_UNAVAILABLE"]
    mail = email_outbox[0]
    assert mail["to"] == owner.email and "no longer available" in mail["subject"]
    assert "youtu" not in mail["html"]                            # the dead URL itself is not repeated
    # the removal itself is exactly what it was: logical, history kept
    assert entry.is_deleted is False and db.query(AuditTrail).filter(AuditTrail.action == "CREATIVE_LINK_REMOVED").count() == 1


def test_transient_link_failures_announce_nothing(db, link_provider, email_outbox):
    c = contest(db, "nomination")
    entry = legacy_entry(db, c, link_round(db, c))
    link_provider.default = 503
    for hours in (0, 13, 26):
        clc.run_link_recheck(db, now=LINK_NOW + timedelta(hours=hours))
    db.refresh(entry)
    assert entry.verification_status == "pending" and rows(db) == []


# ===========================================================================
# TRANSACTIONS, SWITCHES, FAILURE
# ===========================================================================

def test_a_submission_that_does_not_commit_announces_nothing(client, db, world, email_outbox, monkeypatch):
    c, _rnd = world()
    nominator = person(db, 30)

    def fails(*args, **kwargs):
        raise RuntimeError("safety record could not be written")
    monkeypatch.setattr(ce, "record_new_entry", fails)             # inside the submission transaction, before its commit
    resp = _post(client, nominator, c, nominee_age_declaration="ADULT", nominator_country=nominator.country)
    assert resp.status_code >= 400                                  # the endpoint rolls back and reports the failure
    db.rollback()
    assert db.query(Contestant).filter(Contestant.user_id == nominator.id).count() == 0
    assert rows(db) == []


def test_an_uncommitted_reevaluation_announces_nothing(client, db, world, email_outbox, monkeypatch):
    c, _rnd = world()
    with monkeypatch.context() as previous_rule:
        previous_rule.setattr(ce, "_nomination_publication_policy",
                              lambda unmet, holds, **_k: (tuple(unmet), tuple(holds), ()))
        body = _nominate(client, db, c, person(db, 30))
    row = _safety(db, body["id"])
    ce.reevaluate_entry(db, row, actor_id=None, trigger="TEST", today=TODAY, commit=False)
    assert row.exposure_status == "PUBLIC"                        # in the open transaction only
    db.rollback()
    assert _safety(db, body["id"]).exposure_status == "HELD"
    contest_notifications.entries_published(db, [body["id"]])
    contest_notifications.entry_created(db, body["id"])
    assert rows(db) == []


def test_contest_email_switches_never_block_the_business_action(client, db, world, email_outbox, monkeypatch):
    c, _rnd = world()
    svc.set_event_enabled(db, get_event(EmailEvent.CONTEST_NOMINATION_PUBLISHED), False, actor_id=None)
    db.commit()
    first = _nominate(client, db, c, person(db, 30))
    assert first["public_status"] == "PUBLIC"
    assert (rows(db)[0].status, rows(db)[0].failure_category) == ("SUPPRESSED", "event_disabled")

    db.query(svc.EmailEventSetting).delete()
    settings_row = svc.get_settings_for_update(db)
    settings_row.email_enabled = False
    db.commit()
    second = _nominate(client, db, c, person(db, 30))
    assert second["public_status"] == "PUBLIC" and rows(db)[1].failure_category == "master_disabled"

    settings_row.email_enabled, settings_row.emergency_stop = True, True
    db.commit()
    third = _nominate(client, db, c, person(db, 30))
    assert third["public_status"] == "PUBLIC" and rows(db)[2].failure_category == "emergency_stop"
    assert len(email_outbox) == 0

    settings_row.emergency_stop = False
    db.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("email subsystem down")
    monkeypatch.setattr(email_service, "enqueue", boom)
    fourth = _nominate(client, db, c, person(db, 30))
    assert fourth["public_status"] == "PUBLIC" and _safety(db, fourth["id"]).exposure_status == "PUBLIC"
    admin = person(db, 40, admin=True)
    ce.admin_review(db, _safety(db, fourth["id"]), action="BLOCK", admin_id=admin.id, note="x", today=TODAY)
    assert _safety(db, fourth["id"]).exposure_status == "BLOCKED"
    assert len(rows(db)) == 3


def test_an_email_never_announces_a_state_that_is_no_longer_true(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)                    # "published" is queued ...
    admin = person(db, 40, admin=True)
    ce.admin_review(db, _safety(db, body["id"]), action="BLOCK", admin_id=admin.id, note="x", today=TODAY)   # ... then removed
    subjects = [m["subject"].lower() for m in email_outbox]       # the outbox runs only now
    assert len(subjects) == 1 and "removed" in subjects[0]
    published = rows(db, "CONTEST.NOMINATION_PUBLISHED")[0]
    assert (published.status, published.failure_category, published.failure_code) == ("FAILED", "render_error", "state_changed")


def test_recipient_is_always_the_submitting_member(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    row = rows(db)[0]
    assert row.user_id == nominator.id
    # nothing a client sends can redirect the email: the stored context is the entry id only
    from app.services import email_crypto

    payload = email_crypto.decrypt_payload(row.payload_ciphertext)
    assert payload == {"to": nominator.email, "context": {"contestant_id": body["id"]}}
    # rendering for anybody but the entry's own submitter is refused
    stranger = person(db, 30)
    with pytest.raises(RenderError):
        render(db, event_key="CONTEST.NOMINATION_PUBLISHED", to=stranger.email, user_id=stranger.id,
               context={"contestant_id": body["id"]}, lang="en")
    for bad in ({}, {"contestant_id": "x"}, {"contestant_id": 999999}):
        with pytest.raises(RenderError):
            render(db, event_key="CONTEST.NOMINATION_PUBLISHED", to=nominator.email, user_id=nominator.id,
                   context=bad, lang="en")

    # an inactive or address-less submitter gets nothing; the entry is unaffected
    inactive = person(db, 30)
    other = _nominate(client, db, c, inactive)
    db.query(EmailDelivery).delete()
    inactive.is_active = False
    db.commit()
    contest_notifications.entry_created(db, other["id"])
    contest_notifications.entry_removed(db, other["id"])
    assert rows(db) == [] and _safety(db, other["id"]).exposure_status == "PUBLIC"
    contest_notifications.entry_created(db, 999999)               # unknown entry: nothing, no error
    assert rows(db) == []


def test_member_controlled_text_is_escaped_and_kept_out_of_the_subject(client, db, world, email_outbox):
    c, _rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    entry = db.query(Contestant).get(body["id"])
    entry.title = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    c.name = 'Best <b>of</b> "2026" & more'
    db.commit()
    mail = email_outbox[0]
    assert "<script>" not in mail["html"] and "<img src=x" not in mail["html"] and "<b>of</b>" not in mail["html"]
    assert "&lt;script&gt;" in mail["html"] and "&amp; more" in mail["html"]
    assert "script" not in mail["subject"] and "2026" not in mail["subject"]
    assert '<script>alert("x")</script>' in mail["text"]          # plain text is plain text


# ===========================================================================
# NOTHING ELSE MOVES
# ===========================================================================

def test_notifications_touch_no_business_data(client, db, world, email_outbox):
    c, rnd = world()
    nominator = person(db, 30)
    body = _nominate(client, db, c, nominator)
    entry_id = body["id"]

    def snapshot():
        s = _safety(db, entry_id)
        e = db.query(Contestant).get(entry_id)
        m = db.query(ContentModeration).filter(ContentModeration.contestant_id == entry_id).first()
        return (s.exposure_status, s.rights_status, s.safety_status, s.workflow_step, tuple(s.reason_codes or ()),
                s.nominee_user_id, s.claimed_at, e.is_active, e.verification_status, e.entry_type, e.is_qualified,
                getattr(m, "state", None), getattr(m, "rating", None), getattr(m, "decided_by_user_id", None),
                db.query(ContestantVoting).count(), db.query(ContestantSeason).count(),
                db.query(UserVerification).count(), db.query(AuditTrail).count())
    before = snapshot()
    for call in (contest_notifications.entry_created, contest_notifications.entry_removed,
                 contest_notifications.entry_update_requested):
        call(db, entry_id)
    contest_notifications.entries_published(db, [entry_id])
    contest_notifications.creative_unavailable(db, [entry_id])
    email_outbox.drain()
    assert snapshot() == before
    # still unclaimed, rights pending, not reviewed by a human, not votable before its stage: nothing was faked
    s = _safety(db, entry_id)
    assert s.nominee_user_id is None and s.rights_status == "PENDING"
    assert _moderation(db, entry_id).decided_by_user_id is None
    stranger = person(db, 30)
    assert client.post(f"/api/v1/contestants/{entry_id}/vote", headers=auth(stranger)).status_code != 200


def test_no_ranking_progression_or_verification_code_emits_email():
    """Progression, results, voting, TopHigh5, guardian flows and the contest
    media-verification feature are untouched by EMAIL-3."""
    for name in ("season_migration.py", "participation_safety.py", "vote_ranking.py", "guardian_consent.py",
                 "contest_status.py", "monthly_round_scheduler.py", "season_migration_scheduler.py"):
        path = APP / "services" / name
        if path.exists():
            source = path.read_text(encoding="utf-8")
            assert "contest_notifications" not in source and "kyc_notifications" not in source, name
    for name in ("crud/crud_verification.py", "api/api_v1/endpoints/verifications.py", "models/verification.py",
                 "api/api_v1/endpoints/votes.py", "api/api_v1/endpoints/voting.py"):
        path = APP / name
        if path.exists():
            assert "notifications" not in path.read_text(encoding="utf-8"), name
    notifier = (APP / "services" / "contest_notifications.py").read_text(encoding="utf-8")
    for forbidden in ("db.add(", "db.delete(", "ContestantVoting", "ContestantSeason", "TopHigh5"):
        assert forbidden not in notifier
    # it reads state (==) and never assigns it
    assert not re.search(r"\.(is_active|exposure_status|verification_status|rights_status|workflow_step)\s*=[^=]", notifier)


# ===========================================================================
# TEMPLATES
# ===========================================================================

PREFIXES = ("nomination_published", "nomination_removed", "nomination_action", "participation_pending",
            "participation_published", "participation_action", "participation_rejected", "creative_unavailable")


@pytest.mark.parametrize("lang", ["fr", "en", "es", "de"])
def test_every_status_email_exists_in_every_primary_language(lang):
    year = str(datetime.utcnow().year)
    url = "https://myhigh5.com/dashboard/my-applications"
    seen = set()
    for prefix in PREFIXES:
        subject, html, text = tpl.get_status_email(lang, prefix, entry="Chanson", contest="Voix 2026",
                                                   note_key=f"{prefix}_note", button_key="entries_button", button_url=url)
        assert subject and "\n" not in subject and "{" not in subject and "Chanson" not in subject
        assert "Chanson" in html and "Voix 2026" in html and "Chanson" in text and "Voix 2026" in text
        assert "{entry}" not in html + text and "{contest}" not in html + text
        assert f'href="{url}"' in html and url in text and "<" not in text
        assert year in html and year in text
        assert html.count("<!DOCTYPE html>") == 1                 # the one shared layout
        seen.add(subject)
    subject, html, text = tpl.get_status_email(lang, "kyc_action", button_key="kyc_action_button",
                                               button_url="https://myhigh5.com/dashboard/kyc")
    assert subject and "https://myhigh5.com/dashboard/kyc" in html and text.strip()
    assert len(seen) == len(PREFIXES)
    english = tpl.get_status_email("en", "nomination_published", entry="a", contest="b", button_key="entries_button",
                                   button_url=url)[0]
    assert (tpl.get_status_email(lang, "nomination_published", entry="a", contest="b", button_key="entries_button",
                                 button_url=url)[0] == english) == (lang == "en")


def test_other_languages_fall_back_to_english():
    url = "https://myhigh5.com/dashboard/my-applications"
    english = tpl.get_status_email("en", "participation_pending", entry="a", contest="b", note_key="participation_pending_note",
                                   button_key="entries_button", button_url=url)
    for lang in ("sw", "pt_BR", "zh", "", None):
        assert tpl.get_status_email(lang, "participation_pending", entry="a", contest="b",
                                    note_key="participation_pending_note", button_key="entries_button",
                                    button_url=url) == english


def test_links_are_the_canonical_application_urls_only():
    source = (APP / "services" / "email_render.py").read_text(encoding="utf-8")
    block = source[source.index("def _kyc_action_required"):source.index("def _payment_confirmed")]
    links = re.findall(r'f"\{public_site_base\(\)\}([^"]*)"', block)
    assert sorted(set(links)) == ["/dashboard/kyc", "/dashboard/my-applications"]
    for forbidden in ("localhost", "127.0.0.1", "http://", "?token", "/admin", "/media/", "file://"):
        assert forbidden not in block
    # no identity or KYC value can reach a URL: the link is a constant path
    assert "{" not in "".join(links)
    texts = (APP / "services" / "email_event_texts.py").read_text(encoding="utf-8")
    assert "http" not in texts and "<img" not in texts and "logo" not in texts.lower()      # layout owns branding
    assert settings.EMAIL_FROM                                                              # provider config untouched
