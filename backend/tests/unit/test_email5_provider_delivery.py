"""EMAIL-5: provider delivery webhooks and provider-side send idempotency.

Signatures are produced with the same algorithm the provider uses (the Svix
scheme implemented by the installed Resend SDK), from a SYNTHETIC signing
secret. No request leaves the process; emails go to the in-memory
FakeEmailProvider, which behaves like the provider for idempotency keys.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET, AuthToken
from app.models.email import EmailDelivery, EmailWebhookEvent
from app.models.kyc import KYCVerification
from app.models.user import User
from app.services import auth_tokens, email_providers, email_webhooks
from app.services import email_outbox as outbox_module
from app.services import email_settings_service as svc
from app.services.email import email_service
from app.services.email_events import EMAIL_EVENTS, EmailEvent
from app.services.email_outbox import STALE_PROCESSING_AFTER, claim_batch, process_outbox, provider_idempotency_key
from app.services.email_providers import (
    FAIL_CONFLICT, FAIL_NETWORK, EmailMessage, FakeEmailProvider, ProviderResult, WebhookVerificationError,
    classify_http_status, verify_resend_webhook,
)
from tests.unit.test_email2_auth_security import A, PW, PW2, body, link_token, login, member  # noqa: F401
from tests.unit.test_email2_auth_security import ip  # noqa: F401  (fixture)

APP = Path(__file__).resolve().parents[2] / "app"
URL = "/api/v1/webhooks/resend"
SECRET = "whsec_" + base64.b64encode(b"synthetic-webhook-signing-secret-0001").decode()
OTHER_SECRET = "whsec_" + base64.b64encode(b"another-synthetic-signing-secret-2").decode()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", SECRET)


def sign(raw: bytes, *, event_id: str, timestamp: int, secret: str = SECRET) -> str:
    key = base64.b64decode(secret[len("whsec_"):])
    digest = hmac.new(key, f"{event_id}.{timestamp}.".encode() + raw, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def event(kind: str, message_id: str, *, created_at: str = "2026-10-06T10:00:00.000Z", **data) -> dict:
    return {"type": kind, "created_at": created_at,
            "data": {"email_id": message_id, "from": "MyHigh5 <infos@myhigh5.com>",
                     "to": ["private.recipient@example.com"], "subject": "PRIVATE SUBJECT LINE", **data}}


def post(client, payload, *, event_id=None, timestamp=None, secret=SECRET, raw=None, headers=None):
    raw = raw if raw is not None else json.dumps(payload).encode()
    event_id = event_id or f"msg_{uuid.uuid4().hex}"
    timestamp = int(time.time()) if timestamp is None else timestamp
    h = {"svix-id": event_id, "svix-timestamp": str(timestamp),
         "svix-signature": sign(raw, event_id=event_id, timestamp=timestamp, secret=secret),
         "content-type": "application/json"}
    h.update(headers or {})
    h = {k: v for k, v in h.items() if v is not None}
    return client.post(URL, content=raw, headers=h)


def delivery(db, *, status="SENT", message_id=None, event_key="KYC.APPROVED", **cols) -> EmailDelivery:
    now = datetime.utcnow()
    row = EmailDelivery(event_key=event_key, category=event_key.split(".")[0], recipient_masked="m***@e***.com",
                        status=status, attempt_count=1, idempotency_key=f"t:{uuid.uuid4().hex}",
                        provider="resend" if message_id else None, provider_message_id=message_id,
                        created_at=now, updated_at=now, sent_at=now if status != "QUEUED" else None, **cols)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def stored(db) -> str:
    parts = []
    for model in (EmailWebhookEvent, EmailDelivery, AuditTrail):
        for row in db.query(model).all():
            parts += [str(getattr(row, c.name)) for c in model.__table__.columns]
    return " ".join(parts)


def events_for(db, row):
    return [(e.event_type, e.outcome) for e in db.query(EmailWebhookEvent)
            .filter(EmailWebhookEvent.email_delivery_id == row.id).order_by(EmailWebhookEvent.id)]


# ===========================================================================
# WEBHOOK AUTHENTICITY
# ===========================================================================

def test_a_correctly_signed_event_is_accepted(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    r = post(client, event("email.delivered", "re_msg_1"))
    assert r.status_code == 200 and r.json() == {"ok": True, "result": "applied"}
    db.refresh(row)
    assert row.status == "DELIVERED" and row.delivered_at == datetime(2026, 10, 6, 10, 0, 0)


def test_requests_that_cannot_be_authenticated_are_refused(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    payload = event("email.bounced", "re_msg_1")
    raw = json.dumps(payload).encode()
    now = int(time.time())
    eid = "msg_auth_1"
    good = sign(raw, event_id=eid, timestamp=now)
    attempts = {
        "no signature": {"svix-signature": None},
        "no id": {"svix-id": None},
        "no timestamp": {"svix-timestamp": None},
        "garbage signature": {"svix-signature": "v1,AAAA"},
        "unversioned signature": {"svix-signature": good.split(",", 1)[1]},
        "signed with another secret": {"svix-signature": sign(raw, event_id=eid, timestamp=now, secret=OTHER_SECRET)},
        "signature of another event id": {"svix-signature": sign(raw, event_id="msg_other", timestamp=now)},
        "bearer token instead": {"svix-signature": None, "authorization": "Bearer something"},
    }
    for name, override in attempts.items():
        r = post(client, payload, event_id=eid, timestamp=now, headers=override)
        assert r.status_code == 401, name
        assert r.json()["detail"] == "Invalid webhook signature."            # one answer for every reason
    # the body was altered after signing
    tampered = raw.replace(b"email.bounced", b"email.delivered")
    r = client.post(URL, content=tampered, headers={"svix-id": eid, "svix-timestamp": str(now), "svix-signature": good})
    assert r.status_code == 401
    # even re-serialising the same JSON breaks it: the RAW body is what is signed
    reserialised = json.dumps(payload, indent=1).encode()
    r = client.post(URL, content=reserialised, headers={"svix-id": eid, "svix-timestamp": str(now), "svix-signature": good})
    assert r.status_code == 401
    # an old (replayed) or future-dated signature is outside the provider's tolerance
    for skew in (-3600, 3600):
        assert post(client, payload, timestamp=now + skew).status_code == 401
    # the API key is not the signing secret
    assert post(client, payload, secret="whsec_" + base64.b64encode(b"re_synthetic_test_key_not_real").decode()).status_code == 401
    # nothing was stored or changed by any of them
    db.refresh(row)
    assert row.status == "SENT" and db.query(EmailWebhookEvent).count() == 0


def test_no_secret_configured_accepts_nothing(client, db, monkeypatch):
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")
    row = delivery(db, message_id="re_msg_1")
    r = post(client, event("email.bounced", "re_msg_1"))
    assert r.status_code == 503
    db.refresh(row)
    assert row.status == "SENT" and db.query(EmailWebhookEvent).count() == 0


def test_the_endpoint_needs_no_session_and_rejects_other_methods(client, db, webhook_secret):
    delivery(db, message_id="re_msg_1")
    assert post(client, event("email.sent", "re_msg_1")).status_code == 200  # no Authorization header at all
    assert client.get(URL).status_code == 405
    source = (APP / "api/api_v1/endpoints/email_webhooks.py").read_text(encoding="utf-8")
    assert "get_current" not in source and "oauth2" not in source.lower()
    assert "RESEND_API_KEY" not in source                                    # never the API key


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"\"text\"", b"{}", b'{"type": 5}', b'{"data": {}}', b"\xff\xfe\x00"])
def test_authenticated_but_malformed_payloads_are_safe(client, db, webhook_secret, raw):
    r = post(client, None, raw=raw)
    assert r.status_code in (400, 401) and db.query(EmailWebhookEvent).count() == 0


def test_oversized_bodies_are_refused(client, db, webhook_secret):
    big = json.dumps(event("email.delivered", "re_msg_1", padding="x" * (300 * 1024))).encode()
    assert post(client, None, raw=big).status_code == 413
    assert db.query(EmailWebhookEvent).count() == 0


def test_verification_is_the_providers_own_and_lives_in_the_provider_layer():
    raw = b'{"type":"email.sent"}'
    now = int(time.time())
    verify_resend_webhook(raw, event_id="e1", timestamp=str(now), signature=sign(raw, event_id="e1", timestamp=now),
                          secret=SECRET)
    # several signatures in one header (secret rotation at the provider): one valid is enough
    both = "v1,AAAA " + sign(raw, event_id="e1", timestamp=now)
    verify_resend_webhook(raw, event_id="e1", timestamp=str(now), signature=both, secret=SECRET)
    for bad in (dict(signature=""), dict(event_id=""), dict(timestamp=""), dict(secret=""), dict(timestamp="abc"),
                dict(secret="whsec_!!!not-base64!!!")):
        kw = dict(event_id="e1", timestamp=str(now), signature=sign(raw, event_id="e1", timestamp=now), secret=SECRET)
        kw.update(bad)
        with pytest.raises(WebhookVerificationError) as refusal:
            verify_resend_webhook(raw, **kw)
        assert str(refusal.value) == ""                                       # no detail, nothing echoed
    with pytest.raises(WebhookVerificationError):
        verify_resend_webhook(b"", event_id="e1", timestamp=str(now), signature="v1,x", secret=SECRET)
    source = (APP / "services/email_providers.py").read_text(encoding="utf-8")
    assert "resend.Webhooks.verify(" in source                                # the SDK's check, not home-made crypto
    assert "hmac" not in source and "hashlib" not in source
    importers = sorted(p.name for p in APP.rglob("*.py")
                       if re.search(r"^\s*(import resend|from resend)", p.read_text(encoding="utf-8"), re.M))
    assert importers == ["email_providers.py"]


# ===========================================================================
# WEBHOOK IDEMPOTENCY / REPLAY
# ===========================================================================

def test_the_same_event_delivered_again_changes_nothing(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    payload = event("email.bounced", "re_msg_1", bounce={"type": "Permanent", "subType": "General", "message": "x"})
    first = post(client, payload, event_id="msg_dup")
    assert first.json()["result"] == "applied"
    db.refresh(row)
    snapshot = (row.status, row.failed_at, row.updated_at, row.failure_category, row.failure_code)
    for _ in range(3):
        again = post(client, payload, event_id="msg_dup")
        assert again.status_code == 200 and again.json()["result"] == "duplicate"   # acknowledged, so not retried
    db.refresh(row)
    assert (row.status, row.failed_at, row.updated_at, row.failure_category, row.failure_code) == snapshot
    assert db.query(EmailWebhookEvent).count() == 1
    # the durable identity is the provider's event id: a different payload under the same id is still the same event
    other = post(client, event("email.complained", "re_msg_1"), event_id="msg_dup")
    assert other.json()["result"] == "duplicate"
    db.refresh(row)
    assert row.status == "BOUNCED"


def test_unknown_event_types_and_unknown_messages_never_fail(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    unknown_type = post(client, event("email.some_future_event", "re_msg_1"))
    assert unknown_type.status_code == 200 and unknown_type.json()["result"] == "unknown_type"
    unknown_message = post(client, event("email.delivered", "re_msg_nobody_knows"))
    assert unknown_message.status_code == 200 and unknown_message.json()["result"] == "unmatched"
    no_message_id = post(client, {"type": "email.delivered", "created_at": "2026-10-06T10:00:00Z", "data": {}})
    assert no_message_id.status_code == 200 and no_message_id.json()["result"] == "unmatched"
    other_object = post(client, {"type": "domain.updated", "data": {"id": "dom_1"}})
    assert other_object.status_code == 200 and other_object.json()["result"] == "unknown_type"
    db.refresh(row)
    assert row.status == "SENT"                                               # none of them touched a delivery
    kept = {(e.event_type, e.outcome, e.email_delivery_id) for e in db.query(EmailWebhookEvent)}
    assert kept == {("email.some_future_event", "unknown_type", None), ("email.delivered", "unmatched", None),
                    ("domain.updated", "unknown_type", None)}                 # kept for diagnosis, two "delivered" rows
    assert db.query(EmailWebhookEvent).count() == 4


def test_engagement_and_inbound_events_are_acknowledged_and_not_kept(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1", status="DELIVERED")
    for kind in ("email.opened", "email.clicked", "email.received", "email.scheduled"):
        r = post(client, event(kind, "re_msg_1", click={"link": "https://example.com/private"}))
        assert r.status_code == 200 and r.json()["result"] == "ignored"
    db.refresh(row)
    assert row.status == "DELIVERED" and db.query(EmailWebhookEvent).count() == 0   # no tracking data is stored


# ===========================================================================
# DELIVERY STATE
# ===========================================================================

def test_each_provider_event_maps_to_its_state(client, db, webhook_secret):
    expected = {"email.sent": "SENT", "email.delivery_delayed": "DELAYED", "email.delivered": "DELIVERED",
                "email.failed": "FAILED", "email.bounced": "BOUNCED", "email.complained": "COMPLAINED"}
    assert email_webhooks.STATE_EVENTS == expected
    for kind, status in expected.items():
        row = delivery(db, message_id=f"re_{kind}")
        r = post(client, event(kind, f"re_{kind}"))
        db.refresh(row)
        assert row.status == status, kind
        assert r.json()["result"] == ("recorded" if kind == "email.sent" else "applied")   # already SENT locally
        assert row.next_attempt_at is None
        if status in ("FAILED", "BOUNCED", "COMPLAINED"):
            assert row.failed_at is not None and row.failure_category in ("provider_failed", "bounced", "complained")
        if status == "DELIVERED":
            assert row.delivered_at is not None


def test_events_out_of_order_never_move_a_delivery_backwards(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    order = [("email.delivered", "DELIVERED", "applied", "2026-10-06T10:00:05Z"),
             ("email.sent", "DELIVERED", "recorded", "2026-10-06T10:00:01Z"),            # late "sent"
             ("email.delivery_delayed", "DELIVERED", "recorded", "2026-10-06T10:00:03Z"),  # late "delayed"
             ("email.delivered", "DELIVERED", "recorded", "2026-10-06T10:00:06Z"),       # a second "delivered"
             ("email.complained", "COMPLAINED", "applied", "2026-10-06T11:00:00Z"),      # after delivery: meaningful
             ("email.bounced", "COMPLAINED", "recorded", "2026-10-06T10:30:00Z"),
             ("email.delivered", "COMPLAINED", "recorded", "2026-10-06T10:00:07Z"),
             ("email.failed", "COMPLAINED", "recorded", "2026-10-06T10:00:08Z")]
    for kind, status, outcome, when in order:
        r = post(client, event(kind, "re_msg_1", created_at=when))
        db.refresh(row)
        assert (row.status, r.json()["result"]) == (status, outcome), kind
    assert row.delivered_at == datetime(2026, 10, 6, 10, 0, 5)                 # the first delivery fact is kept
    assert row.failure_category == "complained"
    # the provider's full account is the event history, in arrival order
    assert [k for k, _ in events_for(db, row)] == [k for k, _, _, _ in order]


def test_a_bounce_after_delivery_stays_visible(client, db, webhook_secret):
    row = delivery(db, message_id="re_msg_1")
    post(client, event("email.delivered", "re_msg_1", created_at="2026-10-06T10:00:05Z"))
    post(client, event("email.bounced", "re_msg_1", created_at="2026-10-06T10:02:00Z",
                       bounce={"type": "Transient", "subType": "MailboxFull",
                               "message": "mailbox of private.recipient@example.com is full"}))
    db.refresh(row)
    assert (row.status, row.failure_category, row.failure_code) == ("BOUNCED", "bounced", "Transient")
    assert row.delivered_at is not None
    bounce = db.query(EmailWebhookEvent).filter(EmailWebhookEvent.event_type == "email.bounced").one()
    assert bounce.meta == {"bounce_type": "Transient", "bounce_subtype": "MailboxFull"}   # classification only
    # a delivered that arrives after the bounce is recorded and keeps the delivery fact, not the status
    late = delivery(db, message_id="re_msg_2")
    post(client, event("email.bounced", "re_msg_2", bounce={"type": "Permanent", "subType": "Suppressed"}))
    post(client, event("email.delivered", "re_msg_2"))
    db.refresh(late)
    assert late.status == "BOUNCED" and late.delivered_at is not None


def test_a_bounced_or_complained_delivery_is_never_retried(client, db, webhook_secret, email_outbox):
    row = delivery(db, message_id="re_msg_1")
    post(client, event("email.bounced", "re_msg_1", bounce={"type": "Permanent"}))
    summary = process_outbox(db, provider=email_outbox.provider, now=datetime.utcnow() + timedelta(days=2))
    assert summary["claimed"] == 0 and email_outbox.provider.sent == []
    db.refresh(row)
    assert row.status == "BOUNCED" and row.attempt_count == 1
    assert "BOUNCED" in email_outbox_module_terminal() and "COMPLAINED" in email_outbox_module_terminal()


def email_outbox_module_terminal():
    return outbox_module.TERMINAL_STATUSES


def test_bounces_and_complaints_change_nothing_but_the_delivery(client, db, webhook_secret, email_outbox, ip):
    """No suppression, no account change: recording only."""
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:bounce-policy")
    email_outbox.drain()
    row = db.query(EmailDelivery).one()
    before = (user.is_active, user.email, user.email_verified, user.email_verification_required,
              user.security_version, user.status, user.identity_verified)
    post(client, event("email.bounced", row.provider_message_id, bounce={"type": "Permanent"}))
    post(client, event("email.complained", row.provider_message_id))
    db.refresh(row)
    db.refresh(user)
    assert row.status == "COMPLAINED"
    assert (user.is_active, user.email, user.email_verified, user.email_verification_required,
            user.security_version, user.status, user.identity_verified) == before
    assert db.query(KYCVerification).count() == 0
    # the member can still sign in and still receives email: no automatic suppression exists
    assert login(client, user).status_code == 200
    again = email_service.enqueue(db, event=EmailEvent.KYC_REJECTED, recipient=user.email, user_id=user.id,
                                  idempotency_key="t:after-complaint")
    assert again.status == "QUEUED"
    source = (APP / "services/email_webhooks.py").read_text(encoding="utf-8")
    for forbidden in ("User", "is_active", "email_verified", "KYC", "Contestant", "Deposit", "Commission"):
        assert not re.search(rf"\b{forbidden}\b\s*[=(.]", source.split('"""', 2)[2]), forbidden


def test_only_safe_fields_are_stored_and_nothing_sensitive_is_logged(client, db, webhook_secret, caplog):
    row = delivery(db, message_id="re_msg_1")
    with caplog.at_level("DEBUG"):
        post(client, event("email.bounced", "re_msg_1",
                           bounce={"type": "Permanent", "subType": "General",
                                   "message": "550 private.recipient@example.com does not exist"},
                           headers=[{"name": "X-Secret", "value": "HEADER-SECRET"}], html="<p>BODY SECRET</p>",
                           tags={"reset": "TOKEN-IN-TAG"}))
        post(client, event("email.delivered", "re_unknown"))
        bad = client.post(URL, content=b'{"type":"email.sent"}', headers={
            "svix-id": "x", "svix-timestamp": str(int(time.time())), "svix-signature": "v1,FORGED-SIGNATURE-VALUE"})
        assert bad.status_code == 401
    kept = stored(db)
    for secret in ("private.recipient@example.com", "PRIVATE SUBJECT LINE", "does not exist", "HEADER-SECRET",
                   "BODY SECRET", "TOKEN-IN-TAG", "infos@myhigh5.com", SECRET, SECRET[6:]):
        assert secret not in kept and secret not in caplog.text
    assert "FORGED-SIGNATURE-VALUE" not in caplog.text
    assert "verification failed" in caplog.text                              # the refusal itself is logged
    columns = {c.name for c in EmailWebhookEvent.__table__.columns}
    assert not columns & {"payload", "raw", "body", "recipient", "to", "subject", "headers"}
    db.refresh(row)
    assert row.status == "BOUNCED"


# ===========================================================================
# ASSOCIATION: an event that arrives before the send is recorded
# ===========================================================================

def test_an_early_event_is_kept_and_applied_when_the_send_is_recorded(client, db, webhook_secret, email_outbox, ip):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:early")
    # The provider will answer "fake-1" for this send. Its webhooks get here first.
    assert post(client, event("email.delivered", "fake-1", created_at="2026-10-06T10:00:02Z")).json()["result"] == "unmatched"
    assert post(client, event("email.sent", "fake-1", created_at="2026-10-06T10:00:01Z")).json()["result"] == "unmatched"
    assert [e.processed_at for e in db.query(EmailWebhookEvent)] == [None, None]

    email_outbox.drain()                                                      # the outbox now records the send
    row = db.query(EmailDelivery).one()
    assert row.provider_message_id == "fake-1" and row.status == "DELIVERED"  # not regressed to SENT
    assert row.delivered_at == datetime(2026, 10, 6, 10, 0, 2)
    linked = db.query(EmailWebhookEvent).order_by(EmailWebhookEvent.occurred_at).all()
    assert [(e.event_type, e.outcome, e.email_delivery_id) for e in linked] == [
        ("email.sent", "recorded", row.id), ("email.delivered", "applied", row.id)]
    assert all(e.processed_at is not None for e in linked)
    assert email_webhooks.apply_pending(db, row) == 0                         # nothing left; calling again is harmless


def test_a_webhook_cannot_move_a_delivery_that_was_never_sent(client, db, webhook_secret):
    for status in ("QUEUED", "PROCESSING", "SUPPRESSED"):
        row = delivery(db, status=status, message_id=f"re_{status}")
        assert post(client, event("email.delivered", f"re_{status}")).json()["result"] == "recorded"
        db.refresh(row)
        assert row.status == status


# ===========================================================================
# PROVIDER-SIDE SEND IDEMPOTENCY
# ===========================================================================

def test_the_provider_key_is_stable_per_delivery_and_carries_nothing_personal(db):
    a = delivery(db, status="QUEUED")
    b = delivery(db, status="QUEUED")
    key_a = provider_idempotency_key(a)
    assert key_a == provider_idempotency_key(a) and key_a != provider_idempotency_key(b)
    a.attempt_count, a.status, a.updated_at = 4, "PROCESSING", datetime.utcnow() + timedelta(hours=3)
    assert provider_idempotency_key(a) == key_a                               # attempts, time and status do not change it
    assert re.fullmatch(r"mh5-[0-9a-f]{64}", key_a) and len(key_a) <= email_providers.MAX_IDEMPOTENCY_KEY_LENGTH
    for leak in (a.idempotency_key, str(a.id) + ":", "example.com", a.recipient_masked):
        assert leak not in key_a
    source = (APP / "services/email_outbox.py").read_text(encoding="utf-8")
    derivation = source[source.index("def provider_idempotency_key"):source.index("def outbox_executor")]
    for forbidden in ("uuid", "random", "secrets.", "html", "subject", "payload", "recipient", "attempt", "utcnow", "time("):
        assert forbidden not in derivation.split('"""')[2], forbidden


def test_every_attempt_of_a_delivery_sends_the_same_key(db, email_outbox, ip):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id, idempotency_key="t:a")
    email_service.enqueue(db, event=EmailEvent.KYC_REJECTED, recipient=user.email, user_id=user.id, idempotency_key="t:b")
    provider = email_outbox.provider
    provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK),
                       ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)]
    t0 = datetime.utcnow()
    process_outbox(db, provider=provider, now=t0)                             # both fail once
    process_outbox(db, provider=provider, now=t0 + timedelta(minutes=5))      # both succeed
    rows = db.query(EmailDelivery).order_by(EmailDelivery.id).all()
    assert [r.status for r in rows] == ["SENT", "SENT"] and [r.attempt_count for r in rows] == [2, 2]
    key_a, key_b = provider_idempotency_key(rows[0]), provider_idempotency_key(rows[1])
    assert key_a != key_b
    assert provider.idempotency_keys == [key_a, key_b, key_a, key_b]          # same key on the retry of each
    assert len(provider.sent) == 2


def test_crash_after_the_provider_accepted_does_not_send_twice(db, email_outbox, ip):
    """1. the provider accepts the send; 2. the application dies before saving
    it; 3. the stale PROCESSING row is reclaimed; 4. the send is attempted
    again with the same key; 5. the provider answers with the first message
    and creates no second one."""
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id, idempotency_key="t:crash")
    provider = email_outbox.provider
    t0 = datetime.utcnow()

    (delivery_id,) = claim_batch(db, now=t0, batch_size=10)
    row = db.query(EmailDelivery).get(delivery_id)
    assert outbox_module._send_one(db, row, provider, t0) == "SENT"            # provider accepted ...
    db.rollback()                                                             # ... and the process died before the commit
    db.refresh(row)
    assert (row.status, row.provider_message_id, row.attempt_count) == ("PROCESSING", None, 1)
    assert len(provider.sent) == 1

    assert process_outbox(db, provider=provider, now=t0 + timedelta(minutes=5))["claimed"] == 0   # not stale yet
    summary = process_outbox(db, provider=provider, now=t0 + STALE_PROCESSING_AFTER + timedelta(minutes=1))
    assert (summary["requeued"], summary["sent"]) == (1, 1)
    db.refresh(row)
    assert (row.status, row.provider_message_id, row.attempt_count) == ("SENT", "fake-1", 2)
    assert provider.idempotency_keys == [provider_idempotency_key(row)] * 2    # the same key, twice
    assert len(provider.sent) == 1                                            # ONE message exists at the provider
    assert db.query(EmailDelivery).count() == 1


@pytest.mark.parametrize("purpose, page, event_name", [
    (PURPOSE_EMAIL_VERIFICATION, "verify-email", EmailEvent.AUTH_EMAIL_VERIFICATION),
    (PURPOSE_PASSWORD_RESET, "reset-password", EmailEvent.AUTH_PASSWORD_RESET)])
def test_a_resent_auth_email_carries_the_same_working_link(client, db, email_outbox, ip, purpose, page, event_name):
    """The crash window for an email with a one-time link: the member received
    the first copy. The retry must not replace that link, and the provider
    must see identical content under the same key."""
    user = member(db)
    email_service.enqueue(db, event=event_name, recipient=user.email, user_id=user.id, idempotency_key=f"t:{purpose}")
    provider = email_outbox.provider
    t0 = datetime.utcnow()
    (delivery_id,) = claim_batch(db, now=t0, batch_size=10)
    row = db.query(EmailDelivery).get(delivery_id)
    outbox_module._send_one(db, row, provider, t0)
    db.rollback()                                                             # crash after the provider accepted
    first = provider.sent[0]
    token = link_token({"html": first.html}, page)
    stored_token = db.query(AuthToken).one()
    assert stored_token.token_hash == auth_tokens.hash_token(token)           # the mailed link exists in the database
    assert token not in stored(db)                                            # ... as a digest only

    process_outbox(db, provider=provider, now=t0 + STALE_PROCESSING_AFTER + timedelta(minutes=1))
    db.refresh(row)
    assert row.status == "SENT" and row.provider_message_id == "fake-1"
    assert len(provider.sent) == 1 and len(set(provider.idempotency_keys)) == 1
    assert db.query(AuthToken).count() == 1 and db.query(AuthToken).one().revoked_at is None
    # the link the member received still works, once
    if purpose == PURPOSE_EMAIL_VERIFICATION:
        assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
        assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    else:
        assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 200
        assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW}).status_code == 400


def test_link_credentials_are_per_delivery_unguessable_and_still_one_time(client, db, email_outbox, ip):
    user, other = member(db), member(db)
    raw = auth_tokens.delivery_credential(PURPOSE_PASSWORD_RESET, user.id, "7:key")
    assert raw == auth_tokens.delivery_credential(PURPOSE_PASSWORD_RESET, user.id, "7:key")
    assert len(raw) == 43 and re.fullmatch(r"[\w\-]+", raw)                   # 256 bits
    different = {auth_tokens.delivery_credential(PURPOSE_PASSWORD_RESET, user.id, "8:key"),
                 auth_tokens.delivery_credential(PURPOSE_PASSWORD_RESET, other.id, "7:key"),
                 auth_tokens.delivery_credential(PURPOSE_EMAIL_VERIFICATION, user.id, "7:key")}
    assert len(different) == 3 and raw not in different
    # a new request is a new delivery, so a new link that replaces the old one (unchanged EMAIL-2 behaviour)
    first = auth_tokens.issue(db, user, PURPOSE_PASSWORD_RESET, delivery_ref="1:a")
    second = auth_tokens.issue(db, user, PURPOSE_PASSWORD_RESET, delivery_ref="2:b")
    db.commit()
    assert first != second
    assert client.post(f"{A}/password-reset-confirm", json={"token": first, "new_password": PW2}).status_code == 400
    # the superseded delivery cannot be re-issued (and so is not re-sent); neither can a used one
    with pytest.raises(auth_tokens.AuthTokenError) as superseded:
        auth_tokens.issue(db, user, PURPOSE_PASSWORD_RESET, delivery_ref="1:a")
    assert superseded.value.reason == "revoked"
    assert client.post(f"{A}/password-reset-confirm", json={"token": second, "new_password": PW2}).status_code == 200
    with pytest.raises(auth_tokens.AuthTokenError) as used:
        auth_tokens.issue(db, user, PURPOSE_PASSWORD_RESET, delivery_ref="2:b")
    assert used.value.reason == "used"
    # without a delivery (direct callers) a credential is still random
    assert auth_tokens.issue(db, other, PURPOSE_EMAIL_VERIFICATION) != auth_tokens.issue(db, other, PURPOSE_EMAIL_VERIFICATION)


def test_a_conflict_reported_by_the_provider_is_retried_not_resent_as_new(db, email_outbox, ip):
    conflict = classify_http_status(409)
    assert (conflict.success, conflict.retryable, conflict.error_category) == (False, True, FAIL_CONFLICT)
    provider = FakeEmailProvider()
    message = EmailMessage(to="a@example.com", subject="s", html="<p>1</p>", text="1", from_header="MyHigh5 <x@example.com>")
    changed = EmailMessage(to="a@example.com", subject="s", html="<p>2</p>", text="2", from_header="MyHigh5 <x@example.com>")
    first = provider.send(message, api_key="k", idempotency_key="key-1")
    again = provider.send(message, api_key="k", idempotency_key="key-1")
    assert again.success and again.provider_message_id == first.provider_message_id and len(provider.sent) == 1
    other_content = provider.send(changed, api_key="k", idempotency_key="key-1")
    assert (other_content.success, other_content.error_category) == (False, FAIL_CONFLICT) and len(provider.sent) == 1
    assert provider.send(changed, api_key="k", idempotency_key="key-2").success and len(provider.sent) == 2


def test_resend_receives_the_key_as_the_sdk_idempotency_option(monkeypatch):
    import resend

    calls = []

    def fake_send(params, options=None):
        calls.append((params, options, resend.api_key))
        return {"id": "re_real_shape"}
    monkeypatch.setattr(resend.Emails, "send", staticmethod(fake_send))
    message = EmailMessage(to="a@example.com", subject="s", html="<p>h</p>", text="t", from_header="MyHigh5 <x@example.com>")
    provider = email_providers.ResendEmailProvider()
    result = provider.send(message, api_key="re_synthetic_test_key_not_real", idempotency_key="mh5-" + "a" * 64)
    assert result.success and result.provider_message_id == "re_real_shape"
    params, options, key_during_call = calls[0]
    assert options == {"idempotency_key": "mh5-" + "a" * 64} and key_during_call == "re_synthetic_test_key_not_real"
    assert "idempotency" not in json.dumps(params).lower()                    # a header option, never part of the message
    assert resend.api_key is None
    provider.send(message, api_key="re_synthetic_test_key_not_real")          # no key: the plain call, as before
    assert calls[1][1] is None
    # the SDK really does turn that option into the provider's header
    from resend import request as sdk_request

    assert 'headers["Idempotency-Key"]' in Path(sdk_request.__file__).read_text(encoding="utf-8")


def test_the_admin_test_email_also_carries_a_key(db, email_outbox):
    admin = member(db, verified=True, is_admin=True)
    row = email_outbox_send_test(db, admin, email_outbox.provider)
    assert email_outbox.provider.idempotency_keys == [provider_idempotency_key(row)]
    other = email_outbox_send_test(db, admin, email_outbox.provider)
    assert email_outbox.provider.idempotency_keys[1] != email_outbox.provider.idempotency_keys[0]   # each test is its own delivery


def email_outbox_send_test(db, admin, provider):
    return outbox_module.send_test_email(db, recipient="ops.person@example.com", actor_id=admin.id, provider=provider)


# ===========================================================================
# EMAIL-1 / EMAIL-2 / EMAIL-3 keep working through the same layer
# ===========================================================================

def test_business_emails_get_a_key_without_knowing_about_the_provider(client, db, email_outbox, ip):
    data = body()
    assert client.post(f"{A}/register", json=data).status_code == 201           # AUTH.EMAIL_VERIFICATION
    user = db.query(User).filter(User.email == data["email"]).one()
    token = link_token(email_outbox[-1], "verify-email")
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200   # AUTH.WELCOME
    client.post(f"{A}/password-reset-request", json={"email": user.email})      # AUTH.PASSWORD_RESET
    reset = link_token(email_outbox[-1], "reset-password")
    assert client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW2}).status_code == 200
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id, idempotency_key="t:kyc")
    email_outbox.drain()
    rows = db.query(EmailDelivery).order_by(EmailDelivery.id).all()
    assert [r.event_key for r in rows] == ["AUTH.EMAIL_VERIFICATION", "AUTH.WELCOME", "AUTH.PASSWORD_RESET",
                                           "AUTH.PASSWORD_CHANGED", "KYC.APPROVED"]
    assert all(r.status == "SENT" and r.provider_message_id for r in rows)
    keys = email_outbox.provider.idempotency_keys
    assert keys == [provider_idempotency_key(r) for r in rows] and len(set(keys)) == 5
    for name in ("api/api_v1/endpoints/auth.py", "services/kyc_notifications.py", "services/contest_notifications.py",
                 "services/email.py"):
        source = (APP / name).read_text(encoding="utf-8")
        assert "provider_idempotency_key" not in source and "Idempotency-Key" not in source


def test_switches_and_emergency_stop_are_unchanged(client, db, webhook_secret, email_outbox, ip):
    user = member(db, verified=True)
    svc.get_settings_for_update(db).emergency_stop = True
    db.commit()
    stopped = email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                                    idempotency_key="t:stopped")
    assert (stopped.status, stopped.failure_category) == ("SUPPRESSED", "emergency_stop")
    assert email_outbox.provider.idempotency_keys == []                       # nothing reached the provider
    # a provider event is still recorded while email is stopped: it reports the past, it sends nothing
    row = delivery(db, message_id="re_msg_1")
    assert post(client, event("email.delivered", "re_msg_1")).json()["result"] == "applied"
    db.refresh(row)
    assert row.status == "DELIVERED"


def test_admin_views_show_provider_states(client, db, webhook_secret, ip):
    from tests.unit.test_age_gate_registration import auth, make_user
    from tests.unit.test_email_foundation import BASE

    delivered, bounced = delivery(db, message_id="re_1"), delivery(db, message_id="re_2")
    post(client, event("email.delivered", "re_1"))
    post(client, event("email.bounced", "re_2", bounce={"type": "Permanent"}))
    h = auth(make_user(db, admin=True))
    items = {i["id"]: i for i in client.get(f"{BASE}/deliveries", headers=h).json()["items"]}
    assert items[delivered.id]["status"] == "DELIVERED" and items[bounced.id]["status"] == "BOUNCED"
    assert (items[bounced.id]["failure_category"], items[bounced.id]["failure_code"]) == ("bounced", "Permanent")
    assert client.get(f"{BASE}/deliveries?status=BOUNCED", headers=h).json()["total"] == 1
    stats = client.get(f"{BASE}/overview", headers=h).json()["stats"]
    assert (stats["sent_24h"], stats["failed_24h"]) == (1, 1)


def test_provider_events_are_not_business_email_events():
    assert len(EMAIL_EVENTS) == 54                  # 53 of EMAIL-1 + PAYOUT.WALLET_CONFIRMATION (dual cashout)
    assert not any(k.startswith("email.") or "WEBHOOK" in k or "BOUNCE" in k or "COMPLAIN" in k for k in EMAIL_EVENTS)
    wired = {k for k, d in EMAIL_EVENTS.items() if d.trigger_implemented}
    assert len(wired) == 24                         # as after EMAIL-3 + PAYOUT.WALLET_CONFIRMATION (dual cashout)
