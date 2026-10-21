"""Migration f2b4d6e8a0c1 (NOWPayments checkout switch) on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL). Each test runs
in ONE DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import payment_config as pc
from tests.integration.test_payments_postgres import migrate, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MIGRATION = "f2b4d6e8a0c1_nowpayments_checkout_switch.py"
SNAPSHOT = ("select version, provider_enabled, crypto_cashout_enabled, crypto_auto_payout_enabled, "
            "payin_credential_source, payout_credential_source, updated_at from payment_settings order by id")


def has_column(engine) -> bool:
    with engine.connect() as c:
        return c.execute(text("select count(*) from information_schema.columns where table_name = 'payment_settings' "
                              "and column_name = 'checkout_enabled'")).scalar() == 1


def test_the_migration_adds_the_switch_and_activates_nothing(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")                              # the schema of e1a3b5c7d9f2
    assert not has_column(engine)
    # Production today: the provider OFF (both directions stopped), automatic payouts switched on.
    values = {**pc.defaults(), "provider_enabled": False, "crypto_cashout_enabled": True,
              "crypto_auto_payout_enabled": True}
    values.pop("checkout_enabled")
    columns = ", ".join(values)
    with engine.begin() as c:
        c.execute(text(f"insert into payment_settings (id, version, created_at, updated_at, {columns}) "
                       f"values (1, 10, now(), now(), {', '.join(':' + k for k in values)})"), values)
        before = [tuple(r) for r in c.execute(text(SNAPSHOT))]

    for _ in range(2):                                                   # a re-run is a no-op
        migrate(engine, MIGRATION, "upgrade")
        assert has_column(engine)
        with engine.connect() as c:
            assert [tuple(r) for r in c.execute(text(SNAPSHOT))] == before   # no row was written
            assert c.execute(text("select checkout_enabled from payment_settings")).scalar() is True
            meta = c.execute(text("select is_nullable, column_default from information_schema.columns "
                                  "where table_name = 'payment_settings' and column_name = 'checkout_enabled'")).first()
            assert meta[0] == "NO" and meta[1] == "true"
    with Session() as db:
        config = pc.load(db)
        # What is in force did not change: checkout = provider (off), payouts stopped by the provider.
        assert (config.provider_enabled, config.checkout_enabled) == (False, True)
        assert config.checkout_allowed is False and config.auto_payout_allowed is False
        assert pc.nowpayments_checkout_available(db) is False
        db.rollback()

    migrate(engine, MIGRATION, "downgrade")
    assert not has_column(engine)
    with engine.connect() as c:
        assert [tuple(r) for r in c.execute(text(SNAPSHOT))] == before
    migrate(engine, MIGRATION, "upgrade")


def test_the_switch_stores_false_and_the_older_code_path_still_reads_the_row(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")
    with engine.begin() as c:
        values = {**pc.defaults(), "checkout_enabled": False}
        columns = ", ".join(values)
        c.execute(text(f"insert into payment_settings (id, version, created_at, updated_at, {columns}) "
                       f"values (1, 1, now(), now(), {', '.join(':' + k for k in values)})"), values)
    with Session() as db:
        config = pc.load(db)
        assert config.provider_enabled is True and config.checkout_enabled is False
        assert config.checkout_allowed is False and config.auto_payout_allowed == bool(
            pc.crypto_master_switch() and config.crypto_cashout_enabled and config.crypto_auto_payout_enabled)
        db.rollback()
    # 8b93cb6 (the code before this change) selects the row without the new column: it must still work.
    with engine.connect() as c:
        row = c.execute(text("select provider_enabled, crypto_auto_payout_enabled from payment_settings")).first()
        assert row is not None
