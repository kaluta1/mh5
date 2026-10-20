"""SoncoPay customer payment collection settings (Admin > Finance & Payments).

  1. only a Super Admin, with the current password, changes them; an
     administrator with manage_payment_settings may only look; nobody else;
  2. keys and secrets are stored encrypted, per environment, never returned,
     audited or logged; a blank field keeps the saved value;
  3. Test and Live are isolated: separate values, separate encryption
     purposes, Live needs its own credentials and a typed confirmation;
  4. the settings can never change NOWPayments checkout, the NOWPayments
     credentials or the payout engine;
  5. nothing goes live by accident: SoncoPay becomes the default checkout only
     while it is on and its environment's key and secret are saved, the server
     environment is ignored, and the webhook refuses anything unsigned.
     (Checkout and webhook processing: tests/unit/test_soncopay_payments.py.)

Every account, key and secret is SYNTHETIC.
"""
from __future__ import annotations

import json
import logging

import pytest

from app.models.accounting import AuditTrail
from app.models.checkout_gateway import CheckoutGatewaySettings
from app.models.payment_config import PaymentCredential, PaymentSettings
from app.services import payment_config as pc
from app.services import payment_crypto
from app.services import soncopay_settings as sp
from tests.unit.test_admin_security_hardening import PASSWORD, bearer, code_of, person  # noqa: F401
from tests.unit.test_super_admin import superadmin

pytestmark = pytest.mark.unit

URL, WEBHOOK = "/api/v1/admin/finance/soncopay", "/api/v1/webhooks/soncopay"
TEST_KEY, TEST_SECRET = "sp_test_synthetic_key_0000001", "whsec_test_synthetic_secret_01"
LIVE_KEY, LIVE_SECRET = "sp_live_synthetic_key_0000002", "whsec_live_synthetic_secret_02"
ALL_SECRETS = (TEST_KEY, TEST_SECRET, LIVE_KEY, LIVE_SECRET)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")


def put(client, actor, password=PASSWORD, **fields):
    return client.put(URL, headers=bearer(actor), json={"current_password": password, **fields})


def save_test_credentials(client, boss):
    done = put(client, boss, test_api_key=TEST_KEY, test_webhook_secret=TEST_SECRET)
    assert done.status_code == 200, done.text
    return done.json()


def snapshot(db) -> tuple:
    """Everything a refused save must leave exactly as it was."""
    db.expire_all()
    row = db.query(CheckoutGatewaySettings).first()
    return (None if row is None else (row.soncopay_enabled, row.soncopay_environment, row.default_provider, row.version),
            sorted((c.provider, c.name, c.ciphertext) for c in db.query(PaymentCredential).all()),
            # A wrong password is recorded by the re-authentication check (REAUTH_FAILED); that is not a change.
            db.query(AuditTrail).filter(AuditTrail.action != "REAUTH_FAILED").count())


def credential(view: dict, name: str) -> dict:
    return next(c for c in view["credentials"] if c["name"] == name)


# ===========================================================================
# 1. Who may
# ===========================================================================

def test_only_a_super_admin_with_the_password_changes_the_settings(client, db):
    boss = superadmin(db, "boss")
    finance = person(db, "finance", admin=True, permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_ACTIVATE, "all"))
    plain = person(db, "plain", admin=True)
    member = person(db, "member")
    before = snapshot(db)

    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=bearer(member)).status_code == 403
    assert code_of(client.get(URL, headers=bearer(plain))) == "FORBIDDEN"
    seen = client.get(URL, headers=bearer(finance))
    assert seen.status_code == 200 and seen.json()["can_change"] is False         # may look, not change
    assert client.get(URL, headers=bearer(boss)).json()["can_change"] is True

    for actor in (finance, plain):
        refused = put(client, actor, test_api_key=TEST_KEY)
        assert (refused.status_code, code_of(refused)) == (403, "SUPER_ADMIN_REQUIRED"), actor.username
    assert put(client, member, test_api_key=TEST_KEY).status_code == 403
    for password in ("", "not-the-password"):
        refused = put(client, boss, password=password, test_api_key=TEST_KEY)
        assert (refused.status_code, code_of(refused)) == (403, "REAUTH_REQUIRED")
    assert client.put(URL, json={"test_api_key": TEST_KEY}).status_code == 401
    assert snapshot(db) == before
    assert db.query(AuditTrail).filter(AuditTrail.action == "REAUTH_FAILED", AuditTrail.record_id == boss.id).count() >= 1


def test_the_form_rejects_unknown_and_malformed_input(client, db):
    boss = superadmin(db, "boss")
    before = snapshot(db)
    for body, status in (({"nowpayments_api_key": TEST_KEY}, 422),          # not a field of this form
                         ({"environment": "staging"}, 422),
                         ({"default_provider": "paypal"}, 422),
                         ({"test_api_key": "too-short"}, 422),
                         ({"test_api_key": "sp test key with spaces 01"}, 422),
                         ({"test_webhook_secret": "https://myhigh5.com/api/v1/webhooks/soncopay"}, 422),
                         ({}, 422)):
        assert put(client, boss, **body).status_code == status, body
    assert snapshot(db) == before


# ===========================================================================
# 2. Credentials: encrypted, masked, never returned, audited or logged
# ===========================================================================

def test_credentials_are_encrypted_masked_and_never_returned(client, db, caplog):
    boss = superadmin(db, "boss")
    caplog.set_level(logging.DEBUG)
    view = save_test_credentials(client, boss)

    rows = {r.name: r for r in db.query(PaymentCredential).filter(PaymentCredential.provider == "soncopay")}
    assert set(rows) == {"TEST_API_KEY", "TEST_WEBHOOK_SECRET"}
    for name, value in (("TEST_API_KEY", TEST_KEY), ("TEST_WEBHOOK_SECRET", TEST_SECRET)):
        assert value not in rows[name].ciphertext and rows[name].ciphertext.startswith("v1:")
        assert payment_crypto.decrypt(rows[name].ciphertext, "mh5-payments:soncopay-credential:" + name) == value
    key = credential(view, "TEST_API_KEY")
    assert key["configured"] is True and key["masked"] == "••••" + TEST_KEY[-4:]
    assert credential(view, "TEST_WEBHOOK_SECRET")["masked"] is None              # a secret shows nothing at all
    assert credential(view, "LIVE_API_KEY")["configured"] is False and view["ready"] == {"test": True, "live": False}

    # Nowhere: not in a response, not in the audit trail, not in a log line.
    shown = json.dumps(client.get(URL, headers=bearer(boss)).json()) + json.dumps(view)
    audits = json.dumps([[a.old_values, a.new_values] for a in db.query(AuditTrail).all()])
    for secret in (TEST_KEY, TEST_SECRET):
        assert secret not in shown and secret not in audits and secret not in caplog.text
        assert secret[:-4] not in shown                                             # only the last four, if anything
    entry = db.query(AuditTrail).filter(AuditTrail.action == sp.AUDIT_SETTINGS).one()
    assert entry.user_id == boss.id and entry.new_values["changed"] == ["TEST_API_KEY", "TEST_WEBHOOK_SECRET"]


def test_a_blank_field_keeps_the_saved_value_and_a_new_one_replaces_it(client, db):
    boss = superadmin(db, "boss")
    save_test_credentials(client, boss)
    before = db.query(PaymentCredential).filter(PaymentCredential.name == "TEST_API_KEY").one().ciphertext
    kept = put(client, boss, test_api_key="", test_webhook_secret="   ", enabled=None)
    assert code_of(kept) == "NOTHING_TO_CHANGE"
    db.expire_all()
    assert db.query(PaymentCredential).filter(PaymentCredential.name == "TEST_API_KEY").one().ciphertext == before

    replaced = put(client, boss, test_api_key="sp_test_synthetic_key_REPLACED")
    assert replaced.status_code == 200 and credential(replaced.json(), "TEST_API_KEY")["masked"] == "••••ACED"
    db.expire_all()
    rows = db.query(PaymentCredential).filter(PaymentCredential.provider == "soncopay").all()
    assert len(rows) == 2                                                             # replaced, not added


def test_a_value_that_cannot_be_read_is_reported_and_never_used(client, db):
    boss = superadmin(db, "boss")
    save_test_credentials(client, boss)
    row = db.query(PaymentCredential).filter(PaymentCredential.name == "TEST_API_KEY").one()
    row.ciphertext = "v1:" + "A" * 40                                                 # damaged
    db.commit()
    view = client.get(URL, headers=bearer(boss)).json()
    key = credential(view, "TEST_API_KEY")
    assert (key["saved"], key["saved_readable"], key["configured"], key["masked"]) == (True, False, False, None)
    refused = put(client, boss, enabled=True)
    assert code_of(refused) == "NOT_READY"


def test_without_the_encryption_key_nothing_is_stored(client, db, monkeypatch):
    boss = superadmin(db, "boss")
    monkeypatch.delenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(payment_crypto.settings, "PAYMENT_SETTINGS_ENCRYPTION_KEY", "", raising=False)
    before = snapshot(db)
    refused = put(client, boss, test_api_key=TEST_KEY)
    assert code_of(refused) == "ENCRYPTION_KEY_MISSING"
    assert snapshot(db) == before
    assert client.get(URL, headers=bearer(boss)).json()["encryption_key_configured"] is False


# ===========================================================================
# 3. Test and Live are isolated
# ===========================================================================

def test_test_and_live_credentials_are_separate_and_cannot_be_swapped(client, db):
    boss = superadmin(db, "boss")
    save_test_credentials(client, boss)
    assert put(client, boss, live_api_key=LIVE_KEY, live_webhook_secret=LIVE_SECRET).status_code == 200
    rows = {r.name: r for r in db.query(PaymentCredential).filter(PaymentCredential.provider == "soncopay")}
    assert len(rows) == 4
    # A Test ciphertext cannot be read as Live, nor as a NOWPayments or Kaluta credential.
    for purpose in ("mh5-payments:soncopay-credential:LIVE_API_KEY", payment_crypto.PURPOSE_CREDENTIAL + "PAYIN_API_KEY",
                    "mh5-kyc:kaluta-credential:API_KEY"):
        with pytest.raises(payment_crypto.PaymentCryptoError):
            payment_crypto.decrypt(rows["TEST_API_KEY"].ciphertext, purpose)
    # NOWPayments' own credential readers never see a SoncoPay row.
    assert not any(s["stored"] == "CONFIGURED" for s in pc.credential_status(db))


def test_switching_to_live_needs_live_credentials_and_the_typed_confirmation(client, db):
    boss = superadmin(db, "boss")
    save_test_credentials(client, boss)
    assert put(client, boss, enabled=True).status_code == 200                      # on in Test
    before = snapshot(db)

    for confirmation in (None, "use soncopay live", "yes"):
        refused = put(client, boss, environment="live", confirmation=confirmation)
        assert code_of(refused) == "CONFIRMATION_REQUIRED", confirmation
    refused = put(client, boss, environment="live", confirmation=sp.CONFIRM_LIVE)    # no Live credentials yet
    assert code_of(refused) == "NOT_READY" and "Live API key" in refused.json()["detail"]["message"]
    assert snapshot(db) == before

    done = put(client, boss, environment="live", confirmation=sp.CONFIRM_LIVE,
               live_api_key=LIVE_KEY, live_webhook_secret=LIVE_SECRET)
    assert done.status_code == 200, done.text
    view = done.json()
    assert (view["environment"], view["enabled"]) == ("live", True)
    # Back to Test needs no confirmation.
    assert put(client, boss, environment="test").json()["environment"] == "test"


def test_switching_on_needs_the_credentials_of_the_environment_in_use(client, db):
    boss = superadmin(db, "boss")
    assert put(client, boss, live_api_key=LIVE_KEY, live_webhook_secret=LIVE_SECRET).status_code == 200
    before = snapshot(db)
    refused = put(client, boss, enabled=True)                                       # Test has nothing saved
    assert code_of(refused) == "NOT_READY" and "Test API key" in refused.json()["detail"]["message"]
    assert snapshot(db) == before
    assert put(client, boss, enabled=True, test_api_key=TEST_KEY, test_webhook_secret=TEST_SECRET).status_code == 200
    off = put(client, boss, enabled=False)
    assert off.status_code == 200 and off.json()["enabled"] is False
    changes = [a.new_values["changed"] for a in db.query(AuditTrail).filter(AuditTrail.action == sp.AUDIT_SETTINGS)
               .order_by(AuditTrail.id)]
    assert changes[-2:] == [["SONCOPAY_ENABLED", "TEST_API_KEY", "TEST_WEBHOOK_SECRET"], ["SONCOPAY_ENABLED"]]


def test_a_change_made_on_a_stale_page_is_refused(client, db):
    boss = superadmin(db, "boss")
    version = save_test_credentials(client, boss)["version"]
    assert put(client, boss, enabled=True, expected_version=version).status_code == 200
    before = snapshot(db)
    stale = put(client, boss, enabled=False, expected_version=version)
    assert code_of(stale) == "STALE" and snapshot(db) == before


# ===========================================================================
# 4. NOWPayments checkout and the payout engine are never touched
# ===========================================================================

def _nowpayments_state(db) -> tuple:
    db.expire_all()
    settings_row = db.query(PaymentSettings).first()
    columns = None if settings_row is None else {c.name: getattr(settings_row, c.name)
                                                 for c in PaymentSettings.__table__.columns}
    return (columns, pc.load(db), pc.resolve_credentials(db).values,
            sorted((c.name, c.ciphertext) for c in db.query(PaymentCredential)
                   .filter(PaymentCredential.provider == pc.PROVIDER)))


def test_soncopay_changes_never_touch_nowpayments_checkout_or_payouts(client, db):
    boss = superadmin(db, "boss")
    # NOWPayments as it is in production: a stored pay-in key, payout settings saved.
    pc.set_credentials(db, boss, {"PAYIN_API_KEY": "np_synthetic_payin_key_01"}, password=PASSWORD)
    before = _nowpayments_state(db)
    assert before[3]

    save_test_credentials(client, boss)
    assert put(client, boss, live_api_key=LIVE_KEY, live_webhook_secret=LIVE_SECRET).status_code == 200
    assert put(client, boss, enabled=True).status_code == 200
    assert put(client, boss, environment="live", confirmation=sp.CONFIRM_LIVE).status_code == 200
    assert put(client, boss, enabled=False).status_code == 200
    put(client, boss, default_provider="soncopay")                                  # refused below; changes nothing

    assert _nowpayments_state(db) == before
    assert sp.default_checkout_provider(db) == "nowpayments"
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "checkout_gateway_settings").count() == 5   # five accepted saves, the refused default none


# ===========================================================================
# 5. Nothing goes live by accident
# ===========================================================================

def test_soncopay_becomes_the_default_checkout_only_while_on_and_ready(client, db):
    boss = superadmin(db, "boss")
    view = client.get(URL, headers=bearer(boss)).json()
    assert {p["provider"]: p["available"] for p in view["checkout_providers"]} == {"nowpayments": True, "soncopay": True}

    # Nothing saved, or saved but off: refused, nothing changes.
    before = snapshot(db)
    refused = put(client, boss, default_provider="soncopay")
    assert (refused.status_code, code_of(refused)) == (409, "NOT_READY")
    assert snapshot(db) == before
    save_test_credentials(client, boss)
    before = snapshot(db)
    refused = put(client, boss, default_provider="soncopay")
    assert (refused.status_code, code_of(refused)) == (409, "NOT_READY")
    assert snapshot(db) == before
    assert sp.default_checkout_provider(db) == "nowpayments"

    # On, with the Test key and secret: accepted, and in force.
    assert put(client, boss, enabled=True).status_code == 200
    done = put(client, boss, default_provider="soncopay")
    assert done.status_code == 200, done.text
    assert done.json()["default_provider"] == done.json()["default_provider_in_force"] == "soncopay"
    assert sp.checkout_environment(db) == "test"

    # It cannot be switched off while it is the default; NOWPayments first.
    refused = put(client, boss, enabled=False)
    assert (refused.status_code, code_of(refused)) == (409, "DEFAULT_PROVIDER_OFF")
    assert put(client, boss, default_provider="nowpayments").status_code == 200
    assert sp.default_checkout_provider(db) == "nowpayments"


def test_a_hand_edited_default_never_routes_to_soncopay_while_it_cannot_take_payments(client, db):
    boss = superadmin(db, "boss")
    save_test_credentials(client, boss)
    assert put(client, boss, enabled=True).status_code == 200
    # Default SoncoPay written by hand while it is OFF: NOWPayments stays in force.
    db.query(CheckoutGatewaySettings).update({"default_provider": "soncopay", "soncopay_enabled": False})
    db.commit()
    assert sp.default_checkout_provider(db) == "nowpayments" and sp.checkout_environment(db) is None
    # On but in Live, where nothing is saved: NOWPayments stays in force.
    db.query(CheckoutGatewaySettings).update({"soncopay_enabled": True, "soncopay_environment": "live"})
    db.commit()
    assert sp.default_checkout_provider(db) == "nowpayments" and sp.checkout_environment(db) is None
    assert client.get(URL, headers=bearer(boss)).json()["default_provider_in_force"] == "nowpayments"


def test_an_api_key_of_the_other_environment_is_refused(client, db):
    boss = superadmin(db, "boss")
    before = snapshot(db)
    for field, value in (("test_api_key", LIVE_KEY), ("live_api_key", TEST_KEY),
                         ("test_api_key", "pk_synthetic_not_soncopay_01")):
        refused = put(client, boss, **{field: value})
        assert (refused.status_code, code_of(refused)) == (422, "INVALID_VALUE"), field
        assert LIVE_KEY not in refused.text and TEST_KEY not in refused.text
    assert snapshot(db) == before


def test_with_nothing_saved_soncopay_is_off_and_the_environment_is_ignored(client, db, monkeypatch):
    for name in ("SONCOPAY_API_KEY", "SONCOPAY_WEBHOOK_SECRET", "SONCOPAY_ENABLED", "SONCOPAY_ENVIRONMENT"):
        monkeypatch.setenv(name, "true" if name.endswith("ENABLED") else ("live" if name.endswith("ENVIRONMENT")
                                                                           else "sp_env_synthetic_value_ignored"))
    boss = superadmin(db, "boss")
    view = client.get(URL, headers=bearer(boss)).json()
    assert (view["enabled"], view["environment"], view["default_provider"], view["version"]) == (
        False, "test", "nowpayments", 0)
    assert not any(c["configured"] for c in view["credentials"])
    assert view["connection_test"]["available"] is True and view["connection_test"]["reason"] is None
    assert view["webhook_operational"] is True
    assert sp.checkout_environment(db) is None and sp.default_checkout_provider(db) == "nowpayments"
    assert db.query(CheckoutGatewaySettings).count() == 0                          # reading never creates the row


def test_the_webhook_refuses_unsigned_callbacks_and_processes_nothing(client, db):
    boss = superadmin(db, "boss")
    # No signing secret saved: nothing can be verified, SoncoPay is asked to retry later.
    waiting = client.post(WEBHOOK, content=b'{"event":"payment.paid","data":{}}',
                          headers={"Content-Type": "application/json"})
    assert waiting.status_code == 503
    save_test_credentials(client, boss)
    assert put(client, boss, enabled=True).status_code == 200
    before = snapshot(db)
    for body, headers in ((b'{"event":"payment.paid","data":{"amount":100}}', {"Content-Type": "application/json"}),
                          (b"anything", {"X-SoncoPay-Signature": "abc", "Content-Type": "text/plain"}),
                          (b"", {})):
        refused = client.post(WEBHOOK, content=body, headers=headers)
        assert refused.status_code == 400 and refused.json()["detail"] == "invalid signature"
    assert client.get(WEBHOOK).status_code == 405
    assert snapshot(db) == before


def test_the_webhook_url_shown_is_the_public_backend_url(client, db, monkeypatch):
    boss = superadmin(db, "boss")
    monkeypatch.setattr(sp.settings, "BACKEND_PUBLIC_URL", "https://api.example.test/")
    assert client.get(URL, headers=bearer(boss)).json()["webhook_url"] == "https://api.example.test/api/v1/webhooks/soncopay"
    monkeypatch.setattr(sp.settings, "BACKEND_PUBLIC_URL", "")
    assert client.get(URL, headers=bearer(boss)).json()["webhook_url"] is None
