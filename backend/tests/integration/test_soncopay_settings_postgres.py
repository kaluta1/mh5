"""Migration d0f2a4c6e8b1 (checkout_gateway_settings) and the SoncoPay settings
on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL). Each test runs
in ONE DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.services import soncopay_settings as sp
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401
from tests.integration.test_super_admin_postgres import MIGRATION as SUPER_ADMIN_MIGRATION, PASSWORD, roles, seed

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MIGRATION = "d0f2a4c6e8b1_checkout_gateway_settings.py"


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")


def table_columns(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select column_name, data_type, is_nullable, coalesce(column_default, '') from information_schema.columns "
            "where table_name = 'checkout_gateway_settings' order by column_name"))]


def everything_else(engine) -> tuple:
    with engine.connect() as c:
        return (c.execute(text("select count(*), coalesce(max(version), 0) from payment_settings")).first(),
                tuple(c.execute(text("select provider, name, ciphertext from payment_credentials order by 1, 2"))),
                tuple(c.execute(text("select table_name from information_schema.tables where table_schema = 'public' "
                                     "and table_name <> 'checkout_gateway_settings' order by 1"))))


def test_the_migration_adds_one_empty_table_and_nothing_else(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")                              # the production schema before it
    assert table_columns(engine) == []
    before = everything_else(engine)

    for _ in range(2):                                                   # a re-run is a no-op
        migrate(engine, MIGRATION, "upgrade")
        columns = {name: (kind, nullable, default) for name, kind, nullable, default in table_columns(engine)}
        assert columns["default_provider"][0:2] == ("character varying", "NO")
        assert "nowpayments" in columns["default_provider"][2]
        assert columns["soncopay_enabled"] == ("boolean", "NO", "false")
        assert "test" in columns["soncopay_environment"][2]
        assert everything_else(engine) == before
        with engine.connect() as c:
            assert c.execute(text("select count(*) from checkout_gateway_settings")).scalar() == 0

    # The constraints hold whatever writes the table.
    for values in ("(2, 'nowpayments', false, 'test')", "(1, 'paypal', false, 'test')", "(1, 'nowpayments', false, 'prod')"):
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text("insert into checkout_gateway_settings (id, default_provider, soncopay_enabled, "
                               f"soncopay_environment) values {values}"))

    migrate(engine, MIGRATION, "downgrade")
    assert table_columns(engine) == [] and everything_else(engine) == before
    migrate(engine, MIGRATION, "upgrade")


def test_the_downgrade_refuses_while_soncopay_credentials_are_stored(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")
    with engine.begin() as c:
        c.execute(text("insert into payment_credentials (provider, name, ciphertext, set_at, created_at, updated_at) "
                       "values ('soncopay', 'TEST_API_KEY', 'v1:synthetic', now(), now(), now())"))
    with pytest.raises(Exception, match="SoncoPay credentials are stored"):
        migrate(engine, MIGRATION, "downgrade")
    assert table_columns(engine) != []


def test_two_first_saves_at_once_create_one_row_and_one_wins(pg):
    engine, Session = pg
    migrate(engine, SUPER_ADMIN_MIGRATION, "upgrade")                    # the Super Admin role
    migrate(engine, MIGRATION, "upgrade")
    roles(Session, "user")
    ids = [seed(Session, "first", role_name="super_admin"), seed(Session, "second", role_name="super_admin")]

    def save(i: int):
        with Session() as db:
            try:
                sp.update(db, db.get(User, ids[i]), password=PASSWORD, expected_version=0,
                          credentials={"TEST_API_KEY": f"sp_test_synthetic_key_{i:08d}"})
                return "saved"
            except sp.SoncoPaySettingsError as exc:
                return exc.code

    results = in_threads(2, save)
    assert sorted(results) == ["STALE", "saved"], results
    with engine.connect() as c:
        assert c.execute(text("select count(*), max(version) from checkout_gateway_settings")).first() == (1, 1)
        assert c.execute(text("select count(*) from payment_credentials where provider = 'soncopay'")).scalar() == 1
