"""EMAIL-1 hardening (pre-deployment).

* EMAIL_SETTINGS_ENCRYPTION_KEY is the only email encryption key: no fallback
  to SECRET_KEY, a missing key is "configuration required", never plaintext.
* One outbox executor per deployment mode (USE_CELERY).
* Bounded recovery of rows left PROCESSING by a dead worker.
* Idempotency: one row per logical email; retries happen on that row.
* Permission bootstrap with the existing role / permission model.
* Relay ceilings, test-email and template safety.

All values are SYNTHETIC; no test contacts Resend.
"""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.email import EmailDelivery
from app.models.payment import Deposit
from app.models.user import Permission, Role
from app.scripts import grant_email_settings_permission as grant_tool
from app.services import email as email_module
from app.services import email_crypto, email_settings_service as svc
from app.services import email_outbox as outbox_module
from app.services import email_templates as tpl
from app.services.email import GLOBAL_EVENT_LIMITS, email_service
from app.services.email_events import EMAIL_EVENTS, EmailEvent
from app.services.email_providers import FAIL_NETWORK, ProviderResult
from app.services.email_render import render
from tests.unit.test_age_gate_registration import auth, make_user
from tests.unit.test_email_foundation import BASE, ENV_KEY, OVERRIDE_KEY, manager, queue, stored_text
from tests.unit.test_new_business_model import world  # noqa: F401  (fixture)


@pytest.fixture
def no_encryption_key(monkeypatch):
    monkeypatch.delenv("EMAIL_SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "EMAIL_SETTINGS_ENCRYPTION_KEY", "")


# ===========================================================================
# 1. the dedicated key is the ONLY key
# ===========================================================================

def test_email_crypto_never_touches_secret_key(monkeypatch, no_encryption_key):
    source = inspect.getsource(email_crypto)
    code = "\n".join(line for line in source.split("\n") if not line.strip().startswith(("#", "*"))
                     and "NO fallback" not in line)
    assert "SECRET_KEY" not in code and "MASTER_ENCRYPTION_KEY" not in code
    # SECRET_KEY is set in the test environment, and still nothing can be encrypted or decrypted.
    assert settings.SECRET_KEY
    for call in (lambda: email_crypto.encrypt_payload({"to": "a@example.com"}),
                 lambda: email_crypto.decrypt_payload("v1:AAAA"),
                 lambda: email_crypto.encrypt_secret("x" * 20),
                 lambda: email_crypto.decrypt_secret("v1:AAAA")):
        with pytest.raises(email_crypto.EmailCryptoError):
            call()
    assert email_crypto.recipient_hash("a@example.com") is None
    # a key that is too short is not a key
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "short")
    assert not email_crypto.settings_key_configured()
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.encrypt_payload({})


def test_payload_from_one_key_cannot_be_read_with_secret_key_or_another_key(monkeypatch):
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "synthetic-dedicated-email-key-AAAAAAAAAAAA")
    token = email_crypto.encrypt_payload({"to": "a@example.com"})
    assert email_crypto.decrypt_payload(token) == {"to": "a@example.com"}
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", settings.SECRET_KEY)        # SECRET_KEY is not the key
    with pytest.raises(email_crypto.EmailCryptoError):
        email_crypto.decrypt_payload(token)


def test_missing_key_stores_no_plaintext_and_reports_configuration_required(client, db, email_outbox,
                                                                            no_encryption_key, test_user_data):
    # an unrelated flow that triggers an email still works
    assert client.post("/api/v1/auth/register", json=test_user_data).status_code == 201
    from tests.conftest import confirm_email

    confirm_email(db, test_user_data["email"])       # (the verification email could not be queued: no key)
    assert client.post("/api/v1/auth/login", data={"username": test_user_data["email"],
                                                   "password": test_user_data["password"]}).status_code == 200
    assert client.post("/api/v1/auth/password-reset-request",
                       json={"email": test_user_data["email"]}).status_code == 200
    assert client.post("/api/v1/contact", json={"name": "N", "email": "visitor.plain@example.com", "subject": "s",
                                                "category": "general", "message": "secret message body"}
                       ).status_code == 201
    assert client.get("/api/v1/auth/health").status_code == 200
    rows = db.query(EmailDelivery).all()
    assert len(rows) == 4
    assert all((r.status, r.failure_category, r.payload_ciphertext, r.recipient_hash) ==
               ("FAILED", svc.REASON_ENCRYPTION_UNCONFIGURED, None, None) for r in rows)
    text = stored_text(db)
    for plaintext in (test_user_data["email"], "visitor.plain@example.com", "secret message body"):
        assert plaintext not in text
    assert email_outbox.drain()["claimed"] == 0 and email_outbox.provider.sent == []

    # Admin status: clear "configuration required"
    h = auth(make_user(db, admin=True))
    overview = client.get(f"{BASE}/overview", headers=h).json()
    assert overview["status"] == "configuration_required" and overview["encryption_key_configured"] is False
    assert overview["critical_email_active"] is False
    warning = next(w for w in overview["warnings"] if w["code"] == "ENCRYPTION_KEY_MISSING")
    assert warning["level"] == "critical" and "EMAIL_SETTINGS_ENCRYPTION_KEY" in warning["message"]
    assert "synthetic" not in str(overview) and ENV_KEY not in str(overview)
    # the API-key override still REQUIRES the dedicated key
    r = client.put(f"{BASE}/provider/api-key", headers=auth(manager(db)), json={"api_key": OVERRIDE_KEY})
    assert r.status_code == 409 and svc.get_settings(db).resend_api_key_ciphertext is None


def test_configuring_the_key_restores_queueing_on_the_same_row(db, email_outbox, monkeypatch):
    monkeypatch.delenv("EMAIL_SETTINGS_ENCRYPTION_KEY")
    monkeypatch.setattr(settings, "EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    failed = queue(db, key="kyc.approved:1:0")
    assert (failed.status, failed.failure_category) == ("FAILED", svc.REASON_ENCRYPTION_UNCONFIGURED)
    assert queue(db, key="kyc.approved:1:0").status == "FAILED"            # still not configured: unchanged
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "synthetic-dedicated-email-key-BBBBBBBBBBBB")
    again = queue(db, key="kyc.approved:1:0")
    assert again.id == failed.id and again.status == "QUEUED" and again.failure_category is None
    assert db.query(EmailDelivery).count() == 1                             # never a second row
    assert len(email_outbox) == 1
    assert queue(db, key="kyc.approved:1:0").status == "SENT" and len(email_outbox) == 1
    assert queue(db, key="other").status == "QUEUED"                        # new email queues normally


def test_key_removed_after_queueing_fails_the_delivery_cleanly(db, email_outbox, monkeypatch):
    row = queue(db)
    assert row.status == "QUEUED"
    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "synthetic-dedicated-email-key-CCCCCCCCCCCC")
    assert email_outbox.drain()["failed"] == 1
    db.refresh(row)
    assert (row.status, row.failure_category, row.payload_ciphertext) == ("FAILED", "encryption_unavailable", None)


# ===========================================================================
# 2. Resend key resolution (re-verified end to end through the API)
# ===========================================================================

def test_override_then_environment_fallback_through_the_api(client, db, email_outbox, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    h = auth(manager(db))
    assert client.get(f"{BASE}/provider", headers=h).json()["key_source"] == "environment"
    assert client.put(f"{BASE}/provider/api-key", headers=h, json={"api_key": OVERRIDE_KEY}).status_code == 200
    assert client.get(f"{BASE}/provider", headers=h).json()["key_source"] == "admin_override"
    client.post(f"{BASE}/test", headers=h, json={"recipient": "a@example.com"})
    assert client.delete(f"{BASE}/provider/api-key", headers=h).json()["key_source"] == "environment"
    client.post(f"{BASE}/test", headers=h, json={"recipient": "a@example.com"})
    assert email_outbox.provider.api_keys == [OVERRIDE_KEY, ENV_KEY]
    row = svc.get_settings(db)
    assert row.resend_api_key_ciphertext is None and row.resend_api_key_last4 is None
    for path in ("overview", "provider", "events", "deliveries"):
        body = client.get(f"{BASE}/{path}", headers=h).text
        assert OVERRIDE_KEY not in body and ENV_KEY not in body
    assert OVERRIDE_KEY not in caplog.text and ENV_KEY not in caplog.text
    assert OVERRIDE_KEY not in stored_text(db) and ENV_KEY not in stored_text(db)


# ===========================================================================
# 3. one outbox executor per deployment mode
# ===========================================================================

@pytest.mark.parametrize("use_celery,scheduler_runs,celery_runs", [
    ("false", 1, 0), ("", 1, 0), ("true", 0, 1), ("1", 0, 1),
])
def test_exactly_one_executor_drains_the_outbox(monkeypatch, use_celery, scheduler_runs, celery_runs):
    from app.services.scheduler_manager import scheduler_manager
    from app.tasks import email_outbox as celery_task

    monkeypatch.setenv("USE_CELERY", use_celery)
    calls = {"scheduler": 0, "celery": 0}
    monkeypatch.setattr(outbox_module, "run_outbox_once", lambda: calls.__setitem__("scheduler", calls["scheduler"] + 1) or {})
    monkeypatch.setattr(celery_task, "run_outbox_once", lambda: calls.__setitem__("celery", calls["celery"] + 1) or {})
    assert "email-outbox" in scheduler_manager.list_tasks()
    asyncio.run(scheduler_manager.run_task("email-outbox"))
    celery_task.drain_email_outbox.run()
    assert (calls["scheduler"], calls["celery"]) == (scheduler_runs, celery_runs)
    assert calls["scheduler"] + calls["celery"] == 1                        # never none, never both
    assert outbox_module.outbox_executor() == ("celery" if celery_runs else "scheduler")


def test_executor_wiring_and_kill_switch(monkeypatch):
    import main
    from app.celery_app import celery_app
    from app.tasks import email_outbox as celery_task

    # the in-process schedulers are only started when USE_CELERY is not set
    lifespan = inspect.getsource(main.lifespan)
    assert "if use_celery:" in lifespan and "scheduler_manager.start" in lifespan
    assert celery_app.conf.beat_schedule["drain-email-outbox"]["task"] == celery_task.drain_email_outbox.name
    assert "app.tasks.email_outbox" in celery_app.conf.include
    # EMAIL_OUTBOX_ENABLED=false stops both
    monkeypatch.setattr(settings, "EMAIL_OUTBOX_ENABLED", False)
    monkeypatch.setattr(celery_task, "run_outbox_once", lambda: pytest.fail("must not run"))
    monkeypatch.setattr(outbox_module, "run_outbox_once", lambda: pytest.fail("must not run"))
    monkeypatch.setenv("USE_CELERY", "true")
    assert celery_task.drain_email_outbox.run() == {"enabled": False}
    monkeypatch.setenv("USE_CELERY", "false")
    asyncio.run(outbox_module.EmailOutboxScheduler()._drain_outbox())


def test_overview_reports_a_stalled_outbox(client, db, email_outbox):
    h = auth(make_user(db, admin=True))
    queue(db, now=datetime.utcnow() - timedelta(minutes=30))
    overview = client.get(f"{BASE}/overview", headers=h).json()
    assert overview["stats"]["oldest_due_seconds"] > 1700 and overview["outbox_executor"] in ("celery", "scheduler")
    assert "OUTBOX_STALLED" in {w["code"] for w in overview["warnings"]}
    email_outbox.drain()
    overview = client.get(f"{BASE}/overview", headers=h).json()
    assert overview["stats"]["oldest_due_seconds"] == 0
    assert "OUTBOX_STALLED" not in {w["code"] for w in overview["warnings"]}


# ===========================================================================
# 9. stale PROCESSING recovery is bounded
# ===========================================================================

def test_stale_claims_are_recovered_and_bounded(db, email_outbox, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 2)
    row = queue(db)
    t0 = datetime.utcnow()
    stale = outbox_module.STALE_PROCESSING_AFTER + timedelta(minutes=1)
    # worker 1 claims the row and dies before the provider answers
    assert outbox_module.claim_batch(db, now=t0, batch_size=5) == [row.id]
    db.refresh(row)
    assert (row.status, row.attempt_count) == ("PROCESSING", 1)
    # not stale yet: nobody touches it
    assert outbox_module.process_outbox(db, now=t0 + timedelta(minutes=5), provider=email_outbox.provider)["requeued"] == 0
    # worker 2 dies the same way after the row was recovered once
    assert outbox_module._requeue_stale(db, t0 + stale) == 1
    assert outbox_module.claim_batch(db, now=t0 + stale, batch_size=5) == [row.id]
    db.refresh(row)
    assert (row.status, row.attempt_count) == ("PROCESSING", 2)
    # attempts exhausted: the row ends FAILED instead of looping or staying PROCESSING forever
    summary = outbox_module.process_outbox(db, now=t0 + stale + stale, provider=email_outbox.provider)
    db.refresh(row)
    assert (row.status, row.failure_category, row.payload_ciphertext, row.locked_at) == \
        ("FAILED", "stale_claim", None, None)
    assert summary["claimed"] == 0 and email_outbox.provider.sent == []
    assert db.query(EmailDelivery).filter(EmailDelivery.status == "PROCESSING").count() == 0


# ===========================================================================
# 5 / 9. idempotency: retry the same delivery, never a second logical one
# ===========================================================================

def test_retry_reuses_the_delivery_and_a_new_trigger_never_duplicates(db, email_outbox):
    now = datetime.utcnow()
    email_outbox.provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)]
    row = queue(db, key="billing.payment_confirmed:deposit:77", now=now)
    email_outbox.drain(now=now)
    assert queue(db, key="billing.payment_confirmed:deposit:77").id == row.id     # trigger again while retrying
    email_outbox.drain(now=now + timedelta(minutes=2))
    db.refresh(row)
    assert (row.status, row.attempt_count) == ("SENT", 2)
    assert db.query(EmailDelivery).count() == 1 and len(email_outbox.provider.sent) == 1
    # after it was sent, the same trigger does nothing; a finally FAILED send is not re-armed either
    assert queue(db, key="billing.payment_confirmed:deposit:77").status == "SENT"
    email_outbox.provider.script = [ProviderResult(False, retryable=False, error_category="provider_rejected")]
    dead = queue(db, key="billing.payment_confirmed:deposit:78")
    email_outbox.drain()
    assert queue(db, key="billing.payment_confirmed:deposit:78").status == "FAILED"
    db.refresh(dead)
    assert dead.attempt_count == 1 and len(email_outbox.provider.sent) == 1
    # a SUPPRESSED email (switched off) is never re-armed by a later trigger
    svc.get_settings_for_update(db).email_enabled = False
    db.commit()
    off = queue(db, key="kyc.approved:5:0")
    svc.get_settings_for_update(db).email_enabled = True
    db.commit()
    assert queue(db, key="kyc.approved:5:0").id == off.id and off.status == "SUPPRESSED"
    assert email_outbox.drain()["claimed"] == 0


def test_payment_confirmation_transport_only(world, email_outbox, monkeypatch):
    """Payment state is authoritative; the confirmation is one delivery per
    deposit, retried on the same row; a deferred settlement sends nothing."""
    from app.models.affiliate import AffiliateCommission
    from app.services.commission_distribution import process_payment_validation
    from tests.unit.test_new_business_model import _deposit, _register

    db = world
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False)
    sponsor = _register(db, "sponsorh@example.com")
    buyer = _register(db, "buyerh@example.com", sponsor.personal_referral_code)
    deposit = _deposit(db, buyer, "annual_membership")
    db.commit()

    # deferred settlement (webhook path): unchanged, no email at all
    assert process_payment_validation(db, deposit, defer_commit=True) is True
    db.commit()
    assert db.query(EmailDelivery).count() == 0
    commissions = [(c.user_id, c.source_user_id, str(c.commission_amount)) for c in db.query(AffiliateCommission).all()]
    assert len(commissions) == 1

    # non-deferred call + provider trouble: the SAME delivery is retried
    email_outbox.provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)]
    assert process_payment_validation(db, deposit) is True
    now = datetime.utcnow()
    assert email_outbox.drain(now=now)["retry"] == 1
    for _ in range(3):                                                       # reconciliation / scheduler retries
        assert process_payment_validation(db, deposit) is True
    email_outbox.drain(now=now + timedelta(minutes=5))
    rows = db.query(EmailDelivery).all()
    assert [(r.event_key, r.status, r.attempt_count) for r in rows] == [("BILLING.PAYMENT_CONFIRMED", "SENT", 2)]
    assert len(email_outbox.provider.sent) == 1
    # nothing financial moved because of the email layer
    assert [(c.user_id, c.source_user_id, str(c.commission_amount))
            for c in db.query(AffiliateCommission).all()] == commissions
    assert db.query(Deposit).filter(Deposit.id == deposit.id).one().status.value == "validated"


# ===========================================================================
# 4. permission bootstrap
# ===========================================================================

def test_grant_tool_is_dry_run_by_default_and_least_privilege(client, db, email_outbox):
    all_perm = Permission(name="all", category="admin")
    admin_role = Role(name="admin", permissions=[all_perm])
    db.add_all([admin_role, Permission(name=svc.PERMISSION_MANAGE_EMAIL_SETTINGS, category="admin")])
    db.flush()
    chosen = make_user(db, admin=True, role_id=admin_role.id)
    other = make_user(db, admin=True, role_id=admin_role.id)
    member = make_user(db)

    # dry run: nothing changes
    result = grant_tool.grant(db, chosen.email)
    assert (result.action, result.applied, result.role_name) == ("granted", False, "email_settings_manager_admin")
    db.refresh(chosen)
    assert chosen.role_id == admin_role.id and not svc.can_manage_email_settings(chosen)
    assert db.query(Role).count() == 1
    assert client.put(f"{BASE}/master", json={"enabled": False}, headers=auth(chosen)).status_code == 403

    # refused for a non-admin or an unknown account
    for email in (member.email, "nobody@example.com"):
        with pytest.raises(grant_tool.GrantError):
            grant_tool.grant(db, email, apply=True)

    # applied: only the chosen admin, who keeps every existing permission
    assert grant_tool.grant(db, chosen.email, apply=True).applied is True
    db.refresh(chosen), db.refresh(other)
    assert svc.can_manage_email_settings(chosen) and chosen.role.has_permission("all") and chosen.is_admin
    assert not svc.can_manage_email_settings(other) and other.role_id == admin_role.id
    assert svc.PERMISSION_MANAGE_EMAIL_SETTINGS not in admin_role.get_all_permissions()   # shared role untouched
    assert grant_tool.grant(db, chosen.email, apply=True).action == "already_granted"
    audit = db.query(AuditTrail).filter(AuditTrail.action == "EMAIL_PERMISSION_GRANTED").one()
    assert audit.record_id == chosen.id and audit.new_values["role"] == "email_settings_manager_admin"

    # the API follows the permission
    assert client.put(f"{BASE}/master", json={"enabled": False}, headers=auth(chosen)).status_code == 200
    assert client.put(f"{BASE}/emergency-stop", json={"active": True, "confirmation": "STOP ALL EMAIL"},
                      headers=auth(chosen)).status_code == 200
    for method, path, body in (("put", "master", {"enabled": True}),
                               ("put", "emergency-stop", {"active": False}),
                               ("put", "provider/api-key", {"api_key": OVERRIDE_KEY}),
                               ("delete", "provider/api-key", None)):
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(f"{BASE}/{path}", headers=auth(other), **kwargs).status_code == 403
        assert getattr(client, method)(f"{BASE}/{path}", headers=auth(member), **kwargs).status_code == 403
    assert client.get(f"{BASE}/overview", headers=auth(other)).status_code == 200          # admins may read
    assert client.get(f"{BASE}/overview", headers=auth(member)).status_code == 403         # members may not
    assert svc.get_settings(db).emergency_stop is True

    # revoke returns the account to its former role
    assert grant_tool.revoke(db, chosen.email).applied is False
    assert grant_tool.revoke(db, chosen.email, apply=True).applied is True
    db.refresh(chosen)
    assert chosen.role_id == admin_role.id and not svc.can_manage_email_settings(chosen)
    assert client.put(f"{BASE}/master", json={"enabled": True}, headers=auth(chosen)).status_code == 403


def test_grant_through_the_existing_rbac_api(client, db):
    perms = {n: Permission(name=n, category="admin") for n in ("all", svc.PERMISSION_MANAGE_EMAIL_SETTINGS)}
    admin_role = Role(name="admin", permissions=[perms["all"]])
    db.add_all([admin_role, *perms.values()])
    db.flush()
    root = make_user(db, admin=True, role_id=admin_role.id)
    target = make_user(db, admin=True, role_id=admin_role.id)
    h = auth(root)
    r = client.post("/api/v1/rbac/roles", headers=h, json={
        "name": "email_settings_manager_admin", "inherit_from_id": admin_role.id,
        "permission_ids": [perms[svc.PERMISSION_MANAGE_EMAIL_SETTINGS].id]})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/rbac/users/assign-role", headers=h, json={"user_id": target.id, "role_id": r.json()["id"]})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert svc.can_manage_email_settings(target) and not svc.can_manage_email_settings(root)
    assert client.put(f"{BASE}/master", json={"enabled": False}, headers=auth(target)).status_code == 200
    assert client.put(f"{BASE}/master", json={"enabled": True}, headers=h).status_code == 403


# ===========================================================================
# 12. relay ceilings
# ===========================================================================

def test_anonymous_senders_have_a_platform_wide_ceiling(db, email_outbox):
    assert set(GLOBAL_EVENT_LIMITS) == {"SUPPORT.CONTACT_CONFIRMATION", "SUPPORT.NEWSLETTER_CONFIRMATION"}
    limit, _window = GLOBAL_EVENT_LIMITS["SUPPORT.CONTACT_CONFIRMATION"]
    now = datetime.utcnow()
    for i in range(limit):                                                  # distinct victims, distinct "IPs"
        db.add(EmailDelivery(event_key="SUPPORT.CONTACT_CONFIRMATION", category="SUPPORT", recipient_masked="x",
                             status="SENT", idempotency_key=f"seed:{i}", created_at=now, updated_at=now))
    db.commit()
    blocked = queue(db, EmailEvent.SUPPORT_CONTACT_CONFIRMATION, recipient="victim@example.com",
                    context={"name": "n", "subject": "s", "category": "general", "message": "m"})
    assert (blocked.status, blocked.failure_category) == ("SUPPRESSED", svc.REASON_RATE_LIMITED_GLOBAL)
    # other mail (security, account) is not affected by that ceiling
    assert queue(db, EmailEvent.AUTH_PASSWORD_CHANGED, recipient="member@example.com").status == "QUEUED"
    later = now + timedelta(hours=1, minutes=1)
    assert queue(db, EmailEvent.SUPPORT_CONTACT_CONFIRMATION, recipient="victim@example.com", now=later,
                 context={"name": "n", "subject": "s", "category": "general", "message": "m"}).status == "QUEUED"


# ===========================================================================
# 10. test email
# ===========================================================================

def test_test_email_has_no_cc_bcc_or_header_injection(client, db, email_outbox):
    h = auth(manager(db))
    for body in ({"recipient": "a@example.com", "cc": "b@example.com"},
                 {"recipient": "a@example.com", "bcc": ["b@example.com"]},
                 {"recipient": "a@example.com", "subject": "custom"},
                 {"recipient": "a@example.com\nBcc: b@example.com"},
                 {"recipient": "a@example.com\r\nCc: b@example.com"},
                 {"recipient": "A <a@example.com>, b@example.com"},
                 {"recipient": "a@example.com b@example.com"}):
        assert client.post(f"{BASE}/test", headers=h, json=body).status_code == 422, body
    assert email_outbox.provider.sent == [] and db.query(EmailDelivery).count() == 0
    assert client.post(f"{BASE}/test", headers=h, json={"recipient": "a@example.com"}).json()["success"] is True
    message = email_outbox.provider.sent[0]
    assert message.to == "a@example.com" and message.subject.startswith("[TEST]")
    assert not hasattr(message, "cc") and not hasattr(message, "bcc")       # the message type has no such field


# ===========================================================================
# 11. templates
# ===========================================================================

HOSTILE_VALUES = [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<a href="https://evil.example/login">Click here</a>',
    '"><svg/onload=alert(1)>',
    "' onmouseover='alert(1)",
    "Tom & Jerry <tj@example.com>",
    "Zoë 日本語 🎉 Ñandú",
    "line one\r\nBcc: victim@example.com\nSubject: injected",
    "&lt;already escaped&gt; &amp;",
]


@pytest.mark.parametrize("value", HOSTILE_VALUES)
def test_hostile_values_are_text_in_html_and_readable_in_plain_text(db, value):
    for event, context in (
        (EmailEvent.AFFILIATE_INVITATION, {"inviter_name": value, "referral_code": "CODE1", "message": value}),
        (EmailEvent.SUPPORT_CONTACT_CONFIRMATION, {"name": value, "subject": value, "category": "general",
                                                   "message": value}),
        (EmailEvent.ADMIN_CONTACT_MESSAGE, {"name": value, "email": "a@example.com", "subject": value,
                                            "category": "general", "message": value}),
        (EmailEvent.KYC_REJECTED, {"reason": value}),
        (EmailEvent.ADMIN_CONTENT_REPORT, {"contestant_title": value, "author_name": value, "contest_name": value,
                                           "reporter_name": value, "reason": value, "description": value,
                                           "report_id": 1}),
        (EmailEvent.GUARDIAN_CONSENT_REQUEST, {"token": "tok", "username": value}),
    ):
        subject, html, text = render(db, event_key=event.value, to="x@example.com", user_id=None, context=context,
                                     lang="en")
        for raw in ("<script", "<img src=x", "<svg", '<a href="https://evil.example', "onmouseover='alert"):
            assert raw not in html, (event, raw)
        assert "evil.example/login\">" not in html
        assert tpl.esc(value).replace("\r\n", "\n").split("\n")[0] in html      # escaped exactly once
        assert "&amp;lt;" not in html.replace(tpl.esc(value), "") and "&amp;amp;amp;" not in html
        assert "\n" not in subject and "\r" not in subject                    # no header injection
        assert value.split("\r\n")[0].split("\n")[0] in text                  # plain text stays readable, unescaped
        assert "&lt;" not in text.replace(value, "") or "&lt;" in value


def test_already_escaped_input_is_not_unescaped_and_markup_is_not_double_escaped():
    html = tpl.get_kyc_rejected_email("en", "&lt;b&gt; &amp;")[1]
    assert "&amp;lt;b&amp;gt; &amp;amp;" in html                             # shown literally, as typed
    html = tpl.get_payment_confirmation_email("en", "$5 & more", "Plan <A>", "ref", "01/01/2026")[1]
    assert "<strong>$5 &amp; more</strong>" in html and "<strong>Plan &lt;A&gt;</strong>" in html
    assert "&lt;strong&gt;" not in html                                       # trusted markup stays markup


@pytest.mark.parametrize("url,ok", [
    ("https://myhigh5.com/x?a=1&b=2", True), ("http://localhost:3001/reset-password?token=abc", True),
    ("mailto:infos@myhigh5.com", True),
    ("javascript:alert(1)", False), ("JaVaScRiPt:alert(1)", False), ("data:text/html;base64,AAAA", False),
    ("vbscript:x", False), ("file:///etc/passwd", False), ("//evil.example", False), ("/relative", False),
    ("https://a.example/\"onclick=\"x", False), ("https://a.example/<script>", False),
    ("https://a.example/ x", False), ("", False), (None, False),
])
def test_url_helper_allows_only_safe_schemes(url, ok):
    assert (tpl.safe_url(url) is not None) is ok


# ===========================================================================
# 6. registry (re-validated)
# ===========================================================================

def test_registry_is_exactly_the_53_audited_events():
    assert len(EMAIL_EVENTS) == 53 and "CONTEST.NOMINATION_PUBLISHED" in EMAIL_EVENTS
    for forbidden in ("CONTEST.NOMINATION_PENDING_REVIEW", "CONTEST.NOMINATION_SUBMITTED",
                      "CONTEST.PARTICIPATION_SUBMITTED", "KYC.PENDING_REVIEW", "AUTH.EMAIL_CHANGED",
                      "PAYOUT.APPROVED", "PAYOUT.REJECTED", "BILLING.INVOICE"):
        assert forbidden not in EMAIL_EVENTS
    haystack = " ".join(f"{d.key} {d.label} {d.recipient}".upper() for d in EMAIL_EVENTS.values())
    for retired in ("LEVEL 2", "LEVEL_2", "LEVEL-2", "MULTI", "POOL", "FOUNDING", "DSP", "LEADER"):
        assert retired not in haystack, retired
    assert email_module.email_service is email_service
