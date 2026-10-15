"""Kaluta KYC is managed from the Admin Panel only: the database is the single
source of the on/off switch, the API key, the webhook secret, the member fee
and the sessions per attempt. The server environment is never read for them.

Every administrator, member, key, secret, payment and session here is
SYNTHETIC. No request leaves the process (the provider is a fake at the HTTP
boundary; network transports fail the test).
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.kyc import KycSettings
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.payment_config import PaymentCredential
from app.services import kaluta_kyc, kyc_fee, kyc_settings
from app.services import payment_config as pc
from tests.conftest import save_kaluta_settings
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import PASSWORD
from tests.unit.test_kaluta_kyc_integration import FakeProvider, event, open_verification, signed
from tests.unit.test_kyc_initiation_dispatch import ADDRESS, INITIATE, adult, kyc_paid, kyc_rows, no_real_network  # noqa: F401
from tests.unit.test_kyc_member_fee import administrator, invoices, pay, product  # noqa: F401
from tests.unit.test_phase5_contest_eligibility import person
from tests.unit.test_super_admin import super_role

pytestmark = pytest.mark.unit

SETTINGS, WEBHOOK, STATUS = "/api/v1/kyc/admin/settings", "/api/v1/kyc/webhook/kaluta", "/api/v1/kyc/status-detailed"
URLS = "/api/v1/kyc/deployment/kaluta-urls"
ENV_KEY, ENV_SECRET = "klt_env_synthetic_key_must_be_ignored", "whsec_env_synthetic_must_be_ignored"
KEY, SECRET = "klt_db_synthetic_key_000000001", "whsec_db_synthetic_secret_0001"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    """The environment says Kaluta is ON with a key and a secret of its own."""
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    for name, value in (("KALUTA_KYC_ENABLED", "true"), ("KALUTA_API_KEY", ENV_KEY), ("KALUTA_WEBHOOK_SECRET", ENV_SECRET)):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", True)
    monkeypatch.setattr(settings, "KALUTA_API_KEY", ENV_KEY)
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", ENV_SECRET)
    monkeypatch.setattr(settings, "KYC_PROVIDER", "kaluta")
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)


def kyc_admin(db, name="kycadmin"):
    return administrator(db, name, permissions=(kyc_settings.PERMISSION,))


def put(client, admin, password=PASSWORD, **fields):
    return client.put(SETTINGS, headers=auth(admin), json={"current_password": password, **fields})


def deliver(client, payload, secret):
    body = json.dumps(payload).encode()
    return client.post(WEBHOOK, content=body, headers=signed(body, secret=secret))


def snapshot(db) -> tuple:
    """Everything a refused save must leave exactly as it was."""
    row = db.query(KycSettings).first()
    fee = db.query(ProductType).filter(ProductType.code == "kyc").first()
    return (None if row is None else (row.kaluta_enabled, row.sessions_per_attempt, row.version),
            sorted((c.name, c.ciphertext) for c in db.query(PaymentCredential).all()),
            None if fee is None else str(fee.price),
            db.query(AuditTrail).count())


# ===========================================================================
# 1. The environment is never a source
# ===========================================================================

def test_with_nothing_saved_kaluta_is_off_whatever_the_environment_says(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    admin, user = kyc_admin(db), adult(db)
    paid = kyc_paid(db, user)
    view = client.get(SETTINGS, headers=auth(admin)).json()
    assert (view["source"], view["enabled"], view["ready_to_enable"]) == ("database", False, False)
    assert [(c["name"], c["configured"], c["saved"]) for c in view["credentials"]] == \
        [("API_KEY", False, False), ("WEBHOOK_SECRET", False, False)]
    started = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert started.status_code == 503 and "disabled" in started.text
    assert fake.requests == [] and kyc_rows(db, user) == []
    db.expire_all()
    assert db.get(Deposit, paid.id).is_used is False
    v = open_verification(db, person(db, 30))
    assert deliver(client, event("session.expired", v, status="expired"), ENV_SECRET).status_code == 503
    urls = client.get(URLS, headers=auth(admin)).json()
    assert (urls["api_key_configured"], urls["webhook_secret_configured"]) == (False, False)
    assert kyc_settings.kaluta_enabled(db) is False


def test_saved_settings_are_used_and_the_environment_key_and_secret_never_are(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    save_kaluta_settings(db, enabled=True, api_key=KEY, webhook_secret=SECRET)
    user = adult(db)
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    assert fake.requests[0]["headers"]["X-API-Key"] == KEY
    row = kyc_rows(db, user)[0]
    body = event("session.expired", row, status="expired")
    assert deliver(client, body, ENV_SECRET).status_code == 401
    assert deliver(client, body, SECRET).json()["result"] == "applied"


def test_a_saved_secret_that_cannot_be_read_counts_as_missing_and_fails_closed(client, db, monkeypatch):
    """Saved with one encryption key, read with another: not configured."""
    fake = FakeProvider(monkeypatch)
    save_kaluta_settings(db, enabled=True, api_key=KEY, webhook_secret=SECRET)
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "a-different-synthetic-encryption-key-000")
    admin, user = kyc_admin(db), adult(db)
    kyc_paid(db, user)
    view = client.get(SETTINGS, headers=auth(admin)).json()
    assert [(c["saved"], c["saved_readable"], c["configured"]) for c in view["credentials"]] == [(True, False, False)] * 2
    assert (view["enabled"], view["ready_to_enable"]) == (True, False)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 503 and fake.requests == []
    v = open_verification(db, person(db, 30))
    for secret in (SECRET, ENV_SECRET):
        assert deliver(client, event("session.expired", v, status="expired"), secret).status_code == 401


def test_settings_that_cannot_be_read_switch_kaluta_off(db, monkeypatch, caplog):
    save_kaluta_settings(db, enabled=True, api_key=KEY, webhook_secret=SECRET)
    kyc_settings.apply(db)
    assert kaluta_kyc.kaluta_kyc_service.configured() is True

    def broken(_db):
        raise OperationalError("SELECT", {}, Exception("synthetic outage"))

    monkeypatch.setattr(kyc_settings, "saved_values", broken)
    caplog.set_level(logging.ERROR)
    kyc_settings.apply(db)
    svc = kaluta_kyc.kaluta_kyc_service
    assert (svc.enabled, svc.api_key, svc.webhook_secret) == (False, "", "")
    assert "treated as off" in caplog.text and KEY not in caplog.text


def test_no_runtime_code_reads_the_kaluta_environment_variables():
    backend = Path(kyc_settings.__file__).resolve().parents[2]
    for relative in ("app/services/kaluta_kyc.py", "app/services/kyc_settings.py", "app/services/kyc_provider_dispatch.py",
                     "app/api/api_v1/endpoints/kyc.py", "app/services/kyc_fee.py"):
        source = (backend / relative).read_text(encoding="utf-8")
        for name in ("settings.KALUTA_KYC_ENABLED", "settings.KALUTA_API_KEY", "settings.KALUTA_WEBHOOK_SECRET",
                     'getenv("KALUTA_'):
            assert name not in source, (relative, name)


def test_the_migration_imports_nothing_and_switches_nothing_on():
    backend = Path(kyc_settings.__file__).resolve().parents[2]
    source = (backend / "migrations/versions/e6f7a8b9c0d1_kyc_sessions_per_attempt_setting.py").read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]                                      # without the docstring
    assert "INSERT" not in code.upper() and "UPDATE " not in code.upper() and "KALUTA" not in code.upper()
    assert "getenv" not in code and "environ" not in code
    assert 'down_revision = "d5e6f7a8b9c0"' in code


# ===========================================================================
# 2. One form, saved all at once
# ===========================================================================

def test_one_save_sets_every_setting_and_is_audited_without_secrets(client, db, caplog):
    caplog.set_level(logging.DEBUG)
    product(db, "10.00")
    admin = kyc_admin(db)
    answer = put(client, admin, enabled=True, api_key=KEY, webhook_secret=SECRET, member_fee="12.50",
                 sessions_per_attempt=5, expected_version=0, expected_fee="10.00")
    assert answer.status_code == 200, answer.text
    view = answer.json()
    assert (view["enabled"], view["ready_to_enable"], view["sessions_per_attempt"], view["version"]) == (True, True, 5, 1)
    assert (view["member_fee"]["amount"], view["member_fee"]["is_free"]) == ("12.50", False)
    for text in (answer.text, client.get(SETTINGS, headers=auth(admin)).text, caplog.text):
        assert KEY not in text and SECRET not in text and PASSWORD not in text
    trail = db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SETTINGS).one()
    assert trail.old_values == {"kaluta_enabled": False, "sessions_per_attempt": 3, "member_fee": "10.00"}
    assert trail.new_values["changed"] == ["API_KEY", "KALUTA_ENABLED", "MEMBER_FEE", "SESSIONS_PER_ATTEMPT",
                                           "WEBHOOK_SECRET"]
    assert (trail.new_values["member_fee"], trail.new_values["sessions_per_attempt"]) == ("12.50", 5)
    assert KEY not in json.dumps(trail.new_values) and SECRET not in json.dumps(trail.new_values)
    fee_trail = db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).one()
    assert (fee_trail.old_values, fee_trail.new_values) == ({"price": "10.00"}, {"price": "12.50"})
    assert (fee_trail.user_id, trail.user_id) == (admin.id, admin.id)


@pytest.mark.parametrize("bad, field", [
    ({"member_fee": "-1"}, "MEMBER_FEE"), ({"member_fee": "1000.01"}, "MEMBER_FEE"),
    ({"member_fee": "10.001"}, "MEMBER_FEE"), ({"member_fee": "ten"}, "MEMBER_FEE"),
    ({"member_fee": "NaN"}, "MEMBER_FEE"), ({"member_fee": "Infinity"}, "MEMBER_FEE"),
    ({"sessions_per_attempt": 0}, "SESSIONS_PER_ATTEMPT"), ({"sessions_per_attempt": 11}, "SESSIONS_PER_ATTEMPT"),
    ({"sessions_per_attempt": -2}, "SESSIONS_PER_ATTEMPT"), ({"sessions_per_attempt": "2.5"}, "SESSIONS_PER_ATTEMPT"),
    ({"sessions_per_attempt": "three"}, "SESSIONS_PER_ATTEMPT"), ({"sessions_per_attempt": True}, "SESSIONS_PER_ATTEMPT"),
])
def test_an_invalid_fee_or_session_limit_is_refused_and_nothing_else_is_saved(client, db, bad, field):
    product(db, "10.00")
    admin = kyc_admin(db)
    before = snapshot(db)
    answer = put(client, admin, api_key=KEY, webhook_secret=SECRET, enabled=True, **bad)
    assert answer.status_code == 422, answer.text
    detail = answer.json()["detail"]
    if isinstance(detail, dict):                       # the service's refusal (pydantic refuses a bool/str type first)
        assert (detail["code"], detail["field"]) == ("INVALID_VALUE", field)
    assert KEY not in answer.text and SECRET not in answer.text
    db.expire_all()
    assert snapshot(db) == before


def test_a_refusal_late_in_the_save_changes_nothing_that_came_before_it(client, db):
    """Switching on without a webhook secret is refused AFTER the key, the fee
    and the sessions were staged: none of them is kept."""
    product(db, "10.00")
    admin = kyc_admin(db)
    before = snapshot(db)
    refused = put(client, admin, enabled=True, api_key=KEY, member_fee="20", sessions_per_attempt=6)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_READY"
    db.expire_all()
    assert snapshot(db) == before
    stale_fee = put(client, admin, member_fee="20", sessions_per_attempt=6, expected_fee="11.00")
    assert stale_fee.status_code == 409 and stale_fee.json()["detail"] == {
        "code": "STALE", "message": "The fee was changed by somebody else. Reload and try again.", "field": "MEMBER_FEE"}
    db.expire_all()
    assert snapshot(db) == before


def test_blank_credential_fields_keep_the_saved_ones(client, db):
    admin = kyc_admin(db)
    assert put(client, admin, api_key=KEY, webhook_secret=SECRET).status_code == 200
    saved = sorted((c.name, c.ciphertext) for c in db.query(PaymentCredential).all())
    assert put(client, admin, api_key="", webhook_secret="", sessions_per_attempt=4).status_code == 200
    db.expire_all()
    assert sorted((c.name, c.ciphertext) for c in db.query(PaymentCredential).all()) == saved


def test_saving_the_values_already_in_force_changes_nothing(client, db):
    product(db, "10.00")
    admin = kyc_admin(db)
    same = put(client, admin, enabled=False, member_fee="10", sessions_per_attempt=3)
    assert same.status_code == 200 and same.json()["version"] == 0
    assert db.query(KycSettings).count() == 0 and db.query(AuditTrail).count() == 0


# ===========================================================================
# 3. The fee
# ===========================================================================

def test_the_fee_saved_in_the_form_prices_new_payments_and_existing_ones_keep_their_amount(client, db, invoices):
    product(db, "10.00")
    admin, early, later = kyc_admin(db), adult(db), adult(db)
    paid = kyc_paid(db, early)
    assert put(client, admin, member_fee="15.00").status_code == 200
    db.expire_all()
    assert Decimal(str(db.get(Deposit, paid.id).amount)) == Decimal("10.00")              # unchanged
    assert client.get("/api/v1/kyc/fee").status_code in (401, 403)
    assert client.get("/api/v1/kyc/fee", headers=auth(later)).json()["amount"] == "15.00"
    assert client.get(STATUS, headers=auth(later)).json()["kyc_price"] == 15.0
    assert pay(client, later, 10).status_code == 400                                    # the old figure is refused
    created = pay(client, later, 15)
    assert created.status_code == 200 and Decimal(str(invoices[-1]["price_amount"])) == Decimal("15.00")
    new = db.query(Deposit).filter(Deposit.user_id == later.id).one()
    assert (new.status, Decimal(str(new.amount))) == (DepositStatus.PENDING, Decimal("15.00"))


def test_a_fee_of_zero_makes_kyc_free(client, db):
    product(db, "10.00")
    admin, user = kyc_admin(db), adult(db)
    answer = put(client, admin, member_fee="0")
    assert answer.status_code == 200 and answer.json()["member_fee"]["is_free"] is True
    assert client.get(STATUS, headers=auth(user)).json()["kyc_is_free"] is True


def test_without_the_kyc_product_the_fee_cannot_be_saved(client, db):
    admin = kyc_admin(db)
    view = client.get(SETTINGS, headers=auth(admin)).json()
    assert view["member_fee"]["product_configured"] is False
    answer = put(client, admin, member_fee="12", sessions_per_attempt=4)
    assert answer.status_code == 409 and answer.json()["detail"]["code"] == "PRODUCT_MISSING"
    assert db.query(KycSettings).count() == 0


# ===========================================================================
# 4. Sessions per attempt
# ===========================================================================

def test_the_sessions_per_attempt_setting_is_the_limit_members_meet(client, db, monkeypatch):
    fake = FakeProvider(monkeypatch)
    save_kaluta_settings(db, enabled=True, api_key=KEY, webhook_secret=SECRET)
    admin, user = kyc_admin(db), adult(db)
    assert put(client, admin, sessions_per_attempt=1).json()["sessions_per_attempt"] == 1
    kyc_paid(db, user)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert first.status_code == 200 and first.json()["sessions_remaining"] == 0
    refused = client.post(INITIATE + "?force_new=true", json=ADDRESS, headers=auth(user))
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "KYC_SESSION_LIMIT_REACHED"
    # Raised again: the same open attempt may continue, without a payment.
    assert put(client, admin, sessions_per_attempt=2).status_code == 200
    again = client.post(INITIATE + "?force_new=true", json=ADDRESS, headers=auth(user))
    assert again.status_code == 200 and again.json()["sessions_remaining"] == 0
    assert [r["url"] for r in fake.requests].count("https://kalutakyc.com/v1/sessions") == 2
    db.expire_all()
    assert kyc_rows(db, user)[0].attempts_count == 1
    assert db.query(Deposit).filter(Deposit.user_id == user.id).count() == 1


def test_a_stored_session_limit_outside_the_range_falls_back_to_the_default():
    assert kyc_settings._sessions_value(None) == 3
    assert kyc_settings._sessions_value(KycSettings(id=1, sessions_per_attempt=None)) == 3
    assert kyc_settings._sessions_value(KycSettings(id=1, sessions_per_attempt=99)) == 3
    assert kyc_settings._sessions_value(KycSettings(id=1, sessions_per_attempt=7)) == 7


# ===========================================================================
# 5. Who may change it
# ===========================================================================

def test_only_manage_kyc_settings_or_a_super_admin_can_change_any_of_it(client, db):
    product(db, "10.00")
    plain = administrator(db, "plain", permissions=())
    finance = administrator(db, "finance", permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_ACTIVATE))
    before = snapshot(db)
    for admin in (plain, finance):
        assert client.get(SETTINGS, headers=auth(admin)).json()["can_change"] is False
        for fields in ({"member_fee": "11"}, {"sessions_per_attempt": 4}, {"enabled": True},
                       {"api_key": KEY}, {"webhook_secret": SECRET}):
            refused = put(client, admin, **fields)
            assert refused.status_code == 403 and refused.json()["detail"]["code"] == "FORBIDDEN"
        # The older fee endpoint is guarded the same way.
        assert client.put("/api/v1/kyc/admin/fee", headers=auth(admin),
                          json={"amount": "11", "current_password": PASSWORD}).status_code == 403
    db.expire_all()
    assert snapshot(db) == before

    boss = administrator(db, "superadmin", permissions=())
    boss.role_id = super_role(db).id
    db.commit()
    assert client.get(SETTINGS, headers=auth(boss)).json()["can_change"] is True
    assert put(client, boss, password="not-the-password", member_fee="11").json()["detail"]["code"] == "REAUTH_REQUIRED"
    saved = put(client, boss, member_fee="11", sessions_per_attempt=4)
    assert saved.status_code == 200 and (saved.json()["member_fee"]["amount"], saved.json()["sessions_per_attempt"]) == ("11.00", 4)


def test_a_member_cannot_read_or_change_the_settings(client, db):
    user = adult(db)
    assert client.get(SETTINGS, headers=auth(user)).status_code == 403
    assert put(client, user, member_fee="0").status_code == 403
    assert db.query(KycSettings).count() == 0
