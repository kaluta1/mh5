"""Kaluta KYC settings in the Admin Panel (the database is their only source),
the manage_kyc_settings permission, and provider sessions that run out without
using up the member's attempt.

Every administrator, member, key, secret, payment and session here is
SYNTHETIC. No request leaves the process: httpx network transports fail the
test and the provider is a fake at the HTTP boundary.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.crud import crud_kyc
from app.models.accounting import AuditTrail
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, KycSettings
from app.models.payment import Deposit
from app.models.payment_config import PaymentCredential
from app.services import kaluta_kyc, kyc_settings
from app.services import kyc_provider_dispatch as dispatch
from app.services import payment_config as pc
from tests.conftest import save_kaluta_settings
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import PASSWORD
from tests.unit.test_kaluta_kyc_integration import FakeProvider, event, open_verification, signed
from tests.unit.test_kyc_initiation_dispatch import ADDRESS, INITIATE, adult, kyc_paid, kyc_rows, no_real_network  # noqa: F401
from tests.unit.test_kyc_member_fee import administrator, money, product
from tests.unit.test_phase5_contest_eligibility import person

pytestmark = pytest.mark.unit

SETTINGS, WEBHOOK, STATUS, PAY = ("/api/v1/kyc/admin/settings", "/api/v1/kyc/webhook/kaluta",
                                  "/api/v1/kyc/status-detailed", "/api/v1/payments/create")
# In the server environment: must be IGNORED everywhere.
ENV_KEY, ENV_SECRET = "klt_env_synthetic_key_000001", "whsec_env_synthetic_secret_01"
# Saved in Admin > KYC before a test starts (turn_on), and saved during a test.
SAVED_KEY, SAVED_SECRET = "klt_saved_synthetic_key_0001", "whsec_saved_synthetic_secret1"
ADMIN_KEY, ADMIN_SECRET = "klt_admin_synthetic_key_0002", "whsec_admin_synthetic_secret_2"
SESSIONS = "https://kalutakyc.com/v1/sessions"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    """The server environment says Kaluta is ON with its own synthetic key and
    secret: every test proves it is ignored. Nothing is saved in the database
    (Kaluta off) until a test saves it. The dedicated encryption key is present
    (removed explicitly where tested)."""
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    for name, value in (("KALUTA_KYC_ENABLED", "true"), ("KALUTA_API_KEY", ENV_KEY), ("KALUTA_WEBHOOK_SECRET", ENV_SECRET)):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", True)
    monkeypatch.setattr(settings, "KYC_PROVIDER", "kaluta")
    monkeypatch.setattr(settings, "KALUTA_API_KEY", ENV_KEY)
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", ENV_SECRET)
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    return kaluta_kyc.kaluta_kyc_service


def turn_on(db, **kw):
    """Kaluta switched on in Admin > KYC with the SAVED synthetic key and secret."""
    save_kaluta_settings(db, enabled=True, api_key=SAVED_KEY, webhook_secret=SAVED_SECRET, **kw)


def kyc_admin(db, name="kycadmin"):
    return administrator(db, name, permissions=(kyc_settings.PERMISSION,))


def put(client, admin, password=PASSWORD, **fields):
    return client.put(SETTINGS, headers=auth(admin), json={"current_password": password, **fields})


def deliver(client, payload, secret):
    body = json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers=signed(body, secret=secret))


def sessions_opened(fake) -> int:
    return [r["url"] for r in fake.requests].count(SESSIONS)


def expire(db, user):
    row = kyc_rows(db, user)[0]
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    return row


# ===========================================================================
# 1. Who may change the settings
# ===========================================================================

def test_only_manage_kyc_settings_and_the_current_password_change_the_settings(client, db):
    plain = administrator(db, "plain", permissions=())
    finance = administrator(db, "finance", permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_ACTIVATE,
                                                        pc.PERMISSION_PROCESS))
    manager = kyc_admin(db)
    ordinary = adult(db)
    assert client.get(SETTINGS).status_code in (401, 403)
    assert client.get(SETTINGS, headers=auth(ordinary)).status_code == 403
    assert put(client, ordinary, enabled=False).status_code == 403
    for admin in (plain, finance):
        seen = client.get(SETTINGS, headers=auth(admin)).json()
        assert (seen["can_change"], seen["permission"]) == (False, "manage_kyc_settings")
        refused = put(client, admin, enabled=False, api_key=ADMIN_KEY)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "FORBIDDEN"
    wrong = put(client, manager, password="not-the-password", enabled=False)
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "REAUTH_REQUIRED"
    assert put(client, manager, password="", api_key=ADMIN_KEY).status_code == 403
    assert db.query(KycSettings).count() == 0 and db.query(PaymentCredential).count() == 0
    assert db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SETTINGS).count() == 0
    assert client.get(SETTINGS, headers=auth(manager)).json()["can_change"] is True


def test_the_permission_is_held_by_nobody_until_granted_and_is_protected():
    from app.scripts import grant_payment_permissions as grants
    from app.services import admin_security

    assert kyc_settings.PERMISSION == "manage_kyc_settings" == admin_security.PERMISSION_MANAGE_KYC
    assert kyc_settings.PERMISSION in admin_security.PROTECTED_PERMISSIONS        # not through the role API
    assert kyc_settings.PERMISSION in grants.PERMISSIONS                            # granted by name only


# ===========================================================================
# 2. Secrets: encrypted at rest, never shown, never audited
# ===========================================================================

def test_a_saved_key_and_secret_are_encrypted_never_returned_and_never_audited(client, db, caplog):
    caplog.set_level(logging.DEBUG)
    admin = kyc_admin(db)
    answer = put(client, admin, api_key=ADMIN_KEY, webhook_secret=ADMIN_SECRET, expected_version=0)
    assert answer.status_code == 200, answer.text
    for text in (answer.text, client.get(SETTINGS, headers=auth(admin)).text, caplog.text):
        assert ADMIN_KEY not in text and ADMIN_SECRET not in text and ENV_KEY not in text and ENV_SECRET not in text
    stored = {r.name: r for r in db.query(PaymentCredential).filter(PaymentCredential.provider == "kaluta")}
    assert set(stored) == {"API_KEY", "WEBHOOK_SECRET"}
    for row, plain in ((stored["API_KEY"], ADMIN_KEY), (stored["WEBHOOK_SECRET"], ADMIN_SECRET)):
        assert row.ciphertext.startswith("v1:") and plain not in row.ciphertext and row.set_by == admin.id
    # A KYC ciphertext is not readable as a payment credential (its own purpose).
    from app.services import payment_crypto

    with pytest.raises(payment_crypto.PaymentCryptoError):
        payment_crypto.decrypt(stored["API_KEY"].ciphertext, payment_crypto.PURPOSE_CREDENTIAL + "API_KEY")
    view = answer.json()
    assert [(c["name"], c["saved"], c["saved_readable"], c["configured"]) for c in view["credentials"]] == \
        [("API_KEY", True, True, True), ("WEBHOOK_SECRET", True, True, True)]
    assert view["version"] == 1
    trail = db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SETTINGS).one()
    dumped = json.dumps([trail.old_values, trail.new_values])
    assert ADMIN_KEY not in dumped and ADMIN_SECRET not in dumped
    assert trail.new_values["changed"] == ["API_KEY", "WEBHOOK_SECRET"] and trail.user_id == admin.id


def test_the_saved_key_is_what_the_provider_receives_and_a_blank_field_keeps_it(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    admin, user = kyc_admin(db), adult(db)
    assert put(client, admin, api_key=ADMIN_KEY, webhook_secret=ADMIN_SECRET).status_code == 200
    assert put(client, admin, api_key="", webhook_secret="   ", enabled=True).status_code == 200   # blank = keep
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    assert fake.requests[0]["headers"]["X-API-Key"] == ADMIN_KEY
    key_row = lambda: (db.query(PaymentCredential)  # noqa: E731
                       .filter(PaymentCredential.provider == "kaluta", PaymentCredential.name == "API_KEY").one())
    before = key_row().ciphertext
    assert put(client, admin, api_key="klt_admin_synthetic_key_0003").status_code == 200
    db.expire_all()
    assert key_row().ciphertext != before


@pytest.mark.parametrize("field, value, code", [
    ("webhook_secret", "https://myhigh5.com/api/v1/kyc/webhook/kaluta", "INVALID_VALUE"),     # the known mistake
    ("api_key", "klt short key", "INVALID_VALUE"), ("api_key", "klt_x1", "INVALID_VALUE"),
    ("webhook_secret", "x" * 513, None),
])
def test_a_value_that_is_not_a_secret_is_refused_and_nothing_is_saved(client, db, field, value, code):
    answer = put(client, kyc_admin(db), **{field: value})
    assert answer.status_code == 422
    if code:
        assert answer.json()["detail"]["code"] == code
    assert value not in answer.text and PASSWORD not in answer.text          # a refused value is never echoed
    assert db.query(PaymentCredential).count() == 0 and db.query(KycSettings).count() == 0


def test_without_the_encryption_key_nothing_is_stored(client, db, monkeypatch):
    monkeypatch.delenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(settings, "PAYMENT_SETTINGS_ENCRYPTION_KEY", "")
    admin = kyc_admin(db)
    answer = put(client, admin, api_key=ADMIN_KEY)
    assert answer.status_code == 409 and answer.json()["detail"]["code"] == "ENCRYPTION_KEY_MISSING"
    assert db.query(PaymentCredential).count() == 0
    assert client.get(SETTINGS, headers=auth(admin)).json()["encryption_key_configured"] is False


def test_unknown_fields_and_the_webhook_url_cannot_be_sent(client, db):
    admin = kyc_admin(db)
    for extra in ({"webhook_url": "https://evil.example/hook"}, {"provider_cost_percent": "20"}, {"api_secret": "x"}):
        assert put(client, admin, **extra).status_code == 422
    assert put(client, admin).status_code == 422                        # nothing to save
    view = client.get(SETTINGS, headers=auth(admin)).json()
    assert view["webhook_url"].endswith("/api/v1/kyc/webhook/kaluta")     # read-only, shown for copying


def test_a_change_made_on_a_stale_page_is_refused(client, db):
    admin = kyc_admin(db)
    assert put(client, admin, sessions_per_attempt=4, expected_version=0).json()["version"] == 1
    stale = put(client, admin, sessions_per_attempt=5, member_fee="12.00", api_key=ADMIN_KEY, expected_version=0)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE"
    db.expire_all()
    assert db.query(KycSettings).one().sessions_per_attempt == 4 and db.query(PaymentCredential).count() == 0


# ===========================================================================
# 3. On / off
# ===========================================================================

def test_switching_on_needs_a_saved_key_and_secret_and_the_environment_never_counts(client, db):
    admin = kyc_admin(db)
    view = client.get(SETTINGS, headers=auth(admin)).json()
    # The environment says on, with a key and a secret: none of it counts.
    assert (view["source"], view["enabled"], view["ready_to_enable"]) == ("database", False, False)
    assert [c["configured"] for c in view["credentials"]] == [False, False]
    for gone in ("enabled_source", "environment_configured", "in_use"):
        assert gone not in json.dumps(view)
    refused = put(client, admin, enabled=True)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_READY"
    partial = put(client, admin, enabled=True, api_key=ADMIN_KEY)               # still no webhook secret
    assert partial.status_code == 409 and partial.json()["detail"]["code"] == "NOT_READY"
    db.expire_all()
    # The key was not saved either: one change, all or nothing.
    assert db.query(PaymentCredential).count() == 0 and db.query(KycSettings).count() == 0
    on = put(client, admin, enabled=True, api_key=ADMIN_KEY, webhook_secret=ADMIN_SECRET)
    assert on.status_code == 200 and (on.json()["enabled"], on.json()["source"]) == (True, "database")


def test_switched_off_in_the_admin_panel_nothing_reaches_the_provider_and_the_webhook_answers_503(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    admin, user = kyc_admin(db), adult(db)
    assert put(client, admin, enabled=False).status_code == 200
    paid = kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 503
    assert fake.requests == []
    v = open_verification(db, person(db, 30))
    assert deliver(client, event("session.expired", v, status="expired"), ENV_SECRET).status_code == 503
    # Refused before anything was opened: no attempt, and the paid payment is not used.
    db.expire_all()
    assert kyc_rows(db, user) == [] and db.get(Deposit, paid.id).is_used is False
    assert db.get(KYCVerification, v.id).expires_at > datetime.utcnow()


def test_switched_on_in_the_admin_panel_with_its_own_secret(client, db, monkeypatch):
    admin = kyc_admin(db)
    v = open_verification(db, person(db, 30))
    body = event("session.expired", v, status="expired")
    assert deliver(client, body, ENV_SECRET).status_code == 503                    # on in the environment: ignored
    assert put(client, admin, enabled=True, api_key=ADMIN_KEY, webhook_secret=ADMIN_SECRET).status_code == 200
    assert deliver(client, body, ENV_SECRET).status_code == 401                    # the environment secret never holds
    assert deliver(client, body, ADMIN_SECRET).json()["result"] == "applied"


# ===========================================================================
# 4. Free KYC with a paid payment held
# ===========================================================================

def test_free_kyc_starts_without_touching_a_paid_payment(client, db, monkeypatch):
    turn_on(db)
    FakeProvider(monkeypatch)
    product(db, "0")
    user = adult(db)
    paid = kyc_paid(db, user)
    product(db, "0")
    ledger = money(db)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    assert db.get(Deposit, paid.id).is_used is False and money(db) == ledger


# ===========================================================================
# 5. A session that runs out does not use up the attempt
# ===========================================================================

def test_an_expired_session_is_renewed_for_the_same_paid_attempt_without_a_payment(client, db, monkeypatch):
    turn_on(db)
    fake = FakeProvider(monkeypatch)
    product(db, "10")
    user = adult(db)
    kyc_paid(db, user)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(user)).json()
    row = kyc_rows(db, user)[0]
    assert deliver(client, event("session.expired", row, session="sess-1", status="expired"), SAVED_SECRET
                   ).json()["result"] == "applied"
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["status"], state["session_expired"], state["can_continue"], state["needs_payment"],
            state["sessions_remaining"], state["session_limit_reached"]) == ("in_progress", True, True, False, 2, False)
    assert client.post(PAY, headers=auth(user), json={"amount": 10, "currency": "usd", "product_code": "kyc"}
                       ).json()["detail"]["code"] == "KYC_ATTEMPT_OPEN"                 # not charged again
    renewed = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert renewed.status_code == 200 and renewed.json()["status"] == "new"
    assert renewed.json()["verification_url"] != first["verification_url"]
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.attempts_count, row.attempt_sessions_count, row.status) == (1, 2, KYCStatus.IN_PROGRESS)
    assert db.query(Deposit).filter(Deposit.user_id == user.id).count() == 1 and sessions_opened(fake) == 2


def test_renewals_stop_at_the_session_limit_and_an_administrator_can_allow_one_more(client, db, monkeypatch):
    turn_on(db)
    fake = FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    for _ in range(kyc_settings.SESSIONS_PER_ATTEMPT - 1):
        expire(db, user)
        assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    expire(db, user)
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["sessions_remaining"], state["session_limit_reached"]) == (0, True)
    for force in (False, True):                                          # asking for a fresh link counts the same
        refused = client.post(INITIATE + ("?force_new=true" if force else ""), json=ADDRESS, headers=auth(user))
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "KYC_SESSION_LIMIT_REACHED"
    assert sessions_opened(fake) == kyc_settings.SESSIONS_PER_ATTEMPT

    row = kyc_rows(db, user)[0]
    grant = f"/api/v1/kyc/admin/verification/{row.id}/grant-session"
    plain = administrator(db, "plain", permissions=(pc.PERMISSION_MANAGE,))
    assert client.post(grant, headers=auth(plain), json={"current_password": PASSWORD}).status_code == 403
    manager = kyc_admin(db)
    assert client.post(grant, headers=auth(manager), json={"current_password": "wrong"}).status_code == 403
    allowed = client.post(grant, headers=auth(manager), json={"current_password": PASSWORD})
    assert allowed.status_code == 200 and allowed.json()["sessions_left"] == 1
    again = client.post(grant, headers=auth(manager), json={"current_password": PASSWORD})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NOT_NEEDED"     # one at a time
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.attempts_count, row.attempt_sessions_count, row.attempt_sessions_granted) == (1, 4, 1)
    assert db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SESSION_GRANTED).count() == 1
    assert db.query(KYCAuditLog).filter(KYCAuditLog.action == "kyc_session_granted").one().performed_by_user_id == manager.id

    # At most MAX_GRANTED_SESSIONS extra sessions for one attempt.
    for _ in range(kyc_settings.MAX_GRANTED_SESSIONS - 1):
        expire(db, user)
        assert client.post(grant, headers=auth(manager), json={"current_password": PASSWORD}).status_code == 200
        assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    expire(db, user)
    capped = client.post(grant, headers=auth(manager), json={"current_password": PASSWORD})
    assert capped.status_code == 409 and capped.json()["detail"]["code"] == "GRANT_LIMIT"


def test_a_provider_refusal_does_not_use_up_a_session_but_an_unknown_outcome_does(client, db, monkeypatch):
    turn_on(db)
    user = adult(db)
    kyc_paid(db, user)
    FakeProvider(monkeypatch, status=402, body={"detail": "Insufficient balance"})
    for _ in range(kyc_settings.SESSIONS_PER_ATTEMPT + 1):
        assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 503
    db.expire_all()
    assert kyc_rows(db, user)[0].attempt_sessions_count == 0             # nothing was opened, nothing counts
    FakeProvider(monkeypatch, error=httpx.ReadTimeout("synthetic timeout"))
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 503
    db.expire_all()
    assert kyc_rows(db, user)[0].attempt_sessions_count == 1             # a session may exist: it counts


def test_a_new_attempt_after_a_rejection_starts_with_a_full_session_allowance(client, db, monkeypatch):
    turn_on(db)
    FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    row = kyc_rows(db, user)[0]
    row.attempt_sessions_count, row.attempt_sessions_granted, row.status = 3, 1, KYCStatus.REJECTED
    db.commit()
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.attempts_count, row.attempt_sessions_count, row.attempt_sessions_granted) == (2, 1, 0)


def test_the_last_attempt_can_still_renew_its_session(client, db, monkeypatch):
    turn_on(db)
    fake = FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    row = expire(db, user)
    row.attempts_count = row.max_attempts                                # the third and last attempt
    db.commit()
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    assert sessions_opened(fake) == 2


def test_an_older_expired_record_continues_the_same_attempt_without_a_payment(client, db, monkeypatch):
    turn_on(db)
    fake = FakeProvider(monkeypatch)
    product(db, "10")
    user = adult(db)
    v = open_verification(db, user, status=KYCStatus.EXPIRED)
    v.verified_address = ADDRESS["residential_address"]
    db.commit()
    attempts = v.attempts_count
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["can_continue"], state["can_restart"], state["needs_payment"], state["session_expired"]) == \
        (True, False, False, True)
    assert client.post(PAY, headers=auth(user), json={"amount": 10, "currency": "usd", "product_code": "kyc"}
                       ).json()["detail"]["code"] == "KYC_ATTEMPT_OPEN"
    assert client.post(INITIATE, json={}, headers=auth(user)).status_code == 200
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert (row.status, row.attempts_count) == (KYCStatus.IN_PROGRESS, attempts) and sessions_opened(fake) == 1
    assert db.query(Deposit).count() == 0


def test_a_status_read_that_reports_an_expiry_is_not_a_rejection(db, monkeypatch, email_outbox):
    import asyncio

    v = open_verification(db, person(db, 30), session="sess-5")

    async def provider_says(_verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": False, "expired": True,
                "data": {"id": "sess-5", "status": "expired"}}

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "check_reference_validity", provider_says)
    assert asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=v)) == \
        {"status": "session_expired"}
    db.refresh(v)
    assert v.status == KYCStatus.IN_PROGRESS and v.rejection_reason is None and v.expires_at <= datetime.utcnow()
    assert email_outbox is not None and not v.identity_verified


def test_a_rejection_found_while_continuing_never_opens_a_new_attempt(client, db, monkeypatch):
    turn_on(db)
    FakeProvider(monkeypatch)
    user = adult(db)
    kyc_paid(db, user)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))

    async def provider_rejects(verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": False,
                "data": {"id": verification.external_verification_id, "status": "rejected"}}

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "check_reference_validity", provider_rejects)
    ended = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert ended.status_code == 409 and ended.json()["detail"]["code"] == "KYC_ATTEMPT_ENDED"
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.status, row.attempts_count, row.attempt_sessions_count) == (KYCStatus.REJECTED, 1, 1)


def test_settings_and_sessions_touch_no_payment_ledger_or_commission_row(client, db, monkeypatch):
    FakeProvider(monkeypatch)
    admin, user = kyc_admin(db), adult(db)
    kyc_paid(db, user)
    before = money(db)
    assert put(client, admin, api_key=ADMIN_KEY, webhook_secret=ADMIN_SECRET, enabled=True).status_code == 200
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    expire(db, user)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    deposits, journal, commissions = money(db)
    assert (journal, commissions) == before[1:] and deposits == before[0]
    from pathlib import Path

    source = Path(kyc_settings.__file__).read_text(encoding="utf-8")
    for forbidden in ("JournalEntry", "AffiliateCommission", "Deposit", "cashout", "ledger_", "wallet"):
        assert forbidden not in source, forbidden
