"""Kaluta KYC: session creation, the signed webhook and the status it sets.

Written against the provider's published contract (https://kalutakyc.com/docs):
POST /v1/sessions with X-API-Key; a webhook signed "t=<unix>,v1=<hmac>" over
"<t>.<raw body>", refused when older than five minutes; deliveries retried, so
handling is idempotent; a rejected member may retry inside the provider's
widget (a new session with the same external_id).

Every member, key, secret, session and document here is SYNTHETIC. No request
leaves the process: httpx network transports are replaced by a guard that
fails the test, and the provider is a fake at the HTTP boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

import httpx
import pytest

from app.core.config import settings
from app.crud import crud_kyc
from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, VerificationProvider
from app.models.payment import Deposit
from app.services import kaluta_kyc, kyc_settings
from app.services import kyc_provider_dispatch as dispatch
from tests.conftest import save_kaluta_settings
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_email3_kyc_contest import events, verification
from tests.unit.test_kyc_initiation_dispatch import ADDRESS, INITIATE, adult, kyc_paid, kyc_rows, no_real_network  # noqa: F401
from tests.unit.test_phase5_contest_eligibility import person

pytestmark = pytest.mark.unit

WEBHOOK = "/api/v1/kyc/webhook/kaluta"
SECRET = "whsec_synthetic_test_secret_0001"
KEY = "klt_test_synthetic_key_0001"
IDENTITY = {"first_name": "Jane", "last_name": "Doe", "date_of_birth": "1990-01-01", "nationality": "TZA",
            "document_type": "passport", "document_number": "P1234567", "document_expiry": "2031-01-01"}
PRIVATE = ("P1234567", "Jane", "Doe", "MRZ-RAW-LINE", "1990-01-01")


@pytest.fixture(autouse=True)
def provider(monkeypatch, db, kaluta_settings_key):
    """Kaluta switched on in Admin > KYC (the database) with a synthetic key and
    secret, for this test only."""
    svc = kaluta_kyc.kaluta_kyc_service
    monkeypatch.setattr(settings, "KYC_PROVIDER", "kaluta")
    save_kaluta_settings(db, enabled=True, api_key=KEY, webhook_secret=SECRET)
    kyc_settings.apply(db)
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    return svc


def signed(body: bytes, *, secret: str = SECRET, at: float | None = None) -> dict:
    ts = str(int(time.time() if at is None else at))
    v1 = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Kaluta-Signature": f"t={ts},v1={v1}", "Content-Type": "application/json"}


def deliver(client, payload, **kwargs):
    body = json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers=signed(body, **kwargs))


def open_verification(db, user, *, session="sess-1", status=KYCStatus.IN_PROGRESS) -> KYCVerification:
    v = verification(db, user, status=status)
    v.external_verification_id = session
    v.verification_url = f"https://kalutakyc.com/verify/{session}"
    v.expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()
    return v


def event(name, v, *, session="sess-1", **fields) -> dict:
    return {"event": name, "timestamp": "2026-10-13T12:00:00Z",
            "session": {"id": session, "external_id": v.reference_id, **fields}}


def approved(v, **fields) -> dict:
    return event("session.approved", v, status="approved", identity=IDENTITY, overall_score=87,
                 scores={"document": 92, "face": 88, "liveness": None, "poa": None},
                 checks_required={"liveness": False, "proof_of_address": False},
                 ai_extraction={"mrz": "MRZ-RAW-LINE", "tampering_signs": []}, attempt_count=1, **fields)


def rejected(v, **fields) -> dict:
    return event("session.rejected", v, status="rejected", rejection_reason="Face does not match the document",
                 scores={"document": 80, "face": 20}, **fields)


def audit(db, v) -> list:
    db.expire_all()
    return [(a.action, a.details.split(":")[0], a.old_status, a.new_status)
            for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == v.id).order_by(KYCAuditLog.id)]


def audit_details(db, v) -> list:
    db.expire_all()
    return [a.details for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == v.id).order_by(KYCAuditLog.id)]


def money(db) -> tuple:
    return db.query(Deposit).count(), db.query(JournalEntry).count(), db.query(AffiliateCommission).count()


# ===========================================================================
# 1. The signature
# ===========================================================================

def test_only_a_delivery_signed_with_the_secret_and_recent_is_accepted(provider):
    body = b'{"event":"session.approved"}'
    good = signed(body)["X-Kaluta-Signature"]
    assert provider.verify_webhook_signature(body, good) is True
    ts, v1 = (part.split("=", 1)[1] for part in good.split(","))
    refused = {
        "no header": "",
        "another secret": signed(body, secret="whsec_other")["X-Kaluta-Signature"],
        "body changed": good,                                                    # checked against other bytes below
        "older than five minutes": signed(body, at=time.time() - 301)["X-Kaluta-Signature"],
        "far in the future": signed(body, at=time.time() + 3600)["X-Kaluta-Signature"],
        "no timestamp": f"v1={v1}",
        "no signature": f"t={ts}",
        "timestamp not a number": f"t=abc,v1={v1}",
        "signature of the body alone": f"t={ts},v1={hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()}",
        "upper case digest": f"t={ts},v1={v1.upper()}",
        "not ascii": f"t={ts},v1=éé",
        "huge header": "t=1," + "v1=a" * 400,
    }
    for name, header in refused.items():
        payload = b'{"event":"session.rejected"}' if name == "body changed" else body
        assert provider.verify_webhook_signature(payload, header) is False, name
    assert provider.verify_webhook_signature(body, signed(body, at=time.time() - 299)["X-Kaluta-Signature"]) is True


def test_the_timestamp_is_the_real_epoch_whatever_the_servers_time_zone(provider, monkeypatch):
    """The earlier check read a UTC wall clock as local time: on a server whose
    zone is not UTC every genuine delivery looked hours old and was refused."""
    body = b"{}"
    header = signed(body)["X-Kaluta-Signature"]
    for offset_hours in (-8, 0, 3, 6):

        class Shifted(datetime):
            @classmethod
            def utcnow(cls):
                return datetime.utcfromtimestamp(time.time())

            def timestamp(self):                       # what a naive utcnow().timestamp() gives in this zone
                return super().timestamp() - offset_hours * 3600

        monkeypatch.setattr(kaluta_kyc, "datetime", Shifted)
        assert provider.verify_webhook_signature(body, header) is True, offset_hours


def test_without_a_secret_nothing_is_accepted_in_production(provider, monkeypatch):
    monkeypatch.setattr(provider, "webhook_secret", "")
    monkeypatch.setenv("ENVIRONMENT", "production")
    body = b"{}"
    assert provider.verify_webhook_signature(body, signed(body, secret="")["X-Kaluta-Signature"]) is False
    monkeypatch.setattr(provider, "webhook_secret", SECRET)
    monkeypatch.setattr(provider, "enabled", False)
    assert provider.verify_webhook_signature(body, signed(body)["X-Kaluta-Signature"]) is False


# ===========================================================================
# 2. Requests that are not allowed
# ===========================================================================

def test_an_unsigned_or_wrongly_signed_delivery_changes_nothing(client, db):
    v = open_verification(db, person(db, 30))
    body = json.dumps(approved(v)).encode()
    attempts = [
        client.post(WEBHOOK, content=body),                                                   # no signature
        client.post(WEBHOOK, content=body, headers=signed(body, secret="whsec_attacker")),    # another secret
        client.post(WEBHOOK, content=body, headers=signed(body, at=time.time() - 3600)),      # a replay
        client.post(WEBHOOK, content=body.replace(b"approved", b"APPROVED"), headers=signed(body)),   # body changed
        client.post(WEBHOOK, content=body, headers={"X-Kaluta-Signature": "t=1,v1=deadbeef"}),
    ]
    assert [r.status_code for r in attempts] == [401] * 5
    assert all(SECRET not in r.text and KEY not in r.text for r in attempts)
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.IN_PROGRESS and not row.identity_verified and row.webhook_data is None
    assert audit(db, v) == []


def test_a_signed_delivery_that_is_not_a_json_object_is_refused(client, db):
    for body in (b"not json", b"[1, 2]", b'"text"', b"\xff\xfe"):
        assert client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 400
    big = b'{"event":"session.created","pad":"' + b"x" * (kaluta_kyc.WEBHOOK_MAX_BODY_BYTES + 10) + b'"}'
    assert client.post(WEBHOOK, content=big, headers=signed(big)).status_code in (401, 413)


def test_the_integration_switched_off_accepts_nothing(client, db, monkeypatch):
    v = open_verification(db, person(db, 30))
    save_kaluta_settings(db, enabled=False, api_key=KEY, webhook_secret=SECRET)
    assert deliver(client, approved(v)).status_code == 503
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.IN_PROGRESS


def test_starting_and_reading_a_verification_needs_a_signed_in_member(client, db):
    assert client.post(INITIATE, json=ADDRESS).status_code == 401
    assert client.post(INITIATE, json=ADDRESS, headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    assert client.get("/api/v1/kyc/status-detailed").status_code == 401
    assert client.get("/api/v1/kyc/deployment/kaluta-urls", headers=auth(person(db, 30))).status_code == 403
    assert client.get("/api/v1/kyc/admin/verifications", headers=auth(person(db, 30))).status_code == 403
    # One member never reads another member's verification.
    owner, other = person(db, 30), person(db, 30)
    v = open_verification(db, owner)
    assert client.get(f"/api/v1/kyc/verification/{v.id}", headers=auth(other)).status_code in (403, 404)


# ===========================================================================
# 3. Approval, rejection, expiry
# ===========================================================================

def test_an_approval_is_applied_once_and_only_what_is_needed_is_kept(client, db, email_outbox):
    user = person(db, 30)
    v = open_verification(db, user)
    before = money(db)

    first = deliver(client, approved(v))
    assert first.status_code == 200 and first.json() == {"ok": True, "result": "applied"}
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS            # identity accepted; the existing next step
    assert (row.identity_verified, row.document_verified, row.face_verified, row.address_verified) == (True, True, True, False)
    assert (row.verified_first_name, row.verified_last_name, row.verified_nationality) == ("Jane", "Doe", "TZA")
    assert row.verified_date_of_birth == datetime(1990, 1, 1)
    assert (row.identity_confidence_score, row.document_confidence_score, row.face_match_score) == (87, 92, 88)
    assert row.external_verification_id == "sess-1"
    # The raw model output is not stored; the decision and the scores are.
    assert "MRZ-RAW-LINE" not in (row.provider_response or "") + (row.webhook_data or "")
    assert json.loads(row.provider_response)["scores"]["face"] == 88
    assert events(db) == ["KYC.ACTION_REQUIRED"]

    # The provider delivers it again (it retries), and its alias event arrives as well.
    again = deliver(client, approved(v))
    alias = deliver(client, {**approved(v), "event": "session.verified"})
    assert [again.json()["result"], alias.json()["result"]] == ["duplicate", "duplicate"]
    assert events(db) == ["KYC.ACTION_REQUIRED"]                       # one email, not three
    assert money(db) == before                                          # no payment, ledger or commission row
    trail = audit(db, v)
    assert [t[0] for t in trail].count("kaluta_webhook:session.approved") == 2
    assert ("kaluta_webhook:session.approved", "applied", "in_progress", "pending_proof_of_address") in trail
    assert ("kaluta_webhook:session.verified", "duplicate", "pending_proof_of_address", "pending_proof_of_address") in trail
    # The trail says what happened, never who the person is.
    text = " ".join(a.details for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == v.id))
    assert not any(secret in text for secret in PRIVATE) and "Face does not match" not in text
    assert not any(secret in first.text + again.text for secret in PRIVATE)


def test_a_rejection_is_applied_once_and_can_only_be_followed_by_a_paid_new_attempt(client, db, email_outbox):
    user = person(db, 30)
    v = open_verification(db, user)
    assert deliver(client, rejected(v)).json()["result"] == "applied"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.REJECTED and not row.identity_verified
    assert row.rejection_reason == "Face does not match the document"          # kept for the administrator
    assert row.rejection_details == f"{kaluta_kyc.PROVIDER_REJECTION_MARK}sess-1"
    assert events(db) == ["KYC.REJECTED"]
    assert deliver(client, rejected(v)).json()["result"] == "duplicate"
    assert events(db) == ["KYC.REJECTED"]
    # The existing rule is unchanged: starting again needs a new payment.
    refused = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert refused.status_code == 402


def test_an_expired_session_ends_the_session_and_keeps_the_attempt_open(client, db, email_outbox):
    v = open_verification(db, person(db, 30))
    attempts = v.attempts_count
    assert deliver(client, event("session.expired", v, status="expired")).json()["result"] == "applied"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    # The provider's session ran out; the member's attempt (and its payment) did not.
    assert row.status == KYCStatus.IN_PROGRESS and row.attempts_count == attempts
    assert row.expires_at <= datetime.utcnow() and row.rejection_reason is None
    assert deliver(client, event("session.expired", v, status="expired")).json()["result"] == "duplicate"
    assert events(db) == []                                             # an expiry sends no email (as before)
    assert "the attempt stays open" in audit_details(db, v)[-2]

    # Not after a decision, and not for an older session of the same reference.
    done = open_verification(db, person(db, 30))
    deliver(client, approved(done))
    assert deliver(client, event("session.expired", done, status="expired")).json()["result"] == "ignored"
    current = open_verification(db, person(db, 30), session="sess-new")
    assert deliver(client, event("session.expired", current, session="sess-old")).json()["result"] == "ignored"
    db.expire_all()
    assert db.get(KYCVerification, done.id).status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert db.get(KYCVerification, current.id).status == KYCStatus.IN_PROGRESS


# ===========================================================================
# 4. Order, duplicates and events that are not ours
# ===========================================================================

def test_progress_events_never_change_or_overwrite_a_decision(client, db):
    v = open_verification(db, person(db, 30))
    for name in ("session.created", "session.document_submitted", "session.face_submitted"):
        assert deliver(client, event(name, v, status=name.split(".")[1])).json()["result"] == "applied"
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.IN_PROGRESS
    deliver(client, approved(v))
    decided = db.get(KYCVerification, v.id).webhook_data
    # A progress event delivered late (the provider retries with a delay).
    assert deliver(client, event("session.face_submitted", v, status="face_submitted")).json()["result"] == "ignored"
    assert deliver(client, rejected(v)).json()["result"] == "ignored"                 # a stale rejection
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.webhook_data == decided and row.identity_verified


def test_an_event_whose_name_and_status_disagree_decides_nothing(client, db):
    v = open_verification(db, person(db, 30))
    assert deliver(client, {**approved(v), "session": {**approved(v)["session"], "status": "rejected"}}).json()["result"] == "ignored"
    assert deliver(client, {**rejected(v), "session": {**rejected(v)["session"], "status": "approved"}}).json()["result"] == "ignored"
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.IN_PROGRESS


def test_events_for_another_reference_member_or_provider_are_acknowledged_and_change_nothing(client, db):
    user = person(db, 30)
    v = open_verification(db, user)
    # A reference this server does not know (an earlier cycle, or not ours): acknowledged, so it is not retried.
    stranger = {"event": "session.approved", "session": {"id": "sess-x", "external_id": "mh5_999_unknown", "status": "approved"}}
    answer = deliver(client, stranger)
    assert answer.status_code == 200 and answer.json()["result"] == "unknown"
    # The right session id but the reference of an earlier cycle.
    assert deliver(client, {**approved(v), "session": {**approved(v)["session"], "external_id": "mh5_old_reference"}}
                   ).json()["result"] == "ignored"
    # Bound to another member.
    assert deliver(client, {**approved(v), "session": {**approved(v)["session"], "metadata": {"user_id": user.id + 1}}}
                   ).json()["result"] == "unknown"
    # A verification that belongs to the other provider.
    legacy = open_verification(db, person(db, 30), session="sess-legacy")
    legacy.provider = VerificationProvider.SHUFTI_PRO
    db.commit()
    assert deliver(client, approved(legacy, session="sess-legacy")).json()["result"] == "ignored"
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.IN_PROGRESS
    assert db.get(KYCVerification, legacy.id).status == KYCStatus.IN_PROGRESS
    assert not db.get(KYCVerification, v.id).identity_verified


# ===========================================================================
# 5. Retries
# ===========================================================================

def test_the_providers_own_retry_after_its_rejection_is_honoured(client, db, email_outbox):
    """The provider lets a rejected member retry in its widget: a NEW session
    with the SAME external_id. Its approval is the same person passing."""
    user = person(db, 30)
    v = open_verification(db, user)
    deliver(client, rejected(v))
    retry = approved(v, session="sess-2", metadata={"_retry_index": 1})
    answer = deliver(client, retry)
    assert answer.json()["result"] == "applied"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.identity_verified
    assert row.external_verification_id == "sess-2" and row.rejection_reason is None and row.rejection_details is None
    assert row.attempts_count == 1                                       # the same paid attempt
    assert events(db) == ["KYC.REJECTED", "KYC.ACTION_REQUIRED"]
    last = db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == v.id).order_by(KYCAuditLog.id.desc()).first()
    assert "after a provider retry" in last.details and "provider retry 1" in last.details


def test_a_provider_approval_never_overturns_an_administrators_rejection(client, db):
    admin = person(db, 40, admin=True)
    for status in (KYCStatus.IN_PROGRESS,):
        v = open_verification(db, person(db, 30), status=status)
        deliver(client, rejected(v))                                      # the provider rejected first ...
        assert client.post(f"/api/v1/kyc/admin/verification/{v.id}/reject", headers=auth(admin),
                           data={"reason": "Document belongs to somebody else"}).status_code in (200, 400)
    # ... and an administrator rejected an open one directly.
    direct = open_verification(db, person(db, 30), session="sess-9")
    assert client.post(f"/api/v1/kyc/admin/verification/{direct.id}/reject", headers=auth(admin),
                       data={"reason": "Document belongs to somebody else"}).status_code == 200
    db.expire_all()
    assert db.get(KYCVerification, direct.id).status == KYCStatus.REJECTED
    assert not str(db.get(KYCVerification, direct.id).rejection_details or "").startswith(kaluta_kyc.PROVIDER_REJECTION_MARK)
    assert deliver(client, approved(direct, session="sess-10")).json()["result"] == "ignored"
    db.expire_all()
    row = db.get(KYCVerification, direct.id)
    assert row.status == KYCStatus.REJECTED and not row.identity_verified
    # Nor an expired or a reviewed one.
    for closed in (KYCStatus.EXPIRED, KYCStatus.REQUIRES_REVIEW):
        other = open_verification(db, person(db, 30), status=closed)
        assert deliver(client, approved(other)).json()["result"] == "ignored"
        db.expire_all()
        assert db.get(KYCVerification, other.id).status == closed


def test_a_status_poll_and_a_webhook_reach_one_decision(db, monkeypatch, email_outbox):
    import asyncio

    user = person(db, 30)
    v = open_verification(db, user)
    session = approved(v)["session"]

    async def provider_says(_verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": True, "data": dict(session)}

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "check_reference_validity", provider_says)
    first = asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=v))
    assert first == {"status": "pending_proof_of_address", "kyc_step": 2, "needs_proof_of_address": True}
    db.refresh(v)
    assert v.external_verification_id == "sess-1"                       # the provider's session id, not our reference
    assert "MRZ-RAW-LINE" not in (v.provider_response or "")
    # The webhook for the same decision arrives after the poll.
    assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=approved(v)) == dispatch.DUPLICATE
    assert asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=v)) is None
    assert events(db) == ["KYC.ACTION_REQUIRED"]

    # A poll that reports a rejection marks it as the provider's.
    other = open_verification(db, person(db, 30), session="sess-7")

    async def provider_rejects(_verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": False,
                "data": {"id": "sess-7", "status": "rejected", "rejection_reason": "Blurry document"}}

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "check_reference_validity", provider_rejects)
    assert asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=other)) == {"status": "rejected"}
    db.refresh(other)
    assert other.status == KYCStatus.REJECTED and other.rejection_details == f"{kaluta_kyc.PROVIDER_REJECTION_MARK}sess-7"


# ===========================================================================
# 6. Creating the session
# ===========================================================================

class FakeProvider:
    """The provider at the HTTP boundary: records what was sent, answers as told."""

    def __init__(self, monkeypatch, *, status=200, body=None, error=None):
        self.requests, self.status, self.body, self.error = [], status, body, error
        outer = self

        async def post(_client, url, **kwargs):
            outer.requests.append({"url": url, "headers": dict(kwargs.get("headers") or {}), "json": kwargs.get("json")})
            if outer.error is not None:
                raise outer.error
            number = len(outer.requests)
            answer = outer.body if outer.body is not None else {
                "session_id": f"sess-{number}", "verification_url": f"https://kalutakyc.com/verify/sess-{number}",
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")}
            return httpx.Response(outer.status, json=answer, request=httpx.Request("POST", url))

        async def get(_client, url, **kwargs):
            outer.requests.append({"url": url, "headers": dict(kwargs.get("headers") or {}), "json": None})
            return httpx.Response(401, json={"detail": "Invalid API key"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", post)
        monkeypatch.setattr(httpx.AsyncClient, "get", get)


def test_a_session_is_created_server_side_with_the_key_and_the_key_never_leaves_the_server(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    answer = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert (body["verification_url"], body["provider"], body["status"]) == ("https://kalutakyc.com/verify/sess-1", "kaluta", "new")
    sent = fake.requests[0]
    assert sent["url"] == "https://kalutakyc.com/v1/sessions" and sent["headers"]["X-API-Key"] == KEY
    assert sent["json"]["external_id"] == body["reference"] and sent["json"]["metadata"]["user_id"] == user.id
    assert sent["json"]["webhook_url"].endswith("/api/v1/kyc/webhook/kaluta")
    assert sent["json"]["redirect_url"].endswith("/dashboard/kyc")
    assert KEY not in answer.text and SECRET not in answer.text and "api_key" not in answer.text.lower()
    row = kyc_rows(db, user)[0]
    assert row.status == KYCStatus.IN_PROGRESS and row.external_verification_id == "sess-1"
    assert row.expires_at is not None and timedelta(hours=23) < row.expires_at - datetime.utcnow() <= timedelta(hours=24)
    assert row.reference_id.startswith(f"mh5_{user.id}_") and len(row.reference_id.rsplit("_", 1)[1]) == 16
    created = [a for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == row.id) if a.action == "kaluta_session_created"]
    assert len(created) == 1 and created[0].performed_by_user_id == user.id and KEY not in created[0].details

    # Asked again while the session is open: the same session, no second provider call, payment or attempt.
    again = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert again.status_code == 200 and again.json()["reused"] is True and again.json()["verification_url"] == body["verification_url"]
    assert [r["url"] for r in fake.requests].count("https://kalutakyc.com/v1/sessions") == 1
    assert len(kyc_rows(db, user)) == 1 and kyc_rows(db, user)[0].attempts_count == 1
    # The webhook for that session completes the loop.
    assert deliver(client, approved(row, session="sess-1")).json()["result"] == "applied"


@pytest.mark.parametrize("status, body", [(401, {"detail": "Invalid API key"}),
                                          (402, {"detail": "Insufficient balance. Top up to continue."}),
                                          (429, {"detail": "Rate limited"}), (500, {"detail": "boom"}),
                                          (200, {"unexpected": True}), (200, ["not", "an", "object"]),
                                          (200, {"session_id": "s1", "verification_url": "https://evil.example/verify/s1"}),
                                          (200, {"session_id": "s1", "verification_url": "http://kalutakyc.com/verify/s1"}),
                                          (200, {"session_id": "s1", "verification_url": "javascript:alert(1)"})])
def test_a_provider_that_cannot_be_used_is_reported_as_unavailable_and_nothing_of_its_answer_is_shown(
        client, db, monkeypatch, status, body):
    FakeProvider(monkeypatch, status=status, body=body)
    user = adult(db)
    kyc_paid(db, user)
    answer = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert answer.status_code == 503
    assert kaluta_kyc.UNAVAILABLE_MESSAGE in answer.text
    for leak in ("balance", "Invalid API key", "Rate limited", "boom", "evil.example", "javascript", KEY):
        assert leak not in answer.text
    row = kyc_rows(db, user)[0]
    assert row.status == KYCStatus.PENDING and row.verification_url is None and not row.identity_verified
    # The same paid attempt is started again later, without a second payment.
    FakeProvider(monkeypatch)
    later = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert later.status_code == 200 and later.json()["status"] == "new"
    assert kyc_rows(db, user)[0].attempts_count == 1 and len(kyc_rows(db, user)) == 1


def test_a_network_failure_is_not_retried_automatically(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch, error=httpx.ReadTimeout("synthetic timeout"))
    user = adult(db)
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 503
    assert len(fake.requests) == 1                                       # a second call could open a second session


def created(reference, user_id, *, session="sess-late", **fields) -> dict:
    return {"event": "session.created", "timestamp": "2026-10-13T12:00:00Z",
            "session": {"id": session, "external_id": reference, "status": "created",
                        "metadata": {"user_id": user_id}, **fields}}


def timed_out_start(client, db, monkeypatch, user):
    """The provider opened the session but answered after our read timeout."""
    import main

    monkeypatch.setattr(main, "IS_PRODUCTION", True)
    fake = FakeProvider(monkeypatch, error=httpx.ReadTimeout("synthetic timeout"))
    deposits = db.query(Deposit).count()
    answer = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert answer.status_code == 503
    assert answer.json()["detail"] == {"code": "KYC_PROVIDER_UNAVAILABLE", "message": kaluta_kyc.UNAVAILABLE_MESSAGE}
    assert "Internal server error" not in answer.text
    row = kyc_rows(db, user)[0]
    assert row.status == KYCStatus.PENDING and row.verification_url is None and row.attempt_sessions_count == 1
    assert db.query(Deposit).count() == deposits                       # nothing charged again
    return fake, row


def test_a_session_opened_after_a_timeout_is_adopted_from_its_creation_event(client, db, monkeypatch):
    user = adult(db)
    kyc_paid(db, user)
    fake, row = timed_out_start(client, db, monkeypatch, user)
    expires = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert deliver(client, created(row.reference_id, user.id, expires_at=expires)).json()["result"] == "applied"
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.status, row.external_verification_id, row.verification_url) == (
        KYCStatus.IN_PROGRESS, "sess-late", "https://kalutakyc.com/verify/sess-late")
    assert row.expires_at is not None and row.residential_address_locked_at is not None
    assert any("session adopted" in d for d in audit_details(db, row))
    # A second delivery of the same event changes nothing.
    assert deliver(client, created(row.reference_id, user.id)).json()["result"] == "applied"
    db.expire_all()
    assert kyc_rows(db, user)[0].expires_at == row.expires_at

    # Starting again hands out that session: no second provider call, session or payment.
    again = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert again.status_code == 200 and again.json()["reused"] is True
    assert again.json()["verification_url"] == "https://kalutakyc.com/verify/sess-late"
    assert [r["url"] for r in fake.requests].count("https://kalutakyc.com/v1/sessions") == 1
    row = kyc_rows(db, user)[0]
    assert row.attempt_sessions_count == 1 and row.attempts_count == 1 and len(kyc_rows(db, user)) == 1
    assert deliver(client, approved(row, session="sess-late")).json()["result"] == "applied"


def test_a_provider_link_in_the_creation_event_is_kept_only_when_it_is_the_providers_own(client, db, monkeypatch):
    user = adult(db)
    kyc_paid(db, user)
    _, row = timed_out_start(client, db, monkeypatch, user)
    event_ = created(row.reference_id, user.id, verification_url="https://evil.example/verify/sess-late")
    assert deliver(client, event_).json()["result"] == "applied"
    db.expire_all()
    assert kyc_rows(db, user)[0].verification_url == "https://kalutakyc.com/verify/sess-late"


@pytest.mark.parametrize("change", ["no_member", "other_member", "old_reference", "no_session_id", "unsafe_session_id",
                                    "ended_status"])
def test_a_creation_event_that_cannot_be_proved_ours_adopts_nothing(client, db, monkeypatch, change):
    user = adult(db)
    kyc_paid(db, user)
    _, row = timed_out_start(client, db, monkeypatch, user)
    event_ = created(row.reference_id, user.id)
    if change == "no_member":
        event_["session"].pop("metadata")
    elif change == "other_member":
        event_["session"]["metadata"] = {"user_id": user.id + 1}
    elif change == "old_reference":
        event_["session"]["external_id"] = "mh5_old_reference"
    elif change == "no_session_id":
        event_["session"].pop("id")
    elif change == "unsafe_session_id":
        event_["session"]["id"] = "../../evil?x=1"
    else:
        event_["session"]["status"] = "expired"
    deliver(client, event_)
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert row.status == KYCStatus.PENDING and row.verification_url is None
    assert row.external_verification_id in (None, "")


def test_a_creation_event_never_replaces_a_saved_session_or_reopens_a_decision(client, db):
    user = person(db, 30)
    v = open_verification(db, user, session="sess-1")
    other = created(v.reference_id, user.id, session="sess-other")
    assert deliver(client, other).json()["result"] == "applied"           # noted as progress only
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert (row.external_verification_id, row.verification_url) == ("sess-1", "https://kalutakyc.com/verify/sess-1")

    row.verification_url = None
    row.status = KYCStatus.REJECTED
    db.commit()
    assert deliver(client, other).json()["result"] == "ignored"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.REJECTED and row.verification_url is None


def test_a_creation_event_without_a_valid_recent_signature_adopts_nothing(client, db, monkeypatch):
    user = adult(db)
    kyc_paid(db, user)
    _, row = timed_out_start(client, db, monkeypatch, user)
    body = json.dumps(created(row.reference_id, user.id)).encode()
    assert client.post(WEBHOOK, content=body, headers=signed(body, secret="whsec_wrong")).status_code == 401
    assert client.post(WEBHOOK, content=body, headers=signed(body, at=time.time() - 600)).status_code == 401  # replay
    assert client.post(WEBHOOK, content=body, headers={"Content-Type": "application/json"}).status_code == 401
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert row.status == KYCStatus.PENDING and row.verification_url is None and not row.external_verification_id


def provider_that_sends_the_creation_event_first(monkeypatch, db, user, *, then):
    """The provider's creation event reaches us while our request is still waiting for its answer."""
    calls = []

    async def post(_client, url, **kwargs):
        calls.append(url)
        reference = kwargs["json"]["external_id"]
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=created(reference, user.id)) == "applied"
        if then == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(200, json={"session_id": "sess-late", "verification_url": "https://kalutakyc.com/verify/sess-late",
                                         "expires_at": (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                              request=httpx.Request("POST", url))

    async def get(_client, url, **kwargs):
        return httpx.Response(401, json={"detail": "Invalid API key"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    return calls


@pytest.mark.parametrize("then", ["answer", "timeout"])
def test_a_creation_event_arriving_during_the_start_leaves_one_session(client, db, monkeypatch, then):
    user = adult(db)
    kyc_paid(db, user)
    calls = provider_that_sends_the_creation_event_first(monkeypatch, db, user, then=then)
    answer = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert answer.status_code == (200 if then == "answer" else 503), answer.text
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.status, row.external_verification_id, row.verification_url) == (
        KYCStatus.IN_PROGRESS, "sess-late", "https://kalutakyc.com/verify/sess-late")
    assert row.attempt_sessions_count == 1 and row.attempts_count == 1
    again = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert again.status_code == 200 and again.json()["reused"] is True and len(calls) == 1
    used = db.query(Deposit).filter(Deposit.user_id == user.id, Deposit.is_used.is_(True)).count()
    assert used == 1 and db.query(Deposit).filter(Deposit.user_id == user.id).count() == 1


def test_a_session_saved_while_a_start_waits_for_the_lock_is_handed_out_not_replaced(client, db, monkeypatch):
    """Between the unlocked look at the session and the member's lock, the
    creation event (or a request at the same time) saved a session."""
    from app.api.api_v1.endpoints import kyc as kyc_endpoint

    user = adult(db)
    kyc_paid(db, user)
    fake, row = timed_out_start(client, db, monkeypatch, user)
    reference = row.reference_id

    async def meanwhile(_verification):
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=created(reference, user.id)) == "applied"
        return {"is_valid": False, "is_completed": False}

    monkeypatch.setattr(kyc_endpoint, "check_kyc_session_validity", meanwhile)
    answer = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert answer.status_code == 200 and answer.json()["reused"] is True
    assert answer.json()["verification_url"] == "https://kalutakyc.com/verify/sess-late"
    assert len(fake.requests) == 1
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert row.reference_id == reference and row.attempt_sessions_count == 1


def test_a_session_the_provider_no_longer_accepts_is_replaced_within_the_session_limit(client, db, monkeypatch):
    from app.api.api_v1.endpoints import kyc as kyc_endpoint

    fake = FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(user)).json()

    async def no_longer_valid(_verification):
        return {"is_valid": False, "is_completed": False}

    monkeypatch.setattr(kyc_endpoint, "check_kyc_session_validity", no_longer_valid)
    fresh = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert fresh.status_code == 200 and fresh.json()["status"] == "new"
    assert fresh.json()["verification_url"] != first["verification_url"] and len(fake.requests) == 2
    assert kyc_rows(db, user)[0].attempt_sessions_count == 2


def test_a_session_that_ran_out_is_replaced_within_the_same_paid_attempt(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(user)).json()
    row = kyc_rows(db, user)[0]
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)            # 24 hours later
    db.commit()

    state = client.get("/api/v1/kyc/status-detailed", headers=auth(user)).json()
    assert state["session_expired"] is True and state["verification_url"] is None and state["can_continue"] is True
    fresh = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert fresh.status_code == 200 and fresh.json()["status"] == "new"
    assert fresh.json()["verification_url"] != first["verification_url"] and fresh.json()["reference"] != first["reference"]
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert row.attempts_count == 1 and len(kyc_rows(db, user)) == 1      # no new attempt, no new payment
    assert row.expires_at > datetime.utcnow()
    assert [r["url"] for r in fake.requests].count("https://kalutakyc.com/v1/sessions") == 2
    # The old session's events name the old reference: they no longer reach this verification.
    old = {"event": "session.expired", "session": {"id": "sess-1", "external_id": first["reference"], "status": "expired"}}
    assert deliver(client, old).json()["result"] in ("unknown", "ignored")
    db.expire_all()
    assert kyc_rows(db, user)[0].status == KYCStatus.IN_PROGRESS


def test_a_status_read_the_provider_refuses_changes_nothing(client, db, monkeypatch):
    """Whether the session can be read back with the API key is not stated in the
    provider's documentation. If it is refused, the webhook still decides."""
    FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    state = client.get("/api/v1/kyc/status-detailed", headers=auth(user))
    assert state.status_code == 200 and state.json()["status"] == "in_progress" and state.json()["can_continue"] is True
    assert kyc_rows(db, user)[0].status == KYCStatus.IN_PROGRESS


def test_only_the_providers_own_https_page_is_a_verification_url():
    ok = kaluta_kyc.is_provider_verification_url
    assert ok("https://kalutakyc.com/verify/abc123") is True
    for bad in ("http://kalutakyc.com/verify/a", "https://kalutakyc.com.evil.example/verify/a", "https://evil.example/kalutakyc.com",
                "https://user@evil.example/verify/a", "javascript:alert(1)", "//kalutakyc.com/verify/a", "", None,
                "https://sub.kalutakyc.com/verify/a"):
        assert ok(bad) is False, bad


def test_provider_times_are_stored_as_utc():
    parse = kaluta_kyc.parse_provider_time
    assert parse("2026-06-02T00:00:00Z") == datetime(2026, 6, 2)
    assert parse("2026-06-02T03:00:00+03:00") == datetime(2026, 6, 2)
    assert parse("1990-01-01") == datetime(1990, 1, 1)
    assert parse("") is None and parse(None) is None and parse("yesterday") is None and parse(12345) is None


def test_this_change_touches_no_payment_ledger_commission_or_contest_code():
    from pathlib import Path

    app = Path(kaluta_kyc.__file__).resolve().parents[1]
    for name in ("services/kaluta_kyc.py", "services/kyc_provider_dispatch.py"):
        source = (app / name).read_text(encoding="utf-8")
        for forbidden in ("JournalEntry", "AffiliateCommission", "Deposit(", "cashout", "nowpayments", "contest", "vote"):
            assert forbidden not in source, f"{name} mentions {forbidden}"
