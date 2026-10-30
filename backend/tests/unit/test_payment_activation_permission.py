"""Finance & Payments: configuring and ACTIVATING are two authorities.

manage_payment_settings configures. An activation (automatic payouts, USD
settlement, the approval of the network fee limits, the provider fee
behaviour, lifting a payout suspension, payout settings while automatic
payouts are on) needs activate_financial_operations IN ADDITION, and that
permission alone opens nothing. Switching anything off needs only
manage_payment_settings.

Four administrators are used throughout:
  none      is_admin only
  manage    manage_payment_settings
  activate  activate_financial_operations only
  both      manage_payment_settings + activate_financial_operations

Nothing here can reach the provider (see test_payment_config). Every
credential, account and amount is SYNTHETIC.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AuditTrail
from app.models.payment_config import PaymentConfigAudit, PaymentCredential, PaymentSettings
from app.models.user import Permission, Role, User
from app.scripts import grant_payment_permissions as grants
from app.services import cashout_service as cs
from app.services import payment_config as pc
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    FEE_RULES,
    NOW,
    PASSWORD,
    configure,
    ledger,
    member,
    no_network,
)
from tests.unit.test_new_business_model import world  # noqa: F401
from tests.unit.test_payment_config import (  # noqa: F401
    SECRETS,
    env_payout_credentials,
    fake_http,
    payment_env,
    payout_logins,
    plain_admin,
)

pytestmark = pytest.mark.unit

MANAGE, PROCESS, ACTIVATE = pc.PERMISSION_MANAGE, pc.PERMISSION_PROCESS, pc.PERMISSION_ACTIVATE
NOTE = "Compared the payout with the provider statement and resolved the difference."
REFUSED = "ACTIVATION_PERMISSION_REQUIRED"
SETTINGS_URL = "/api/v1/admin/finance/settings"


@pytest.fixture
def admins(ledger):
    db = ledger
    return {"none": plain_admin(db),
            "manage": member(db, "cfg", admin=True, permissions=(MANAGE,)),
            "activate": member(db, "act", admin=True, permissions=(ACTIVATE,)),
            "both": member(db, "both", admin=True, permissions=(MANAGE, ACTIVATE))}


def stored(db) -> tuple:
    """Everything a refused attempt must leave exactly as it was."""
    db.expire_all()
    row = db.query(PaymentSettings).first()
    values = None if row is None else {name: getattr(row, name) for name in pc.FIELDS} | {
        "version": row.version, "suspended": row.payout_suspended_reason}
    return values, db.query(PaymentConfigAudit).count(), db.query(PaymentCredential).count()


def code(call) -> str:
    with pytest.raises(pc.PaymentConfigError) as error:
        call()
    return error.value.code


def update(db, actor, changes, confirmation=None, **kwargs):
    return pc.update_settings(db, actor, changes, password=PASSWORD, confirmation=confirmation, now=NOW,
                              expected_version=pc.load(db).version, **kwargs)


# ===========================================================================
# 1. What each administrator is told, and ordinary configuration
# ===========================================================================

def test_the_panel_is_told_who_may_activate_and_the_activation_permission_alone_is_nothing(client, ledger, admins):
    seen = {name: client.get("/api/v1/admin/finance/overview", headers=auth(user)).json()["permissions"]
            for name, user in admins.items()}
    assert seen == {
        "none": {"can_manage": False, "can_process": False, "can_activate": False},
        "manage": {"can_manage": True, "can_process": False, "can_activate": False},
        "activate": {"can_manage": False, "can_process": False, "can_activate": False},
        "both": {"can_manage": True, "can_process": False, "can_activate": True},
    }
    view = client.get(SETTINGS_URL, headers=auth(admins["none"])).json()["activation"]
    assert view["permission"] == ACTIVATE and view["automatic_payouts_on"] is False
    assert view["values"] == {"crypto_auto_payout_enabled": True, "checkout_enabled": True, "usd_settlement_enabled": True,
                              "fee_terms_approved": True, "provider_fee_mode": "DEDUCTED_BY_PROVIDER"}
    assert view["while_automatic_payouts_on"] == {"fields": list(pc.LIVE_PAYOUT_FIELDS),
                                                  "switches": list(pc.LIVE_PAYOUT_SWITCHES),
                                                  "credential_group": "payout"}


def test_ordinary_configuration_needs_manage_and_only_manage(ledger, admins, monkeypatch):
    db = ledger
    for name in ("none", "activate"):
        before = stored(db)
        assert code(lambda: update(db, admins[name], {"usd_min_usd": "150"})) == "FORBIDDEN"
        assert code(lambda: pc.set_credentials(db, admins[name], SECRETS, password=PASSWORD)) == "FORBIDDEN"
        assert code(lambda: pc.delete_credential(db, admins[name], "IPN_SECRET", password=PASSWORD)) == "FORBIDDEN"
        assert code(lambda: pc.run_connection_test(db, admins[name], http=fake_http()[0], now=NOW)) == "FORBIDDEN"
        assert stored(db) == before

    manager = admins["manage"]
    # Every group of settings, the credentials and the connection test: no activation permission involved.
    for changes in ({"provider_display_name": "NOWPayments (main)"}, {"crypto_min_usd": "2.50"},
                    {"max_single_payout_usd": "500", "max_daily_payout_usd": "2000"}, {"usd_min_usd": "150"},
                    {"wallet_hold_hours": 96}, {"member_fee_cap_usd": "1.00", "fee_estimate_margin_percent": "20"},
                    {"crypto_cashout_enabled": False}, {"crypto_cashout_enabled": True},
                    {"provider_enabled": False}, {"provider_enabled": True}, {"usd_cashout_enabled": False}):
        version = pc.load(db).version
        assert update(db, manager, changes).version == version + 1, changes
    assert pc.set_credentials(db, manager, SECRETS, password=PASSWORD) == sorted(SECRETS)
    assert update(db, manager, {"payout_credential_source": "DATABASE"}).payout_credential_source == "DATABASE"
    assert pc.delete_credential(db, manager, "IPN_SECRET", password=PASSWORD) is True
    env_payout_credentials(monkeypatch)
    assert pc.run_connection_test(db, manager, http=fake_http()[0], now=NOW)["status"] in ("OK", "PARTIAL", "FAILED")
    assert {r.actor_id for r in db.query(PaymentConfigAudit).all()} == {manager.id}


# ===========================================================================
# 2. The four activations in the settings
# ===========================================================================

def prepare(db, key, admin, monkeypatch):
    """Everything an activation needs EXCEPT the permission, so that a refusal
    in these tests can only be about who is asking."""
    if key == "crypto_auto_payout_enabled":
        configure(db, **FEE_RULES)
        env_payout_credentials(monkeypatch)
        pc.run_connection_test(db, admin, http=fake_http()[0], now=NOW)
        return {"crypto_auto_payout_enabled": True}, pc.CONFIRM_AUTO_PAYOUT
    if key == "usd_settlement_enabled":
        return {"usd_settlement_enabled": True, "usd_settlement_account": "1010"}, pc.CONFIRM_USD_SETTLEMENT
    if key == "fee_terms_approved":
        configure(db, **{**FEE_RULES, "fee_terms_approved": False})
        return {"fee_terms_approved": True}, None
    configure(db, usd_min_usd=Decimal("100.00"))                    # the row exists; the fee mode is UNVERIFIED
    return {"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}, None


ACTIVATIONS = ("crypto_auto_payout_enabled", "usd_settlement_enabled", "fee_terms_approved", "provider_fee_mode")


@pytest.mark.parametrize("key", ACTIVATIONS)
def test_an_activation_needs_both_permissions(client, ledger, admins, monkeypatch, key):
    db = ledger
    changes, phrase = prepare(db, key, admins["both"], monkeypatch)
    before = stored(db)

    # A: no payment permission.  C: the activation permission alone.  Neither configures anything.
    for name in ("none", "activate"):
        assert code(lambda: update(db, admins[name], changes, phrase)) == "FORBIDDEN", name
    # B: may configure, may not activate. Refused with everything else in order ...
    assert code(lambda: update(db, admins["manage"], changes, phrase)) == REFUSED
    # ... and told so before any gate is looked at (no phrase, no version).
    assert code(lambda: pc.update_settings(db, admins["manage"], changes, password=PASSWORD, now=NOW)) == REFUSED
    # The password is still asked first, of everybody.
    assert code(lambda: pc.update_settings(db, admins["manage"], changes, password="wrong", now=NOW)) == "REAUTH_REQUIRED"
    answer = client.put(SETTINGS_URL, headers=auth(admins["manage"]), json={
        "changes": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in changes.items()},
        "current_password": PASSWORD, "confirmation": phrase, "expected_version": pc.load(db).version})
    assert answer.status_code == 403 and answer.json()["detail"]["code"] == REFUSED
    assert answer.json()["detail"]["field"] == key and ACTIVATE in answer.json()["detail"]["message"]
    # Nothing was stored, versioned or written to the history by any refused attempt.
    assert stored(db) == before

    # D: both permissions. The existing gates still apply to them ...
    if phrase is not None:     # the fee behaviour and the fee approval have no typed phrase (2026-10-30)
        assert code(lambda: update(db, admins["both"], changes)) == "CONFIRMATION_REQUIRED"
    assert code(lambda: pc.update_settings(db, admins["both"], changes, password=PASSWORD, confirmation=phrase,
                                           now=NOW)) == "VERSION_REQUIRED"
    assert stored(db) == before
    # ... and then it is activated, versioned and on record under their name.
    version = pc.load(db).version
    config = update(db, admins["both"], changes, phrase)
    assert getattr(config, key) == changes[key] and config.version == version + 1
    entry = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert (entry.action, entry.actor_id, entry.version) == ("SETTINGS_UPDATED", admins["both"].id, version + 1)
    assert key in entry.changed_fields


def test_the_gates_of_an_activation_are_not_replaced_by_the_permission(ledger, admins, monkeypatch):
    db = ledger
    both = admins["both"]
    change = {"crypto_auto_payout_enabled": True}
    # Fee rules not in force, no credentials, no connection test: still refused, permission or not.
    assert code(lambda: update(db, both, change, pc.CONFIRM_AUTO_PAYOUT)) == "UNSAFE_ACTIVATION"
    configure(db, **FEE_RULES)
    assert code(lambda: update(db, both, change, pc.CONFIRM_AUTO_PAYOUT)) == "UNSAFE_ACTIVATION"
    env_payout_credentials(monkeypatch)
    assert code(lambda: update(db, both, change, pc.CONFIRM_AUTO_PAYOUT)) == "UNSAFE_ACTIVATION"
    pc.run_connection_test(db, both, http=fake_http()[0], now=NOW - timedelta(hours=25))
    assert code(lambda: update(db, both, change, pc.CONFIRM_AUTO_PAYOUT)) == "UNSAFE_ACTIVATION"
    assert code(lambda: update(db, both, {"usd_settlement_enabled": True}, pc.CONFIRM_USD_SETTLEMENT)) == "UNSAFE_ACTIVATION"
    assert pc.load(db).crypto_auto_payout_enabled is False and pc.load(db).usd_settlement_enabled is False
    # And the server master switches still decide whether anything can move.
    pc.run_connection_test(db, both, http=fake_http()[0], now=NOW)
    config = update(db, both, change, pc.CONFIRM_AUTO_PAYOUT)
    assert config.crypto_auto_payout_enabled is True and config.auto_payout_allowed is False


def test_switching_off_needs_only_manage(ledger, admins):
    db = ledger
    configure(db, crypto_auto_payout_enabled=True, usd_settlement_enabled=True, usd_settlement_account="1010",
              **FEE_RULES)
    manager = admins["manage"]
    for name in ("none", "activate"):                               # but it does need manage
        assert code(lambda: update(db, admins[name], {"crypto_auto_payout_enabled": False})) == "FORBIDDEN"
    assert update(db, manager, {"crypto_auto_payout_enabled": False}).crypto_auto_payout_enabled is False
    assert update(db, manager, {"usd_settlement_enabled": False}).usd_settlement_enabled is False
    assert update(db, manager, {"fee_terms_approved": False}).fee_terms_approved is False
    assert update(db, manager, {"provider_fee_mode": "UNVERIFIED"}).provider_fee_mode == "UNVERIFIED"
    assert update(db, manager, {"crypto_cashout_enabled": False, "provider_enabled": False,
                                "usd_cashout_enabled": False}).provider_enabled is False
    # Off is one way for them: switching any of it back on is an activation again.
    for changes, phrase in (({"crypto_auto_payout_enabled": True}, pc.CONFIRM_AUTO_PAYOUT),
                            ({"usd_settlement_enabled": True}, pc.CONFIRM_USD_SETTLEMENT),
                            ({"fee_terms_approved": True}, None),
                            ({"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}, None)):
        assert code(lambda: update(db, manager, changes, phrase)) == REFUSED, changes


# ===========================================================================
# 3. Lifting a payout suspension
# ===========================================================================

def suspend(db):
    configure(db, **FEE_RULES)
    pc.suspend_payouts(db, reason="PROVIDER_AMOUNT_MISMATCH", now=NOW)
    db.commit()
    configure(db, **FEE_RULES)                                      # the fee rules are in force again
    assert pc.load(db).suspended_reason == "PROVIDER_AMOUNT_MISMATCH"


@pytest.mark.parametrize("reactivate", [pc.reactivate_payouts, cs.reactivate_payouts], ids=["config", "cashout"])
def test_lifting_a_suspension_needs_both_permissions(ledger, admins, reactivate):
    db = ledger
    suspend(db)
    before = stored(db)

    def attempt(actor, **overrides):
        return reactivate(db, actor, **{"password": PASSWORD, "confirmation": pc.CONFIRM_REACTIVATION, "note": NOTE,
                                        **overrides})

    assert code(lambda: attempt(admins["none"])) == "FORBIDDEN"
    assert code(lambda: attempt(admins["activate"])) == "FORBIDDEN"
    assert code(lambda: attempt(admins["manage"])) == REFUSED
    assert code(lambda: attempt(admins["manage"], password="wrong")) == REFUSED       # who is asking comes first
    assert stored(db) == before and pc.load(db).suspended_reason == "PROVIDER_AMOUNT_MISMATCH"
    # Both permissions, and every existing requirement still applies.
    assert code(lambda: attempt(admins["both"], password="wrong")) == "REAUTH_REQUIRED"
    assert code(lambda: attempt(admins["both"], confirmation="REACTIVATE")) == "CONFIRMATION_REQUIRED"
    assert code(lambda: attempt(admins["both"], note="ok")) == "REVIEW_NOTE_REQUIRED"
    assert stored(db) == before
    config = attempt(admins["both"])
    assert config.suspended_reason is None and config.crypto_auto_payout_enabled is False
    event = db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_REACTIVATED").one()
    assert event.actor_id == admins["both"].id and event.new_values["review_note"] == NOTE


def test_the_reactivation_endpoint_refuses_an_administrator_who_may_only_configure(client, ledger, admins):
    db = ledger
    suspend(db)
    before = stored(db)
    url = "/api/v1/admin/finance/payouts/reactivate"
    body = {"current_password": PASSWORD, "confirmation": pc.CONFIRM_REACTIVATION, "note": NOTE}
    for name, expected in (("none", "FORBIDDEN"), ("activate", "FORBIDDEN"), ("manage", REFUSED)):
        answer = client.post(url, headers=auth(admins[name]), json=body)
        assert (answer.status_code, answer.json()["detail"]["code"]) == (403, expected), name
    assert stored(db) == before
    done = client.post(url, headers=auth(admins["both"]), json=body)
    assert done.status_code == 200 and done.json()["payout_suspension"] is None


# ===========================================================================
# 4. While automatic payouts are on
# ===========================================================================

LIVE_CHANGES = {
    "crypto_payout_currency": None,                                 # one supported value only: see the test
    "payout_credential_source": "DATABASE",
    "provider_balance_reserve_usd": "25.00",
    "crypto_min_usd": "0.50",
    "max_network_fee_percent": "90",
    "max_daily_payout_usd": "9000000",
    "max_single_payout_usd": "900000",
    "max_daily_payout_count": 90000,
    "min_hours_between_payouts": 1,
    "payout_interval_seconds": 60,
    "retry_backoff_hours": 1,
    "retry_max_attempts": 20,
}


def test_every_setting_the_running_engine_depends_on_is_covered():
    assert set(LIVE_CHANGES) == set(pc.LIVE_PAYOUT_FIELDS)
    assert set(pc.LIVE_PAYOUT_FIELDS) | set(pc.LIVE_PAYOUT_SWITCHES) <= set(pc.FIELDS)
    # The limits and schedule of the payout engine, the asset, the reserve and the credentials in use.
    limits = next(names for key, _title, _note, names in pc.CRYPTO_SECTIONS if key == "limits")
    assert set(limits) <= set(pc.LIVE_PAYOUT_FIELDS)
    on = {"crypto_auto_payout_enabled": True}
    for name in pc.LIVE_PAYOUT_FIELDS:
        assert [n for n, _ in pc.activation_required(on, {name: "x"})] == [name]
        assert pc.activation_required({"crypto_auto_payout_enabled": False}, {name: "x"}) == []
        # Switched off in the same change: nothing is running under the new value.
        assert pc.activation_required(on, {name: "x", "crypto_auto_payout_enabled": False}) == []
    for name in pc.LIVE_PAYOUT_SWITCHES:
        assert [n for n, _ in pc.activation_required(on, {name: True})] == [name]
        assert pc.activation_required(on, {name: False}) == []
    # Fee settings are not activations: changing one withdraws the approval, which stops payouts.
    for name in ("member_fee_cap_usd", "fee_estimate_margin_percent", "max_unreconciled_payouts",
                 "wallet_hold_hours", "usd_min_usd", "fee_terms_version"):
        assert pc.activation_required(on, {name: "x"}) == []


def test_payout_settings_are_an_activation_while_automatic_payouts_are_on(ledger, admins):
    db = ledger
    manager, both = admins["manage"], admins["both"]
    pc.set_credentials(db, both, SECRETS, password=PASSWORD)
    configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
    before = stored(db)
    for name, value in LIVE_CHANGES.items():
        if value is None:
            continue
        assert code(lambda: update(db, manager, {name: value})) == REFUSED, name
    for switch in pc.LIVE_PAYOUT_SWITCHES:
        configure(db, **{switch: False})                            # stopped by somebody ...
        before = stored(db)
        assert code(lambda: update(db, manager, {switch: True})) == REFUSED, switch   # ... not resumed by a manager
        assert stored(db) == before
        configure(db, **{switch: True})
        assert update(db, manager, {switch: False}) is not None     # stopping is always allowed
        if switch == "provider_enabled":
            # Payouts would resume: a recent successful connection test and the phrase are needed too.
            assert code(lambda: update(db, both, {switch: True})) == "UNSAFE_ACTIVATION"
            row = db.query(PaymentSettings).first()
            row.last_connection_test_status, row.last_connection_ok_at = "OK", NOW - timedelta(hours=1)
            db.commit()
            assert code(lambda: update(db, both, {switch: True})) == "CONFIRMATION_REQUIRED"
            assert update(db, both, {switch: True}, pc.CONFIRM_PROVIDER_RESUME) is not None
        else:
            assert update(db, both, {switch: True}) is not None
    before = stored(db)
    # The credentials the engine pays with.
    assert code(lambda: pc.set_credentials(db, manager, {"PAYOUT_API_KEY": "SYNTHETIC-OTHER-PAYOUT-KEY"},
                                           password=PASSWORD)) == REFUSED
    assert code(lambda: pc.set_credentials(db, manager, SECRETS, password=PASSWORD)) == REFUSED
    assert code(lambda: pc.delete_credential(db, manager, "PAYOUT_TOTP_SECRET", password=PASSWORD)) == REFUSED
    assert stored(db) == before

    # What is NOT the running payout configuration stays ordinary configuration.
    assert pc.set_credentials(db, manager, {"PAYIN_API_KEY": "SYNTHETIC-PAYIN-KEY-0009"},
                              password=PASSWORD) == ["PAYIN_API_KEY"]
    assert update(db, manager, {"wallet_hold_hours": 96}).wallet_hold_hours == 96
    assert update(db, manager, {"usd_min_usd": "150"}).usd_min_usd == Decimal("150.00")
    # A fee setting withdraws the approval: payouts stop, so no activation is involved.
    tightened = update(db, manager, {"member_fee_cap_usd": "0.50"})
    assert tightened.fee_terms_approved is False and tightened.fee_gate() == "FEE_LIMITS_NOT_APPROVED"
    assert code(lambda: update(db, manager, {"fee_terms_approved": True}, None)) == REFUSED

    # Both permissions: the same changes are accepted.
    changed = update(db, both, {"max_single_payout_usd": "500", "max_daily_payout_count": 5})
    assert (changed.max_single_payout_usd, changed.max_daily_payout_count) == (Decimal("500.00"), 5)
    assert pc.set_credentials(db, both, {"PAYOUT_API_KEY": "SYNTHETIC-OTHER-PAYOUT-KEY"},
                              password=PASSWORD) == ["PAYOUT_API_KEY"]

    # A manager may stop automatic payouts, alone or together with the change ...
    stopped = update(db, manager, {"crypto_auto_payout_enabled": False, "max_single_payout_usd": "400"})
    assert stopped.crypto_auto_payout_enabled is False and stopped.max_single_payout_usd == Decimal("400.00")
    # ... and with payouts off these are ordinary settings again.
    for name, value in LIVE_CHANGES.items():
        if value is None or name == "payout_credential_source":
            continue
        assert update(db, manager, {name: value}) is not None, name
    assert pc.set_credentials(db, manager, {"PAYOUT_API_KEY": SECRETS["PAYOUT_API_KEY"]},
                              password=PASSWORD) == ["PAYOUT_API_KEY"]


def test_the_api_refuses_a_live_payout_change_and_stores_nothing(client, ledger, admins):
    db = ledger
    configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
    before = stored(db)
    answer = client.put(SETTINGS_URL, headers=auth(admins["manage"]), json={
        "changes": {"max_daily_payout_usd": "9000000"}, "current_password": PASSWORD,
        "expected_version": pc.load(db).version})
    assert answer.status_code == 403 and answer.json()["detail"]["code"] == REFUSED
    assert answer.json()["detail"]["field"] == "max_daily_payout_usd"
    stored_answer = client.put("/api/v1/admin/finance/credentials", headers=auth(admins["manage"]), json={
        "values": {"PAYOUT_PASSWORD": SECRETS["PAYOUT_PASSWORD"]}, "current_password": PASSWORD})
    assert stored_answer.status_code == 403 and stored_answer.json()["detail"]["code"] == REFUSED
    assert stored(db) == before
    assert client.get(SETTINGS_URL, headers=auth(admins["manage"])).json()["activation"]["automatic_payouts_on"] is True


# ===========================================================================
# 5. Granting: every permission by name, and nobody else is ever affected
# ===========================================================================

def staff(db):
    """Three administrators on the SAME ordinary role, which other members share."""
    base = Role(name="user", is_system=True, permissions=[Permission(name="vote", category="user")])
    db.add(base)
    db.add_all([Permission(name=name, category="admin") for name in grants.PERMISSIONS])
    db.flush()
    people = []
    for name in ("owner", "developer", "other", "plainmember"):
        row = plain_admin(db, name)
        row.role_id = base.id
        row.is_admin = name != "plainmember"
        people.append(row)
    db.commit()
    return people


def held(db, user) -> set:
    db.expire_all()
    user = db.get(User, user.id)
    return {name for name in grants.PERMISSIONS if pc.has_permission(user, name)}


def test_nothing_is_granted_that_was_not_named(db, capsys):
    owner, _developer, _other, _member = staff(db)
    with pytest.raises(grants.GrantError):
        grants.grant(db, owner.email, [], apply=True)
    with pytest.raises(grants.GrantError):
        grants.grant(db, owner.email, ["all"], apply=True)
    with pytest.raises(SystemExit):                                 # the command line has no default either
        grants.main(["--email", owner.email, "--apply"])
    assert "--permission" in capsys.readouterr().err
    assert held(db, owner) == set() and db.query(Role).count() == 1

    assert grants.grant(db, owner.email, [MANAGE]) == ("granted", "finance_manager_m_user", False)   # dry run
    assert held(db, owner) == set() and db.query(Role).count() == 1
    assert grants.grant(db, owner.email, [MANAGE], apply=True) == ("granted", "finance_manager_m_user", True)
    assert held(db, owner) == {MANAGE}                              # manage only: not activate, not process
    assert pc.can_activate(db.get(User, owner.id)) is False
    assert db.get(User, owner.id).role.has_permission("vote")       # what the account had is kept
    assert grants.grant(db, owner.email, [MANAGE], apply=True)[0] == "already_granted"
    trail = db.query(AuditTrail).filter_by(action="PAYMENT_PERMISSION_GRANTED").one()
    assert trail.new_values == {"role": "finance_manager_m_user", "permissions": [MANAGE]}


def test_a_grant_to_one_administrator_never_reaches_another(db):
    owner, developer, other, plain = staff(db)
    for person in (owner, developer):
        grants.grant(db, person.email, [MANAGE], apply=True)
    assert held(db, owner) == held(db, developer) == {MANAGE}
    assert db.get(User, owner.id).role_id == db.get(User, developer.id).role_id   # the same grant, the same role

    # The owner alone is given the activation authority. The developer shares the owner's old role
    # and must not receive it.
    assert grants.grant(db, owner.email, [ACTIVATE], apply=True) == ("granted", "finance_manager_ma_user", True)
    assert held(db, owner) == {MANAGE, ACTIVATE} and pc.can_activate(db.get(User, owner.id)) is True
    assert held(db, developer) == {MANAGE} and pc.can_activate(db.get(User, developer.id)) is False
    assert held(db, other) == held(db, plain) == set()
    # No role was given a permission after it was created.
    assert {r.name: sorted(p.name for p in r.permissions) for r in db.query(Role).all()} == {
        "user": ["vote"], "finance_manager_m_user": [MANAGE], "finance_manager_ma_user": sorted([MANAGE, ACTIVATE])}

    # The activation permission alone, to somebody who cannot configure: held, and worth nothing.
    grants.grant(db, other.email, [ACTIVATE], apply=True)
    assert held(db, other) == {ACTIVATE} and pc.can_activate(db.get(User, other.id)) is False
    # A member who is not an administrator is refused.
    with pytest.raises(grants.GrantError):
        grants.grant(db, plain.email, [MANAGE], apply=True)
    assert held(db, plain) == set()


def test_a_role_that_does_not_hold_what_its_name_says_is_never_used_or_changed(db):
    owner, developer, _other, _member = staff(db)
    grants.grant(db, developer.email, [MANAGE], apply=True)
    role = db.query(Role).filter_by(name="finance_manager_m_user").one()
    role.permissions.append(db.query(Permission).filter_by(name=ACTIVATE).one())   # changed behind the tool's back
    db.commit()
    with pytest.raises(grants.GrantError):
        grants.grant(db, owner.email, [MANAGE], apply=True)
    assert held(db, owner) == set()


def test_revoking_takes_away_what_is_named_or_everything_and_touches_nobody_else(db):
    owner, developer, _other, _member = staff(db)
    for person in (owner, developer):
        grants.grant(db, person.email, [MANAGE, ACTIVATE, PROCESS], apply=True)
    assert db.get(User, owner.id).role.name == "finance_manager_map_user"
    assert grants.revoke(db, owner.email, [ACTIVATE]) == ("revoked", "finance_manager_mp_user", False)   # dry run
    assert held(db, owner) == {MANAGE, ACTIVATE, PROCESS}
    assert grants.revoke(db, owner.email, [ACTIVATE], apply=True) == ("revoked", "finance_manager_mp_user", True)
    assert held(db, owner) == {MANAGE, PROCESS} and held(db, developer) == {MANAGE, ACTIVATE, PROCESS}
    assert grants.revoke(db, owner.email, [ACTIVATE], apply=True)[0] == "not_granted"
    assert grants.revoke(db, owner.email, apply=True) == ("revoked", "user", True)
    assert held(db, owner) == set() and db.get(User, owner.id).role.name == "user"
    assert held(db, developer) == {MANAGE, ACTIVATE, PROCESS}
