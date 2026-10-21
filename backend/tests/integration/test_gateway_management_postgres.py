"""Payment gateway management under concurrency, on a real PostgreSQL server.

  * choosing NOWPayments as the default holds the gateway row (FOR UPDATE) and
    then the NOWPayments settings row (FOR SHARE): switching NOWPayments off
    waits until that choice is committed or refused, so a choice is never
    validated against a state that is changing underneath it;
  * many Super Admins saving gateway and NOWPayments settings at once never
    deadlock, never lose a change, and the effective default always follows
    the gateways that are ready (no fall back).

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL). Each test runs
in ONE DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os
import random

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.models.checkout_gateway import CheckoutGatewaySettings
from app.models.payment_config import PaymentSettings
from app.models.user import User
from app.services import checkout_routing
from app.services import payment_config as pc
from app.services import soncopay_settings as sp
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401
from tests.integration.test_super_admin_postgres import PASSWORD, roles, seed
from tests.integration.test_payments_postgres import migrate
from tests.integration.test_super_admin_postgres import MIGRATION as SUPER_ADMIN_MIGRATION

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

TEST_KEY, TEST_SECRET = "sp_test_synthetic_key_0000001", "whsec_test_synthetic_secret_01"


@pytest.fixture(autouse=True)
def synthetic_credentials(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-api-key")
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "synthetic-ipn-secret-0001")


def world(engine, Session, admins: int = 1) -> list:
    """The Super Admin role, Super Admins, NOWPayments ready and SoncoPay ready (Test) with SoncoPay the default."""
    migrate(engine, SUPER_ADMIN_MIGRATION, "upgrade")
    roles(Session, "user")
    ids = [seed(Session, f"boss{i}", role_name="super_admin") for i in range(admins)]
    with Session() as db:
        db.add(PaymentSettings(id=pc.SETTINGS_ROW_ID, version=0, **pc.defaults()))
        db.commit()
        boss = db.get(User, ids[0])
        sp.update(db, boss, password=PASSWORD, credentials={"TEST_API_KEY": TEST_KEY, "TEST_WEBHOOK_SECRET": TEST_SECRET})
        sp.update(db, boss, password=PASSWORD, enabled=True)
        sp.update(db, boss, password=PASSWORD, default_provider="soncopay")
    return ids


def test_switching_nowpayments_off_waits_while_it_is_being_chosen_as_the_default(pg):
    engine, Session = pg
    boss_id = world(engine, Session)[0]
    chooser = Session()
    try:
        # Exactly what soncopay_settings.update holds while it validates NOWPayments as the default.
        chooser.query(CheckoutGatewaySettings).filter(CheckoutGatewaySettings.id == 1).with_for_update().one()
        assert pc.nowpayments_checkout_problem(chooser, pc.load_shared(chooser)) is None

        with Session() as other:
            other.execute(text("set local lock_timeout = '400ms'"))
            with pytest.raises(DBAPIError, match="lock"):          # it waits on the shared lock
                pc.update_settings(other, other.get(User, boss_id), {"provider_enabled": False}, password=PASSWORD)
            other.rollback()
        chooser.rollback()                                          # the choice is released
    finally:
        chooser.close()

    with Session() as other:                                        # now it goes through at once
        assert pc.update_settings(other, other.get(User, boss_id), {"provider_enabled": False},
                                  password=PASSWORD).provider_enabled is False
    with Session() as db:
        refused = None
        try:
            sp.update(db, db.get(User, boss_id), password=PASSWORD, default_provider="nowpayments")
        except sp.SoncoPaySettingsError as exc:
            refused = exc.code
        assert refused == "NOT_READY"                               # validated against the committed state
        assert checkout_routing.stored_default(db) == "soncopay"


def test_choosing_nowpayments_as_the_default_waits_for_a_nowpayments_change_in_progress(pg):
    engine, Session = pg
    boss_id = world(engine, Session)[0]
    changer = Session()
    try:
        # A NOWPayments settings change in progress (payment_config.update_settings holds this lock).
        changer.query(PaymentSettings).filter(PaymentSettings.id == pc.SETTINGS_ROW_ID).with_for_update().one()
        with Session() as db:
            db.execute(text("set lock_timeout = '400ms'"))
            try:
                with pytest.raises(DBAPIError, match="lock"):      # the real save path waits on it
                    sp.update(db, db.get(User, boss_id), password=PASSWORD, default_provider="nowpayments")
            finally:
                db.rollback()
                db.execute(text("reset lock_timeout"))
                db.commit()
            assert checkout_routing.stored_default(db) == "soncopay"
        changer.rollback()
    finally:
        changer.close()
    with Session() as db:                                           # once it is done, the choice goes through
        sp.update(db, db.get(User, boss_id), password=PASSWORD, default_provider="nowpayments")
        assert checkout_routing.new_payment_gateway(db) == "nowpayments"


def test_concurrent_gateway_and_nowpayments_saves_never_deadlock_and_never_fall_back(pg):
    engine, Session = pg
    ids = world(engine, Session, admins=4)
    expected_refusals = {"STALE", "NOT_READY", "STALE_CONFIGURATION", "NOTHING_TO_CHANGE"}

    def work(i: int):
        rng = random.Random(i)
        outcomes = []
        for _ in range(12):
            with Session() as db:
                actor = db.get(User, ids[i % len(ids)])
                action = rng.choice(("default_now", "default_sonco", "sonco_on", "sonco_off", "now_on", "now_off"))
                try:
                    if action == "default_now":
                        sp.update(db, actor, password=PASSWORD, default_provider="nowpayments")
                    elif action == "default_sonco":
                        sp.update(db, actor, password=PASSWORD, default_provider="soncopay")
                    elif action in ("sonco_on", "sonco_off"):
                        sp.update(db, actor, password=PASSWORD, enabled=action == "sonco_on")
                    else:
                        pc.update_settings(db, actor, {"provider_enabled": action == "now_on"}, password=PASSWORD)
                    outcomes.append("ok")
                except (sp.SoncoPaySettingsError, pc.PaymentConfigError) as exc:
                    outcomes.append(exc.code)
                except DBAPIError as exc:                           # a deadlock would end up here
                    outcomes.append("DB:" + type(exc.orig).__name__)
        return outcomes

    results = [o for outcomes in in_threads(8, work) for o in outcomes]
    assert not [o for o in results if o.startswith("DB:")], results
    assert set(results) <= {"ok"} | expected_refusals, set(results)
    assert results.count("ok") > 0

    with Session() as db:
        stored = checkout_routing.stored_default(db)
        states = checkout_routing.states(db)
        effective = checkout_routing.new_payment_gateway(db)
        assert effective == (stored if states[stored].ready else None)       # never the other gateway
        assert db.query(CheckoutGatewaySettings).count() == 1 and db.query(PaymentSettings).count() == 1
        # Every accepted gateway save is in the audit trail, with consecutive versions.
        versions = [r[0] for r in db.execute(text(
            "select (new_values->>'version')::int from audit_trails where action = 'SONCOPAY_SETTINGS_CHANGED' "
            "order by 1"))]
        assert versions == list(range(1, len(versions) + 1))
        assert db.query(CheckoutGatewaySettings).one().version == len(versions)
