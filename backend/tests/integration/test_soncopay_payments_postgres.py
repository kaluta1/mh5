"""Migration e1a3b5c7d9f2 (SoncoPay payments) and SoncoPay concurrency on a
real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL). Each test runs
in ONE DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.checkout_gateway import SoncoPayWebhookEvent
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import soncopay_payments as scp
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MIGRATION = "e1a3b5c7d9f2_soncopay_payments.py"
NEW_COLUMNS = {"payment_provider", "provider_environment", "provider_status", "provider_checkout_url",
               "provider_expires_at"}


def deposit_columns(engine) -> set:
    with engine.connect() as c:
        return {r[0] for r in c.execute(text(
            "select column_name from information_schema.columns where table_name = 'deposits'"))}


def has_table(engine, name) -> bool:
    with engine.connect() as c:
        return c.execute(text("select to_regclass(:n) is not null"), {"n": f"public.{name}"}).scalar()


def seed_legacy(engine, Session) -> tuple:
    """A member, a product (through the ORM: this migration does not change them) and two NOWPayments-era
    deposits written with SQL as today's production code writes them, with the SAME provider payment id
    (the column has never been unique)."""
    with Session() as db:
        user = User(email="legacy@example.com", username="legacy", hashed_password="x", is_active=True,
                    is_deleted=False)
        product = ProductType(code="annual_membership", name="annual_membership", price=50, currency="USD",
                              validity_days=365)
        db.add_all([user, product])
        db.commit()
        user_id, product_id = user.id, product.id
    with engine.begin() as c:
        for order in ("mh5-legacy-1", "mh5-legacy-2"):
            c.execute(text("insert into deposits (user_id, product_type_id, amount, currency, status, order_id, "
                           "external_payment_id, is_used, created_at, updated_at) values (:u, :p, 50, 'USD', "
                           "'validated', :o, 'np-shared-1', false, now(), now())"),
                      {"u": user_id, "p": product_id, "o": order})
    return user_id, product_id


def legacy_rows(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select id, user_id, amount, status::text, order_id, external_payment_id from deposits order by id"))]


def test_the_migration_is_additive_and_leaves_existing_deposits_as_they_are(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")                              # the production schema (d0f2a4c6e8b1)
    assert not (deposit_columns(engine) & NEW_COLUMNS) and not has_table(engine, "soncopay_webhook_events")
    seed_legacy(engine, Session)
    before = legacy_rows(engine)

    for _ in range(2):                                                   # a re-run is a no-op
        migrate(engine, MIGRATION, "upgrade")
        assert NEW_COLUMNS <= deposit_columns(engine) and has_table(engine, "soncopay_webhook_events")
        assert legacy_rows(engine) == before                             # nothing existing is written
        with engine.connect() as c:
            assert c.execute(text("select count(*) from deposits where payment_provider is not null")).scalar() == 0
            assert c.execute(text("select count(*) from soncopay_webhook_events")).scalar() == 0

    user, product = before[0][1], None
    with engine.connect() as c:
        product = c.execute(text("select id from product_types limit 1")).scalar()

    def insert(order, provider, environment, payment_id):
        with engine.begin() as c:
            c.execute(text("insert into deposits (user_id, product_type_id, amount, currency, status, order_id, "
                           "external_payment_id, is_used, payment_provider, provider_environment, created_at, "
                           "updated_at) values (:u, :p, 50, 'USD', 'pending', :o, :x, false, :pr, :env, now(), now())"),
                      {"u": user, "p": product, "o": order, "x": payment_id, "pr": provider, "env": environment})

    insert("np-3", "nowpayments", None, "np-shared-1")                   # NOWPayments ids are still not checked
    insert("sp-1", "soncopay", "test", "pay_00000000000000000001")
    with pytest.raises(IntegrityError):                                  # one SoncoPay payment = one deposit
        insert("sp-2", "soncopay", "test", "pay_00000000000000000001")
    for provider, environment in (("paypal", None), ("soncopay", "prod")):
        with pytest.raises(IntegrityError):
            insert(f"bad-{provider}", provider, environment, None)
    with engine.begin() as c:
        c.execute(text("insert into soncopay_webhook_events (delivery_id, event, environment, outcome) "
                       "values ('dlv_1', 'payment.paid', 'test', 'PROCESSED')"))
    with pytest.raises(IntegrityError):                                  # a delivery is recorded once
        with engine.begin() as c:
            c.execute(text("insert into soncopay_webhook_events (delivery_id, event, environment, outcome) "
                           "values ('dlv_1', 'payment.paid', 'test', 'PROCESSED')"))


def test_the_downgrade_refuses_while_a_soncopay_deposit_exists(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")
    seed_legacy(engine, Session)
    migrate(engine, MIGRATION, "upgrade")
    with engine.begin() as c:
        c.execute(text("update deposits set payment_provider = 'soncopay', provider_environment = 'test' "
                       "where order_id = 'mh5-legacy-1'"))
    with pytest.raises(Exception, match="SoncoPay deposits exist"):
        migrate(engine, MIGRATION, "downgrade")
    assert NEW_COLUMNS <= deposit_columns(engine)
    with engine.begin() as c:
        c.execute(text("update deposits set payment_provider = null, provider_environment = null"))
    migrate(engine, MIGRATION, "downgrade")                              # without one it goes back cleanly
    assert not (deposit_columns(engine) & NEW_COLUMNS) and not has_table(engine, "soncopay_webhook_events")
    migrate(engine, MIGRATION, "upgrade")


def test_two_workers_applying_the_same_paid_payment_confirm_it_once(pg, monkeypatch):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")
    user, product = seed_legacy(engine, Session)
    with Session() as db:
        dep = Deposit(user_id=user, product_type_id=product, amount=50, currency="USD", status=DepositStatus.PENDING,
                      order_id="mh5-sp-race", external_payment_id="pay_00000000000000000009", is_used=False,
                      payment_provider="soncopay", provider_environment="test")
        db.add(dep)
        db.commit()
        deposit_id = dep.id
    from app.services import commission_distribution

    confirmations = []
    monkeypatch.setattr(commission_distribution, "process_payment_validation",
                        lambda _db, deposit, **_kw: confirmations.append(deposit.id) or True)
    paid = {"id": "pay_00000000000000000009", "order_id": "mh5-sp-race", "status": "paid", "amount": "50.00",
            "currency": "USD", "livemode": False, "asset": "USDT", "network": "BSC"}

    def work(i: int):
        with Session() as db:
            outcome, _dep = scp.apply_locked(db, deposit_id, paid)
            db.add(SoncoPayWebhookEvent(delivery_id="dlv_race", event="payment.paid", environment="test",
                                        payment_id=paid["id"], deposit_id=deposit_id, outcome="PROCESSED"))
            try:
                db.commit()
                return outcome
            except IntegrityError:
                db.rollback()
                return "DUPLICATE"

    results = in_threads(2, work)
    assert sorted(results) == ["DUPLICATE", "SYNCED"], results
    assert confirmations == [deposit_id]                                 # the row lock let only one confirm
    with engine.connect() as c:
        assert c.execute(text("select status::text from deposits where id = :i"), {"i": deposit_id}).scalar() == "validated"
        assert c.execute(text("select count(*) from soncopay_webhook_events")).scalar() == 1
