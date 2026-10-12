"""Dual cashout, payment configuration and pay-in crediting on REAL PostgreSQL.

SQLite cannot prove row locks, partial unique indexes, transactional DDL or
two workers racing. Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in
POSTGRES_ADMIN_URL, default postgresql://postgres@127.0.0.1:5432/postgres).

SAFETY. The admin URL must be a loopback address, otherwise every test here
fails before connecting. Each test creates a DISPOSABLE database with a random
name (never an existing one), builds the schema in it and drops it afterwards.
The application's own DATABASE_URL is never used. All rows are synthetic and
the payout provider is a fake object: nothing is sent anywhere.

The two migrations of the dual cashout are run from their source files
(f3a4b5c6d7e8 then a5b6c7d8e9f0) against a schema taken back to the revision
production runs today (e2f3a4b5c6d7), with production-like rows in it.
"""
from __future__ import annotations

import importlib.util
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (register every model)
from app.core.config import settings
from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.business_model import BusinessModelVersion
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.payment_config import (
    CashoutFeeConsent,
    PaymentConfigAudit,
    PaymentCredential,
    PaymentSettings,
    PaymentWebhookStat,
    PayoutWalletVerification,
)
from app.models.user import Permission, User
from app.services import cashout_engine as engine_service
from app.services import cashout_service as cs
from app.services import nowpayments_service as nowpayments
from app.services import payment_config as pc
from app.services.financial_balances import get_commission_balance
from app.services.new_model_reference_data import seed_new_model_reference_data
from tests.integration.test_month_end_locking_postgres import _build_schema
from tests.unit.test_dual_cashout import (
    FEE_RULES,
    NOW,
    PASSWORD,
    PAYOUT_ENV,
    WALLET,
    FakeProvider,
    accept_terms,
    commission,
    configure,
    member,
)
from tests.unit.test_new_business_model import BASE_ACCOUNTS, _deposit, _user

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
DATABASE_PREFIX = "mh5_pay_test_"
VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
DUAL_CASHOUT = "f3a4b5c6d7e8_dual_cashout.py"
PAYMENT_CONFIGURATION = "a5b6c7d8e9f0_payment_configuration.py"
FEE_ACCOUNT = "b6c7d8e9f0a1_crypto_payout_network_fee_account.py"
BENEFICIARY_FEE = "c7d8e9f0a1b2_beneficiary_paid_network_fee.py"
FEE_SAFETY = "d8e9f0a1b2c3_payout_fee_safety.py"
PRODUCTION_REVISION = "e2f3a4b5c6d7"

PAYMENT_TABLES = ("payment_settings", "payment_credentials", "payment_config_audit", "payout_wallet_verifications",
                  "payment_webhook_stats", "payout_wallet_changes", "affiliate_cashout_requests",
                  "cashout_fee_consents")
NEW_USER_COLUMNS = ("cashout_method", "cashout_method_changed_at", "payout_wallet_verified_at")


# ---------------------------------------------------------------------------
# disposable database
# ---------------------------------------------------------------------------

@pytest.fixture
def pg():
    url = make_url(ADMIN_URL)
    assert url.host in LOOPBACK, f"refusing to run destructive fixtures against a non-local server ({url.host})"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = f"{DATABASE_PREFIX}{uuid.uuid4().hex[:12]}"
    with admin.connect() as c:
        assert c.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).first() is None
        c.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(url.set(database=name), pool_pre_ping=True, pool_size=10, max_overflow=20,
                           pool_timeout=10, connect_args={"options": "-c statement_timeout=15000"})
    try:
        with engine.connect() as c:
            assert c.execute(text("select current_database()")).scalar() == name
        _build_schema(engine)
        yield engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False)
    pc.invalidate_runtime()
    yield
    pc.invalidate_runtime()


@pytest.fixture
def engine_on(monkeypatch):
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)


def seed_ledger(db) -> None:
    """Chart of accounts, products and the business model: what `world` builds on SQLite."""
    for code, kind in {**BASE_ACCOUNTS, "4005": AccountType.REVENUE, "1010": AccountType.ASSET}.items():
        db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind, is_active=True))
    db.flush()
    for code, price in [("kyc", 10), ("annual_membership", 50)]:
        db.add(ProductType(code=code, name=code, price=price, currency="USD", validity_days=365))
    db.flush()
    seed_new_model_reference_data(db)
    version = db.query(BusinessModelVersion).one()
    version.effective_at = datetime.utcnow() - timedelta(days=1)
    db.commit()


def in_threads(count: int, work) -> list:
    """Run `work(i)` in `count` threads released together; return results or exceptions."""
    barrier = threading.Barrier(count)
    results: list = [None] * count

    def run(i: int) -> None:
        try:
            barrier.wait(timeout=10)
            results[i] = work(i)
        except Exception as exc:  # noqa: BLE001 - the caller inspects it
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a worker is still blocked"
    return results


# ---------------------------------------------------------------------------
# migrations
# ---------------------------------------------------------------------------

def load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(filename[:-3], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migrate(engine, filename: str, direction: str) -> None:
    """Run one migration's upgrade()/downgrade() in a single transaction, as Alembic does."""
    module = load_migration(filename)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(module, direction)()


def schema_snapshot(engine) -> dict:
    with engine.connect() as c:
        columns = c.execute(text(
            "select table_name, column_name, data_type, is_nullable, coalesce(character_maximum_length, 0), "
            "coalesce(numeric_precision, 0), coalesce(numeric_scale, 0) from information_schema.columns "
            "where table_schema = 'public' and (table_name = any(:t) or "
            "(table_name = 'users' and column_name = any(:u))) order by 1, 2"),
            {"t": list(PAYMENT_TABLES), "u": list(NEW_USER_COLUMNS)}).fetchall()
        unique = c.execute(text(
            "select indexdef from pg_indexes where schemaname = 'public' and tablename = any(:t) "
            "and indexdef ilike 'create unique index%'"), {"t": list(PAYMENT_TABLES)}).fetchall()
    # What an index enforces, not what it is called (a model-built and a
    # migration-built constraint may be named differently).
    rules = sorted(r[0].split(" ON ", 1)[1] for r in unique)
    return {"columns": [tuple(r) for r in columns], "unique_indexes": rules}


def back_to_production_revision(engine) -> None:
    migrate(engine, FEE_SAFETY, "downgrade")
    migrate(engine, BENEFICIARY_FEE, "downgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "downgrade")
    migrate(engine, DUAL_CASHOUT, "downgrade")


def production_like_rows(db) -> dict:
    """What production holds before the dual cashout: members with a saved
    wallet, commissions in every state, and cashout rows written by the earlier
    payout code."""
    sponsor = _user(db, "sponsor@t.com")                       # has a saved (legacy) wallet
    no_wallet = _user(db, "nowallet@t.com", wallet=False)
    payer = _user(db, "payer@t.com", sponsor=sponsor, wallet=False)
    from app.models.affiliate import CommissionType

    for amount, status in (("5.00", CommissionStatus.APPROVED), ("7.50", CommissionStatus.PENDING),
                           ("3.00", CommissionStatus.PAID), ("2.00", CommissionStatus.CANCELLED)):
        db.add(AffiliateCommission(user_id=sponsor.id, source_user_id=payer.id,
                                   commission_type=CommissionType.KYC_PAYMENT, level=1, base_amount=Decimal("10.00"),
                                   commission_amount=Decimal(amount), status=status,
                                   transaction_date=datetime(2026, 8, 1)))
    db.add(AffiliateCashoutRequest(user_id=sponsor.id, gross_amount=Decimal("3.00"), fee=Decimal("0"),
                                   net_amount=Decimal("3.00"), status="completed",
                                   payout_reference="intent:legacy-1;provider:5000000001",
                                   wallet_snapshot="0x" + "1" * 40, requested_at=datetime(2026, 8, 2),
                                   processed_at=datetime(2026, 8, 2)))
    db.add(AffiliateCashoutRequest(user_id=sponsor.id, gross_amount=Decimal("4.00"), fee=Decimal("0"),
                                   net_amount=Decimal("4.00"), status="failed", payout_reference="intent:legacy-2",
                                   requested_at=datetime(2026, 8, 3)))
    db.add(AffiliateCashoutRequest(user_id=sponsor.id, gross_amount=Decimal("1.00"), fee=Decimal("0"),
                                   net_amount=Decimal("1.00"), status="failed", payout_reference=None,
                                   requested_at=datetime(2026, 8, 4)))
    db.commit()
    return {"sponsor": sponsor.id, "no_wallet": no_wallet.id}


def money_fingerprint(engine) -> tuple:
    with engine.connect() as c:
        return (
            tuple(c.execute(text("select id, user_id, commission_amount, status::text, payout_reference "
                                 "from affiliate_commissions order by id")).fetchall()),
            tuple(c.execute(text("select id, user_id, gross_amount, fee, net_amount, status, payout_reference, "
                                 "wallet_snapshot from affiliate_cashout_requests order by id")).fetchall()),
            tuple(c.execute(text("select id, usdt_wallet_address from users order by id")).fetchall()),
            c.execute(text("select count(*) from journal_entries")).scalar(),
        )


def test_the_migration_chain_is_the_one_the_deployment_plan_assumes():
    first, second = load_migration(DUAL_CASHOUT), load_migration(PAYMENT_CONFIGURATION)
    assert (first.revision, first.down_revision) == ("f3a4b5c6d7e8", PRODUCTION_REVISION)
    assert (second.revision, second.down_revision) == ("a5b6c7d8e9f0", "f3a4b5c6d7e8")
    assert first.depends_on is None and second.depends_on is None
    assert first.branch_labels is None and second.branch_labels is None
    revisions = {}
    for path in VERSIONS.glob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for line in source.splitlines():
            if line.startswith("down_revision"):
                revisions[path.name] = line
    third = load_migration(FEE_ACCOUNT)
    assert (third.revision, third.down_revision, third.depends_on) == ("b6c7d8e9f0a1", "a5b6c7d8e9f0", None)
    children = [name for name, line in revisions.items() if '"a5b6c7d8e9f0"' in line or "'a5b6c7d8e9f0'" in line]
    assert children == [FEE_ACCOUNT]                               # one line, no branch
    fourth = load_migration(BENEFICIARY_FEE)
    assert (fourth.revision, fourth.down_revision, fourth.depends_on) == ("c7d8e9f0a1b2", "b6c7d8e9f0a1", None)
    children = [name for name, line in revisions.items() if '"b6c7d8e9f0a1"' in line or "'b6c7d8e9f0a1'" in line]
    assert children == [BENEFICIARY_FEE]                           # one line, no branch
    fifth = load_migration(FEE_SAFETY)
    assert (fifth.revision, fifth.down_revision, fifth.depends_on) == ("d8e9f0a1b2c3", "c7d8e9f0a1b2", None)
    children = [name for name, line in revisions.items() if '"c7d8e9f0a1b2"' in line or "'c7d8e9f0a1b2'" in line]
    assert children == [FEE_SAFETY]                                # one line, no branch
    heads = [name for name, line in revisions.items() if '"d8e9f0a1b2c3"' in line or "'d8e9f0a1b2c3'" in line]
    assert heads == []                                             # d8e9f0a1b2c3 is the single head


def test_upgrade_from_the_production_revision_keeps_every_existing_row(pg):
    engine, Session = pg
    as_models_define_it = schema_snapshot(engine)
    with Session() as db:
        ids = production_like_rows(db)
    back_to_production_revision(engine)
    before = schema_snapshot(engine)
    assert not any(row[0] in ("payment_settings", "payment_credentials", "payout_wallet_changes")
                   or row[0] == "users" for row in before["columns"])                    # the pre-deployment schema
    assert before["unique_indexes"] == ["public.affiliate_cashout_requests USING btree (id)"]   # no cashout rule yet
    rows_before = money_fingerprint(engine)

    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    assert money_fingerprint(engine) == rows_before                 # no commission, cashout, wallet or journal row changed
    # What the migrations build is exactly what the models expect.
    assert schema_snapshot(engine) == as_models_define_it

    with engine.connect() as c:
        assert c.execute(text("select count(*) from payment_settings")).scalar() == 0   # defaults until an admin saves
        assert c.execute(text("select count(*) from payment_credentials")).scalar() == 0  # nothing imported from the env
        assert c.execute(text("select count(*) from payout_wallet_changes")).scalar() == 0
        granted = c.execute(text(
            "select p.name, (select count(*) from role_permissions rp where rp.permission_id = p.id) "
            "from permissions p where p.name in ('manage_payment_settings', 'process_cashouts') order by 1")).fetchall()
        assert [tuple(r) for r in granted] == [("manage_payment_settings", 0), ("process_cashouts", 0)]
        assert c.execute(text("select count(*) from users where cashout_method is not null "
                              "or payout_wallet_verified_at is not null")).scalar() == 0

    # Existing wallets are kept but are NOT payable until the member confirms them again.
    with Session() as db:
        sponsor = db.get(User, ids["sponsor"])
        state = cs.wallet_state(sponsor, NOW)
        assert sponsor.usdt_wallet_address == "0x" + "1" * 40 and state.payable is False
        assert cs.wallet_state(db.get(User, ids["no_wallet"]), NOW).payable is False
        balance = get_commission_balance(db, sponsor.id)
        assert (balance.available, balance.reserved, balance.paid_lifetime) == (Decimal("5.00"), 0, Decimal("3.00"))
        assert engine_service.candidate_user_ids(db, 50) == []       # nobody has chosen Crypto Cashout


def test_the_migrations_can_be_applied_twice_and_taken_back_on_a_disposable_database(pg):
    engine, Session = pg
    with Session() as db:
        production_like_rows(db)
    target = schema_snapshot(engine)
    back_to_production_revision(engine)
    rows = money_fingerprint(engine)
    for _ in range(2):                                             # a re-run after a partial deployment
        migrate(engine, DUAL_CASHOUT, "upgrade")
        migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
        migrate(engine, BENEFICIARY_FEE, "upgrade")
        migrate(engine, FEE_SAFETY, "upgrade")
        assert schema_snapshot(engine) == target and money_fingerprint(engine) == rows
    with engine.connect() as c:
        assert c.execute(text("select count(*) from permissions where name in "
                              "('manage_payment_settings', 'process_cashouts')")).scalar() == 2   # not duplicated
    back_to_production_revision(engine)                            # downgrade: only what was added is removed
    assert money_fingerprint(engine) == rows
    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    assert schema_snapshot(engine) == target and money_fingerprint(engine) == rows


def test_a_downgrade_keeps_a_permission_that_a_role_already_holds(pg):
    engine, _Session = pg
    back_to_production_revision(engine)
    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")                 # creates the two permissions
    migrate(engine, FEE_SAFETY, "upgrade")
    with engine.begin() as c:
        c.execute(text("insert into roles (name, is_system, created_at, updated_at) "
                       "values ('finance', false, now(), now())"))
        c.execute(text("insert into role_permissions (role_id, permission_id) select r.id, p.id from roles r, "
                       "permissions p where r.name = 'finance' and p.name = 'process_cashouts'"))
    back_to_production_revision(engine)
    with engine.connect() as c:
        names = [r[0] for r in c.execute(text("select name from permissions where name in "
                                              "('manage_payment_settings', 'process_cashouts')")).fetchall()]
    assert names == ["process_cashouts"]


@pytest.mark.parametrize("violation, message", [
    ("two_open_cashouts", "more than one open cashout"),
    ("duplicate_reference", "duplicate payout_reference"),
])
def test_the_upgrade_stops_without_changing_anything_when_existing_rows_would_break_a_constraint(pg, violation,
                                                                                                message):
    engine, Session = pg
    with Session() as db:
        ids = production_like_rows(db)
    back_to_production_revision(engine)
    with engine.begin() as c:
        if violation == "two_open_cashouts":
            for ref in ("intent:open-1", "intent:open-2"):
                c.execute(text("insert into affiliate_cashout_requests (user_id, gross_amount, fee, net_amount, "
                               "status, payout_reference, requested_at, created_at, updated_at) values "
                               "(:u, 1, 0, 1, 'processing', :r, now(), now(), now())"),
                          {"u": ids["sponsor"], "r": ref})
        else:
            c.execute(text("insert into affiliate_cashout_requests (user_id, gross_amount, fee, net_amount, status, "
                           "payout_reference, requested_at, created_at, updated_at) values "
                           "(:u, 1, 0, 1, 'failed', 'intent:legacy-2', now(), now(), now())"), {"u": ids["sponsor"]})
    rows, schema = money_fingerprint(engine), schema_snapshot(engine)
    with pytest.raises(DBAPIError) as error:
        migrate(engine, DUAL_CASHOUT, "upgrade")
    assert message in str(error.value)
    # Transactional DDL: nothing half-applied, and no row was deleted to make the data fit.
    assert money_fingerprint(engine) == rows and schema_snapshot(engine) == schema


PRE_MIGRATION_CHECKS = {
    "members with more than one open cashout":
        "select user_id, count(*) from affiliate_cashout_requests "
        "where status in ('requested', 'processing', 'unknown') group by user_id having count(*) > 1",
    "duplicate payout references":
        "select payout_reference, count(*) from affiliate_cashout_requests "
        "where payout_reference is not null group by payout_reference having count(*) > 1",
}


def test_the_pre_migration_checks_find_exactly_the_rows_the_upgrade_would_refuse(pg):
    """The SQL in the deployment plan: no rows = the upgrade will not stop."""
    engine, Session = pg
    with Session() as db:
        ids = production_like_rows(db)
    back_to_production_revision(engine)
    with engine.connect() as c:
        assert all(c.execute(text(sql)).fetchall() == [] for sql in PRE_MIGRATION_CHECKS.values())
    with engine.begin() as c:
        for ref in ("intent:open-1", "intent:open-2", "intent:legacy-2"):
            c.execute(text("insert into affiliate_cashout_requests (user_id, gross_amount, fee, net_amount, status, "
                           "payout_reference, requested_at, created_at, updated_at) values "
                           "(:u, 1, 0, 1, :s, :r, now(), now(), now())"),
                      {"u": ids["sponsor"], "r": ref, "s": "failed" if ref.endswith("legacy-2") else "unknown"})
    with engine.connect() as c:
        found = {name: [tuple(r) for r in c.execute(text(sql)).fetchall()]
                 for name, sql in PRE_MIGRATION_CHECKS.items()}
    assert found == {"members with more than one open cashout": [(ids["sponsor"], 2)],
                     "duplicate payout references": [("intent:legacy-2", 2)]}


# ---------------------------------------------------------------------------
# constraints
# ---------------------------------------------------------------------------

def cashout_row(user_id: int, status: str, reference: str) -> AffiliateCashoutRequest:
    return AffiliateCashoutRequest(user_id=user_id, gross_amount=Decimal("5"), fee=Decimal("0"),
                                   net_amount=Decimal("5"), status=status, payout_reference=reference,
                                   cashout_method="CRYPTO", requested_at=NOW)


def refused(Session, build) -> bool:
    with Session() as db:
        try:
            build(db)
            db.commit()
        except (IntegrityError, DBAPIError):
            db.rollback()
            return True
    return False


def test_the_database_itself_enforces_the_cashout_and_configuration_rules(pg):
    engine, Session = pg
    back_to_production_revision(engine)                            # the schema exactly as the migrations build it
    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    with Session() as db:
        first = member(db, "m1", method="CRYPTO")
        second = member(db, "m2", method="CRYPTO")
        db.add(cashout_row(first.id, "processing", "intent:a"))
        db.add(cashout_row(first.id, "completed", "intent:done-1"))
        db.add(cashout_row(first.id, "failed", "intent:failed-1"))             # closed rows are not limited
        db.add(PaymentSettings(id=1, version=1, **pc.defaults()))
        db.add(PaymentCredential(provider="nowpayments", name="PAYIN_API_KEY", ciphertext="x", set_at=NOW))
        db.add(PaymentWebhookStat(provider="nowpayments", day=NOW.date(), outcome="ACCEPTED", count=1, last_at=NOW))
        db.add(PayoutWalletVerification(user_id=first.id, address=WALLET, currency="usdtbsc", token_hash="a" * 64,
                                        requested_at=NOW, expires_at=NOW + timedelta(hours=1)))
        db.commit()
        a, b = first.id, second.id

    for status in ("requested", "processing", "unknown"):                      # one open cashout per member
        assert refused(Session, lambda db, s=status: db.add(cashout_row(a, s, f"intent:second-{s}")))
    assert refused(Session, lambda db: db.add(cashout_row(b, "processing", "intent:a")))      # one row per intent
    assert refused(Session, lambda db: db.add(cashout_row(b, "failed", "intent:done-1")))
    assert not refused(Session, lambda db: db.add(cashout_row(b, "processing", "intent:b")))  # another member: fine
    assert refused(Session, lambda db: db.execute(text("update users set cashout_method = 'BANK' where id = :i"),
                                                  {"i": a}))
    assert refused(Session, lambda db: db.add(PaymentSettings(id=2, version=1, **pc.defaults())))  # a single row
    assert refused(Session, lambda db: db.add(PaymentCredential(provider="nowpayments", name="PAYIN_API_KEY",
                                                                ciphertext="y", set_at=NOW)))
    assert refused(Session, lambda db: db.add(PaymentWebhookStat(provider="nowpayments", day=NOW.date(),
                                                                 outcome="ACCEPTED", count=1, last_at=NOW)))
    assert refused(Session, lambda db: db.add(PayoutWalletVerification(
        user_id=b, address=WALLET, currency="usdtbsc", token_hash="a" * 64, requested_at=NOW,
        expires_at=NOW + timedelta(hours=1))))                                                   # a token is used once
    for column, value in (("crypto_min_usd", 0), ("max_daily_payout_count", 0), ("network_fee_policy", "'NOBODY'"),
                          ("payout_credential_source", "'FILE'"), ("payout_interval_seconds", 5)):
        assert refused(Session, lambda db, c=column, v=value: db.execute(
            text(f"update payment_settings set {c} = {v} where id = 1")))


# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------

def slow_provider(**kwargs) -> FakeProvider:
    """A provider whose create call takes long enough for the workers to overlap."""
    provider = FakeProvider(**kwargs)
    original = provider.create_payout

    def create_payout(**call):
        time.sleep(0.3)
        return original(**call)

    provider.create_payout = create_payout
    return provider


def test_concurrent_engine_workers_pay_one_member_exactly_once(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        for amount in ("5.00", "2.50", "1.25"):
            commission(db, user, amount)
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        user_id = user.id
    provider = slow_provider()

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW)

    reports = in_threads(4, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    outcomes = [code for r in reports for code, n in r["members"].items() for _ in range(n)]
    assert outcomes.count("SUBMITTED") == 1 and len(provider.created) == 1      # one payout, however many workers
    assert provider.created[0]["amount"] == Decimal("8.75")
    with Session() as db:
        rows = db.query(AffiliateCashoutRequest).filter_by(user_id=user_id).all()
        assert [(r.status, Decimal(str(r.gross_amount))) for r in rows] == [("processing", Decimal("8.75"))]
        balance = get_commission_balance(db, user_id)
        assert (balance.available, balance.reserved) == (0, Decimal("8.75"))
        references = {c.payout_reference for c in db.query(AffiliateCommission).filter_by(user_id=user_id)}
        assert len(references) == 1 and None not in references                    # every row reserved once, together


def test_concurrent_reconciliation_posts_a_finished_payout_exactly_once(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        provider = FakeProvider()
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["members"] == {"SUBMITTED": 1}
        user_id = user.id
        cashout_id = db.query(AffiliateCashoutRequest.id).filter_by(user_id=user_id).scalar()
    provider.statuses["batch-1"] = "FINISHED"

    def reconcile(_i):
        with Session() as db:
            return engine_service.reconcile_cashout(db, cashout_id, provider, now=NOW)

    results = in_threads(4, reconcile)
    assert sorted(results) == ["COMPLETED", "SKIPPED", "SKIPPED", "SKIPPED"]
    with Session() as db:
        balance = get_commission_balance(db, user_id)
        assert (balance.paid_lifetime, balance.reserved, balance.available) == (Decimal("5.00"), 0, 0)
        assert db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{cashout_id}").count() == 1
        assert engine_service.discrepancies(db) == []


def test_a_release_and_a_completion_racing_settle_the_cashout_one_way_only(pg, engine_on):
    """An administrator records NOT SENT while the engine sees FINISHED."""
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        admin = member(db, "boss", admin=True)
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)

        def timeout(**_kwargs):
            raise TimeoutError("no answer")

        engine_service.run_cycle(db, provider=FakeProvider(create=timeout), now=NOW)
        row = db.query(AffiliateCashoutRequest).filter_by(user_id=user.id).one()
        row.provider_batch_id = "batch-9"                              # located later by its reference
        db.commit()
        user_id, cashout_id, admin_id = user.id, row.id, admin.id
    provider = FakeProvider(statuses={"batch-9": "FINISHED"})

    def work(i):
        with Session() as db:
            if i == 0:
                return engine_service.reconcile_cashout(db, cashout_id, provider, now=NOW)
            try:
                cs.resolve_uncertain(db, db.get(AffiliateCashoutRequest, cashout_id), admin=db.get(User, admin_id),
                                     outcome="NOT_SENT", now=NOW)
                return "RELEASED"
            except cs.CashoutError as exc:
                db.rollback()
                return exc.code

    results = in_threads(2, work)
    with Session() as db:
        row = db.get(AffiliateCashoutRequest, cashout_id)
        balance = get_commission_balance(db, user_id)
        journals = db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{cashout_id}").count()
        if row.status == "completed":
            assert (balance.paid_lifetime, balance.available, journals) == (Decimal("5.00"), 0, 1), results
        else:
            assert row.status == "failed", results
            assert (balance.paid_lifetime, balance.available, journals) == (0, Decimal("5.00"), 0), results
        assert balance.reserved == 0                                   # never both, never neither


def test_concurrent_usd_requests_reserve_the_balance_once(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="USD")
        commission(db, user, "150.00")
        configure(db, usd_destination_required=False)
        user_id = user.id

    def ask(i):
        with Session() as db:
            try:
                return cs.request_usd_cashout(db, db.get(User, user_id), idempotency_key=f"key-{i}", now=NOW).id
            except cs.CashoutError as exc:
                db.rollback()
                return exc.code

    results = in_threads(4, ask)
    created = [r for r in results if isinstance(r, int)]
    assert len(created) == 1 and set(results) - set(created) == {"CASHOUT_IN_PROGRESS"}, results
    with Session() as db:
        assert db.query(AffiliateCashoutRequest).filter_by(user_id=user_id).count() == 1
        balance = get_commission_balance(db, user_id)
        assert (balance.available, balance.reserved) == (0, Decimal("150.00"))


def test_the_same_usd_request_sent_twice_at_once_is_one_request(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="USD")
        commission(db, user, "150.00")
        configure(db, usd_destination_required=False)
        user_id = user.id

    def ask(_i):
        with Session() as db:
            return cs.request_usd_cashout(db, db.get(User, user_id), idempotency_key="same-key", now=NOW).id

    results = in_threads(3, ask)
    assert len(set(results)) == 1 and isinstance(results[0], int), results
    with Session() as db:
        assert db.query(AffiliateCashoutRequest).count() == 1


def test_a_crypto_payout_and_a_method_change_cannot_both_take_the_balance(pg, engine_on):
    """The member switches to USD and asks for a USD cashout while the engine is paying."""
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        commission(db, user, "150.00")
        configure(db, crypto_auto_payout_enabled=True, usd_destination_required=False)
        user_id = user.id
    provider = slow_provider()

    def work(i):
        with Session() as db:
            if i == 0:
                return engine_service.run_cycle(db, provider=provider, now=NOW)["members"]
            try:
                cs.set_cashout_method(db, db.get(User, user_id), "USD", now=NOW)
                return cs.request_usd_cashout(db, db.get(User, user_id), now=NOW).cashout_method
            except cs.CashoutError as exc:
                db.rollback()
                return exc.code

    results = in_threads(2, work)
    with Session() as db:
        rows = db.query(AffiliateCashoutRequest).filter_by(user_id=user_id).all()
        open_rows = [r for r in rows if r.status in ("requested", "processing", "unknown")]
        balance = get_commission_balance(db, user_id)
        assert len(open_rows) <= 1, results
        assert balance.available + balance.reserved == Decimal("150.00"), results        # nothing duplicated or lost
        assert balance.reserved in (0, Decimal("150.00")), results
        if len(provider.created) == 1:                                 # the payout went out: it is the open cashout
            assert [r.cashout_method for r in open_rows] == ["CRYPTO"], results


def test_two_notifications_for_the_same_payment_credit_it_once(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        sponsor = _user(db, "sponsor@t.com")
        buyer = _user(db, "buyer@t.com", sponsor=sponsor)
        deposit = _deposit(db, buyer, "annual_membership", status=DepositStatus.PENDING, tag="race")
        db.commit()
        deposit_id, order_id, payment_id = deposit.id, deposit.order_id, deposit.external_payment_id
    payload = {"payment_id": payment_id, "order_id": order_id, "payment_status": "finished", "price_amount": 50,
               "price_currency": "usd", "pay_amount": 50, "actually_paid": 50, "pay_currency": "usdtbsc"}

    def notify(_i):
        with Session() as db:                                          # the webhook's own steps
            row = db.query(Deposit).filter(Deposit.order_id == order_id).with_for_update().first()
            ok = nowpayments.finalize_deposit_from_nowpayments(db, row, dict(payload), defer_commit=True)
            db.commit()
            return ok

    assert in_threads(4, notify) == [True] * 4
    with Session() as db:
        assert db.get(Deposit, deposit_id).status == DepositStatus.VALIDATED
        assert db.query(AffiliateCommission).count() == 1
        amounts = db.query(func.sum(AffiliateCommission.commission_amount)).scalar()
        journals = db.query(JournalEntry).count()
    with Session() as db:                                              # a later duplicate changes nothing either
        row = db.query(Deposit).filter(Deposit.order_id == order_id).with_for_update().first()
        nowpayments.finalize_deposit_from_nowpayments(db, row, dict(payload), defer_commit=True)
        db.commit()
        assert db.query(func.sum(AffiliateCommission.commission_amount)).scalar() == amounts
        assert db.query(JournalEntry).count() == journals


def test_concurrent_callbacks_are_all_counted_in_one_row(pg):
    _engine, Session = pg

    def count(_i):
        with Session() as db:
            pc.record_webhook(db, "ACCEPTED", now=NOW)
            db.commit()

    in_threads(8, count)
    with Session() as db:
        rows = db.query(PaymentWebhookStat).all()
        assert [(r.outcome, r.count) for r in rows] == [("ACCEPTED", 8)]


def test_two_administrators_saving_settings_at_once_never_lose_or_duplicate_the_row(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        admin = member(db, "boss", admin=True)
        admin_id = admin.id
    from tests.unit.test_dual_cashout import PASSWORD

    def save(i):
        with Session() as db:
            try:
                pc.update_settings(db, db.get(User, admin_id), {"crypto_min_usd": str(2 + i)}, password=PASSWORD,
                                   now=NOW)
                return "saved"
            except pc.PaymentConfigError as exc:
                db.rollback()
                return exc.code

    results = in_threads(4, save)
    assert "saved" in results, results
    with Session() as db:
        row = db.query(PaymentSettings).one()                          # exactly one row
        assert row.version == results.count("saved") and Decimal(row.crypto_min_usd) in {Decimal(2 + i) for i in range(4)}
        assert db.query(Permission).filter(Permission.name == pc.PERMISSION_MANAGE).count() == 1


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

def test_a_payout_that_cannot_be_posted_leaves_no_partial_trace(pg, engine_on):
    """FINISHED at the provider, but the ledger account cannot be found: nothing
    is half-written (no PAID commission without its journal entry)."""
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        provider = FakeProvider()
        engine_service.run_cycle(db, provider=provider, now=NOW)
        user_id = user.id
        cashout_id = db.query(AffiliateCashoutRequest.id).filter_by(user_id=user_id).scalar()
    with engine.begin() as c:
        c.execute(text("update chart_of_accounts set account_code = '1001-missing' where account_code = '1001'"))
    provider.statuses["batch-1"] = "FINISHED"
    with Session() as db:
        assert engine_service.reconcile_cashout(db, cashout_id, provider, now=NOW) == "PAID_BUT_NOT_POSTED"
    with Session() as db:
        row = db.get(AffiliateCashoutRequest, cashout_id)
        balance = get_commission_balance(db, user_id)
        assert row.status == "processing" and (balance.reserved, balance.paid_lifetime) == (Decimal("5.00"), 0)
        assert db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{cashout_id}").count() == 0
    with engine.begin() as c:
        c.execute(text("update chart_of_accounts set account_code = '1001' where account_code = '1001-missing'"))
    with Session() as db:                                              # once the ledger is fixed it posts, once
        assert engine_service.reconcile_cashout(db, cashout_id, provider, now=NOW) == "COMPLETED"
        assert get_commission_balance(db, user_id).paid_lifetime == Decimal("5.00")


# ---------------------------------------------------------------------------
# Phase 3.1
# ---------------------------------------------------------------------------

def test_concurrent_workers_never_post_a_payout_to_an_inactive_account(pg, engine_on):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        provider = FakeProvider()
        engine_service.run_cycle(db, provider=provider, now=NOW)
        user_id = user.id
        cashout_id = db.query(AffiliateCashoutRequest.id).filter_by(user_id=user_id).scalar()
    with engine.begin() as c:
        c.execute(text("update chart_of_accounts set is_active = false where account_code = '1001'"))
    provider.statuses["batch-1"] = "FINISHED"

    def reconcile(_i):
        with Session() as db:
            return engine_service.reconcile_cashout(db, cashout_id, provider, now=NOW)

    assert in_threads(4, reconcile) == ["PAID_BUT_NOT_POSTED"] * 4
    with Session() as db:
        balance = get_commission_balance(db, user_id)
        assert db.get(AffiliateCashoutRequest, cashout_id).status == "processing"
        assert (balance.reserved, balance.paid_lifetime) == (Decimal("5.00"), 0)
        assert db.query(JournalEntry).count() == 0
    with engine.begin() as c:
        c.execute(text("update chart_of_accounts set is_active = true where account_code = '1001'"))
    assert sorted(in_threads(4, reconcile)) == ["COMPLETED", "SKIPPED", "SKIPPED", "SKIPPED"]
    with Session() as db:
        assert db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{cashout_id}").count() == 1


# PROPOSAL, not part of the migration chain: a unique rule for the provider's
# payment id. Only NOWPayments writes deposits.external_payment_id today and
# the table has no provider column, so the rule is on the id alone; NULL and
# the empty string (legacy rows that never reached a provider) are left out.
# A second provider would need a provider column and (provider, id) instead.
PROPOSED_UNIQUE_PAYMENT_ID = (
    "CREATE UNIQUE INDEX uq_deposits_external_payment_id ON deposits (external_payment_id) "
    "WHERE external_payment_id IS NOT NULL AND external_payment_id <> ''")
DUPLICATE_PAYMENT_IDS = (
    "select external_payment_id, count(*), array_agg(id order by id) from deposits "
    "where external_payment_id is not null and external_payment_id <> '' "
    "group by external_payment_id having count(*) > 1")


def test_the_proposed_unique_payment_id_rule_on_representative_legacy_rows(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        buyer = _user(db, "buyer@t.com")
        for tag, payment_id in (("stub1", None), ("stub2", None), ("empty1", ""), ("empty2", ""),
                                ("np1", "5745459419"), ("np2", "6249365965"), ("old", "0xlegacy-reference"),
                                ("dup1", "4000000001"), ("dup2", "4000000001")):
            _deposit(db, buyer, "kyc", status=DepositStatus.PENDING, tag=tag, external_payment_id=payment_id)
        db.commit()
        buyer_id = buyer.id
    with engine.connect() as c:
        duplicates = [(r[0], r[1]) for r in c.execute(text(DUPLICATE_PAYMENT_IDS)).fetchall()]
    assert duplicates == [("4000000001", 2)]                       # NULL and '' are not duplicates of each other
    with pytest.raises(DBAPIError):                                # it cannot be created over a duplicate
        with engine.begin() as c:
            c.execute(text(PROPOSED_UNIQUE_PAYMENT_ID))
    with engine.connect() as c:
        assert c.execute(text("select count(*) from deposits")).scalar() == 9      # and nothing was removed
    with engine.begin() as c:                                      # (the remediation is a human decision, simulated here)
        c.execute(text("update deposits set external_payment_id = null where id = "
                       "(select max(id) from deposits where external_payment_id = '4000000001')"))
        c.execute(text(PROPOSED_UNIQUE_PAYMENT_ID))

    def add(payment_id):
        def build(db):
            _deposit(db, db.get(User, buyer_id), "kyc", status=DepositStatus.PENDING,
                     tag=uuid.uuid4().hex[:8], external_payment_id=payment_id)
        return build

    assert refused(Session, add("5745459419"))                     # a second deposit for the same provider payment
    assert not refused(Session, add(None)) and not refused(Session, add(""))       # still any number of these
    assert not refused(Session, add("7000000001"))

    def race(_i):                                                  # two workers attaching the same new id
        return refused(Session, add("8000000001"))

    assert sorted(in_threads(4, race)) == [False, True, True, True]


# ---------------------------------------------------------------------------
# Network fee account (migration b6c7d8e9f0a1) and its posting
# ---------------------------------------------------------------------------

def account_5005(engine):
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select a.account_code, a.account_name, a.account_type::text, p.account_code, a.is_active "
            "from chart_of_accounts a left join chart_of_accounts p on p.id = a.parent_id "
            "where a.account_code = '5005'")).fetchall()]


def test_the_fee_account_migration_adds_one_expense_account_and_nothing_else(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        production_like_rows(db)
    rows = money_fingerprint(engine)
    with engine.connect() as c:
        accounts_before = c.execute(text("select count(*) from chart_of_accounts")).scalar()
    assert account_5005(engine) == []
    for _ in range(2):                                             # applying it twice adds it once
        migrate(engine, FEE_ACCOUNT, "upgrade")
        assert account_5005(engine) == [("5005", "Crypto payout network fees (paid by MyHigh5)", "EXPENSE", "5000",
                                         True)]
    with engine.connect() as c:
        assert c.execute(text("select count(*) from chart_of_accounts")).scalar() == accounts_before + 1
    assert money_fingerprint(engine) == rows
    migrate(engine, FEE_ACCOUNT, "downgrade")                      # never used: removed
    assert account_5005(engine) == []
    migrate(engine, FEE_ACCOUNT, "upgrade")
    with Session() as db:                                          # used once: a downgrade keeps it and its history
        from app.services.accounting_service import accounting_service

        accounting_service.create_journal_entry(db, description="synthetic fee", commit=True, lines=[
            {"account_code": "5005", "debit": 1, "credit": 0}, {"account_code": "1001", "debit": 0, "credit": 1}])
    migrate(engine, FEE_ACCOUNT, "downgrade")
    assert len(account_5005(engine)) == 1


def test_the_fee_account_migration_does_nothing_without_the_expense_parent(pg):
    engine, _Session = pg
    migrate(engine, FEE_ACCOUNT, "upgrade")                        # empty chart of accounts
    assert account_5005(engine) == []


def test_an_existing_account_5005_is_left_exactly_as_it_is(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        db.add(ChartOfAccounts(account_code="5005", account_name="Already here", account_type=AccountType.EXPENSE,
                               is_active=False))
        db.commit()
    migrate(engine, FEE_ACCOUNT, "upgrade")
    assert account_5005(engine) == [("5005", "Already here", "EXPENSE", None, False)]


def test_concurrent_administrators_record_one_network_fee(pg, engine_on):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
    migrate(engine, FEE_ACCOUNT, "upgrade")
    with Session() as db:
        user = member(db, "m1", method="CRYPTO")
        admin = member(db, "boss", admin=True)
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        provider = FakeProvider(statuses={})
        engine_service.run_cycle(db, provider=provider, now=NOW)
        # A payout written while MyHigh5 bore the fee (retired policy): the only kind 5005 is for.
        db.query(AffiliateCashoutRequest).update({"network_fee_policy": "COMPANY_PAYS"})
        db.commit()
        provider.statuses["batch-1"] = "FINISHED"
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["reconciled"] == {"COMPLETED": 1}
        cashout_id = db.query(AffiliateCashoutRequest.id).filter_by(user_id=user.id).scalar()
        admin_id = admin.id

    def record(i):
        with Session() as db:
            try:
                cs.record_network_fee_by_admin(db, db.get(AffiliateCashoutRequest, cashout_id),
                                               admin=db.get(User, admin_id), amount="0.25",
                                               reference=f"statement {i}", now=NOW)
                return "POSTED"
            except cs.CashoutError as exc:
                return exc.code

    results = in_threads(4, record)
    assert sorted(results) == ["FEE_ALREADY_RECORDED"] * 3 + ["POSTED"], results
    with Session() as db:
        entries = db.query(JournalEntry).filter(
            JournalEntry.description == cs.network_fee_description(cashout_id)).all()
        assert len(entries) == 1 and Decimal(str(entries[0].total_debit)) == Decimal("0.25")
        assert cs.network_fee_state(db, db.get(AffiliateCashoutRequest, cashout_id))["status"] == "POSTED"
    with engine.connect() as c:
        totals = c.execute(text("select coalesce(sum(debit_amount), 0), coalesce(sum(credit_amount), 0) "
                                "from journal_lines")).one()
    assert totals[0] == totals[1] == Decimal("5.25")               # the payout and its fee, balanced


def test_the_seed_never_renames_an_existing_account_5005_and_still_updates_the_others(pg):
    from app.scripts.init_coa import init_chart_of_accounts

    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        db.add(ChartOfAccounts(account_code="5005", account_name="Already here", description="Someone else's account",
                               account_type=AccountType.EXPENSE, is_active=False))
        db.add(ChartOfAccounts(account_code="5002", account_name="Old name", account_type=AccountType.EXPENSE))
        db.commit()
        init_chart_of_accounts(db)
    with engine.connect() as c:
        rows = dict((code, (name, description)) for code, name, description in c.execute(text(
            "select account_code, account_name, description from chart_of_accounts "
            "where account_code in ('5005', '5002')")).fetchall())
    assert rows["5005"] == ("Already here", "Someone else's account")
    assert account_5005(engine) == [("5005", "Already here", "EXPENSE", None, False)]
    assert rows["5002"][0] == "KYC Provider Expense"               # every other account behaves as before


def test_the_seed_creates_account_5005_when_it_is_missing(pg):
    from app.scripts.init_coa import init_chart_of_accounts

    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        init_chart_of_accounts(db)
        init_chart_of_accounts(db)
    assert account_5005(engine) == [("5005", "Crypto payout network fees (paid by MyHigh5)", "EXPENSE", "5000", True)]


# ---------------------------------------------------------------------------
# Beneficiary-paid network fee (migration c7d8e9f0a1b2)
# ---------------------------------------------------------------------------

def test_the_beneficiary_fee_migration_is_additive_and_every_default_fails_closed(pg):
    engine, Session = pg
    with Session() as db:
        ids = production_like_rows(db)
    migrate(engine, FEE_SAFETY, "downgrade")
    migrate(engine, BENEFICIARY_FEE, "downgrade")                  # the schema as deployed before it
    with engine.begin() as c:
        # A settings row saved before the migration, under the retired policy.
        columns = [r[0] for r in c.execute(text(
            "select column_name from information_schema.columns where table_name = 'payment_settings' "
            "and column_name not in ('id', 'created_at', 'updated_at', 'version', 'updated_by') "
            "and column_name not like 'last_connection%'")).fetchall()]
        values = {**pc.defaults(), "network_fee_policy": "COMPANY_PAYS", "crypto_auto_payout_enabled": True}
        c.execute(text(f"insert into payment_settings (id, version, created_at, updated_at, {', '.join(columns)}) "
                       f"values (1, 3, now(), now(), {', '.join(':' + name for name in columns)})"),
                  {name: values[name] for name in columns})
    rows = money_fingerprint(engine)
    journal = account_5005(engine)

    for _ in range(2):                                             # a re-run after a partial deployment
        migrate(engine, BENEFICIARY_FEE, "upgrade")
        migrate(engine, FEE_SAFETY, "upgrade")
    assert money_fingerprint(engine) == rows and account_5005(engine) == journal
    with engine.connect() as c:
        row = c.execute(text(
            "select network_fee_policy, provider_fee_mode, member_fee_cap_percent, member_fee_cap_usd, "
            "min_net_payout_usd, fee_terms_version, fee_consent_valid_days, fee_terms_approved, version "
            "from payment_settings")).one()
        # The stored policy is NOT rewritten; the new settings arrive closed.
        assert tuple(row) == ("COMPANY_PAYS", "UNVERIFIED", Decimal("0"), Decimal("0"), Decimal("0.01"), 1, 0,
                              False, 3)
        assert c.execute(text("select count(*) from cashout_fee_consents")).scalar() == 0
        assert c.execute(text(
            "select count(*) from affiliate_cashout_requests where amount_sent is not null or fee_flag is not null "
            "or network_fee_estimate is not null or network_fee_actual is not null or net_received is not null "
            "or fee_cap is not null or fee_consent_id is not null or provider_fee_mode is not null")).scalar() == 0
    migrate(engine, FEE_SAFETY, "upgrade")                         # the models need it to read the row
    with Session() as db:
        config = pc.load(db)
        assert config.fee_gate() == "FEE_POLICY_NOT_BENEFICIARY_PAID" and config.crypto_auto_payout_enabled is True
        assert get_commission_balance(db, ids["sponsor"]).available == Decimal("5.00")
    migrate(engine, FEE_SAFETY, "downgrade")

    migrate(engine, BENEFICIARY_FEE, "downgrade")                  # nothing recorded yet: it can be taken back
    assert money_fingerprint(engine) == rows
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    with Session() as db:
        accept_terms(db, db.get(User, ids["sponsor"]))
    migrate(engine, FEE_SAFETY, "downgrade")                       # nothing of its own recorded: it can go
    with pytest.raises(DBAPIError) as error:                       # an acceptance exists: never destroyed
        migrate(engine, BENEFICIARY_FEE, "downgrade")
    assert "would destroy" in str(error.value)
    with engine.connect() as c:
        assert c.execute(text("select count(*) from cashout_fee_consents")).scalar() == 1


def test_the_database_itself_enforces_the_fee_rules(pg):
    engine, Session = pg
    back_to_production_revision(engine)                            # the schema exactly as the migrations build it
    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    with Session() as db:
        user = member(db, "m1", method="CRYPTO")                   # holds one acceptance
        db.add(PaymentSettings(id=1, version=1, **pc.defaults()))
        db.add(cashout_row(user.id, "completed", "intent:done-1"))
        db.commit()
        uid = user.id

    def consent(**values):
        return CashoutFeeConsent(**{"user_id": uid, "terms_version": 1, "cap_percent": Decimal("10"),
                                    "cap_usd": Decimal("1"), "accepted_at": NOW, **values})

    assert refused(Session, lambda db: db.add(consent()))                                  # one in force per member
    assert not refused(Session, lambda db: db.add(consent(revoked_at=NOW, revoked_reason="REPLACED")))
    assert refused(Session, lambda db: db.add(consent(revoked_at=NOW, cap_percent=Decimal("0"),
                                                      cap_usd=Decimal("0"))))              # an acceptance of no limit
    assert refused(Session, lambda db: db.add(consent(revoked_at=NOW, cap_percent=Decimal("101"))))
    assert refused(Session, lambda db: db.add(consent(revoked_at=NOW, terms_version=0)))
    for column, value in (("provider_fee_mode", "'ANYTHING'"), ("member_fee_cap_percent", "-1"),
                          ("member_fee_cap_percent", "100.5"), ("member_fee_cap_usd", "-0.01"),
                          ("min_net_payout_usd", "0"), ("fee_terms_version", "0"), ("fee_consent_valid_days", "-1")):
        assert refused(Session, lambda db, c=column, v=value: db.execute(
            text(f"update payment_settings set {c} = {v} where id = 1"))), column
    for column, value in (("amount_sent", "0"), ("network_fee_estimate", "-0.01"), ("network_fee_actual", "-0.01"),
                          ("net_received", "0"), ("fee_cap", "-1"), ("fee_consent_id", "999999")):
        assert refused(Session, lambda db, c=column, v=value: db.execute(
            text(f"update affiliate_cashout_requests set {c} = {v}"))), column
    with engine.connect() as c:                                    # eight decimal places survive the round trip
        c.execute(text("update affiliate_cashout_requests set network_fee_actual = 0.12345678, "
                       "net_received = 4.87654322"))
        assert tuple(c.execute(text("select network_fee_actual, net_received from affiliate_cashout_requests")).one()) \
            == (Decimal("0.12345678"), Decimal("4.87654322"))


def test_concurrent_acceptances_leave_one_in_force(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO", terms=False)
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        user_id = user.id

    def accept(_i):
        with Session() as db:
            return cs.accept_fee_terms(db, db.get(User, user_id), version=1, cap_percent="10", cap_usd="1",
                                       now=NOW).id

    results = in_threads(6, accept)
    assert not any(isinstance(r, Exception) for r in results), results
    with Session() as db:
        rows = db.query(CashoutFeeConsent).filter_by(user_id=user_id).all()
        assert len(rows) == 1 and set(results) == {rows[0].id}     # the same acceptance, once


def test_an_acceptance_and_a_withdrawal_racing_a_payout_never_pay_without_consent(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        user_id = user.id
    provider = slow_provider()

    def work(i):
        with Session() as db:
            if i == 0:
                return engine_service.run_cycle(db, provider=provider, now=NOW)["members"]
            return cs.withdraw_fee_consent(db, db.get(User, user_id), now=NOW)

    results = in_threads(2, work)
    assert not any(isinstance(r, Exception) for r in results), results
    with Session() as db:
        row = db.query(AffiliateCashoutRequest).filter_by(user_id=user_id).first()
        consent = db.query(CashoutFeeConsent).filter_by(user_id=user_id).one()
        assert consent.revoked_at is not None
        # Either the payout was sent while the acceptance was in force (and carries it),
        # or it was never sent. Never sent without one.
        if provider.created:
            assert row.status == "processing" and row.fee_consent_id == consent.id
        else:
            assert row is None or row.status == "cancelled"
            assert get_commission_balance(db, user_id).available == Decimal("5.00")


def test_concurrent_administrators_record_one_actual_fee_and_suspend_once(pg, engine_on):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        admin = member(db, "boss", admin=True)
        commission(db, user, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        provider = FakeProvider(statuses={})
        engine_service.run_cycle(db, provider=provider, now=NOW)
        assert provider.created[0]["amount"] == Decimal("5.00")   # the whole amount: the fee is taken once, by the provider
        provider.statuses["batch-1"] = "FINISHED"
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["reconciled"] == {"COMPLETED": 1}
        cashout_id = db.query(AffiliateCashoutRequest.id).filter_by(user_id=user.id).scalar()
        admin_id = admin.id

    def record(i):
        with Session() as db:
            try:
                cs.record_member_fee_by_admin(db, db.get(AffiliateCashoutRequest, cashout_id),
                                              admin=db.get(User, admin_id), amount="0.75",
                                              charged_to="PAYOUT_AMOUNT", reference=f"statement {i}", now=NOW,
                                              evidence="PROVIDER_STATEMENT", verified=True, received="4.25")
                return "RECORDED"
            except cs.CashoutError as exc:
                return exc.code

    results = in_threads(4, record)
    assert sorted(results) == ["FEE_ALREADY_RECORDED"] * 3 + ["RECORDED"], results
    with Session() as db:
        row = db.get(AffiliateCashoutRequest, cashout_id)
        assert (row.network_fee_actual, row.net_received, row.fee_flag) == (
            Decimal("0.75"), Decimal("4.25"), "FEE_CAP_EXCEEDED")   # above the member's 0.50 limit
        config = pc.load(db)
        assert (config.provider_fee_mode, config.fee_terms_approved) == ("UNVERIFIED", False)
        assert (config.suspended_reason, config.suspended_cashout_id) == ("FEE_CAP_EXCEEDED", cashout_id)
        assert row.fee_reconciliation == "ADMIN_VERIFIED"
        assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 1
        assert db.query(PaymentSettings).count() == 1
        assert db.query(JournalEntry).count() == 1                 # the payout's own entry; nothing for the fee
    with engine.connect() as c:
        totals = c.execute(text("select coalesce(sum(debit_amount), 0), coalesce(sum(credit_amount), 0) "
                                "from journal_lines")).one()
        assert totals[0] == totals[1] == Decimal("5.00")
        assert c.execute(text("select count(*) from journal_lines l join chart_of_accounts a on a.id = l.account_id "
                              "where a.account_code = '5005'")).scalar() == 0


def test_concurrent_workers_send_the_whole_amount_once_and_stop_after_a_mismatch(pg, engine_on, monkeypatch):
    monkeypatch.setenv("NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES", "sender")
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
        commission(db, first, "5.00")
        configure(db, crypto_auto_payout_enabled=True, **FEE_RULES)
        first_id, second_id = first.id, second.id

    class Reporting(FakeProvider):
        details: dict = {}

        def payout_details(self, batch_id):
            return dict(self.details.get(batch_id, {"status": "PROCESSING"}))

    provider = Reporting(fee="0.30")
    with Session() as db:
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["members"] == {"SUBMITTED": 1}
        commission(db, db.get(User, second_id), "7.00")
    # The provider charged its fee to the MyHigh5 balance: not the configured behaviour.
    provider.details["batch-1"] = {"status": "FINISHED", "address": WALLET, "fee": "0.30", "fee_paid_by": "sender"}

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW + timedelta(days=2))

    reports = in_threads(4, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    with Session() as db:
        row = db.query(AffiliateCashoutRequest).filter_by(user_id=first_id).one()
        assert (row.amount_sent, row.fee_flag, row.net_received) == (Decimal("5.00"), "PROVIDER_FEE_MODE_MISMATCH",
                                                                     Decimal("5.00"))
        assert pc.load(db).provider_fee_mode == "UNVERIFIED"
        assert pc.load(db).suspended_reason == "PROVIDER_FEE_MODE_MISMATCH"
        assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 1
        assert db.query(JournalEntry).count() == 1
    # A worker that had already read the configuration may have reserved for the second
    # member; whatever it did, a payout created after the suspension was seen is refused.
    with Session() as db:
        assert engine_service.run_cycle(db, provider=provider, now=NOW + timedelta(days=3))["stopped"] == \
            "PAYOUTS_SUSPENDED"
        sent = len(provider.created)
        assert engine_service.run_cycle(db, provider=provider, now=NOW + timedelta(days=4)).get("members") == {}
        assert len(provider.created) == sent


# ---------------------------------------------------------------------------
# Recording gate, safety margin, suspension (migration d8e9f0a1b2c3)
# ---------------------------------------------------------------------------

def safety_state(engine) -> tuple:
    with engine.connect() as c:
        return (tuple(c.execute(text(
            "select fee_estimate_margin_percent, max_unreconciled_payouts, payout_suspended_reason, "
            "payout_suspended_at, payout_suspended_cashout_id from payment_settings order by id")).fetchall()),
                c.execute(text(
                    "select count(*) from affiliate_cashout_requests where fee_estimate_adjusted is not null "
                    "or fee_margin_percent is not null or fee_reconciliation is not null "
                    "or fee_evidence is not null")).scalar())


def test_the_safety_migration_is_additive_fails_closed_and_keeps_every_row(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        user = member(db, "m1", method="CRYPTO")
        db.add(PaymentSettings(id=1, version=4, **{**pc.defaults(), **FEE_RULES}))        # approved rules, saved earlier
        # A beneficiary-paid payout completed BEFORE the gate existed: figures, no verification.
        db.add(AffiliateCashoutRequest(
            user_id=user.id, gross_amount=Decimal("5.00"), fee=Decimal("0"), net_amount=Decimal("4.98"),
            status="completed", payout_reference="intent:old-1;provider:5000000001", cashout_method="CRYPTO",
            payout_currency="usdtbsc", network_fee_policy="MEMBER_PAYS", amount_sent=Decimal("5"),
            network_fee_estimate=Decimal("0.02"), network_fee_actual=Decimal("0.0234"),
            net_received=Decimal("4.9766"), requested_at=NOW, processed_at=NOW))
        db.commit()
    migrate(engine, FEE_SAFETY, "downgrade")                       # the schema as deployed before it
    rows = money_fingerprint(engine)
    with engine.connect() as c:
        before = c.execute(text("select version, provider_fee_mode, fee_terms_approved, member_fee_cap_usd, "
                                "crypto_auto_payout_enabled from payment_settings")).one()
        figures = c.execute(text("select network_fee_actual, net_received, amount_sent "
                                 "from affiliate_cashout_requests")).one()

    for _ in range(2):                                             # a re-run after a partial deployment
        migrate(engine, FEE_SAFETY, "upgrade")
    assert money_fingerprint(engine) == rows
    with engine.connect() as c:
        assert c.execute(text("select version, provider_fee_mode, fee_terms_approved, member_fee_cap_usd, "
                              "crypto_auto_payout_enabled from payment_settings")).one() == before
        assert c.execute(text("select network_fee_actual, net_received, amount_sent "
                              "from affiliate_cashout_requests")).one() == figures
    # No margin, one payout at a time, not suspended; nothing written on the payout.
    assert safety_state(engine) == (((None, 0, None, None, None),), 0)
    with Session() as db:
        config = pc.load(db)
        # The rules that were approved before are NOT in force until a margin is set and approved again.
        assert config.fee_terms_approved is True and config.fee_gate() == "FEE_SAFETY_MARGIN_NOT_SET"
        # The earlier payout counts as NOT reconciled: an unknown state is never taken as verified.
        assert cs.reconciliation_exposure(db) == {"in_flight": 0, "completed_unreconciled": 1, "total": 1}
        assert cs.recording_gate(db, config) == "FEE_RECONCILIATION_PENDING"

    migrate(engine, FEE_SAFETY, "downgrade")                       # nothing recorded yet: it can be taken back
    assert money_fingerprint(engine) == rows
    migrate(engine, FEE_SAFETY, "upgrade")
    with Session() as db:
        pc.suspend_payouts(db, reason="FEE_CAP_EXCEEDED", cashout_id=1, now=NOW)
        db.commit()
    with pytest.raises(DBAPIError) as error:                       # a suspension is recorded: never destroyed
        migrate(engine, FEE_SAFETY, "downgrade")
    assert "would destroy" in str(error.value)
    assert safety_state(engine)[0][0][2] == "FEE_CAP_EXCEEDED"


def test_the_database_itself_enforces_the_safety_rules(pg):
    engine, Session = pg
    back_to_production_revision(engine)                            # the schema exactly as the migrations build it
    migrate(engine, DUAL_CASHOUT, "upgrade")
    migrate(engine, PAYMENT_CONFIGURATION, "upgrade")
    migrate(engine, BENEFICIARY_FEE, "upgrade")
    migrate(engine, FEE_SAFETY, "upgrade")
    with Session() as db:
        user = member(db, "m1", method="CRYPTO")
        db.add(PaymentSettings(id=1, version=1, **pc.defaults()))
        db.add(cashout_row(user.id, "completed", "intent:done-1"))
        db.commit()
    for column, value in (("fee_estimate_margin_percent", "-0.001"), ("fee_estimate_margin_percent", "500.001"),
                          ("max_unreconciled_payouts", "-1"), ("max_unreconciled_payouts", "1001"),
                          ("payout_suspended_reason", "'BECAUSE'"),
                          # a fee that is only missing is the gate's business, never a stored suspension
                          ("payout_suspended_reason", "'FEE_NOT_RECONCILED'")):
        assert refused(Session, lambda db, c=column, v=value: db.execute(
            text(f"update payment_settings set {c} = {v} where id = 1"))), (column, value)
    for column, value in (("fee_estimate_margin_percent", "null"), ("fee_estimate_margin_percent", "12.345"),
                          ("payout_suspended_reason", "'FEE_CAP_EXCEEDED'"), ("payout_suspended_reason", "null")):
        assert not refused(Session, lambda db, c=column, v=value: db.execute(
            text(f"update payment_settings set {c} = {v} where id = 1"))), (column, value)
    for statement in ("fee_estimate_adjusted = -1", "fee_margin_percent = -1", "fee_reconciliation = 'TRUST_ME'",
                      # a verified reconciliation without the figures or the evidence it rests on
                      "fee_reconciliation = 'ADMIN_VERIFIED'",
                      "fee_reconciliation = 'PROVIDER_VERIFIED', network_fee_actual = 0.02, net_received = 4.98",
                      "fee_reconciliation = 'ADMIN_VERIFIED', network_fee_actual = 0.02, fee_evidence = 'OTHER'"):
        assert refused(Session, lambda db, st=statement: db.execute(
            text(f"update affiliate_cashout_requests set {st}"))), statement
    assert not refused(Session, lambda db: db.execute(text(
        "update affiliate_cashout_requests set fee_reconciliation = 'ADMIN_VERIFIED', network_fee_actual = 0.02, "
        "net_received = 4.98, fee_evidence = 'PROVIDER_STATEMENT', fee_estimate_adjusted = 0.03333334, "
        "fee_margin_percent = 66.667")))
    with engine.connect() as c:                                    # the precision survives the round trip
        assert tuple(c.execute(text("select fee_estimate_adjusted, fee_margin_percent "
                                    "from affiliate_cashout_requests")).one()) == (Decimal("0.03333334"),
                                                                                  Decimal("66.667"))


def test_concurrent_workers_cannot_both_pass_the_recording_gate_for_different_members(pg, engine_on):
    """The gate counts payouts across ALL members, so the member lock alone
    would let every worker pass at once. With the default of zero, one payout
    leaves, however many workers and members there are."""
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        ids = []
        for index in range(6):
            user = member(db, f"m{index}", method="CRYPTO")
            commission(db, user, "5.00")
            ids.append(user.id)
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": 0})
    provider = slow_provider()
    facts = {"balance": Decimal("1000"), "minimum": Decimal("0.10")}

    def pay(i):                                                    # one worker per member, released together
        with Session() as db:
            return engine_service.process_member(db, ids[i], provider, facts=dict(facts), now=NOW)

    results = in_threads(6, pay)
    assert not any(isinstance(r, Exception) for r in results), results
    assert sorted(results) == ["FEE_RECONCILIATION_PENDING"] * 5 + ["SUBMITTED"], results
    assert len(provider.created) == 1 and provider.created[0]["amount"] == Decimal("5.00")

    def cycle(_i):                                                 # whole cycles, and again: no retry gets through
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW)

    for _ in range(2):
        reports = in_threads(4, cycle)
        assert not any(isinstance(r, Exception) for r in reports), reports
    assert len(provider.created) == 1
    with Session() as db:
        rows = db.query(AffiliateCashoutRequest).all()
        assert [r.status for r in rows] == ["processing"]
        assert cs.reconciliation_exposure(db) == {"in_flight": 1, "completed_unreconciled": 0, "total": 1}
        assert sum(get_commission_balance(db, i).available for i in ids) == Decimal("25.00")


@pytest.mark.parametrize("limit", [1, 2])
def test_concurrent_workers_send_exactly_as_many_as_the_gate_allows(pg, engine_on, limit):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        ids = []
        for index in range(6):
            user = member(db, f"m{index}", method="CRYPTO")
            commission(db, user, "5.00")
            ids.append(user.id)
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": limit})
    provider = slow_provider()

    def pay(i):
        with Session() as db:
            return engine_service.process_member(db, ids[i], provider, now=NOW,
                                                 facts={"balance": Decimal("1000"), "minimum": Decimal("0.10")})

    results = in_threads(6, pay)
    assert not any(isinstance(r, Exception) for r in results), results
    assert results.count("SUBMITTED") == limit + 1 and len(provider.created) == limit + 1
    assert results.count("FEE_RECONCILIATION_PENDING") == 6 - (limit + 1)


def test_concurrent_reconciliation_of_an_unverified_payout_holds_every_worker_back_without_a_suspension(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
        commission(db, first, "5.00")
        commission(db, second, "7.00")
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": 0})
        provider = FakeProvider()
        report = engine_service.run_cycle(db, provider=provider, now=NOW)
        assert report["members"] == {"SUBMITTED": 1, "FEE_RECONCILIATION_PENDING": 1}
        second_id = second.id
    provider.statuses["batch-1"] = "FINISHED"                      # finished; nothing known about its fee

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW + timedelta(days=2))

    for _ in range(2):                                             # and again: no retry gets through
        reports = in_threads(5, cycle)
        assert not any(isinstance(r, Exception) for r in reports), reports
        assert all(r.get("stopped") == "FEE_RECONCILIATION_PENDING" and r["members"] == {} for r in reports), reports
    assert len(provider.created) == 1                              # the second member was never sent
    with Session() as db:
        config = pc.load(db)
        # Held back, not suspended: nothing was inconsistent and nothing was un-confirmed.
        assert (config.suspended_reason, config.provider_fee_mode, config.fee_terms_approved) == (
            None, "DEDUCTED_BY_PROVIDER", True)
        assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 0
        assert cs.reconciliation_exposure(db) == {"in_flight": 0, "completed_unreconciled": 1, "total": 1}
        assert db.query(AffiliateCashoutRequest).filter_by(user_id=second_id).count() == 0
        assert db.query(JournalEntry).count() == 1 and db.query(PaymentSettings).count() == 1


def test_a_verified_reconciliation_releases_the_gate_for_exactly_one_of_the_concurrent_workers(pg, engine_on):
    """An administrator verifies the fee. No reactivation is involved: the gate
    opens by itself, and it opens for one payout, however many workers race."""
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        ids = []
        for index in range(4):
            user = member(db, f"m{index}", method="CRYPTO")
            commission(db, user, "5.00")
            ids.append(user.id)
        admin = member(db, "boss", admin=True)
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": 0})
        provider = slow_provider(statuses={})
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["members"].get("SUBMITTED") == 1
        provider.statuses["batch-1"] = "FINISHED"
        assert engine_service.run_cycle(db, provider=provider, now=NOW)["stopped"] == "FEE_RECONCILIATION_PENDING"
        cashout = db.query(AffiliateCashoutRequest).one()
        cs.record_member_fee_by_admin(db, cashout, admin=admin, amount="0.02", charged_to="PAYOUT_AMOUNT",
                                      reference="payout batch-1", evidence="BLOCKCHAIN_EXPLORER", verified=True,
                                      received="4.98", now=NOW)
        assert cs.recording_gate(db, pc.load(db)) is None and pc.load(db).suspended_reason is None
    later = NOW + timedelta(days=2)

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=later)

    reports = in_threads(5, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    assert sum(r["members"].get("SUBMITTED", 0) for r in reports) == 1, reports
    assert len(provider.created) == 2 and provider.created[1]["amount"] == Decimal("5.00")
    with Session() as db:
        assert sorted(r.status for r in db.query(AffiliateCashoutRequest).all()) == ["completed", "processing"]
        assert cs.reconciliation_exposure(db) == {"in_flight": 1, "completed_unreconciled": 0, "total": 1}
        assert db.query(PaymentConfigAudit).filter(
            PaymentConfigAudit.action.in_(["PAYOUTS_SUSPENDED", "PAYOUTS_REACTIVATED"])).count() == 0


def test_concurrent_administrators_reactivate_once_and_a_racing_worker_never_pays_before_it(pg, engine_on):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
        admin = member(db, "boss", admin=True)
        commission(db, first, "5.00")
        commission(db, second, "7.00")
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": 0})
        provider = FakeProvider(statuses={})
        engine_service.run_cycle(db, provider=provider, now=NOW)
        provider.statuses["batch-1"] = "FINISHED"
        engine_service.run_cycle(db, provider=provider, now=NOW)
        cashout = db.query(AffiliateCashoutRequest).filter_by(user_id=first.id).one()
        cs.record_member_fee_by_admin(db, cashout, admin=admin, amount="0.02", charged_to="PAYOUT_AMOUNT",
                                      reference="payout batch-1", evidence="PROVIDER_STATEMENT", verified=True,
                                      received="4.98", now=NOW)
        assert pc.load(db).suspended_reason is None                # reconciled; nothing was ever suspended
        # A confirmed inconsistency on that payout, reviewed and the settings put back by an administrator.
        pc.suspend_payouts(db, reason="PROVIDER_AMOUNT_MISMATCH", cashout_id=cashout.id, now=NOW)
        db.commit()
        configure(db, crypto_auto_payout_enabled=True, **{**FEE_RULES, "max_unreconciled_payouts": 0})
        assert pc.load(db).suspended_reason == "PROVIDER_AMOUNT_MISMATCH" and pc.load(db).fee_rules_gate() is None
        admin_id, second_id = admin.id, second.id
    later = NOW + timedelta(days=2)

    def work(i):
        with Session() as db:
            if i < 3:
                try:
                    cs.reactivate_payouts(db, db.get(User, admin_id), password=PASSWORD,
                                          confirmation=pc.CONFIRM_REACTIVATION,
                                          note="Checked payout batch-1 against the provider statement.")
                    return "REACTIVATED"
                except pc.PaymentConfigError as exc:
                    return exc.code
            return engine_service.run_cycle(db, provider=provider, now=later).get("stopped", "RAN")

    results = in_threads(6, work)
    assert not any(isinstance(r, Exception) for r in results), results
    assert sorted(results[:3]) == ["NOT_SUSPENDED", "NOT_SUSPENDED", "REACTIVATED"], results
    assert set(results[3:]) <= {"PAYOUTS_SUSPENDED", "RAN", "FEE_RECONCILIATION_PENDING"}, results
    with Session() as db:
        assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_REACTIVATED").count() == 1
        assert pc.load(db).suspended_reason is None
        engine_service.run_cycle(db, provider=provider, now=later)
        rows = db.query(AffiliateCashoutRequest).filter_by(user_id=second_id).all()
        assert [r.status for r in rows] == ["processing"]          # paid once, after the reactivation
    assert len(provider.created) == 2 and provider.created[1]["amount"] == Decimal("7.00")
