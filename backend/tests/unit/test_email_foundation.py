"""EMAIL-1: central email foundation.

Registry, settings and send policy, encrypted API-key override, permissions,
outbox worker (claim / retry / failure), idempotency, template security, the
delivery log, the Admin test email and the existing send sites routed through
the central service.

Everything is SYNTHETIC. No test contacts Resend: emails go to an in-memory
FakeEmailProvider (conftest.email_outbox). The API keys below are fake values.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import get_password_hash, verify_email_verification_token, verify_password_reset_token
from app.models.accounting import AuditTrail
from app.models.email import EmailDelivery, EmailEventSetting, EmailSettings
from app.models.user import Permission, Role, User
from app.services import email_crypto, email_providers, email_settings_service as svc
from app.services import email_outbox as outbox_module
from app.services import email_templates as tpl
from app.services.email import INVITATIONS_PER_DAY, email_service
from app.services.email_events import (
    EMAIL_EVENTS, TEST_EMAIL_KEY, EmailCategory, EmailEvent, UnknownEmailEvent, all_events, get_event,
)
from app.services.email_providers import FAIL_NETWORK, FAIL_REJECTED, ProviderResult
from app.services.email_render import RENDERERS, render
from tests.unit.test_age_gate_registration import auth, make_user
from tests.unit.test_new_business_model import world  # noqa: F401  (fixture)

BASE = "/api/v1/admin/email-settings"
ENV_KEY = "re_synthetic_test_key_not_real"          # set by conftest.email_outbox
OVERRIDE_KEY = "re_override_SYNTHETIC_value_9876"
ENCRYPTION_KEY = "synthetic-email-settings-encryption-key-0001"
HOSTILE = '<script>alert("x")</script><img src=x onerror=alert(1)>'


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def manager(db, *, permission=svc.PERMISSION_MANAGE_EMAIL_SETTINGS, admin=True) -> User:
    perm = Permission(name=permission, category="admin")
    role = Role(name=f"role_{uuid.uuid4().hex[:8]}", permissions=[perm])
    db.add(role)
    db.flush()
    return make_user(db, admin=admin, role_id=role.id)


def queue(db, event=EmailEvent.KYC_APPROVED, recipient="member@example.com", key=None, **kw):
    return email_service.enqueue(db, event=event, recipient=recipient,
                                 idempotency_key=key or f"test:{uuid.uuid4().hex}", **kw)


@pytest.fixture
def enc_key(monkeypatch):
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", ENCRYPTION_KEY)


def stored_text(db) -> str:
    """Every value held in the email tables and the audit trail, as one string."""
    parts = []
    for model in (EmailSettings, EmailEventSetting, EmailDelivery, AuditTrail):
        for row in db.query(model).all():
            parts += [str(getattr(row, c.name)) for c in model.__table__.columns]
    return " ".join(parts)


# ===========================================================================
# FOUNDATION: registry
# ===========================================================================

def test_registry_matches_the_audited_inventory():
    assert len(EMAIL_EVENTS) == 53 == len(all_events()) == len(EmailEvent)
    assert len({d.key for d in all_events()}) == 53                       # unique keys
    per_category = {c.value: sum(1 for d in all_events() if d.category == c) for c in EmailCategory}
    assert per_category == {"AUTH": 6, "GUARDIAN": 2, "KYC": 5, "CONTEST": 17, "BILLING": 7, "AFFILIATE": 4,
                            "PAYOUT": 3, "ADMIN": 7, "SUPPORT": 2}
    by_phase = {}
    for d in all_events():
        by_phase[d.phase.value] = by_phase.get(d.phase.value, 0) + 1
    assert by_phase == {"IMPLEMENT_NOW": 25, "LATER": 15, "REQUIRES_BUSINESS_APPROVAL": 13}
    for d in all_events():
        assert d.key == d.key.upper() and d.key.split(".")[0] == d.category.value and d.label


def test_forbidden_events_are_absent():
    keys = set(EMAIL_EVENTS)
    for forbidden in ("CONTEST.NOMINATION_PENDING_REVIEW", "CONTEST.NOMINATION_SUBMITTED",
                      "CONTEST.PARTICIPATION_SUBMITTED", "KYC.PENDING_REVIEW", "AUTH.EMAIL_CHANGED",
                      "PAYOUT.APPROVED", "PAYOUT.REJECTED", "BILLING.INVOICE", TEST_EMAIL_KEY):
        assert forbidden not in keys
    joined = " ".join(keys) + " " + " ".join(d.label.upper() for d in all_events())
    for retired in ("POOL", "FOUNDING", "LEADER", "DSP", "LEVEL_2", "LEVEL 2", "PENDING_REVIEW" + "_NOMINATION"):
        assert retired not in joined
    assert not any("NOMINATION" in k and ("PENDING" in k or "SUBMITTED" in k) for k in keys)
    with pytest.raises(UnknownEmailEvent):
        get_event("CONTEST.NOMINATION_PENDING_REVIEW")


def test_registry_defaults_and_critical_events():
    critical = {d.key for d in all_events() if d.critical}
    assert critical == {"AUTH.EMAIL_VERIFICATION", "AUTH.PASSWORD_RESET", "AUTH.PASSWORD_CHANGED",
                        "GUARDIAN.CONSENT_REQUEST", "GUARDIAN.REGISTRATION_COMPLETION"}
    for d in all_events():
        if d.critical:
            assert d.default_enabled and d.disable_warning
        if d.phase.value != "IMPLEMENT_NOW":
            assert not d.trigger_implemented                              # future events are never emitted
    # defaults exactly as audited: 25 on, 28 off
    assert sum(1 for d in all_events() if d.default_enabled) == 25
    assert {d.key for d in all_events() if d.default_enabled and d.phase.value != "IMPLEMENT_NOW"} == {
        "KYC.ACTION_REQUIRED"}
    assert {d.key for d in all_events() if not d.default_enabled and d.phase.value == "IMPLEMENT_NOW"} == {
        "ADMIN.KYC_REVIEW_REQUIRED"}
    # exactly the events the application emits today have a template
    live = {d.key for d in all_events() if d.trigger_implemented}
    assert live == set(RENDERERS) - {TEST_EMAIL_KEY} and len(live) == 13


def test_nomination_and_participation_events_stay_separate():
    assert get_event(EmailEvent.CONTEST_NOMINATION_PUBLISHED).label == "Nomination published"
    participation = {k for k in EMAIL_EVENTS if k.startswith("CONTEST.PARTICIPATION_")}
    assert participation == {"CONTEST.PARTICIPATION_PENDING_REVIEW", "CONTEST.PARTICIPATION_PUBLISHED",
                             "CONTEST.PARTICIPATION_ACTION_REQUIRED", "CONTEST.PARTICIPATION_REJECTED"}
    # Registered, not wired: EMAIL-1 emits no contest email and touches no contest logic.
    assert not any(get_event(k).trigger_implemented for k in EMAIL_EVENTS if k.startswith("CONTEST."))
    app_dir = Path(__file__).resolve().parents[2] / "app"
    users = [p.name for p in app_dir.rglob("*.py")
             if "EmailEvent.CONTEST_" in p.read_text(encoding="utf-8") and p.name != "email_events.py"]
    assert users == []


def test_no_application_code_calls_resend_directly():
    app_dir = Path(__file__).resolve().parents[2] / "app"
    direct = [p.name for p in app_dir.rglob("*.py")
              if re.search(r"^\s*(import resend|from resend)", p.read_text(encoding="utf-8"), re.M)]
    assert direct == ["email_providers.py"]


# ===========================================================================
# SETTINGS / POLICY
# ===========================================================================

def test_without_a_key_nothing_is_queued_or_sent(db, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    row = queue(db, EmailEvent.AUTH_PASSWORD_CHANGED)
    assert (row.status, row.failure_category) == ("FAILED", svc.REASON_PROVIDER_UNCONFIGURED)
    assert row.payload_ciphertext is None and row.failed_at is not None
    assert outbox_module.process_outbox(db)["claimed"] == 0


def test_master_switch_suppresses_normal_email_but_not_security_email(db, email_outbox):
    row = svc.get_settings_for_update(db)
    row.email_enabled = False
    db.commit()
    normal = queue(db, EmailEvent.KYC_APPROVED)
    critical = queue(db, EmailEvent.AUTH_PASSWORD_CHANGED)
    assert (normal.status, normal.failure_category) == ("SUPPRESSED", svc.REASON_MASTER_DISABLED)
    assert normal.payload_ciphertext is None                           # not kept for a later replay
    assert critical.status == "QUEUED"
    assert len(email_outbox) == 1
    # Re-enabling does not flush anything: the suppressed email stays suppressed.
    svc.get_settings_for_update(db).email_enabled = True
    db.commit()
    assert email_outbox.drain()["claimed"] == 0 and len(email_outbox) == 1
    assert db.query(EmailDelivery).filter_by(id=normal.id).one().status == "SUPPRESSED"


def test_emergency_stop_suppresses_everything_including_security_email(db, email_outbox):
    queued_before = queue(db, EmailEvent.AUTH_PASSWORD_RESET, user_id=1)
    svc.get_settings_for_update(db).emergency_stop = True
    db.commit()
    for event in (EmailEvent.AUTH_PASSWORD_RESET, EmailEvent.AUTH_EMAIL_VERIFICATION, EmailEvent.KYC_APPROVED):
        row = queue(db, event)
        assert (row.status, row.failure_category) == ("SUPPRESSED", svc.REASON_EMERGENCY_STOP)
    # An email queued BEFORE the stop is not sent after it either.
    assert len(email_outbox) == 0
    db.refresh(queued_before)
    assert (queued_before.status, queued_before.failure_category) == ("SUPPRESSED", svc.REASON_EMERGENCY_STOP)
    assert queued_before.payload_ciphertext is None


def test_provider_disabled_is_separate_from_the_switches(db, email_outbox):
    svc.get_settings_for_update(db).resend_enabled = False
    db.commit()
    row = queue(db, EmailEvent.AUTH_PASSWORD_CHANGED)
    assert (row.status, row.failure_category) == ("FAILED", svc.REASON_PROVIDER_DISABLED)
    assert len(email_outbox) == 0


def test_event_switch_uses_the_registry_default_until_overridden(db, email_outbox):
    definition = get_event(EmailEvent.KYC_APPROVED)
    assert db.query(EmailEventSetting).count() == 0 and svc.event_enabled(db, definition)
    assert svc.set_event_enabled(db, definition, False, actor_id=None) is True
    db.commit()
    row = queue(db, EmailEvent.KYC_APPROVED)
    assert (row.status, row.failure_category) == ("SUPPRESSED", svc.REASON_EVENT_DISABLED)
    assert queue(db, EmailEvent.KYC_REJECTED).status == "QUEUED"        # other events unaffected
    # a critical event can be switched off too (owner requirement)
    svc.set_event_enabled(db, get_event(EmailEvent.AUTH_PASSWORD_RESET), False, actor_id=None)
    db.commit()
    assert queue(db, EmailEvent.AUTH_PASSWORD_RESET).failure_category == svc.REASON_EVENT_DISABLED
    assert db.query(EmailEventSetting).count() == 2                      # overrides only


def test_api_key_resolution_override_then_environment_then_none(db, email_outbox, enc_key, monkeypatch):
    row = svc.get_settings_for_update(db)
    assert svc.resolve_api_key(row) == (ENV_KEY, svc.KEY_SOURCE_ENV)
    svc.set_api_key_override(db, row, OVERRIDE_KEY, actor_id=None)
    db.commit()
    assert svc.resolve_api_key(row) == (OVERRIDE_KEY, svc.KEY_SOURCE_OVERRIDE)
    queue(db)
    email_outbox.drain()
    assert email_outbox.provider.api_keys == [OVERRIDE_KEY]             # resolved per send, no restart
    svc.clear_api_key_override(row, actor_id=None)
    db.commit()
    queue(db)
    email_outbox.drain()
    assert email_outbox.provider.api_keys == [OVERRIDE_KEY, ENV_KEY]
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    assert svc.resolve_api_key(row) == (None, svc.KEY_SOURCE_NONE)


def test_override_is_encrypted_and_needs_the_dedicated_key(db, enc_key, monkeypatch):
    row = svc.get_settings_for_update(db)
    svc.set_api_key_override(db, row, OVERRIDE_KEY, actor_id=None)
    db.commit()
    cipher = row.resend_api_key_ciphertext
    assert cipher.startswith("v1:") and OVERRIDE_KEY not in cipher and row.resend_api_key_last4 == "9876"
    assert OVERRIDE_KEY not in stored_text(db)
    assert email_crypto.decrypt_secret(cipher) == OVERRIDE_KEY
    # a second encryption of the same value differs (random nonce)
    assert email_crypto.encrypt_secret(OVERRIDE_KEY) != cipher
    # authenticated: a modified ciphertext, another purpose or another key all fail
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.decrypt_secret(cipher[:-4] + ("AAAA" if not cipher.endswith("AAAA") else "BBBB"))
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.decrypt_secret(cipher, email_crypto.PURPOSE_WEBHOOK_SECRET)
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "another-synthetic-encryption-key-000002")
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.decrypt_secret(cipher)
    assert svc.override_readable(row) is False
    # without the dedicated key there is no fallback to SECRET_KEY or any other application key
    monkeypatch.delenv("EMAIL_SETTINGS_ENCRYPTION_KEY")
    monkeypatch.setattr(settings, "EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    assert not email_crypto.settings_key_configured()
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.decrypt_secret(cipher)
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.encrypt_secret(OVERRIDE_KEY)
    # an unreadable override falls back to the environment key, never to a guess
    monkeypatch.setenv("RESEND_API_KEY", ENV_KEY)
    assert svc.resolve_api_key(row) == (ENV_KEY, svc.KEY_SOURCE_ENV)


def test_audit_refuses_sensitive_fields(db):
    for name in ("api_key", "resend_api_key_ciphertext", "webhook_secret", "token", "payload"):
        with pytest.raises(ValueError):
            svc.audit(db, actor_id=None, action="X", new={name: "v"})


# ===========================================================================
# ADMIN API: permissions, secrets, audit
# ===========================================================================

def test_api_requires_an_admin(client, db):
    assert client.get(f"{BASE}/overview").status_code == 401
    member = make_user(db)
    assert client.get(f"{BASE}/overview", headers=auth(member)).status_code == 403
    # the permission alone, without being an administrator, is not enough either
    not_admin = manager(db, admin=False)
    assert client.get(f"{BASE}/overview", headers=auth(not_admin)).status_code == 403
    assert client.put(f"{BASE}/master", json={"enabled": False}, headers=auth(not_admin)).status_code == 403


@pytest.mark.parametrize("permission", [None, "all", "manage_users"])
def test_ordinary_admin_can_read_but_not_change(client, db, enc_key, permission):
    admin = manager(db, permission=permission) if permission else make_user(db, admin=True)
    h = auth(admin)
    for path in ("overview", "provider", "events", "deliveries"):
        assert client.get(f"{BASE}/{path}", headers=h).status_code == 200
    assert client.get(f"{BASE}/overview", headers=h).json()["can_manage"] is False
    for method, path, body in (
        ("put", "master", {"enabled": False}),
        ("put", "emergency-stop", {"active": True, "confirmation": "STOP ALL EMAIL"}),
        ("put", "provider", {"from_name": "X"}),
        ("put", "provider/api-key", {"api_key": OVERRIDE_KEY}),
        ("delete", "provider/api-key", None),
        ("put", "events/KYC.APPROVED", {"enabled": False}),
        ("post", "test", {"recipient": "a@example.com"}),
    ):
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(f"{BASE}/{path}", headers=h, **kwargs).status_code == 403, path
    row = svc.get_settings(db)
    assert row.email_enabled and not row.emergency_stop and not row.resend_api_key_ciphertext
    assert db.query(EmailEventSetting).count() == 0 and db.query(EmailDelivery).count() == 0
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "email_settings").count() == 0


def test_manager_changes_are_applied_and_audited_without_secrets(client, db, enc_key, email_outbox):
    admin = manager(db)
    h = auth(admin)
    assert client.get(f"{BASE}/overview", headers=h).json()["can_manage"] is True

    assert client.put(f"{BASE}/master", json={"enabled": False}, headers=h).json() == {"email_enabled": False}
    # emergency stop: typed confirmation
    assert client.put(f"{BASE}/emergency-stop", json={"active": True}, headers=h).status_code == 422
    assert client.put(f"{BASE}/emergency-stop", json={"active": True, "confirmation": "stop"},
                      headers=h).status_code == 422
    assert svc.get_settings(db).emergency_stop is False
    assert client.put(f"{BASE}/emergency-stop", json={"active": True, "confirmation": "STOP ALL EMAIL"},
                      headers=h).json() == {"emergency_stop": True}
    overview = client.get(f"{BASE}/overview", headers=h).json()
    assert overview["status"] == "stopped" and overview["critical_email_active"] is False
    assert {w["code"] for w in overview["warnings"]} >= {"EMERGENCY_STOP", "MASTER_DISABLED"}
    assert client.put(f"{BASE}/emergency-stop", json={"active": False}, headers=h).status_code == 200

    # provider settings
    r = client.put(f"{BASE}/provider", headers=h, json={
        "from_name": "MyHigh5 Team", "from_address": "hello@myhigh5.com", "reply_to": "support@example.org",
        "support_address": "help@myhigh5.com", "admin_alert_recipients": ["ops@example.org", "OPS@example.org"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective_from_address"] == "hello@myhigh5.com" and body["admin_alert_recipients"] == ["ops@example.org"]
    for bad in ({"from_address": "hello@evil.example"}, {"from_address": "not-an-address"},
                {"reply_to": "a@b.com, c@d.com"}, {"from_name": "Evil\r\nBcc: x@y.z"},
                {"admin_alert_recipients": ["nope"]}):
        assert client.put(f"{BASE}/provider", headers=h, json=bad).status_code == 422, bad
    assert svc.from_header(svc.get_settings(db)) == "MyHigh5 Team <hello@myhigh5.com>"

    # API key override: stored, never returned
    r = client.put(f"{BASE}/provider/api-key", headers=h, json={"api_key": OVERRIDE_KEY})
    assert r.status_code == 200 and OVERRIDE_KEY not in r.text
    for path in ("overview", "provider", "events", "deliveries"):
        text = client.get(f"{BASE}/{path}", headers=h).text
        assert OVERRIDE_KEY not in text and ENV_KEY not in text and "ciphertext" not in text and "v1:" not in text
    view = client.get(f"{BASE}/provider", headers=h).json()
    assert view["key_source"] == "admin_override" and view["override_last4"] == "9876"
    assert view["environment_key_configured"] is True and "api_key" not in view
    assert client.delete(f"{BASE}/provider/api-key", headers=h).json()["key_source"] == "environment"

    # event switch; a critical one needs explicit confirmation
    assert client.put(f"{BASE}/events/KYC.APPROVED", headers=h, json={"enabled": False}).status_code == 200
    r = client.put(f"{BASE}/events/AUTH.PASSWORD_RESET", headers=h, json={"enabled": False})
    assert r.status_code == 409 and "CRITICAL_EVENT_CONFIRMATION_REQUIRED" in r.text
    assert svc.event_enabled(db, get_event(EmailEvent.AUTH_PASSWORD_RESET)) is True
    assert client.put(f"{BASE}/events/AUTH.PASSWORD_RESET", headers=h,
                      json={"enabled": False, "confirm_critical": True}).status_code == 200
    assert client.put(f"{BASE}/events/CONTEST.NOMINATION_PENDING_REVIEW", headers=h,
                      json={"enabled": True}).status_code == 404
    listed = {e["key"]: e for e in client.get(f"{BASE}/events", headers=h).json()["events"]}
    assert len(listed) == 53 and listed["AUTH.PASSWORD_RESET"]["enabled"] is False
    assert listed["CONTEST.NOMINATION_PUBLISHED"]["trigger_implemented"] is False
    assert "CRITICAL_EVENT_DISABLED" in {w["code"] for w in client.get(f"{BASE}/overview", headers=h).json()["warnings"]}

    # every change is audited: who / what / when, never a secret
    audits = db.query(AuditTrail).filter(AuditTrail.table_name == "email_settings").order_by(AuditTrail.id).all()
    assert [a.action for a in audits] == [
        "EMAIL_MASTER_SWITCH", "EMAIL_EMERGENCY_STOP", "EMAIL_EMERGENCY_STOP", "EMAIL_PROVIDER_UPDATE",
        "EMAIL_API_OVERRIDE_ADDED", "EMAIL_API_OVERRIDE_REMOVED", "EMAIL_EVENT_SWITCH", "EMAIL_EVENT_SWITCH"]
    assert all(a.user_id == admin.id and a.timestamp for a in audits)
    assert audits[1].new_values == {"emergency_stop": True}
    assert audits[-1].new_values == {"event": "AUTH.PASSWORD_RESET", "enabled": False, "critical": True}
    text = stored_text(db)
    assert OVERRIDE_KEY not in text and ENV_KEY not in text and "v1:" not in " ".join(
        str(a.old_values) + str(a.new_values) for a in audits)


def test_api_key_cannot_be_stored_without_the_encryption_key(client, db, monkeypatch):
    monkeypatch.delenv("EMAIL_SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    r = client.put(f"{BASE}/provider/api-key", headers=auth(manager(db)), json={"api_key": OVERRIDE_KEY})
    assert r.status_code == 409 and OVERRIDE_KEY not in r.text
    assert svc.get_settings(db).resend_api_key_ciphertext is None


# ===========================================================================
# OUTBOX
# ===========================================================================

def test_enqueue_claim_send(db, email_outbox):
    now = datetime(2026, 10, 5, 12, 0, 0)
    row = queue(db, EmailEvent.KYC_REJECTED, recipient="Jane.Member@Example.com", context={"reason": "blurry"},
                user_id=None, lang="fr", now=now)
    assert row.status == "QUEUED" and row.attempt_count == 0 and row.queued_at == now and row.lang == "fr"
    assert row.recipient_masked == "J***@E***.com" and len(row.recipient_hash) == 64
    assert "Jane.Member" not in row.payload_ciphertext and "blurry" not in row.payload_ciphertext
    assert email_crypto.decrypt_payload(row.payload_ciphertext) == {"to": "Jane.Member@Example.com",
                                                                    "context": {"reason": "blurry"}}
    summary = email_outbox.drain(now=now + timedelta(seconds=5))
    assert (summary["claimed"], summary["sent"]) == (1, 1)
    db.refresh(row)
    assert row.status == "SENT" and row.provider == "fake" and row.provider_message_id == "fake-1"
    assert row.attempt_count == 1 and row.sent_at == now + timedelta(seconds=5)
    assert row.payload_ciphertext is None and row.locked_at is None        # retention: payload purged
    message = email_outbox.provider.sent[0]
    assert message.to == "Jane.Member@Example.com" and "blurry" in message.html and message.text
    assert message.from_header == "MyHigh5 <infos@myhigh5.com>"
    assert email_outbox.drain()["claimed"] == 0                             # nothing is sent twice


def test_transient_failure_is_retried_with_backoff(db, email_outbox):
    now = datetime(2026, 10, 5, 12, 0, 0)
    email_outbox.provider.script = [
        ProviderResult(False, retryable=True, error_category=FAIL_NETWORK, error_code="ConnectionError"),
        ProviderResult(False, retryable=True, error_category="provider_rate_limited", error_code="429"),
    ]
    row = queue(db, now=now)
    assert email_outbox.drain(now=now)["retry"] == 1
    db.refresh(row)
    assert (row.status, row.attempt_count, row.failure_category) == ("QUEUED", 1, FAIL_NETWORK)
    assert row.next_attempt_at == now + timedelta(seconds=60) and row.payload_ciphertext   # kept for the retry
    assert email_outbox.drain(now=now + timedelta(seconds=30))["claimed"] == 0             # not due yet
    assert email_outbox.drain(now=now + timedelta(seconds=61))["retry"] == 1
    db.refresh(row)
    assert row.attempt_count == 2 and row.next_attempt_at == now + timedelta(seconds=61 + 120)
    assert email_outbox.drain(now=now + timedelta(seconds=400))["sent"] == 1
    db.refresh(row)
    assert (row.status, row.attempt_count, row.failure_category) == ("SENT", 3, None)
    assert [outbox_module.backoff_seconds(n) for n in (1, 2, 3, 4, 10)] == [60, 120, 240, 480, 3600]


def test_permanent_failure_is_not_retried(db, email_outbox):
    email_outbox.provider.script = [ProviderResult(False, retryable=False, error_category=FAIL_REJECTED,
                                                   error_code="422")]
    row = queue(db)
    assert email_outbox.drain()["failed"] == 1
    db.refresh(row)
    assert (row.status, row.attempt_count, row.failure_category, row.failure_code) == ("FAILED", 1, FAIL_REJECTED, "422")
    assert row.failed_at is not None and row.payload_ciphertext is None
    assert email_outbox.drain()["claimed"] == 0 and email_outbox.provider.sent == []


def test_max_attempts_ends_in_failed(db, email_outbox, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 3)
    email_outbox.provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)] * 5
    row = queue(db)
    now = datetime.utcnow()
    statuses = []
    for i in range(4):
        email_outbox.drain(now=now + timedelta(hours=2 * (i + 1)))
        db.refresh(row)
        statuses.append((row.status, row.attempt_count))
    assert statuses == [("QUEUED", 1), ("QUEUED", 2), ("FAILED", 3), ("FAILED", 3)]
    assert row.payload_ciphertext is None
    assert outbox_module.health(db)["failed_24h"] == 1 and outbox_module.health(db)["queued"] == 0


def test_a_provider_that_raises_does_not_stop_the_batch(db, email_outbox):
    class Exploding(email_providers.EmailProvider):
        name = "exploding"

        def __init__(self):
            self.calls = 0

        def send(self, message, *, api_key):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom with secret " + api_key)
            return ProviderResult(True, provider_message_id="ok")

    first, second = queue(db), queue(db)
    summary = outbox_module.process_outbox(db, provider=Exploding())
    assert (summary["claimed"], summary["retry"], summary["sent"]) == (2, 1, 1)
    db.refresh(first), db.refresh(second)
    assert first.status == "QUEUED" and first.failure_code == "RuntimeError" and second.status == "SENT"
    assert ENV_KEY not in stored_text(db)


def test_overlapping_workers_never_take_the_same_row(db, email_outbox):
    STALE_PROCESSING_AFTER, claim_batch = outbox_module.STALE_PROCESSING_AFTER, outbox_module.claim_batch
    rows = [queue(db) for _ in range(5)]
    now = datetime.utcnow()
    first = claim_batch(db, now=now, batch_size=3)
    second = claim_batch(db, now=now, batch_size=3)
    third = claim_batch(db, now=now, batch_size=3)
    assert len(first) == 3 and len(second) == 2 and third == [] and not set(first) & set(second)
    assert sorted(first + second) == sorted(r.id for r in rows)
    assert all(r.status == "PROCESSING" and r.attempt_count == 1 for r in db.query(EmailDelivery).all())
    # a second pass does not re-send rows another worker is processing ...
    assert email_outbox.drain(now=now + timedelta(minutes=1))["claimed"] == 0 and email_outbox.provider.sent == []
    # ... but a row whose worker died is recovered later
    summary = email_outbox.drain(now=now + STALE_PROCESSING_AFTER + timedelta(minutes=1))
    assert summary["requeued"] == 5 and summary["sent"] == 5


def test_account_gone_before_send_fails_cleanly(db, email_outbox):
    row = queue(db, EmailEvent.AUTH_PASSWORD_RESET, user_id=999999)
    assert email_outbox.drain()["failed"] == 1
    db.refresh(row)
    assert (row.status, row.failure_category, row.failure_code) == ("FAILED", "render_error", "recipient_gone")


def test_scheduler_is_registered_and_never_raises(monkeypatch):
    import asyncio

    from app.services.scheduler_manager import scheduler_manager

    assert "email-outbox" in scheduler_manager.list_tasks()
    calls = []
    monkeypatch.setattr(outbox_module, "run_outbox_once", lambda: calls.append(1) or {})
    asyncio.run(scheduler_manager.run_task("email-outbox"))
    assert calls == [1]
    monkeypatch.setattr(settings, "EMAIL_OUTBOX_ENABLED", False)
    asyncio.run(scheduler_manager.run_task("email-outbox"))
    assert calls == [1]


# ===========================================================================
# IDEMPOTENCY / durable limits / failure isolation
# ===========================================================================

def test_duplicate_event_produces_one_delivery(db, email_outbox):
    first = queue(db, key="kyc.approved:7:0")
    again = queue(db, key="kyc.approved:7:0")
    assert again.id == first.id and db.query(EmailDelivery).count() == 1
    assert len(email_outbox) == 1
    assert queue(db, key="kyc.approved:7:0").status == "SENT"            # still the same row after sending
    assert len(email_outbox) == 1


def test_unique_constraint_is_the_authority(db, email_outbox, monkeypatch):
    queue(db, key="race:1")
    now = datetime.utcnow()
    db.add(EmailDelivery(event_key="KYC.APPROVED", category="KYC", recipient_masked="x", status="QUEUED",
                         idempotency_key="race:1", created_at=now, updated_at=now))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    # A racing request that passed the "exists?" check still ends with ONE row and no error.
    real_query = db.query
    state = {"hidden": True}

    class _Hidden:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    def racing_query(*entities, **kw):
        if state["hidden"] and entities == (EmailDelivery,):
            state["hidden"] = False
            return _Hidden()
        return real_query(*entities, **kw)

    monkeypatch.setattr(db, "query", racing_query)
    row = queue(db, key="race:1")
    monkeypatch.undo()
    assert row is not None and row.idempotency_key == "race:1" and db.query(EmailDelivery).count() == 1


def test_per_recipient_limit_is_durable(db, email_outbox):
    statuses = [queue(db, EmailEvent.AUTH_PASSWORD_RESET, recipient="victim@example.com", user_id=1).status
                for _ in range(7)]
    assert statuses == ["QUEUED"] * 5 + ["SUPPRESSED"] * 2
    last = db.query(EmailDelivery).order_by(EmailDelivery.id.desc()).first()
    assert last.failure_category == svc.REASON_RATE_LIMITED
    assert queue(db, EmailEvent.AUTH_PASSWORD_RESET, recipient="other@example.com", user_id=2).status == "QUEUED"
    # the window slides: an hour later the address can be reached again
    later = datetime.utcnow() + timedelta(hours=1, minutes=1)
    assert queue(db, EmailEvent.AUTH_PASSWORD_RESET, recipient="victim@example.com", user_id=1,
                 now=later).status == "QUEUED"


def test_invalid_recipient_is_never_sent(db, email_outbox):
    for bad in ("", "not-an-address", "a@b", "a@b.com, c@d.com", "a@b.com\nBcc: x@y.com", "<a@b.com>"):
        row = queue(db, recipient=bad)
        assert (row.status, row.failure_category) == ("SUPPRESSED", svc.REASON_INVALID_RECIPIENT), bad
    assert len(email_outbox) == 0


def test_email_failure_never_breaks_the_caller(db, email_outbox, monkeypatch):
    user = make_user(db)
    user.bio = "committed business state"
    db.commit()
    monkeypatch.setattr(email_crypto, "encrypt_payload", lambda payload: (_ for _ in ()).throw(RuntimeError("down")))
    assert queue(db, user_id=user.id) is None                               # swallowed, logged
    db.refresh(user)
    assert user.bio == "committed business state" and db.query(EmailDelivery).count() == 0
    with pytest.raises(UnknownEmailEvent):                                  # only a programming error raises
        email_service.enqueue(db, event="NOT.AN_EVENT", recipient="a@example.com", idempotency_key="k")


# ===========================================================================
# TEMPLATES
# ===========================================================================

@pytest.mark.parametrize("event,context", [
    (EmailEvent.AFFILIATE_INVITATION, {"inviter_name": HOSTILE, "referral_code": HOSTILE, "message": HOSTILE}),
    (EmailEvent.KYC_REJECTED, {"reason": HOSTILE}),
    (EmailEvent.ADMIN_CONTACT_MESSAGE, {"name": HOSTILE, "email": "a@example.com", "subject": HOSTILE,
                                        "category": HOSTILE, "message": HOSTILE}),
    (EmailEvent.SUPPORT_CONTACT_CONFIRMATION, {"name": HOSTILE, "subject": HOSTILE, "category": HOSTILE,
                                               "message": HOSTILE}),
    (EmailEvent.ADMIN_CONTENT_REPORT, {"contestant_title": HOSTILE, "author_name": HOSTILE, "contest_name": HOSTILE,
                                       "reporter_name": HOSTILE, "reason": HOSTILE, "description": HOSTILE,
                                       "report_id": 5}),
    (EmailEvent.GUARDIAN_CONSENT_REQUEST, {"token": "tok_synthetic", "username": HOSTILE}),
    (EmailEvent.BILLING_PAYMENT_CONFIRMED, {"amount": HOSTILE, "product": HOSTILE, "reference": HOSTILE,
                                            "date": HOSTILE}),
    (EmailEvent.AUTH_PASSWORD_CHANGED, {"ip_address": HOSTILE}),
])
def test_user_values_are_escaped_in_html(db, event, context):
    subject, html, text = render(db, event_key=event.value, to="x@example.com", user_id=None, context=context,
                                 lang="en", support_email='"><script>s</script>@example.com')
    assert "<script" not in html and "<img src=x" not in html and "onerror=alert(1)>" not in html
    assert "&lt;script&gt;" in html                                        # rendered as text
    assert "\n" not in subject and "\r" not in subject
    assert text and "<p " not in text and "<div" not in text               # a real plain-text alternative
    assert str(datetime.utcnow().year) in html and "2024" not in html + text


def test_urls_are_validated_and_trusted_markup_is_not_double_escaped():
    assert tpl.safe_url("javascript:alert(1)") is None and tpl.safe_url("data:text/html,x") is None
    assert tpl.safe_url('https://a.example/x" onclick="y') is None
    assert tpl.safe_url("https://myhigh5.com/r/AB?x=1&y=2") == "https://myhigh5.com/r/AB?x=1&amp;y=2"
    html = tpl.get_base_email_template("en", "T", "<p>trusted <strong>markup</strong></p>", "Go", "javascript:x")
    assert "<strong>markup</strong>" in html and "javascript:" not in html and ">Go<" not in html
    subject, html, text = tpl.get_invitation_email("en", "Ann & Bob", "CODE1", "https://myhigh5.com/r/CODE1", "hi\nthere")
    assert "<strong style='color: #8B5CF6;'>Ann &amp; Bob</strong>" in html and "hi<br>there" in html
    assert subject == "Ann & Bob invites you to join MyHigh5!" and "<strong" not in text and "Ann & Bob invites" in text
    assert 'href="https://myhigh5.com/r/CODE1"' in html and html.count("https://myhigh5.com/r/CODE1") >= 2  # fallback URL


def test_branding_layout_and_admin_support_address(db):
    _, html, text = render(db, event_key="KYC.APPROVED", to="x@example.com", user_id=None, context={}, lang="en",
                           support_email="help@myhigh5.com")
    assert "help@myhigh5.com" in html and "/logo.png" in html and 'alt="MyHigh5"' in html
    assert f"© {datetime.utcnow().year} MyHigh5" in html and f"© {datetime.utcnow().year} MyHigh5" in text


def test_localization_and_english_fallback(db):
    subjects = {lang: render(db, event_key="KYC.APPROVED", to="x@example.com", user_id=None, context={}, lang=lang)[0]
                for lang in ("fr", "en", "es", "de", "sw", "zh", "", None, "FR-fr", "pt_BR")}
    assert len({subjects[k] for k in ("fr", "en", "es", "de")}) == 4
    assert subjects["sw"] == subjects["zh"] == subjects[""] == subjects[None] == subjects["pt_BR"] == subjects["en"]
    assert subjects["FR-fr"] == subjects["fr"]
    assert tpl.normalize_lang(None) == "en" and tpl.normalize_lang("de-AT") == "de"


# ===========================================================================
# DELIVERY LOG
# ===========================================================================

def test_delivery_log_is_masked_and_carries_no_content(client, db, email_outbox):
    user = make_user(db)
    user.hashed_password = get_password_hash("Str0ng*Passw0rd!")
    db.commit()
    queue(db, EmailEvent.AUTH_PASSWORD_RESET, recipient=user.email, user_id=user.id)
    queue(db, EmailEvent.GUARDIAN_CONSENT_REQUEST, recipient="parent.secret@example.com",
          context={"token": "raw-guardian-token-SYNTHETIC", "username": "kid"})
    email_outbox.provider.script = [ProviderResult(True, provider_message_id="msg_1"),
                                    ProviderResult(False, retryable=False, error_category=FAIL_REJECTED)]
    assert len(email_outbox) == 1
    reset_link = re.search(r"reset-password\?token=([\w\-.]+)", email_outbox[0]["html"]).group(1)
    assert verify_password_reset_token(reset_link, user.hashed_password) == user.email   # created at send time

    h = auth(make_user(db, admin=True))
    data = client.get(f"{BASE}/deliveries", headers=h).json()
    assert data["total"] == 2 and [i["status"] for i in data["items"]] == ["FAILED", "SENT"]
    sent = data["items"][1]
    assert sent["recipient"] == mask(user.email) and sent["provider_message_id"] == "msg_1" and sent["attempts"] == 1
    assert sent["event_label"] == "Password reset" and sent["category"] == "AUTH"
    assert set(data["items"][0]) == {"id", "created_at", "event_key", "event_label", "category", "recipient",
                                     "provider", "status", "attempts", "provider_message_id", "failure_category",
                                     "failure_code", "sent_at", "next_attempt_at"}
    raw = client.get(f"{BASE}/deliveries", headers=h).text
    for secret in (user.email, "parent.secret@example.com", "raw-guardian-token-SYNTHETIC", reset_link, "payload"):
        assert secret not in raw
    assert all(s not in stored_text(db) for s in ("parent.secret@example.com", "raw-guardian-token-SYNTHETIC",
                                                  reset_link))
    # filters
    assert client.get(f"{BASE}/deliveries?status=FAILED", headers=h).json()["total"] == 1
    assert client.get(f"{BASE}/deliveries?event=AUTH.PASSWORD_RESET", headers=h).json()["total"] == 1
    assert client.get(f"{BASE}/deliveries?category=guardian", headers=h).json()["total"] == 1
    assert client.get(f"{BASE}/deliveries?provider=fake", headers=h).json()["total"] == 2
    assert client.get(f"{BASE}/deliveries?date_from=2099-01-01", headers=h).json()["total"] == 0
    assert client.get(f"{BASE}/deliveries?status=NOPE", headers=h).status_code == 422
    stats = client.get(f"{BASE}/overview", headers=h).json()["stats"]
    assert (stats["sent_24h"], stats["failed_24h"], stats["queued"]) == (1, 1, 0)


def mask(address: str) -> str:
    from app.core.redaction import mask_email

    return mask_email(address)


# ===========================================================================
# TEST EMAIL
# ===========================================================================

def test_test_email_single_recipient_logged_and_audited(client, db, email_outbox):
    admin = manager(db)
    h = auth(admin)
    for bad in ("a@example.com, b@example.com", "a@example.com;b@example.com", "nope", ["a@example.com"]):
        assert client.post(f"{BASE}/test", headers=h, json={"recipient": bad}).status_code == 422
    assert client.post(f"{BASE}/test", headers=h, json={"recipients": ["a@example.com"]}).status_code == 422
    assert db.query(EmailDelivery).count() == 0 and email_outbox.provider.sent == []

    r = client.post(f"{BASE}/test", headers=h, json={"recipient": "ops.person@example.com"})
    assert r.status_code == 200 and r.json()["success"] is True and "ops.person" not in r.text
    assert ENV_KEY not in r.text
    assert len(email_outbox.provider.sent) == 1                                  # sent right away, exactly once
    message = email_outbox.provider.sent[0]
    assert message.to == "ops.person@example.com" and message.subject.startswith("[TEST]") and "TEST" in message.html
    row = db.query(EmailDelivery).one()
    assert (row.event_key, row.status, row.user_id, row.payload_ciphertext) == (TEST_EMAIL_KEY, "SENT", admin.id, None)
    audit = db.query(AuditTrail).filter(AuditTrail.action == "EMAIL_TEST_SENT").one()
    assert audit.user_id == admin.id and audit.new_values["recipient"] == mask("ops.person@example.com")
    assert "ops.person@example.com" not in stored_text(db)

    # a failing provider gives a clear, safe result
    email_outbox.provider.script = [ProviderResult(False, error_category="provider_auth", error_code="403")]
    r = client.post(f"{BASE}/test", headers=h, json={"recipient": "ops.person@example.com"})
    assert r.json()["success"] is False and r.json()["failure_category"] == "provider_auth"
    # blocked by the emergency stop, and independent of the normal master switch
    row = svc.get_settings_for_update(db)
    row.email_enabled = False
    db.commit()
    assert client.post(f"{BASE}/test", headers=h, json={"recipient": "a@example.com"}).json()["success"] is True
    row.emergency_stop = True
    db.commit()
    blocked = client.post(f"{BASE}/test", headers=h, json={"recipient": "a@example.com"}).json()
    assert (blocked["success"], blocked["failure_category"]) == (False, "emergency_stop")


# ===========================================================================
# EXISTING FLOWS now routed through the central service
# ===========================================================================

def _events(db):
    return [r.event_key for r in db.query(EmailDelivery).order_by(EmailDelivery.id).all()]


def test_registration_sends_the_welcome_verification_email(client, db, email_outbox, test_user_data):
    assert client.post("/api/v1/auth/register?lang=fr", json=test_user_data).status_code == 201
    assert _events(db) == ["AUTH.EMAIL_VERIFICATION"]
    row = db.query(EmailDelivery).one()
    user = db.query(User).filter(User.email == test_user_data["email"]).one()
    assert (row.user_id, row.lang, row.idempotency_key) == (user.id, "fr", f"auth.email_verification:user:{user.id}")
    mail = email_outbox[0]
    assert mail["to"] == test_user_data["email"] and "Bienvenue" in mail["subject"]
    token = re.search(r"/verify-email\?token=([\w\-.]+)", mail["html"]).group(1)
    assert verify_email_verification_token(token) == test_user_data["email"]
    assert token not in stored_text(db)                                     # the token is never stored
    assert client.post(f"/api/v1/auth/verify-email?token={token}").status_code == 200
    db.refresh(user)
    assert user.email_verified is True


def test_password_reset_and_password_changed(client, db, email_outbox, test_user_data):
    client.post("/api/v1/auth/register", json=test_user_data)
    email = test_user_data["email"]
    for _ in range(2):                                                      # double submit in the same minute
        assert client.post("/api/v1/auth/password-reset-request", json={"email": email}).status_code == 200
    # unknown address: same answer, nothing recorded
    r = client.post("/api/v1/auth/password-reset-request", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert _events(db) == ["AUTH.EMAIL_VERIFICATION", "AUTH.PASSWORD_RESET"]
    mail = email_outbox[-1]
    token = re.search(r"/reset-password\?token=([\w\-.]+)", mail["html"]).group(1)
    r = client.post("/api/v1/auth/password-reset-confirm", json={"token": token, "new_password": "N3w*Passw0rd!x"})
    assert r.status_code == 200, r.text
    assert _events(db)[-1] == "AUTH.PASSWORD_CHANGED"
    assert "MyHigh5" in email_outbox[-1]["subject"] and email_outbox[-1]["to"] == email
    # the used link is dead (bound to the old password)
    assert client.post("/api/v1/auth/password-reset-confirm",
                       json={"token": token, "new_password": "An0ther*Passw0rd!"}).status_code == 400
    # change-password also notifies, once per new password
    login = client.post("/api/v1/auth/login", data={"username": email, "password": "N3w*Passw0rd!x"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = client.post("/api/v1/auth/change-password", headers=h,
                    json={"current_password": "N3w*Passw0rd!x", "new_password": "Third*Passw0rd!9"})
    assert r.status_code == 200, r.text
    assert _events(db).count("AUTH.PASSWORD_CHANGED") == 2 and len(email_outbox) == 4


def test_contact_form_sends_two_emails_once(client, db, email_outbox):
    payload = {"name": HOSTILE, "email": "sender@example.com", "subject": "Hello <b>there</b>",
               "category": "general", "message": "line 1\n" + HOSTILE}
    r = client.post("/api/v1/contact", json=payload, headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert r.status_code == 201, r.text
    assert _events(db) == ["ADMIN.CONTACT_MESSAGE", "SUPPORT.CONTACT_CONFIRMATION"]
    to_support, to_sender = email_outbox[0], email_outbox[1]
    assert to_support["to"] == "infos@myhigh5.com" and to_support["subject"].startswith("[MyHigh5 Contact]")
    assert to_sender["to"] == "sender@example.com"
    for mail in (to_support, to_sender):
        assert "<script" not in mail["html"] and "&lt;script&gt;" in mail["html"]
    # the support address follows Admin > Email Settings
    svc.get_settings_for_update(db).support_address = "help@myhigh5.com"
    db.commit()
    client.post("/api/v1/contact", json={**payload, "email": "second@example.com"})
    assert email_outbox[2]["to"] == "help@myhigh5.com"


def test_contact_and_newsletter_cannot_flood_a_mailbox(client, db, email_outbox):
    from app.core.rate_limit import _buckets

    body = {"name": "A", "email": "victim@example.com", "subject": "s", "category": "general", "message": "m"}
    codes = [client.post("/api/v1/contact", json=body).status_code for _ in range(7)]
    assert codes == [201] * 5 + [429] * 2                                   # per-IP route limit
    _buckets.clear()                                                        # the attacker changes IP ...
    for _ in range(3):
        client.post("/api/v1/contact", json=body)
    confirmations = db.query(EmailDelivery).filter(EmailDelivery.event_key == "SUPPORT.CONTACT_CONFIRMATION").all()
    assert [c.status for c in confirmations].count("QUEUED") == 3           # ... the durable limit still holds
    assert all(c.failure_category == "rate_limited" for c in confirmations if c.status == "SUPPRESSED")

    _buckets.clear()
    for _ in range(4):
        assert client.post("/api/v1/newsletter/subscribe", json={"email": "victim@example.com"}).status_code == 201
    newsletter = db.query(EmailDelivery).filter(EmailDelivery.event_key == "SUPPORT.NEWSLETTER_CONFIRMATION").all()
    assert len(newsletter) == 1                                             # one confirmation per subscription and day


def test_referral_invitation_is_capped_per_member(client, db, email_outbox):
    inviter = make_user(db, personal_referral_code="REF12345", first_name="Ina", last_name="Viter",
                        preferred_language="es")
    h = auth(inviter)
    r = client.post("/api/v1/affiliates/invitations", headers=h,
                    json={"email": "friend@example.com", "message": HOSTILE})
    assert r.status_code == 200, r.text
    row = db.query(EmailDelivery).one()
    assert (row.event_key, row.user_id, row.lang) == ("AFFILIATE.INVITATION", inviter.id, "es")
    assert row.idempotency_key == f"affiliate.invitation:{r.json()['invitation_id']}"
    mail = email_outbox[0]
    assert mail["to"] == "friend@example.com" and "/r/REF12345" in mail["html"] and "<script" not in mail["html"]
    assert "Ina Viter" in mail["subject"]
    # bulk stays limited to 10 addresses per request
    many = [f"f{i}@example.com" for i in range(11)]
    assert client.post("/api/v1/affiliates/invitations/bulk", headers=h, json={"emails": many}).status_code == 422
    # durable daily cap per member
    now = datetime.utcnow()
    for i in range(INVITATIONS_PER_DAY - 2):
        db.add(EmailDelivery(event_key="AFFILIATE.INVITATION", category="AFFILIATE", user_id=inviter.id,
                             recipient_masked="x", status="SENT", idempotency_key=f"seed:{i}", created_at=now,
                             updated_at=now))
    db.commit()
    r = client.post("/api/v1/affiliates/invitations/bulk", headers=h,
                    json={"emails": ["b1@example.com", "b2@example.com", "b3@example.com"]})
    assert [x["success"] for x in r.json()] == [True, False, False]
    assert r.json()[1]["message"] == "Daily invitation limit reached"
    assert client.post("/api/v1/affiliates/invitations", headers=h,
                       json={"email": "late@example.com"}).status_code == 429


def test_kyc_decisions_notify_the_member(client, db, email_outbox):
    from app.models.kyc import KYCStatus, KYCVerification

    admin = make_user(db, admin=True)
    approved, rejected = make_user(db, preferred_language="de"), make_user(db)
    rows = []
    for member in (approved, rejected):
        v = KYCVerification(user_id=member.id, status=KYCStatus.PENDING)
        db.add(v)
        rows.append(v)
    db.commit()
    r = client.post(f"/api/v1/kyc/admin/verification/{rows[0].id}/approve", headers=auth(admin))
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/kyc/admin/verification/{rows[1].id}/reject", headers=auth(admin),
                    data={"reason": "Document <b>unreadable</b>"})
    assert r.status_code == 200, r.text
    assert _events(db) == ["KYC.APPROVED", "KYC.REJECTED"]
    first, second = email_outbox[0], email_outbox[1]
    assert first["to"] == approved.email and "KYC" in first["subject"] and "Ihre" in first["html"]   # member's language
    assert second["to"] == rejected.email and "Document &lt;b&gt;unreadable&lt;/b&gt;" in second["html"]
    db.refresh(rows[0])
    assert rows[0].status == KYCStatus.APPROVED                                # the decision itself is unchanged


def test_guardian_emails_use_the_layout_and_keep_the_token_out_of_storage(db, email_outbox):
    from app.services import guardian_notifications as gn

    assert gn.send_guardian_request_email(db, "parent@example.com", "raw-token-SYNTHETIC-1", "<b>kid</b>") is True
    gn.send_guardian_request_email(db, "parent@example.com", "raw-token-SYNTHETIC-1", "kid")   # same token: once
    assert db.query(EmailDelivery).count() == 1
    assert gn.send_completion_email(db, "minor@example.com", "raw-token-SYNTHETIC-2") is True
    assert "raw-token-SYNTHETIC" not in stored_text(db)                       # encrypted while queued
    request, completion = email_outbox[0], email_outbox[1]
    assert "/guardian/consent#token=raw-token-SYNTHETIC-1" in request["html"] and "&lt;b&gt;kid&lt;/b&gt;" in request["html"]
    assert "/register/complete#token=raw-token-SYNTHETIC-2" in completion["html"]
    assert request["text"] and "raw-token-SYNTHETIC-1" in request["text"]
    assert "raw-token-SYNTHETIC" not in stored_text(db)                       # purged once sent


def test_content_report_goes_to_configured_recipients(db, email_outbox):
    context = {"contestant_title": "Entry", "author_name": "Author", "contest_name": "Contest",
               "reporter_name": "Reporter", "reason": "spam", "description": "ten characters", "report_id": 12}
    queue(db, EmailEvent.ADMIN_CONTENT_REPORT, recipient="ops@example.org", context=context,
          key="admin.content_report:12:0")
    mail = email_outbox[0]
    assert mail["to"] == "ops@example.org" and "/admin/reports/12" in mail["html"] and "#12" in mail["html"]


def test_payment_confirmation_is_queued_and_cannot_undo_the_payment(world, email_outbox, monkeypatch):
    from app.models.payment import Deposit
    from app.services.commission_distribution import process_payment_validation
    from tests.unit.test_new_business_model import _deposit

    db = world
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False)
    buyer = make_user(db, preferred_language="es")
    deposit = _deposit(db, buyer, "annual_membership")
    db.commit()
    assert process_payment_validation(db, deposit) is True
    assert process_payment_validation(db, deposit) is True                     # webhook / scheduler retry
    rows = db.query(EmailDelivery).all()
    assert [(r.event_key, r.idempotency_key, r.user_id) for r in rows] == [
        ("BILLING.PAYMENT_CONFIRMED", f"billing.payment_confirmed:deposit:{deposit.id}", buyer.id)]
    mail = email_outbox[0]
    assert mail["to"] == buyer.email and "$50.00" in mail["html"] and len(email_outbox) == 1

    # an email system that is down does not fail or roll back a payment
    other = _deposit(db, make_user(db), "annual_membership")
    db.commit()
    monkeypatch.setattr(email_crypto, "encrypt_payload", lambda payload: (_ for _ in ()).throw(RuntimeError("down")))
    assert process_payment_validation(db, other) is True
    db.expire_all()
    assert db.query(Deposit).filter(Deposit.id == other.id).one().status.value == "validated"
    assert db.query(EmailDelivery).count() == 1
