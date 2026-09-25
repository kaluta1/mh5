"""Phase 4 final hardening: contact/inbox confirmation is NOT guardian authority
verification; ADMIN_DOCUMENT_REVIEW is the only configurable authority method;
fail-closed configuration; consent validity; log/token/PII privacy; retention.

All data is SYNTHETIC. No real email is sent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx
import pytest

from app.core.child_safety import GuardianConsentScope as S, GuardianVerificationMethod
from app.core.config import settings
from app.core.redaction import mask_email
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent
from app.models.guardian import GuardianConsent, GuardianRelationship, PendingRegistration
from app.services import email as email_module
from app.services import guardian_consent as gc
from app.services import teen_privacy
from app.services.age_policy_engine import utc_today
from tests.unit.test_guardian_consent import (  # noqa: F401
    PASSWORD,
    TOKEN_RE,
    accept_admin_review,
    admin_verify,
    approve,
    complete,
    consent_world,
    full_flow,
    outbox,
    start_pending,
    token_from,
)
from tests.unit.test_age_gate_registration import auth, make_user, register  # noqa: F401

VERIFY = "/api/v1/admin/age-safety/guardian-relationships/{}/verify"
BODY = {"method": "ADMIN_DOCUMENT_REVIEW", "note": "synthetic evidence reviewed out of band"}


def responded(client, register, outbox, db):
    _, token = start_pending(register, outbox)
    assert approve(client, token, (S.ACCOUNT_PARTICIPATION, S.NAME_DISPLAY)).json()["status"] == "VERIFICATION_REQUIRED"
    return db.query(GuardianRelationship).one(), db.query(PendingRegistration).one()


# 1-3 ------------------------------------------------------------------------

@pytest.mark.parametrize("config", ["", "EMAIL_LINK_CONFIRMATION", "EMAIL_LINK", "email_link_confirmation,bogus"])
def test_email_confirmation_is_not_authority_verification(consent_world, client, register, outbox, monkeypatch, config):
    db = consent_world
    monkeypatch.setattr(settings, "GUARDIAN_ACCEPTED_VERIFICATION_METHODS", config)
    assert gc.accepted_verification_methods() == frozenset()             # can never be enabled
    rel, pending = responded(client, register, outbox, db)
    assert gc.contact_confirmed(rel) is True                               # A. inbox control
    assert gc.authority_verified(rel) is False                             # B. not authority
    assert rel.verification_status == "VERIFICATION_REQUIRED" and rel.verification_method is None
    assert all(c.verification_method is None for c in db.query(GuardianConsent))
    check = gc.check_consent(db, scope=S.ACCOUNT_PARTICIPATION, at=datetime.utcnow() + timedelta(seconds=1),
                             pending_registration_id=pending.id)
    assert not check.valid and check.reason == "GUARDIAN_AUTHORITY_NOT_VERIFIED"
    assert pending.status == "AWAITING_GUARDIAN" and pending.completion_token_hash is None
    assert len(outbox) == 1                                                 # no completion email


def test_unconfigured_method_cannot_verify(consent_world, client, register, outbox):
    db = consent_world
    rel, _ = responded(client, register, outbox, db)
    admin = make_user(db, admin=True)
    r = client.post(VERIFY.format(rel.id), json=BODY, headers=auth(admin))
    assert r.status_code == 409
    r = client.post(VERIFY.format(rel.id), json={**BODY, "method": "EMAIL_LINK_CONFIRMATION"}, headers=auth(admin))
    assert r.status_code == 422                                             # not an authority method at all
    db.refresh(rel)
    assert rel.verification_status == "VERIFICATION_REQUIRED" and rel.verified_at is None


# 4-7 ------------------------------------------------------------------------

def test_admin_document_review_requires_admin(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    rel, _ = responded(client, register, outbox, db)
    member = make_user(db, dob="1980-01-01")
    assert client.post(VERIFY.format(rel.id), json=BODY).status_code == 401
    assert client.post(VERIFY.format(rel.id), json=BODY, headers=auth(member)).status_code == 403
    db.refresh(rel)
    assert rel.verification_status == "VERIFICATION_REQUIRED"


def test_admin_review_records_actor_method_time_audit_and_event(consent_world, client, register, outbox,
                                                                accept_admin_review):
    db = consent_world
    rel, _ = responded(client, register, outbox, db)
    admin = make_user(db, admin=True)
    before = datetime.utcnow()
    assert client.post(VERIFY.format(rel.id), json=BODY, headers=auth(admin)).json()["status"] == "APPROVED"
    db.refresh(rel)
    assert rel.verification_status == "VERIFIED" and rel.verification_method == "ADMIN_DOCUMENT_REVIEW"
    assert rel.verified_by_user_id == admin.id and rel.verified_at >= before
    assert all(c.verification_method == "ADMIN_DOCUMENT_REVIEW" for c in db.query(GuardianConsent))
    audit = db.query(AuditTrail).filter(AuditTrail.table_name == "guardian_relationships").one()
    assert audit.user_id == admin.id and audit.new_values["method"] == "ADMIN_DOCUMENT_REVIEW"
    assert audit.new_values["note"] == BODY["note"]
    assert db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == "GUARDIAN_VERIFIED").count() == 1


def test_nonexistent_relationship_cannot_be_verified(consent_world, client, accept_admin_review):
    admin = make_user(consent_world, admin=True)
    assert client.post(VERIFY.format(999999), json=BODY, headers=auth(admin)).status_code == 404


def test_invalid_state_transitions_rejected(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    admin = make_user(db, admin=True)
    start_pending(register, outbox)
    unresponded = db.query(GuardianRelationship).one()
    assert client.post(VERIFY.format(unresponded.id), json=BODY, headers=auth(admin)).status_code == 409  # PENDING
    rel = unresponded
    approve(client, token_from(outbox[-1]))
    assert client.post(VERIFY.format(rel.id), json=BODY, headers=auth(admin)).status_code == 200
    assert client.post(VERIFY.format(rel.id), json=BODY, headers=auth(admin)).status_code == 409          # duplicate
    assert client.post(f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/reject",
                       json={"note": "too late now"}, headers=auth(admin)).status_code == 409
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "guardian_relationships").count() == 1


def test_rejected_relationship_cannot_be_verified(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    rel, _ = responded(client, register, outbox, db)
    admin = make_user(db, admin=True)
    assert client.post(f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/reject",
                       json={"note": "evidence insufficient"}, headers=auth(admin)).status_code == 200
    assert client.post(VERIFY.format(rel.id), json=BODY, headers=auth(admin)).status_code == 409


# 8-11 -----------------------------------------------------------------------

def test_consent_requires_authority_method_and_matching_subject(consent_world, client, register, outbox,
                                                                accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.PUBLICITY))
    later = datetime.utcnow() + timedelta(seconds=1)
    assert gc.check_consent(db, scope=S.PUBLICITY, at=later, minor_user_id=minor.id).valid
    rel = db.query(GuardianRelationship).one()
    rel.verification_method = "EMAIL_LINK_CONFIRMATION"        # simulate a bad/legacy record
    db.commit()
    assert gc.check_consent(db, scope=S.PUBLICITY, at=later, minor_user_id=minor.id).reason == \
        "GUARDIAN_AUTHORITY_NOT_VERIFIED"
    rel.verification_method = "ADMIN_DOCUMENT_REVIEW"
    rel.minor_user_id = make_user(db, dob="2012-01-01").id        # relationship for someone else
    db.commit()
    assert gc.check_consent(db, scope=S.PUBLICITY, at=later, minor_user_id=minor.id).reason == "SUBJECT_MISMATCH"


def test_wrong_scope_withdrawn_and_expired_fail(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.MEDIA_USE, S.PUBLICITY))
    later = datetime.utcnow() + timedelta(seconds=1)
    assert not gc.check_consent(db, scope=S.PRIZE_ACCEPTANCE, at=later, minor_user_id=minor.id).valid
    media = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "MEDIA_USE").one()
    gc.withdraw_consent(db, media, actor_id=None, reason="withdrawn in test")
    assert gc.check_consent(db, scope=S.MEDIA_USE, at=datetime.utcnow() + timedelta(seconds=1),
                            minor_user_id=minor.id).reason == "WITHDRAWN"
    pub = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "PUBLICITY").one()
    pub.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert gc.check_consent(db, scope=S.PUBLICITY, at=datetime.utcnow(), minor_user_id=minor.id).reason == "EXPIRED"


# 12-13: logs ----------------------------------------------------------------

def test_real_email_path_masks_recipient_and_never_logs_tokens(consent_world, client, register, monkeypatch,
                                                               accept_admin_review, caplog):
    """Exercise the REAL EmailService.send_email (provider call stubbed) end to end."""
    db = consent_world
    sent = []
    monkeypatch.setattr(email_module.email_service, "api_key", "test-key-not-real")
    monkeypatch.setattr(email_module.resend.Emails, "send",
                        staticmethod(lambda params: sent.append(params) or {"id": "synthetic-id"}))
    caplog.set_level(logging.DEBUG)
    resp, body = register(date_of_birth="2012-06-01", guardian_email="parent.log@example.com")
    assert resp.status_code == 202
    gtoken = TOKEN_RE.search(sent[-1]["html"]).group(1)
    approve(client, gtoken)
    admin_verify(client, db)
    ctoken = TOKEN_RE.search(sent[-1]["html"]).group(1)
    assert complete(client, ctoken).status_code == 201
    logs = caplog.text
    for secret in (gtoken, ctoken, "parent.log@example.com", body["email"], PASSWORD, "2012-06-01"):
        assert secret not in logs
    assert mask_email("parent.log@example.com") in logs                 # the event is still logged (masked)


def test_email_failure_log_is_masked(monkeypatch, caplog):
    monkeypatch.setattr(email_module.email_service, "api_key", "test-key-not-real")

    def boom(params):
        raise RuntimeError(f"provider rejected {params['to'][0]}")

    monkeypatch.setattr(email_module.resend.Emails, "send", staticmethod(boom))
    caplog.set_level(logging.DEBUG)
    assert email_module.email_service.send_email("secret.person@example.com", "s", "<p>x</p>") is False
    assert "secret.person@example.com" not in caplog.text and "RuntimeError" in caplog.text


def test_fragment_tokens_are_never_sent_to_the_server():
    request = httpx.Request("GET", "https://kalutasociety.com/guardian/consent#token=abcdefghijklmnop")
    assert b"token" not in request.url.raw_path and "abcdefghijklmnop" not in str(request.headers)


# 14: PII exposure -------------------------------------------------------------

def test_pending_registration_pii_not_exposed(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    body, token = start_pending(register, outbox)
    admin = make_user(db, admin=True)
    responses = [
        client.post("/api/v1/guardian/requests/lookup", json={"token": token}),
        client.get("/api/v1/admin/age-safety/guardian-relationships?status=PENDING", headers=auth(admin)),
        client.get("/api/v1/admin/age-safety/minor-accounts", headers=auth(admin)),
    ]
    for r in responses:
        assert r.status_code == 200
        for leak in (body["email"], body["date_of_birth"], "parent.p4@example.com", "date_of_birth", "password"):
            assert leak not in r.text
    assert "password" not in PendingRegistration.__table__.columns.keys()


# 15: retention ----------------------------------------------------------------

def test_retention_keeps_history_and_skips_active_requests(consent_world, client, register, outbox,
                                                           accept_admin_review):
    db = consent_world
    full_flow(client, register, outbox, db)                                 # completed
    start_pending(register, outbox, ip="198.51.100.240", guardian="other.parent@example.com")   # active
    for p in db.query(PendingRegistration):
        p.updated_at = datetime.utcnow() - timedelta(days=40)
    db.commit()
    admin = make_user(db, admin=True)
    assert client.post("/api/v1/admin/age-safety/pending-registrations/expire-and-purge").status_code == 401
    result = client.post("/api/v1/admin/age-safety/pending-registrations/expire-and-purge", headers=auth(admin)).json()
    assert result == {"expired": 0, "purged": 1}
    active = db.query(PendingRegistration).filter(PendingRegistration.status == "AWAITING_GUARDIAN").one()
    assert active.email is not None and active.date_of_birth is not None      # active data untouched
    assert db.query(GuardianConsent).count() == 1 and db.query(GuardianRelationship).count() == 2


# 16: privacy floor --------------------------------------------------------------

def test_guardian_consent_cannot_weaken_privacy_floor(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=list(S))
    eff = teen_privacy.resolve_privacy(db, minor, on=utc_today())
    for f in ("public_date_of_birth", "exact_age_visible", "public_contact_information", "precise_location_visible",
              "location_sharing", "search_engine_indexing"):
        assert eff.settings[f] is False and f in eff.locked_fields
    r = client.put("/api/v1/users/me/privacy", json={"exact_age_visible": True},
                   headers=auth(minor))
    assert r.status_code == 422
    assert client.put("/api/v1/users/me/privacy", json={"name_display": True}, headers=auth(minor)).status_code == 422


def test_admin_document_review_is_not_described_as_legally_sufficient():
    doc = (GuardianVerificationMethod.__doc__ or "") + (gc.__doc__ or "")
    assert "stores no document" in doc or "no document is stored" in doc
    assert "not" in doc.lower() and "legally sufficient" in doc.lower()
