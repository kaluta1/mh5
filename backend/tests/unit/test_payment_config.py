"""Finance & Payments: the central payment configuration, encrypted provider
credentials, the read-only connection test, payout wallet email confirmation
and the engine limits that the configuration drives.

Nothing here can reach NOWPayments: the payout provider is a fake object, the
connection test gets a fake HTTP function, and `no_network` (imported from the
dual cashout tests) fails a test that touches the real HTTP helpers. Every
credential, wallet, user and amount is SYNTHETIC.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.accounting.distribution_formulas import cashout_fee_and_net
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest, PayoutWalletChange
from app.models.email import EmailDelivery
from app.models.payment_config import (
    PaymentConfigAudit,
    PaymentCredential,
    PaymentSettings,
    PaymentWebhookStat,
    PayoutWalletVerification,
)
from app.models.user import User
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import nowpayments_service as nowpayments
from app.services import payment_config as pc
from app.services import payment_crypto
from app.services.financial_balances import get_commission_balance
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    OTHER_WALLET,
    PASSWORD,
    PAYOUT_ENV,
    WALLET,
    FakeProvider,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    no_network,
    run,
)
from tests.unit.test_new_business_model import _assert_all_journals_balance, _balance, world  # noqa: F401

pytestmark = pytest.mark.unit

ENCRYPTION_KEY = "synthetic-test-payment-settings-encryption-key"
SECRETS = {
    "PAYIN_API_KEY": "SYNTHETIC-PAYIN-KEY-0001",
    "IPN_SECRET": "synthetic-ipn-secret-0002",
    "PAYOUT_API_KEY": "SYNTHETIC-PAYOUT-KEY-0003",
    "PAYOUT_EMAIL": "treasury@example.com",
    "PAYOUT_PASSWORD": "synthetic payout pass 0004",
    "PAYOUT_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
}


@pytest.fixture(autouse=True)
def payment_env(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", ENCRYPTION_KEY)
    for name in ("NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET", "NOWPAYMENTS_PAYOUT_API_KEY", "NOWPAYMENTS_EMAIL",
                 "NOWPAYMENTS_PASSWORD", "NOWPAYMENTS_PAYOUT_TOTP_SECRET"):
        monkeypatch.setattr(settings, name, "")
    pc.invalidate_runtime()
    from app.api.api_v1.endpoints import payment_webhooks

    payment_webhooks._bad_callbacks.clear()
    yield
    pc.invalidate_runtime()


@pytest.fixture(autouse=True)
def payout_logins(monkeypatch):
    """The connection test's payout login never leaves the process: it is
    recorded here and succeeds unless a test replaces it."""
    seen = []
    monkeypatch.setattr(pc, "_payout_login", lambda credentials: seen.append(credentials))
    return seen


def plain_admin(db, name="plainadmin") -> User:
    """An administrator who holds NEITHER Finance & Payments permission."""
    row = User(email=f"{name}@example.com", username=name, hashed_password=get_password_hash(PASSWORD),
               is_active=True, is_deleted=False, is_admin=True, date_of_birth=datetime(1990, 1, 1),
               personal_referral_code=name.upper())
    db.add(row)
    db.commit()
    return row


def fake_http(responses=None):
    """A GET-only stand-in for the provider. Records every call."""
    calls = []
    table = {"payout-withdrawal/min-amount": (200, '{"result": 0.5}'), "payout/fee": (200, '{"fee": 0.0234}'),
             "/balance": (200, '{"usdtbsc": {"amount": 250.5, "pendingAmount": 0}}'),
             "/currencies": (200, '{"currencies": ["usdtbsc"]}'), "/status": (200, '{"message": "OK"}')}
    table.update(responses or {})

    def http(url, headers):
        calls.append((url, dict(headers)))
        for fragment, answer in table.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return 404, "{}"

    return http, calls


def env_payout_credentials(monkeypatch):
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")


def everything_audited(db) -> str:
    rows = db.query(PaymentConfigAudit).all()
    trail = db.query(AuditTrail).all()
    return json.dumps([[r.action, r.changed_fields, r.old_values, r.new_values] for r in rows]
                      + [[t.action, t.old_values, t.new_values] for t in trail], default=str)


# ===========================================================================
# 1. Defaults and precedence
# ===========================================================================

def test_defaults_are_the_owner_rules_and_every_money_switch_is_off(db):
    config = pc.load(db)
    assert (config.version, config.persisted) == (0, False) and db.query(PaymentSettings).count() == 0
    assert (config.crypto_min_usd, config.usd_min_usd) == (Decimal("1.00"), Decimal("100.00"))
    assert (config.usd_fee_percent, config.usd_fee_min, config.usd_fee_max) == (Decimal("1"), Decimal("20"),
                                                                                Decimal("1000"))
    assert (config.wallet_hold_hours, config.crypto_payout_currency) == (72, "usdtbsc")
    assert config.network_fee_policy == "COMPANY_PAYS" and pc.FIELDS["network_fee_policy"].approval
    assert config.crypto_auto_payout_enabled is False and config.usd_settlement_enabled is False
    assert config.auto_payout_allowed is False and config.usd_settlement_allowed is False
    assert config.wallet_email_verification_required is True
    assert (config.payin_credential_source, config.payout_credential_source) == ("ENVIRONMENT", "ENVIRONMENT")


@pytest.mark.parametrize("amount", ["100", "1999.99", "2000", "2000.01", "5000", "99999.99", "100000", "250000"])
def test_the_default_usd_fee_is_exactly_the_existing_authoritative_rule(db, amount):
    fee, net = pc.load(db).usd_fee(amount)
    expected = cashout_fee_and_net(Decimal(amount))
    assert (fee, net) == (expected.fee, expected.net_to_member)


def test_defaults_keep_the_values_the_deployment_ran_with_and_reject_unsafe_ones(db, monkeypatch):
    monkeypatch.setattr(settings, "CRYPTO_CASHOUT_MIN_USD", Decimal("2.50"))
    monkeypatch.setattr(settings, "PAYOUT_WALLET_HOLD_HOURS", 48)
    assert (pc.load(db).crypto_min_usd, pc.load(db).wallet_hold_hours) == (Decimal("2.50"), 48)
    monkeypatch.setattr(settings, "CRYPTO_CASHOUT_MIN_USD", Decimal("-5"))      # a broken environment value
    monkeypatch.setattr(settings, "PAYOUT_WALLET_HOLD_HOURS", 999999)
    assert (pc.load(db).crypto_min_usd, pc.load(db).wallet_hold_hours) == (Decimal("1.00"), 72)


def test_the_database_row_is_authoritative_once_it_exists(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    pc.update_settings(db, admin, {"crypto_min_usd": "3"}, password=PASSWORD)
    monkeypatch.setattr(settings, "CRYPTO_CASHOUT_MIN_USD", Decimal("9.00"))     # ignored from now on
    assert pc.load(db).crypto_min_usd == Decimal("3.00") and cs.crypto_minimum(db) == Decimal("3.00")


def test_the_server_master_switches_cannot_be_overridden_from_the_admin_panel(db, monkeypatch):
    env_payout_credentials(monkeypatch)
    configure(db, crypto_auto_payout_enabled=True, usd_settlement_enabled=True, usd_settlement_account="1010")
    assert pc.load(db).auto_payout_allowed is False and engine.engine_enabled(db) is False
    assert pc.load(db).usd_settlement_allowed is False
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)
    assert engine.engine_enabled(db) is True and pc.load(db).usd_settlement_allowed is True
    configure(db, provider_enabled=False)
    assert engine.engine_enabled(db) is False


# ===========================================================================
# 2. Who may change the configuration
# ===========================================================================

def test_only_an_administrator_with_the_explicit_permission_and_password_changes_settings(client, db):
    user, plain, manager = member(db, "m1"), plain_admin(db), member(db, "boss", admin=True)
    body = {"changes": {"usd_min_usd": "150"}, "current_password": PASSWORD}
    assert client.get("/api/v1/admin/finance/settings").status_code in (401, 403)
    assert client.get("/api/v1/admin/finance/settings", headers=auth(user)).status_code == 403
    assert client.put("/api/v1/admin/finance/settings", headers=auth(user), json=body).status_code == 403

    # An administrator reads everything, but is_admin alone changes nothing.
    assert client.get("/api/v1/admin/finance/settings", headers=auth(plain)).status_code == 200
    overview = client.get("/api/v1/admin/finance/overview", headers=auth(plain)).json()
    assert overview["permissions"] == {"can_manage": False, "can_process": False}
    refused = client.put("/api/v1/admin/finance/settings", headers=auth(plain), json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "FORBIDDEN"
    assert client.post("/api/v1/admin/finance/connection-test", headers=auth(plain)).status_code == 403
    assert client.put("/api/v1/admin/finance/credentials", headers=auth(plain),
                      json={"values": {"PAYIN_API_KEY": SECRETS["PAYIN_API_KEY"]},
                            "current_password": PASSWORD}).status_code == 403

    for password in ("", "not-the-password"):
        denied = client.put("/api/v1/admin/finance/settings", headers=auth(manager),
                            json={**body, "current_password": password})
        assert denied.status_code == 403 and denied.json()["detail"]["code"] == "REAUTH_REQUIRED"
    assert db.query(PaymentSettings).count() == 0 and db.query(PaymentConfigAudit).count() == 0

    saved = client.put("/api/v1/admin/finance/settings", headers=auth(manager), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1 and pc.load(db).usd_min_usd == Decimal("150.00")
    entry = db.query(PaymentConfigAudit).one()
    assert (entry.action, entry.actor_id, entry.version, entry.changed_fields) == (
        "SETTINGS_UPDATED", manager.id, 1, ["usd_min_usd"])
    assert entry.old_values == {"usd_min_usd": "100.00"} and entry.new_values == {"usd_min_usd": "150"}
    history = client.get("/api/v1/admin/finance/audit", headers=auth(plain)).json()
    assert history["total"] == 1 and history["items"][0]["changed_fields"] == ["usd_min_usd"]


def test_every_change_is_versioned_and_an_unchanged_value_is_not_a_change(db):
    admin = member(db, "boss", admin=True)
    pc.update_settings(db, admin, {"usd_min_usd": "150", "wallet_hold_hours": 96}, password=PASSWORD)
    pc.update_settings(db, admin, {"usd_min_usd": "150.00"}, password=PASSWORD)          # same value
    pc.update_settings(db, admin, {"usd_fee_percent": "2"}, password=PASSWORD)
    assert [(a.version, a.changed_fields) for a in db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id)] == [
        (1, ["usd_min_usd", "wallet_hold_hours"]), (2, ["usd_fee_percent"])]
    assert pc.load(db).version == 2


# ===========================================================================
# 3. Validation
# ===========================================================================

@pytest.mark.parametrize("changes", [
    {"crypto_min_usd": "-1"}, {"crypto_min_usd": "0"}, {"crypto_min_usd": "abc"}, {"crypto_min_usd": "1.005"},
    {"crypto_min_usd": None}, {"crypto_min_usd": True}, {"crypto_min_usd": "NaN"}, {"crypto_min_usd": "Infinity"},
    {"usd_min_usd": "0"}, {"usd_fee_percent": "-1"}, {"usd_fee_percent": "51"}, {"usd_fee_min": "-0.01"},
    {"usd_fee_min": "30", "usd_fee_max": "20"},                       # minimum fee above the maximum fee
    {"usd_min_usd": "10"},                                            # the $20 minimum fee would leave nothing
    {"usd_min_usd": "20"},                                            # exactly zero net
    {"payout_interval_seconds": 5}, {"payout_interval_seconds": "12.5"}, {"wallet_hold_hours": -1},
    {"wallet_hold_hours": 100000}, {"max_daily_payout_count": 0}, {"retry_max_attempts": 0},
    {"crypto_payout_currency": "usdttrc20"}, {"crypto_payout_currency": "dogecoin"},
    {"network_fee_policy": "NOBODY_PAYS"}, {"payout_credential_source": "FILE"},
    {"crypto_min_usd": "2000"},                                       # above the maximum single payout
    {"max_single_payout_usd": "9000"},                                # above the maximum daily amount
    {"provider_enabled": "yes"}, {"provider_display_name": ""}, {"provider_display_name": "<b>x</b>"},
    {"usd_processing_policy": "AUTOMATIC"}, {"usd_destination_note": "x" * 501},
    {"usd_settlement_account": "9999"},                               # not in the chart of accounts
    {"no_such_setting": 1},
])
def test_invalid_or_unsafe_values_are_rejected_and_nothing_is_stored(db, changes):
    admin = member(db, "boss", admin=True)
    with pytest.raises(pc.PaymentConfigError) as refused:
        pc.update_settings(db, admin, changes, password=PASSWORD)
    assert refused.value.code in ("INVALID_VALUE", "INVALID_FIELD")
    assert db.query(PaymentConfigAudit).count() == 0 and pc.load(db).version == 0


def test_valid_boundaries_are_accepted_with_decimal_precision(db):
    admin = member(db, "boss", admin=True)
    config = pc.update_settings(db, admin, {"crypto_min_usd": "0.01", "usd_min_usd": "20.01", "usd_fee_percent": "0",
                                            "usd_fee_min": "0", "usd_fee_max": "0", "wallet_hold_hours": 0,
                                            "network_fee_policy": "member_pays"}, password=PASSWORD)
    assert config.crypto_min_usd == Decimal("0.01") and config.network_fee_policy == "MEMBER_PAYS"
    assert config.usd_fee("20.01") == (Decimal("0.00"), Decimal("20.01"))
    assert pc.update_settings(db, admin, {"usd_fee_percent": "1.125", "usd_fee_max": "1000"},
                              password=PASSWORD).usd_fee("333.33") == (Decimal("3.75"), Decimal("329.58"))


def test_validation_errors_reach_the_api_as_422_with_the_field(client, db):
    admin = member(db, "boss", admin=True)
    resp = client.put("/api/v1/admin/finance/settings", headers=auth(admin),
                      json={"changes": {"usd_fee_percent": "75"}, "current_password": PASSWORD})
    assert resp.status_code == 422 and resp.json()["detail"]["field"] == "usd_fee_percent"
    extra = client.put("/api/v1/admin/finance/settings", headers=auth(admin),
                       json={"changes": {}, "current_password": PASSWORD, "force": True})
    assert extra.status_code == 422


# ===========================================================================
# 4. Credentials: encrypted at rest, write-only, explicit replace and delete
# ===========================================================================

def test_encryption_round_trip_is_bound_to_its_purpose_and_to_the_dedicated_key(monkeypatch):
    sealed = payment_crypto.encrypt("plain-value", "purpose-a")
    assert sealed.startswith("v1:") and "plain-value" not in sealed
    assert payment_crypto.decrypt(sealed, "purpose-a") == "plain-value"
    assert payment_crypto.encrypt("plain-value", "purpose-a") != sealed          # fresh nonce every time
    with pytest.raises(payment_crypto.PaymentCryptoError):
        payment_crypto.decrypt(sealed, "purpose-b")
    with pytest.raises(payment_crypto.PaymentCryptoError):
        payment_crypto.decrypt(sealed[:-4] + "AAAA", "purpose-a")                # tampered
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "another-synthetic-key-of-sufficient-length")
    with pytest.raises(payment_crypto.PaymentCryptoError):
        payment_crypto.decrypt(sealed, "purpose-a")
    # No fallback to any other application secret.
    monkeypatch.delenv("PAYMENT_SETTINGS_ENCRYPTION_KEY")
    monkeypatch.setattr(settings, "PAYMENT_SETTINGS_ENCRYPTION_KEY", "")
    assert payment_crypto.key_configured() is False and settings.SECRET_KEY
    with pytest.raises(payment_crypto.PaymentCryptoError):
        payment_crypto.encrypt("plain-value", "purpose-a")


def test_credentials_are_stored_encrypted_and_never_returned(client, db):
    admin = member(db, "boss", admin=True)
    resp = client.put("/api/v1/admin/finance/credentials", headers=auth(admin),
                      json={"values": SECRETS, "current_password": PASSWORD})
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["stored"]) == sorted(SECRETS)
    stored = {r.name: r for r in db.query(PaymentCredential).all()}
    assert set(stored) == set(SECRETS)
    for name, value in SECRETS.items():
        assert stored[name].ciphertext.startswith("v1:") and value not in stored[name].ciphertext
        assert stored[name].set_by == admin.id

    pages = [resp.text] + [client.get(f"/api/v1/admin/finance/{path}", headers=auth(admin)).text
                           for path in ("overview", "provider", "settings", "audit", "webhook", "reconciliation")]
    for page in pages:
        for name, value in SECRETS.items():
            assert value not in page and stored[name].ciphertext not in page
    statuses = {c["name"]: c for c in client.get("/api/v1/admin/finance/provider", headers=auth(admin)).json()["credentials"]}
    assert all(c["stored"] == "CONFIGURED" and c["stored_readable"] is True for c in statuses.values())
    assert all(c["in_use"] == "NOT CONFIGURED" for c in statuses.values())      # source is still the environment
    assert set(statuses["PAYOUT_PASSWORD"]) == {"name", "label", "group", "source", "stored", "stored_readable",
                                                "stored_updated_at", "stored_updated_by", "environment", "in_use"}
    audited = everything_audited(db)
    assert all(value not in audited for value in SECRETS.values())
    entry = db.query(PaymentConfigAudit).one()
    assert entry.action == "CREDENTIALS_STORED" and entry.new_values["credentials_added"] == sorted(SECRETS)


def test_a_blank_credential_keeps_the_existing_one_and_replacement_is_explicit(db):
    admin = member(db, "boss", admin=True)
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    before = {r.name: r.ciphertext for r in db.query(PaymentCredential).all()}

    assert pc.set_credentials(db, admin, {"PAYIN_API_KEY": "", "IPN_SECRET": None, "PAYOUT_API_KEY": "   "},
                              password=PASSWORD) == []
    assert {r.name: r.ciphertext for r in db.query(PaymentCredential).all()} == before
    assert db.query(PaymentConfigAudit).count() == 1                            # a blank save is not a change

    assert pc.set_credentials(db, admin, {"PAYIN_API_KEY": "SYNTHETIC-PAYIN-KEY-9999", "IPN_SECRET": ""},
                              password=PASSWORD) == ["PAYIN_API_KEY"]
    after = {r.name: r.ciphertext for r in db.query(PaymentCredential).all()}
    assert after["PAYIN_API_KEY"] != before["PAYIN_API_KEY"] and after["IPN_SECRET"] == before["IPN_SECRET"]
    assert db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first().new_values == {
        "credentials_added": [], "credentials_replaced": ["PAYIN_API_KEY"]}
    configure(db, payin_credential_source="DATABASE")
    assert pc.resolve_credentials(db).get("PAYIN_API_KEY") == "SYNTHETIC-PAYIN-KEY-9999"


def test_deleting_a_credential_is_a_separate_authenticated_action(client, db):
    admin, plain = member(db, "boss", admin=True), plain_admin(db)
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    url = "/api/v1/admin/finance/credentials/PAYOUT_PASSWORD/delete"
    assert client.post(url, headers=auth(plain), json={"current_password": PASSWORD}).status_code == 403
    assert client.post(url, headers=auth(admin), json={"current_password": "wrong"}).status_code == 403
    assert db.query(PaymentCredential).count() == len(SECRETS)

    done = client.post(url, headers=auth(admin), json={"current_password": PASSWORD})
    assert done.status_code == 200 and done.json()["deleted"] is True
    assert {r.name for r in db.query(PaymentCredential).all()} == set(SECRETS) - {"PAYOUT_PASSWORD"}
    assert client.post(url, headers=auth(admin), json={"current_password": PASSWORD}).json()["deleted"] is False
    assert db.query(PaymentConfigAudit).filter_by(action="CREDENTIAL_DELETED").one().new_values == {
        "credential": "PAYOUT_PASSWORD"}

    # Not while it is the credential the running engine depends on.
    pc.set_credentials(db, admin, {"PAYOUT_PASSWORD": SECRETS["PAYOUT_PASSWORD"]}, password=PASSWORD)
    configure(db, payout_credential_source="DATABASE", crypto_auto_payout_enabled=True)
    with pytest.raises(pc.PaymentConfigError) as in_use:
        pc.delete_credential(db, admin, "PAYOUT_TOTP_SECRET", password=PASSWORD)
    assert in_use.value.code == "IN_USE" and db.query(PaymentCredential).count() == len(SECRETS)


@pytest.mark.parametrize("values", [{"PAYOUT_TOTP_SECRET": "not base32 !!"}, {"PAYOUT_EMAIL": "not-an-email"},
                                    {"PAYIN_API_KEY": "short"}, {"PAYIN_API_KEY": "has a space in it"},
                                    {"UNKNOWN_SECRET": "whatever-value-here"}])
def test_malformed_credentials_are_rejected(db, values):
    admin = member(db, "boss", admin=True)
    with pytest.raises(pc.PaymentConfigError):
        pc.set_credentials(db, admin, values, password=PASSWORD)
    assert db.query(PaymentCredential).count() == 0


def test_without_the_encryption_key_nothing_is_stored_and_stored_values_are_not_used(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    configure(db, payin_credential_source="DATABASE", payout_credential_source="DATABASE")
    assert pc.resolve_credentials(db).payout_ready is True

    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "a-different-synthetic-key-with-enough-length")
    credentials = pc.resolve_credentials(db)                                   # the key was changed
    assert credentials.payout_ready is False and credentials.get("PAYIN_API_KEY") is None
    assert all(c["stored_readable"] is False for c in pc.credential_status(db))

    monkeypatch.delenv("PAYMENT_SETTINGS_ENCRYPTION_KEY")
    with pytest.raises(pc.PaymentConfigError) as missing:
        pc.set_credentials(db, admin, {"PAYIN_API_KEY": "SYNTHETIC-PAYIN-KEY-7777"}, password=PASSWORD)
    assert missing.value.code == "ENCRYPTION_KEY_MISSING"


def test_resolved_credentials_never_show_their_values_when_printed(db, monkeypatch):
    env_payout_credentials(monkeypatch)
    credentials = pc.resolve_credentials(db)
    text = f"{credentials!r} {credentials} {pc.build_payin_runtime(db)!r}"
    assert all(value not in text for value in PAYOUT_ENV.values()) and "synthetic-env-payin-key" not in text


# ===========================================================================
# 5. Credential source: one place per group, never mixed, no fallback
# ===========================================================================

def test_environment_is_the_default_source_and_stored_credentials_are_inert_until_switched(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    env_payout_credentials(monkeypatch)
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    credentials = pc.resolve_credentials(db)
    assert credentials.get("PAYOUT_API_KEY") == PAYOUT_ENV["NOWPAYMENTS_PAYOUT_API_KEY"]
    assert credentials.get("PAYIN_API_KEY") == "synthetic-env-payin-key"

    pc.update_settings(db, admin, {"payout_credential_source": "DATABASE"}, password=PASSWORD)
    credentials = pc.resolve_credentials(db)
    assert credentials.get("PAYOUT_API_KEY") == SECRETS["PAYOUT_API_KEY"]         # the database, only
    assert credentials.get("PAYIN_API_KEY") == "synthetic-env-payin-key"          # pay-in was not switched
    assert db.query(PaymentCredential).count() == len(SECRETS)                    # nothing imported or copied


def test_switching_to_the_database_needs_every_credential_and_never_falls_back(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    env_payout_credentials(monkeypatch)
    pc.set_credentials(db, admin, {k: v for k, v in SECRETS.items() if k != "PAYOUT_TOTP_SECRET"},
                       password=PASSWORD)
    with pytest.raises(pc.PaymentConfigError) as incomplete:
        pc.update_settings(db, admin, {"payout_credential_source": "DATABASE"}, password=PASSWORD)
    assert incomplete.value.code == "CREDENTIALS_INCOMPLETE" and "TOTP" in str(incomplete.value)

    configure(db, payout_credential_source="DATABASE")                            # forced, as if one was deleted
    credentials = pc.resolve_credentials(db)
    assert credentials.get("PAYOUT_TOTP_SECRET") is None and credentials.payout_ready is False
    assert credentials.payout_missing == ["Payout authenticator (TOTP) secret"]   # the environment one is NOT used


def test_the_pay_in_key_is_never_used_as_the_payout_key(db, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")
    for name in ("NOWPAYMENTS_EMAIL", "NOWPAYMENTS_PASSWORD", "NOWPAYMENTS_PAYOUT_TOTP_SECRET"):
        monkeypatch.setattr(settings, name, PAYOUT_ENV[name])
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    configure(db, crypto_auto_payout_enabled=True)
    credentials = pc.resolve_credentials(db)
    assert credentials.get("PAYOUT_API_KEY") is None and credentials.payout_missing == ["Payout API key"]
    assert engine.engine_enabled(db) is False and run(db, FakeProvider())["enabled"] is False


def test_pay_in_helpers_use_the_selected_source_and_stop_when_the_provider_is_disabled(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")
    assert pc.build_payin_runtime(db).api_key == "synthetic-env-payin-key"
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    pc.update_settings(db, admin, {"payin_credential_source": "DATABASE"}, password=PASSWORD)
    runtime = pc.build_payin_runtime(db)
    assert (runtime.source, runtime.api_key, runtime.provider_enabled) == ("DATABASE", SECRETS["PAYIN_API_KEY"], True)

    monkeypatch.setattr(pc, "payin_runtime", lambda: runtime)
    assert nowpayments._headers()["x-api-key"] == SECRETS["PAYIN_API_KEY"]
    monkeypatch.setattr(pc, "payin_runtime", lambda: pc.PayinRuntime(False, "DATABASE", SECRETS["PAYIN_API_KEY"]))
    with pytest.raises(nowpayments.NowPaymentsError):                             # refused before any HTTP call
        asyncio.run(nowpayments.create_payment(price_amount=Decimal("10"), price_currency="usd", order_id="o-1",
                                               order_description="synthetic"))


def test_pay_in_keeps_working_from_the_environment_when_the_store_was_never_readable(monkeypatch):
    import app.db.session as session_module

    def broken():
        raise RuntimeError("configuration store unavailable")

    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")
    monkeypatch.setattr(session_module, "SessionLocal", broken)
    pc.invalidate_runtime()
    runtime = pc.payin_runtime()
    assert (runtime.source, runtime.api_key, runtime.provider_enabled) == ("ENVIRONMENT", "synthetic-env-payin-key", True)


# ===========================================================================
# 6. Connection test: read-only, sanitized
# ===========================================================================

def test_connection_test_uses_only_read_requests_and_records_a_sanitized_result(db, monkeypatch, payout_logins):
    admin = member(db, "boss", admin=True)
    env_payout_credentials(monkeypatch)
    http, calls = fake_http()
    result = pc.run_connection_test(db, admin, http=http, now=NOW)
    assert result["status"] == "OK" and result["last_success_at"] == NOW.isoformat()
    assert {c["name"]: c["status"] for c in result["checks"]} == {
        "api_status": "OK", "payin_api_key": "OK", "custody_balance": "OK", "payout_minimum": "OK",
        "payout_network_fee": "OK", "payout_login": "OK"}
    assert result["facts"] == {"custody_balance": "250.5", "custody_pending": "0", "payout_minimum": "0.5",
                               "network_fee": "0.0234"}
    assert result["payout_login"] == "OK" and len(payout_logins) == 1             # one login, nothing else

    paths = [url.split("/v1/", 1)[1].split("?")[0] for url, _ in calls]
    assert paths == ["status", "currencies", "balance", "payout-withdrawal/min-amount/usdtbsc", "payout/fee"]
    assert not any(path in ("payout", "payment", "auth") or path.endswith("/verify") for path in paths)
    assert all("Authorization" not in headers for _, headers in calls)            # no payout session is opened
    assert cashouts(db) == [] and db.query(JournalEntry).count() == 0

    row = db.query(PaymentSettings).one()
    saved = json.dumps(row.last_connection_test_detail) + everything_audited(db)
    assert all(value not in saved for value in list(PAYOUT_ENV.values()) + ["synthetic-env-payin-key"])
    assert "pendingAmount" not in saved                                           # no provider response body is kept


@pytest.mark.parametrize("responses, status, failing", [
    ({"/balance": (403, '{"message": "Invalid IP"}')}, "IP_NOT_WHITELISTED", "custody_balance"),
    ({"/balance": (403, '{"message": "Access denied"}')}, "PERMISSION_DENIED", "custody_balance"),
    ({"/currencies": (401, '{"message": "Invalid api key"}')}, "AUTH_FAILED", "payin_api_key"),
    ({"/status": TimeoutError("no answer")}, "UNREACHABLE", "api_status"),
    ({"/balance": (500, "upstream error with details")}, "PROVIDER_ERROR", "custody_balance"),
    ({"/balance": (200, "<html>not json</html>")}, "INVALID_RESPONSE", "custody_balance"),
])
def test_connection_test_reports_authentication_ip_and_permission_errors_clearly(db, monkeypatch, responses, status,
                                                                                 failing):
    admin = member(db, "boss", admin=True)
    env_payout_credentials(monkeypatch)
    http, _calls = fake_http(responses)
    result = pc.run_connection_test(db, admin, http=http, now=NOW)
    assert result["status"] == status and result["last_success_at"] is None
    check = next(c for c in result["checks"] if c["name"] == failing)
    assert check["status"] == status and check["message"] == pc.CONNECTION_MESSAGES[status]
    assert "Invalid IP" not in json.dumps(result) and "upstream error" not in json.dumps(result)


def test_connection_test_without_payout_credentials_is_partial_and_never_enough_to_activate(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")
    http, calls = fake_http()
    result = pc.run_connection_test(db, admin, http=http, now=NOW)
    assert result["status"] == "PARTIAL" and len(calls) == 2                      # status + pay-in key only
    assert pc.provider_view(db)["custody_status"] == "NOT VERIFIED"


def test_a_connection_result_belongs_to_the_credentials_it_was_made_with(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    env_payout_credentials(monkeypatch)
    pc.run_connection_test(db, admin, http=fake_http()[0], now=NOW)
    assert pc.connection_view(pc.load_row(db))["status"] == "OK"
    pc.set_credentials(db, admin, {"PAYOUT_API_KEY": SECRETS["PAYOUT_API_KEY"]}, password=PASSWORD)
    assert pc.connection_view(pc.load_row(db))["status"] == "NOT_TESTED"


# ===========================================================================
# 7. Unsafe activation
# ===========================================================================

def test_automatic_payouts_cannot_be_switched_on_until_everything_is_proven(db, monkeypatch):
    admin = member(db, "boss", admin=True)
    change = {"crypto_auto_payout_enabled": True}

    def refused(**kwargs) -> str:
        with pytest.raises(pc.PaymentConfigError) as error:
            pc.update_settings(db, admin, change, password=PASSWORD, now=NOW, **kwargs)
        assert pc.load(db).crypto_auto_payout_enabled is False
        return error.value.code

    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "UNSAFE_ACTIVATION"             # no credentials
    env_payout_credentials(monkeypatch)
    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "UNSAFE_ACTIVATION"             # no connection test
    pc.run_connection_test(db, admin, http=fake_http({"/balance": (403, "Invalid IP")})[0], now=NOW)
    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "UNSAFE_ACTIVATION"             # the test failed
    pc.run_connection_test(db, admin, http=fake_http()[0], now=NOW - timedelta(hours=25))
    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "UNSAFE_ACTIVATION"             # the test is stale
    pc.run_connection_test(db, admin, http=fake_http()[0], now=NOW)
    assert refused() == "CONFIRMATION_REQUIRED"
    assert refused(confirmation="enable") == "CONFIRMATION_REQUIRED"
    configure(db, provider_enabled=False)
    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "UNSAFE_ACTIVATION"             # provider disabled
    configure(db, provider_enabled=True)

    config = pc.update_settings(db, admin, change, password=PASSWORD, confirmation=pc.CONFIRM_AUTO_PAYOUT, now=NOW)
    assert config.crypto_auto_payout_enabled is True
    # ... and still nothing is paid: the server master switch is off.
    assert engine.engine_enabled(db) is False and run(db, FakeProvider()) == {"enabled": False, "reconciled": {},
                                                                              "members": {}}


def test_usd_settlement_cannot_be_switched_on_without_an_account_and_a_confirmation(ledger):
    db = ledger
    admin = member(db, "boss", admin=True)

    def refused(changes, **kwargs) -> str:
        with pytest.raises(pc.PaymentConfigError) as error:
            pc.update_settings(db, admin, changes, password=PASSWORD, **kwargs)
        return error.value.code

    assert refused({"usd_settlement_enabled": True}, confirmation=pc.CONFIRM_USD_SETTLEMENT) == "UNSAFE_ACTIVATION"
    assert refused({"usd_settlement_enabled": True, "usd_settlement_account": "1010"}) == "CONFIRMATION_REQUIRED"
    config = pc.update_settings(db, admin, {"usd_settlement_enabled": True, "usd_settlement_account": "1010"},
                                password=PASSWORD, confirmation=pc.CONFIRM_USD_SETTLEMENT)
    assert config.usd_settlement_enabled is True and config.usd_settlement_allowed is False   # server switch off


def test_changing_settings_releases_no_reservation_and_sends_nothing(ledger, engine_on):
    db = ledger
    admin = member(db, "boss", admin=True)
    usd, crypto = member(db, "m1", method="USD", wallet=None), member(db, "m2", method="CRYPTO")
    commission(db, usd, "150.00")
    commission(db, crypto, "5.00")
    request = cs.request_usd_cashout(db, usd, idempotency_key="k", now=NOW)
    provider = FakeProvider()
    run(db, provider)
    assert len(provider.created) == 1

    pc.update_settings(db, admin, {"usd_min_usd": "500", "usd_fee_percent": "5", "crypto_min_usd": "50",
                                   "usd_cashout_enabled": False, "crypto_cashout_enabled": False,
                                   "crypto_auto_payout_enabled": False, "wallet_hold_hours": 1}, password=PASSWORD)
    db.expire_all()
    assert [c.status for c in cashouts(db)] == ["requested", "processing"]
    assert (request.gross_amount, request.fee, request.net_amount) == (Decimal("150.00"), Decimal("20.00"),
                                                                       Decimal("130.00"))
    assert get_commission_balance(db, usd.id).reserved == Decimal("150.00")
    assert get_commission_balance(db, crypto.id).reserved == Decimal("5.00")
    assert len(provider.created) == 1 and db.query(JournalEntry).count() == 0


# ===========================================================================
# 8. Webhook (IPN): signature verification is unchanged, outcomes are counted
# ===========================================================================

def _sign(body: dict, secret: str) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha512).hexdigest()


def test_ipn_signature_is_still_required_and_rejections_are_counted(client, db, monkeypatch):
    admin = member(db, "boss", admin=True)
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "synthetic-env-ipn-secret")
    body = {"order_id": "mh5-unknown-synthetic", "payment_id": "1", "payment_status": "finished"}
    url = "/api/v1/webhooks/nowpayments"

    assert client.post(url, json=body).status_code == 403                                   # no signature
    assert client.post(url, json=body, headers={"x-nowpayments-sig": "0" * 128}).status_code == 403
    assert client.post(url, json=body, headers={"x-nowpayments-sig": _sign(body, "wrong-secret")}).status_code == 403
    assert client.post(url, json=body, headers={"x-nowpayments-sig": _sign(body, "synthetic-env-ipn-secret")}
                       ).json() == {"ok": True}
    assert client.post(url, content=b"{not json", headers={"content-type": "application/json"}).status_code == 400
    health = client.get("/api/v1/admin/finance/webhook", headers=auth(admin)).json()
    assert health["last_7_days"]["REJECTED_SIGNATURE"] == 3 and health["last_7_days"]["UNKNOWN_ORDER"] == 1
    assert health["last_7_days"]["INVALID_JSON"] == 1 and health["last_7_days"]["ACCEPTED"] == 0
    # The last SIGNED callback verified (after three rejected ones): the secret in force is right.
    assert health["status"] == "HEALTHY" and health["callback_url_editable"] is False
    assert health["last_verified_signature_at"] is not None and health["last_accepted_at"] is None
    assert health["callback_url"].endswith("/api/v1/webhooks/nowpayments")
    assert db.query(PaymentWebhookStat).count() == 3                                        # bounded: one row per outcome/day

    # The IPN secret follows the selected source: after the switch only the stored one verifies.
    pc.set_credentials(db, admin, SECRETS, password=PASSWORD)
    pc.update_settings(db, admin, {"payin_credential_source": "DATABASE"}, password=PASSWORD)
    assert client.post(url, json=body, headers={"x-nowpayments-sig": _sign(body, "synthetic-env-ipn-secret")}
                       ).status_code == 403
    assert client.post(url, json=body, headers={"x-nowpayments-sig": _sign(body, SECRETS["IPN_SECRET"])}
                       ).status_code == 200


def test_an_empty_ipn_secret_never_verifies_anything(db):
    body = {"order_id": "x"}
    assert nowpayments.verify_ipn_signature(body, _sign(body, ""), secret="") is False
    assert nowpayments.verify_ipn_signature(body, "", secret="some-secret") is False


# ===========================================================================
# 9. Payout wallet: password + one-time emailed link bound to the wallet
# ===========================================================================

def ask(db, user, address=OTHER_WALLET, now=NOW):
    return cs.change_payout_wallet(db, user, address=address, currency="usdtbsc", password=PASSWORD, now=now,
                                   ip="203.0.113.7")


def test_a_wallet_change_takes_effect_only_after_the_emailed_link_is_confirmed(client, ledger, monkeypatch):
    db = ledger
    monkeypatch.setenv("RESEND_API_KEY", "re_synthetic_test_key_000000")
    user = member(db, "m1", method="CRYPTO")
    body = {"usdt_wallet_address": OTHER_WALLET, "payout_currency": "usdtbsc"}
    denied = client.patch("/api/v1/users/me/wallet", headers=auth(user), json={**body, "current_password": "nope"})
    assert denied.status_code == 403 and db.query(PayoutWalletVerification).count() == 0

    resp = client.patch("/api/v1/users/me/wallet", headers=auth(user), json={**body, "current_password": PASSWORD})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["confirmation_required"] is True and data["confirmation_email_sent"] is True
    assert data["usdt_wallet_address"] == WALLET and data["wallet_status"] == "VERIFIED"      # unchanged so far
    assert data["pending_wallet"]["wallet"] == "0xbbbb...bbbb" and data["hold_hours"] == 72
    db.refresh(user)
    assert user.usdt_wallet_address == WALLET and db.query(PayoutWalletChange).count() == 0

    pending = db.query(PayoutWalletVerification).one()
    assert (pending.address, pending.currency, pending.consumed_at) == (OTHER_WALLET, "usdtbsc", None)
    assert re.fullmatch(r"[0-9a-f]{64}", pending.token_hash)                    # a digest, never the token
    delivery = db.query(EmailDelivery).one()
    assert (delivery.event_key, delivery.status, delivery.user_id) == ("PAYOUT.WALLET_CONFIRMATION", "QUEUED", user.id)
    assert OTHER_WALLET not in (delivery.payload_ciphertext or "") and pending.token_hash not in resp.text
    assert cs.summary(db, user)["destination"]["pending_wallet"]["wallet"] == "0xbbbb...bbbb"


def test_the_confirmation_email_names_the_masked_wallet_and_carries_the_link_in_the_fragment(ledger):
    from app.services.email_render import render

    db = ledger
    user = member(db, "m1")
    result = ask(db, user)
    subject, html, text = render(db, event_key="PAYOUT.WALLET_CONFIRMATION", to=user.email, user_id=user.id, lang="en",
                                 context={"link_credential": result.token, "wallet": "0xbbbb...bbbb",
                                          "network": "USDT BSC (BEP20)", "minutes": 60})
    assert subject == "Confirm your MyHigh5 payout wallet"
    assert f"/payout-wallet/confirm#token={result.token}" in html and f"#token={result.token}" in text
    assert "0xbbbb...bbbb" in html and OTHER_WALLET not in html and "USDT BSC (BEP20)" in html
    assert "expires in 60 minutes" in text and "did not make this request" in text


def test_the_link_works_once_for_its_own_account_wallet_and_lifetime(ledger, engine_on):
    db = ledger
    user, other = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
    commission(db, user, "5.00")
    result = ask(db, user)
    assert result.pending is True and result.state.address == WALLET and len(result.token) >= 40

    def invalid(account, token, **kwargs) -> bool:
        with pytest.raises(cs.CashoutError) as error:
            cs.confirm_payout_wallet(db, account, token, **kwargs)
        return error.value.code == "LINK_INVALID"

    assert invalid(other, result.token, now=NOW)                                  # another account
    assert invalid(user, result.token + "x", now=NOW) and invalid(user, "short", now=NOW)
    assert invalid(user, result.token, now=NOW + timedelta(minutes=61))           # expired
    db.refresh(user)
    assert user.usdt_wallet_address == WALLET

    state = cs.confirm_payout_wallet(db, user, result.token, now=NOW + timedelta(minutes=5), ip="203.0.113.7")
    assert (state.status, state.address) == ("ON_HOLD", OTHER_WALLET)
    change = db.query(PayoutWalletChange).one()
    assert (change.old_address, change.new_address, change.verification_method) == (WALLET, OTHER_WALLET, "EMAIL")
    assert invalid(user, result.token, now=NOW + timedelta(minutes=6))            # replay
    assert db.query(PayoutWalletChange).count() == 1

    # Nothing is paid during the hold; afterwards the engine pays the confirmed wallet.
    provider = FakeProvider()
    assert run(db, provider, now=NOW + timedelta(hours=1))["members"] == {"WALLET_ON_HOLD": 1}
    assert run(db, provider, now=NOW + timedelta(hours=73))["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["address"] == OTHER_WALLET
    audited = everything_audited(db)
    assert result.token not in audited and OTHER_WALLET not in audited and WALLET not in audited


def test_a_newer_request_revokes_the_earlier_link_and_the_token_is_bound_to_the_exact_wallet(ledger):
    db = ledger
    user = member(db, "m1")
    first = ask(db, user, address=OTHER_WALLET)
    second = ask(db, user, address="0x" + "c" * 40, now=NOW + timedelta(minutes=1))
    with pytest.raises(cs.CashoutError):
        cs.confirm_payout_wallet(db, user, first.token, now=NOW + timedelta(minutes=2))       # replaced
    # Tampering with the stored destination breaks the link instead of redirecting the payout.
    row = db.query(PayoutWalletVerification).filter_by(id=second.verification_id).one()
    row.address = "0x" + "d" * 40
    db.commit()
    with pytest.raises(cs.CashoutError) as tampered:
        cs.confirm_payout_wallet(db, user, second.token, now=NOW + timedelta(minutes=2))
    assert tampered.value.code == "LINK_INVALID"
    row.address, row.currency = "0x" + "c" * 40, "usdterc20"
    db.commit()
    with pytest.raises(cs.CashoutError):
        cs.confirm_payout_wallet(db, user, second.token, now=NOW + timedelta(minutes=2))      # another network
    db.refresh(user)
    assert user.usdt_wallet_address == WALLET and db.query(PayoutWalletChange).count() == 0


def test_wallet_change_requests_are_limited_and_wait_for_an_open_payout(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    for index in range(3):
        ask(db, user, address="0x" + str(index) * 40, now=NOW + timedelta(minutes=index))
    with pytest.raises(cs.CashoutError) as limited:
        ask(db, user, now=NOW + timedelta(minutes=5))
    assert limited.value.code == "TOO_MANY_CHANGES"

    other = member(db, "m2", method="CRYPTO")
    commission(db, other, "5.00")
    result = ask(db, other)
    run(db, FakeProvider())                                                       # a payout is now in progress
    with pytest.raises(cs.CashoutError) as busy:
        cs.confirm_payout_wallet(db, other, result.token, now=NOW + timedelta(minutes=1))
    assert busy.value.code == "PAYOUT_IN_PROGRESS"
    db.refresh(other)
    assert other.usdt_wallet_address == WALLET and cashouts(db, other)[0].wallet_snapshot == WALLET


def test_a_legacy_wallet_is_never_paid_until_it_is_confirmed(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", verified_at=None)                    # saved before these rules
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"WALLET_UNVERIFIED": 1} and provider.created == []
    result = ask(db, user, address=WALLET, now=datetime.utcnow())                 # the same address, now proven
    assert cs.summary(db, user)["status"] == "WALLET_CONFIRMATION_PENDING"
    confirm = client.post("/api/v1/wallet/payout-wallet/confirm", headers=auth(user), json={"token": result.token})
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["wallet_status"] == "ON_HOLD" and confirm.json()["wallet"] == "0xaaaa...aaaa"
    again = client.post("/api/v1/wallet/payout-wallet/confirm", headers=auth(user), json={"token": result.token})
    assert again.status_code == 400 and again.json()["detail"]["code"] == "LINK_INVALID"
    assert client.post("/api/v1/wallet/payout-wallet/confirm", json={"token": result.token}).status_code in (401, 403)


# ===========================================================================
# 10. Crypto engine limits driven by the configuration
# ===========================================================================

def test_the_crypto_minimum_is_configurable(ledger, engine_on):
    db = ledger
    below, exact, above = (member(db, name, method="CRYPTO") for name in ("m1", "m2", "m3"))
    for user, amount in ((below, "4.99"), (exact, "5.00"), (above, "5.01")):
        commission(db, user, amount)
    configure(db, crypto_min_usd=Decimal("5.00"), max_daily_payout_count=10)
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"BELOW_MINIMUM": 1, "SUBMITTED": 2}
    assert sorted(c["amount"] for c in provider.created) == [Decimal("5.00"), Decimal("5.01")]


@pytest.mark.parametrize("settings_, provider_kwargs, amounts, expected", [
    ({"max_single_payout_usd": Decimal("10.00")}, {}, ["10.01"], {"EXCEEDS_SINGLE_LIMIT": 1}),
    ({"max_single_payout_usd": Decimal("10.00")}, {}, ["10.00"], {"SUBMITTED": 1}),
    ({"provider_balance_reserve_usd": Decimal("50.00")}, {"balance": "54.00"}, ["5.00"],
     {"INSUFFICIENT_PROVIDER_BALANCE": 1}),
    ({"provider_balance_reserve_usd": Decimal("50.00")}, {"balance": "55.02"}, ["5.00"], {"SUBMITTED": 1}),
    ({"max_network_fee_percent": Decimal("1.00")}, {"fee": "0.06"}, ["5.00"], {"NETWORK_FEE_TOO_HIGH": 1}),
    ({}, {"minimum": "5.01"}, ["5.00"], {"BELOW_PROVIDER_MINIMUM": 1}),        # $1 is eligible, not executable
])
def test_single_payout_reserve_fee_and_provider_minimum_limits(ledger, engine_on, settings_, provider_kwargs,
                                                               amounts, expected):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    for amount in amounts:
        commission(db, user, amount)
    configure(db, **settings_)
    provider = FakeProvider(**provider_kwargs)
    assert run(db, provider)["members"] == expected
    if "SUBMITTED" not in expected:
        assert provider.created == [] and cashouts(db) == []
        assert get_commission_balance(db, user.id).reserved == 0


def test_daily_amount_and_count_limits_stop_new_payouts(ledger, engine_on):
    db = ledger
    users = [member(db, f"m{i}", method="CRYPTO") for i in range(4)]
    for user in users:
        commission(db, user, "40.00")
    configure(db, max_daily_payout_usd=Decimal("100.00"), max_single_payout_usd=Decimal("100.00"))
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 2, "DAILY_LIMIT_REACHED": 2}
    assert run(db, provider)["members"] == {"DAILY_LIMIT_REACHED": 2}             # counted from the database too
    assert len(provider.created) == 2
    assert engine.reconciliation_report(db, now=NOW)["last_24_hours"]["crypto_payout_amount"] == 80.0
    configure(db, max_daily_payout_usd=Decimal("5000.00"), max_daily_payout_count=3)
    assert run(db, provider)["members"] == {"SUBMITTED": 1, "DAILY_LIMIT_REACHED": 1}
    assert run(db, provider, now=NOW + timedelta(hours=25))["members"] == {"SUBMITTED": 1}


def test_minimum_interval_between_payouts_and_the_retry_limit(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider)
    run(db, provider)                                                             # reconciled: paid
    commission(db, user, "6.00")
    assert run(db, provider, now=NOW + timedelta(hours=23))["members"] == {"PAYOUT_INTERVAL": 1}
    assert run(db, provider, now=NOW + timedelta(hours=25))["members"] == {"SUBMITTED": 1}

    failing = member(db, "m2", method="CRYPTO")
    commission(db, failing, "5.00")
    refuse = FakeProvider(create=lambda **_k: (_ for _ in ()).throw(nowpayments.NowPaymentsError("no", status_code=400)))
    configure(db, retry_max_attempts=2, retry_backoff_hours=1)
    for hours in (30, 32):
        assert run(db, refuse, now=NOW + timedelta(hours=hours))["members"]["PROVIDER_REFUSED"] == 1
    assert run(db, refuse, now=NOW + timedelta(hours=34))["members"]["RETRY_LIMIT_REACHED"] == 1
    assert len(refuse.created) == 2 and get_commission_balance(db, failing.id).available == Decimal("5.00")


def test_member_pays_deducts_the_network_fee_from_what_is_sent_and_the_ledger_balances(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "10.00")
    configure(db, network_fee_policy="MEMBER_PAYS")
    provider = FakeProvider(fee="0.25", statuses={"batch-1": "FINISHED"})
    run(db, provider)
    row = cashouts(db, user)[0]
    assert provider.created[0]["amount"] == Decimal("9.75")
    assert (row.gross_amount, row.fee, row.net_amount, row.network_fee, row.network_fee_policy) == (
        Decimal("10.00"), Decimal("0.00"), Decimal("9.75"), Decimal("0.25"), "MEMBER_PAYS")
    run(db, provider)
    assert cashouts(db, user)[0].status == "completed"
    assert _balance(db, "2001") == Decimal("10.00") and _balance(db, "1001") == Decimal("-10.00")
    assert _balance(db, "4005") == 0                                              # a network fee is not MyHigh5 income
    _assert_all_journals_balance(db)
    assert cs.summary(db, user)["fees"]["CRYPTO"]["network_fee_policy"] == "MEMBER_PAYS"


def test_company_pays_sends_the_full_amount(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "10.00")
    provider = FakeProvider(fee="0.25")
    run(db, provider)
    row = cashouts(db, user)[0]
    assert provider.created[0]["amount"] == Decimal("10.00")
    assert (row.net_amount, row.network_fee, row.network_fee_policy) == (Decimal("10.00"), Decimal("0.25"),
                                                                         "COMPANY_PAYS")


def test_pausing_automatic_payouts_still_reconciles_what_was_already_sent(ledger, engine_on):
    db = ledger
    first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
    commission(db, first, "5.00")
    provider = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider)
    configure(db, crypto_auto_payout_enabled=False)                               # an administrator pauses payouts
    commission(db, second, "7.00")
    report = run(db, provider)
    assert report == {"enabled": False, "reconciled": {"COMPLETED": 1}, "members": {}}
    assert cashouts(db, first)[0].status == "completed" and len(provider.created) == 1
    assert cashouts(db, second) == [] and cs.summary(db, second)["status"] == "AUTOMATIC_PAYOUT_NOT_ACTIVE"


def test_disabling_crypto_cashout_hides_the_method_and_stops_payouts(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    configure(db, crypto_cashout_enabled=False)
    assert run(db, FakeProvider())["enabled"] is False and cashouts(db) == []
    assert cs.summary(db, user)["status"] == "METHOD_UNAVAILABLE"
    fresh = member(db, "m2")
    refused = client.put("/api/v1/wallet/cashout/method", headers=auth(fresh), json={"method": "CRYPTO"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "METHOD_UNAVAILABLE"
    assert get_commission_balance(db, user.id).available == Decimal("5.00")      # kept in full


# ===========================================================================
# 11. USD cashout settings
# ===========================================================================

@pytest.mark.parametrize("amount, allowed, fee", [("49.99", False, None), ("50.00", True, "5.00"),
                                                  ("400.00", True, "8.00"), ("9000.00", True, "100.00")])
def test_usd_minimum_and_fee_follow_the_configuration(ledger, amount, allowed, fee):
    db = ledger
    configure(db, usd_min_usd=Decimal("50.00"), usd_fee_percent=Decimal("2.000"), usd_fee_min=Decimal("5.00"),
              usd_fee_max=Decimal("100.00"))
    user = member(db, "m1", method="USD", wallet=None)
    commission(db, user, amount)
    if not allowed:
        with pytest.raises(cs.CashoutError) as below:
            cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
        assert below.value.code == "BELOW_MINIMUM" and cashouts(db) == []
        return
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    assert (row.fee, row.net_amount) == (Decimal(fee), Decimal(amount) - Decimal(fee))
    preview = cs.summary(db, user, now=NOW)
    assert preview["minimums"]["USD"] == 50.0 and preview["fees"]["USD"]["rule"] == (
        "2% of the amount, minimum $5, maximum $100")


def test_usd_requests_can_be_switched_off_and_member_cancellation_can_be_restricted(client, ledger):
    db = ledger
    user, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    commission(db, user, "150.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    configure(db, usd_member_cancellation_allowed=False, usd_cashout_enabled=False)
    denied = client.post(f"/api/v1/wallet/cashout/{row.id}/cancel", headers=auth(user), json={"reason": "x"})
    assert denied.status_code == 409 and denied.json()["detail"]["code"] == "CANCELLATION_NOT_ALLOWED"
    assert get_commission_balance(db, user.id).reserved == Decimal("150.00")
    assert client.post(f"/api/v1/admin/cashouts/{row.id}/cancel", headers=auth(admin),
                       json={"reason": "duplicate"}).status_code == 200
    again = client.post("/api/v1/wallet/cashout/usd", headers=auth(user), json={})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "METHOD_UNAVAILABLE"
    assert get_commission_balance(db, user.id).available == Decimal("150.00")


def test_usd_destination_details_are_required_encrypted_and_revealed_only_with_an_audit(client, ledger):
    db = ledger
    user, admin, plain = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True), plain_admin(db)
    commission(db, user, "150.00")
    configure(db, usd_destination_required=True, usd_destination_note="Bank transfer details")
    missing = client.post("/api/v1/wallet/cashout/usd", headers=auth(user), json={})
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "DESTINATION_REQUIRED"
    assert cashouts(db) == []

    details = "SYNTHETIC BANK, IBAN XX00 0000 0000 0000"
    made = client.post("/api/v1/wallet/cashout/usd", headers=auth(user), json={"destination": details})
    assert made.status_code == 200 and details not in made.text
    row = cashouts(db, user)[0]
    assert row.destination_ciphertext.startswith("v1:") and details not in row.destination_ciphertext
    listing = client.get("/api/v1/admin/cashouts", headers=auth(plain))
    assert details not in listing.text and listing.json()["items"][0]["has_destination_details"] is True
    assert details not in client.get(f"/api/v1/admin/cashouts/{row.id}", headers=auth(plain)).text

    assert client.get(f"/api/v1/admin/cashouts/{row.id}/destination", headers=auth(plain)).status_code == 403
    shown = client.get(f"/api/v1/admin/cashouts/{row.id}/destination", headers=auth(admin))
    assert shown.json() == {"destination": details}
    viewed = db.query(AuditTrail).filter_by(action="CASHOUT_DESTINATION_VIEWED").one()
    assert (viewed.user_id, viewed.record_id, viewed.new_values) == (admin.id, row.id, None)
    assert details not in everything_audited(db)
    assert cs.summary(db, user)["methods"]["USD"] == {"available": True, "destination_required": True,
                                                      "destination_note": "Bank transfer details",
                                                      "cancellation_allowed": True}


def test_usd_settlement_needs_the_permission_a_real_reference_and_never_reuses_one(ledger, monkeypatch):
    db = ledger
    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)
    configure(db, usd_settlement_enabled=True, usd_settlement_account="1010", usd_reference_min_length=8)
    admin, plain = member(db, "boss", admin=True), plain_admin(db)
    first, second = member(db, "m1", method="USD", wallet=None), member(db, "m2", method="USD", wallet=None)
    for user in (first, second):
        commission(db, user, "200.00")
    one = cs.request_usd_cashout(db, first, idempotency_key="a", now=NOW)
    two = cs.request_usd_cashout(db, second, idempotency_key="b", now=NOW)

    def refused(row, actor, reference) -> str:
        with pytest.raises(cs.CashoutError) as error:
            cs.settle_usd_cashout(db, row, admin=actor, reference=reference, now=NOW)
        return error.value.code

    assert refused(one, plain, "WIRE-2026-0001") == "FORBIDDEN"                   # is_admin is not enough
    assert refused(one, admin, "short") == "REFERENCE_REQUIRED"
    cs.settle_usd_cashout(db, one, admin=admin, reference="WIRE-2026-0001", now=NOW)
    assert refused(two, admin, "WIRE-2026-0001") == "REFERENCE_ALREADY_USED"
    assert cashouts(db, second)[0].status == "requested" and db.query(JournalEntry).count() == 1
    assert _balance(db, "1010") == Decimal("-180.00") and _balance(db, "4005") == Decimal("-20.00")
    _assert_all_journals_balance(db)


# ===========================================================================
# 12. Admin monitoring
# ===========================================================================

def test_admin_reads_transactions_attempts_wallet_history_audit_and_discrepancies(client, ledger, engine_on):
    db = ledger
    admin, plain = member(db, "boss", admin=True), plain_admin(db)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    run(db, FakeProvider(create=lambda **_k: (_ for _ in ()).throw(TimeoutError())))       # unknown outcome
    row = cashouts(db, user)[0]

    listing = client.get("/api/v1/admin/cashouts?method=CRYPTO&status=unknown", headers=auth(plain)).json()
    assert listing["total"] == 1 and listing["items"][0]["username"] == "m1"
    assert client.get("/api/v1/admin/cashouts?method=USD", headers=auth(plain)).json()["total"] == 0
    detail = client.get(f"/api/v1/admin/cashouts/{row.id}", headers=auth(plain)).json()
    assert detail["cashout"]["failure_code"] == "PROVIDER_OUTCOME_UNKNOWN" and len(detail["attempts"]) == 1
    assert [c["amount"] for c in detail["commissions"]] == [5.0] and detail["member"]["wallet"] == "0xaaaa...aaaa"

    report = client.get("/api/v1/admin/finance/reconciliation", headers=auth(plain)).json()
    assert [d["type"] for d in report["discrepancies"]] == ["UNKNOWN_OUTCOME"]
    assert report["provider_balance_state"] == "NOT_VERIFIED"                     # internal numbers prove nothing
    assert client.get("/api/v1/admin/finance/reconciliation?read_provider=true",
                      headers=auth(plain)).status_code == 403
    events = client.get(f"/api/v1/admin/finance/financial-audit?cashout_id={row.id}", headers=auth(plain)).json()
    assert [e["action"] for e in events["items"]] == ["CASHOUT_RESERVED"]

    # Only the explicit permission may act, and there is no way to send a payout by hand.
    for path, body in ((f"/api/v1/admin/cashouts/{row.id}/resolve", {"outcome": "NOT_SENT"}),
                       (f"/api/v1/admin/cashouts/{row.id}/cancel", {"reason": "x"}),
                       ("/api/v1/admin/cashouts/run", {}), ("/api/v1/admin/affiliate/retry-payouts", {})):
        assert client.post(path, headers=auth(plain), json=body).status_code == 403
    assert client.post(f"/api/v1/admin/cashouts/{row.id}/pay", headers=auth(admin), json={}).status_code in (404, 405)
    done = client.post(f"/api/v1/admin/cashouts/{row.id}/resolve", headers=auth(admin), json={"outcome": "NOT_SENT"})
    assert done.status_code == 200 and done.json()["status"] == "failed"
    assert client.get("/api/v1/admin/finance/reconciliation", headers=auth(plain)).json()["discrepancies"] == []

    cs.change_payout_wallet(db, user, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD)
    history = client.get(f"/api/v1/admin/finance/wallet-history?user_id={user.id}", headers=auth(plain))
    assert history.json()["pending"][0]["wallet"] == "0xbbbb...bbbb" and OTHER_WALLET not in history.text


def test_reconciliation_flags_reservations_that_do_not_add_up(ledger):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None)
    first = commission(db, user, "150.00")
    cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    assert engine.discrepancies(db) == []
    first.payout_reference = "intent:orphan"                                      # simulated corruption
    db.commit()
    kinds = sorted(d["type"] for d in engine.discrepancies(db))
    assert kinds == ["ORPHAN_RESERVATION", "RESERVATION_MISMATCH"]


# ===========================================================================
# 13. Guards
# ===========================================================================

def test_the_earlier_direct_payout_writers_have_no_caller_in_the_application():
    """They mark a payout completed when the provider merely accepts it and do
    not check wallet verification, so they must stay unreachable."""
    names = ("trigger_commission_payout_sync", "process_manual_withdrawal_sync", "retry_failed_payouts_sync",
             "pay_pending_commissions_for_user_sync", "process_commission_payouts_sync", "send_single_payout")
    app_dir = Path(__file__).resolve().parents[2] / "app"
    callers = []
    for path in app_dir.rglob("*.py"):
        if path.name in ("commission_payout_service.py", "nowpayments_service.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        callers += [f"{path.name}:{name}" for name in names if name in text]
    assert callers == []


def test_no_payment_setting_is_duplicated_as_a_hardcoded_threshold():
    app_dir = Path(__file__).resolve().parents[2] / "app"
    for name in ("services/cashout_service.py", "services/cashout_engine.py", "api/api_v1/endpoints/wallet.py",
                 "api/api_v1/endpoints/cashouts.py"):
        text = (app_dir / name).read_text(encoding="utf-8")
        assert "settings.CRYPTO_CASHOUT_MIN_USD" not in text and "settings.USD_CASHOUT_MIN_USD" not in text
        assert "settings.PAYOUT_WALLET" not in text and "cashout_fee_and_net" not in text
        assert "MIN_WITHDRAWAL" not in text
