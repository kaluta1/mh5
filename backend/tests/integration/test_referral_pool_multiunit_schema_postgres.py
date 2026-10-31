"""Multi-Unit Referral Pool, P2: the database foundation on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.

Schema only: no service writes these tables yet. The tests prove what the database
itself guarantees (uniqueness, references, checks, one OPEN round, one queue row per
referral, one assignment per slot), that migration a7c9e1f3b5d2 goes down and up to
exactly the model schema, and that historical seat-model rows survive it unchanged.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import referral_pool_service as retired_pool
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MIGRATION = "a7c9e1f3b5d2_referral_pool_multiunit_foundation.py"
# Later migrations whose tables reference these ones; they go down first and come back after,
# in chain order, as Alembic itself would run them.
DEPENDENTS = ("d2f4b6c8e0a1_referral_pool_manual_refund_records.py",)
NEW_TABLES = ("referral_pool_purchases", "referral_pool_units", "referral_pool_rounds",
              "referral_pool_round_slots", "referral_pool_pending")
TOUCHED = NEW_TABLES + ("referral_pool_assignments", "referral_pool_config")
NOW = datetime(2026, 10, 23, 12, 0, 0)
# Every column a historical assignment row had before the migration, hashed in id order.
HISTORY = ("select md5(string_agg(concat_ws('|', id, created_at, updated_at, referred_user_id, pool_member_user_id, "
           "membership_id, method, candidate_count, min_assignment_count, assigned_at), ',' order by id)) "
           "from referral_pool_assignments")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def schema_snapshot(engine) -> dict:
    """Columns, constraints and indexes of the touched tables (column defaults aside).
    The model base gives every table an ``ix_<table>_id`` index that hand-written
    migrations never create (true of every table here), so those are left out."""
    with engine.connect() as c:
        columns = c.execute(text(
            "select table_name, column_name, data_type, is_nullable, coalesce(character_maximum_length, 0), "
            "coalesce(numeric_precision, 0), coalesce(numeric_scale, 0) from information_schema.columns "
            "where table_schema = 'public' and table_name = any(:t) order by 1, 2"), {"t": list(TOUCHED)}).fetchall()
        constraints = c.execute(text(
            "select cl.relname, con.conname, con.contype, replace(pg_get_constraintdef(con.oid), ' NOT VALID', '') "
            "from pg_constraint con join pg_class cl on cl.oid = con.conrelid "
            "where cl.relname = any(:t) order by 1, 2"), {"t": list(TOUCHED)}).fetchall()
        indexes = c.execute(text(
            "select tablename, indexname, indexdef from pg_indexes where schemaname = 'public' "
            "and tablename = any(:t) and indexname <> 'ix_' || tablename || '_id' order by 1, 2"),
            {"t": list(TOUCHED)}).fetchall()
    return {"columns": [tuple(r) for r in columns], "constraints": [tuple(r) for r in constraints],
            "indexes": [tuple(r) for r in indexes]}


def tables(engine) -> set:
    with engine.connect() as c:
        return {r[0] for r in c.execute(text(
            "select table_name from information_schema.tables where table_schema = 'public'"))}


def nullable(engine, table: str, column: str) -> str:
    with engine.connect() as c:
        return c.execute(text("select is_nullable from information_schema.columns where table_name = :t "
                              "and column_name = :c"), {"t": table, "c": column}).scalar()


def sql(engine, statement: str, **params):
    with engine.begin() as c:
        result = c.execute(text(statement), params)
        return result.scalar() if result.returns_rows else None


def refused(engine, statement: str, **params) -> str:
    """The SQLSTATE a statement is refused with (23505 unique, 23514 check, 23503 FK, 23502 not null)."""
    with pytest.raises((IntegrityError, DBAPIError)) as info:
        sql(engine, statement, **params)
    return getattr(info.value.orig, "pgcode", None)


def seed(Session, *, members: int = 3) -> dict:
    """Synthetic members, a referred user and three $100-unit pool deposits per member."""
    with Session() as db:
        product = db.query(ProductType).filter(ProductType.code == "referral_pool_entry").first()
        if product is None:
            product = ProductType(code="referral_pool_entry", name="Referral Pool unit", price=Decimal("100.00"),
                                  currency="USD", validity_days=0, is_active=True)
            db.add(product)
            db.flush()
        tag = uuid.uuid4().hex[:6]
        users = []
        for i in range(members + 2):
            u = User(email=f"rp{tag}{i}@example.com", username=f"rp{tag}{i}", hashed_password="x", is_active=True,
                     is_deleted=False, date_of_birth=datetime(1990, 1, 1), personal_referral_code=f"RP{tag}{i}".upper(),
                     email_verified=True)
            db.add(u)
            users.append(u)
        db.flush()
        deposits = {}
        for u in users[:members]:
            deposits[u.id] = []
            for n in range(3):
                d = Deposit(user_id=u.id, product_type_id=product.id, amount=Decimal("300.00"), currency="USD",
                            order_id=f"rp-{tag}-{u.id}-{n}", status=DepositStatus.VALIDATED, validated_at=NOW)
                db.add(d)
                db.flush()
                deposits[u.id].append(d.id)
        db.commit()
        return {"members": [u.id for u in users[:members]], "referred": [u.id for u in users[members:]],
                "deposits": deposits}


def purchase(engine, user_id: int, deposit_id: int, quantity: int, *, status: str = "PAID") -> int:
    return sql(engine, "insert into referral_pool_purchases (user_id, deposit_id, quantity, unit_price, total_amount, "
                       "status, paid_at) values (:u, :d, :q, 100, :q * 100, :s, :t) returning id",
               u=user_id, d=deposit_id, q=quantity, s=status, t=NOW)


def unit(engine, user_id: int, purchase_id: int, index: int, *, status: str = "ACTIVE") -> int:
    return sql(engine, "insert into referral_pool_units (user_id, purchase_id, unit_index, source, status, amount, "
                       "activated_at) values (:u, :p, :i, 'PAID', :s, 100, :t) returning id",
               u=user_id, p=purchase_id, i=index, s=status, t=NOW if status != "PENDING" else None)


def open_round(engine, number: int, total: int) -> int:
    return sql(engine, "insert into referral_pool_rounds (round_number, status, opened_at, total_slots, snapshot_sha256) "
                       "values (:n, 'OPEN', :t, :total, :h) returning id", n=number, t=NOW, total=total, h="0" * 64)


def slot(engine, round_id: int, unit_id: int, member: int) -> int:
    return sql(engine, "insert into referral_pool_round_slots (round_id, unit_id, member_user_id) "
                       "values (:r, :u, :m) returning id", r=round_id, u=unit_id, m=member)


def round_assignment(engine, referred: int, member: int, round_id: int, slot_id: int, unit_id: int) -> int:
    return sql(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                       "candidate_count, assigned_at, round_id, slot_id, unit_id) values (:r, :m, 'QUOTA_ROUND_V1', "
                       "1, :t, :ro, :s, :u) returning id", r=referred, m=member, t=NOW, ro=round_id, s=slot_id, u=unit_id)


def down(engine) -> None:
    for dependent in reversed(DEPENDENTS):
        migrate(engine, dependent, "downgrade")
    migrate(engine, MIGRATION, "downgrade")


def up(engine) -> None:
    migrate(engine, MIGRATION, "upgrade")
    for dependent in DEPENDENTS:
        migrate(engine, dependent, "upgrade")


@pytest.fixture
def pool_pg(pg):
    """The model schema with the column defaults production has on the pre-existing pool
    tables (migration w6x7y8z9a0b1 created them with created_at/updated_at DEFAULT now();
    the model only sets them from Python)."""
    engine, Session = pg
    with engine.begin() as c:
        for table in ("referral_pool_config", "referral_pool_memberships", "referral_pool_assignments"):
            c.execute(text(f"ALTER TABLE {table} ALTER COLUMN created_at SET DEFAULT now(), "
                           f"ALTER COLUMN updated_at SET DEFAULT now()"))
    return engine, Session


@pytest.fixture
def migrated(pool_pg):
    """Taken down by the migration and brought back up by it: every test below runs on
    the schema the migration itself produces."""
    engine, Session = pool_pg
    down(engine)
    up(engine)
    return engine, Session


def unit_ids(engine, purchase_id: int) -> list:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("select id from referral_pool_units where purchase_id = :p "
                                             "order by unit_index"), {"p": purchase_id})]


# ---------------------------------------------------------------------------
# 1. Migration: down, up, again; exactly the model schema
# ---------------------------------------------------------------------------

def test_the_migration_goes_down_and_up_to_exactly_the_model_schema(pg):
    engine, _Session = pg
    model = schema_snapshot(engine)
    assert set(NEW_TABLES) <= tables(engine)

    down(engine)
    assert not set(NEW_TABLES) & tables(engine)
    assert nullable(engine, "referral_pool_assignments", "membership_id") == "NO"
    assert nullable(engine, "referral_pool_assignments", "min_assignment_count") == "NO"
    with engine.connect() as c:
        left = {r[0] for r in c.execute(text(
            "select column_name from information_schema.columns where table_name = any(:t)"),
            {"t": ["referral_pool_assignments", "referral_pool_config"]})}
    assert not left & {"round_id", "slot_id", "unit_id", "multiunit_sales_enabled", "allocation_enabled",
                       "max_units_per_member", "max_units_per_purchase", "max_active_units"}
    down(engine)                                                 # twice: a no-op

    up(engine)
    up(engine)                                                   # re-run: a no-op
    from tests.integration.test_payments_postgres import migrate

    migrate(engine, "e2a4c6e8f0b1_referral_pool_signup_trigger.py", "upgrade")   # later: SIGNED_UP (2026-10-31)
    assert schema_snapshot(engine) == model


def test_the_migration_is_the_single_head_after_the_live_one():
    from tests.integration.test_payments_postgres import load_migration

    module = load_migration(MIGRATION)
    assert (module.revision, module.down_revision) == ("a7c9e1f3b5d2", "f2b4d6e8a0c1")


def test_new_switches_are_off_and_limits_unlimited_by_default(migrated):
    engine, _Session = migrated
    row_id = sql(engine, "insert into referral_pool_config (capacity, price_product_code, reservation_minutes, "
                         "assignment_method, is_open) values (10000, 'referral_pool_entry', 90, 'FAIR_RANDOM_V1', false) "
                         "returning id")
    with engine.connect() as c:
        row = c.execute(text("select multiunit_sales_enabled, allocation_enabled, max_units_per_member, "
                             "max_units_per_purchase, max_active_units from referral_pool_config where id = :i"),
                        {"i": row_id}).one()
    assert tuple(row) == (False, False, None, None, None)
    assert refused(engine, "update referral_pool_config set max_units_per_member = 0 where id = :i", i=row_id) == "23514"


# ---------------------------------------------------------------------------
# 2. Historical rows survive; downgrade refuses to destroy round-based history
# ---------------------------------------------------------------------------

def test_historical_memberships_and_assignments_survive_the_migration_unchanged(pool_pg):
    engine, Session = pool_pg
    s = seed(Session)
    down(engine)                                                  # the live (retired) schema
    member, referred, other = s["members"][0], s["referred"][0], s["referred"][1]
    membership = sql(engine, "insert into referral_pool_memberships (user_id, status, seat_number, entitlement_source, "
                             "source_deposit_id, joined_at, assignment_eligible, assignments_count) values (:u, 'ACTIVE', "
                             "1, 'PAID', :d, :t, true, 2) returning id",
                     u=member, d=s["deposits"][member][0], t=NOW)
    sql(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, membership_id, method, "
                "candidate_count, min_assignment_count, assigned_at) values (:r, :m, :ms, 'FAIR_RANDOM_V1', 4, 0, :t)",
        r=referred, m=member, ms=membership, t=NOW)
    # A historical row that today's rules would refuse (self-assignment) is not re-judged.
    sql(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, membership_id, method, "
                "candidate_count, min_assignment_count, assigned_at) values (:m, :m, :ms, 'FAIR_RANDOM_V1', 4, 0, :t)",
        m=member, ms=membership, t=NOW)
    before = sql(engine, HISTORY)
    seats = sql(engine, "select md5(string_agg(t::text, ',' order by t.id)) from referral_pool_memberships t")

    up(engine)
    after = sql(engine, HISTORY)
    with engine.connect() as c:
        rows = c.execute(text("select round_id, slot_id, unit_id from referral_pool_assignments")).fetchall()
    assert all(tuple(r) == (None, None, None) for r in rows) and len(rows) == 2
    assert sql(engine, "select md5(string_agg(t::text, ',' order by t.id)) from referral_pool_memberships t") == seats
    assert before is not None and after == before

    # New rows: a historical-style row still needs its membership, and nobody is their own sponsor.
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                           "candidate_count, min_assignment_count, assigned_at) values (:r, :m, 'X', 1, 0, :t)",
                   r=other, m=member, t=NOW) == "23514"
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, membership_id, "
                           "method, candidate_count, min_assignment_count, assigned_at) values (:r, :r, :ms, 'X', 1, 0, :t)",
                   r=other, ms=membership, t=NOW) == "23514"


def test_downgrade_refuses_while_round_based_assignments_exist(migrated):
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    p = purchase(engine, member, s["deposits"][member][0], 1)
    u = unit(engine, member, p, 1)
    r = open_round(engine, 1, 1)
    round_assignment(engine, s["referred"][0], member, r, slot(engine, r, u, member), u)
    before = schema_snapshot(engine)
    with pytest.raises(DBAPIError, match="downgrade refused"):
        down(engine)
    assert schema_snapshot(engine) == before                                 # one transaction: nothing dropped


# ---------------------------------------------------------------------------
# 3. Purchases and units
# ---------------------------------------------------------------------------

def test_a_purchase_of_n_units_and_several_purchases_per_member(migrated):
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    first = purchase(engine, member, s["deposits"][member][0], 3)
    second = purchase(engine, member, s["deposits"][member][1], 1)          # bought again later
    for i in (1, 2, 3):
        unit(engine, member, first, i)
    unit(engine, member, second, 1)
    assert sql(engine, "select count(*) from referral_pool_units where user_id = :u", u=member) == 4
    assert len(set(unit_ids(engine, first))) == 3                           # each unit individually identifiable
    # The amount is quantity x unit price; quantity >= 1; one purchase per deposit.
    assert refused(engine, "insert into referral_pool_purchases (user_id, deposit_id, quantity, unit_price, total_amount) "
                           "values (:u, :d, 2, 100, 250)", u=member, d=s["deposits"][member][2]) == "23514"
    assert refused(engine, "insert into referral_pool_purchases (user_id, deposit_id, quantity, unit_price, total_amount) "
                           "values (:u, :d, 0, 100, 0)", u=member, d=s["deposits"][member][2]) == "23514"
    assert refused(engine, "insert into referral_pool_purchases (user_id, deposit_id, quantity, unit_price, total_amount) "
                           "values (:u, :d, 1, 100, 100)", u=member, d=s["deposits"][member][0]) == "23505"


def test_unit_rules_index_source_status_and_references(migrated):
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    p = purchase(engine, member, s["deposits"][member][0], 2)
    unit(engine, member, p, 1)
    assert refused(engine, "insert into referral_pool_units (user_id, purchase_id, unit_index, source, amount) "
                           "values (:u, :p, 1, 'PAID', 100)", u=member, p=p) == "23505"          # same unit twice
    assert refused(engine, "insert into referral_pool_units (user_id, source, amount) values (:u, 'PAID', 100)",
                   u=member) == "23514"                                                           # paid without purchase
    assert refused(engine, "insert into referral_pool_units (user_id, purchase_id, source) values (:u, :p, 'PAID')",
                   u=member, p=p) == "23514"                                                      # purchase without index
    assert refused(engine, "insert into referral_pool_units (user_id, source) values (:u, 'HISTORICAL_CONVERSION')",
                   u=member) == "23514"                                                           # conversion needs a seat
    assert refused(engine, "insert into referral_pool_units (user_id, source) values (:u, 'GIFT')", u=member) == "23514"
    assert refused(engine, "insert into referral_pool_units (user_id, purchase_id, unit_index, source, status) "
                           "values (:u, :p, 2, 'PAID', 'ACTIVE')", u=member, p=p) == "23514"      # active without date
    assert refused(engine, "insert into referral_pool_units (user_id, purchase_id, unit_index, source) "
                           "values (:u, 999999, 1, 'PAID')", u=member) == "23503"                 # unknown purchase
    admin_unit = sql(engine, "insert into referral_pool_units (user_id, source) values (:u, 'ADMIN_GRANT') returning id",
                     u=member)
    assert sql(engine, "select status from referral_pool_units where id = :i", i=admin_unit) == "PENDING"


def test_duplicate_payment_callbacks_cannot_create_a_unit_or_a_purchase_twice(migrated):
    """Eight deliveries at once of the same callback: one purchase, one row per unit."""
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    deposit = s["deposits"][member][0]

    def deliver(_i):
        try:
            with engine.begin() as c:
                pid = c.execute(text(
                    "insert into referral_pool_purchases (user_id, deposit_id, quantity, unit_price, total_amount, status) "
                    "values (:u, :d, 2, 100, 200, 'PAID') on conflict (deposit_id) do nothing returning id"),
                    {"u": member, "d": deposit}).scalar()
                pid = pid or c.execute(text("select id from referral_pool_purchases where deposit_id = :d"),
                                       {"d": deposit}).scalar()
                for i in (1, 2):
                    c.execute(text("insert into referral_pool_units (user_id, purchase_id, unit_index, source, amount) "
                                   "values (:u, :p, :i, 'PAID', 100) on conflict (purchase_id, unit_index) do nothing"),
                              {"u": member, "p": pid, "i": i})
            return "ok"
        except DBAPIError as exc:
            return f"sqlstate:{getattr(exc.orig, 'pgcode', None)}"

    results = in_threads(8, deliver)
    assert results == ["ok"] * 8, results
    assert sql(engine, "select count(*) from referral_pool_purchases where deposit_id = :d", d=deposit) == 1
    assert sql(engine, "select count(*) from referral_pool_units u join referral_pool_purchases p on p.id = u.purchase_id "
                       "where p.deposit_id = :d", d=deposit) == 2


def test_partial_refund_of_a_multi_unit_purchase_is_traceable_per_unit(migrated):
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    p = purchase(engine, member, s["deposits"][member][0], 3)
    for i in (1, 2, 3):
        unit(engine, member, p, i)
    second = unit_ids(engine, p)[1]
    assert refused(engine, "update referral_pool_units set status = 'REFUNDED' where id = :i", i=second) == "23514"
    sql(engine, "update referral_pool_units set status = 'REFUNDED', refunded_at = :t, ended_at = :t, "
                "refund_reference = 'provider-refund-synthetic-1' where id = :i", t=NOW, i=second)
    sql(engine, "update referral_pool_purchases set refunded_quantity = 1, status = 'PARTIALLY_REFUNDED' where id = :p", p=p)
    assert refused(engine, "update referral_pool_purchases set refunded_quantity = 4 where id = :p", p=p) == "23514"
    with engine.connect() as c:
        states = [tuple(r) for r in c.execute(text(
            "select unit_index, status, refund_reference from referral_pool_units where purchase_id = :p order by 1"),
            {"p": p})]
    assert states == [(1, "ACTIVE", None), (2, "REFUNDED", "provider-refund-synthetic-1"), (3, "ACTIVE", None)]
    # Each unit links to at most one revenue recognition and one commission (per-unit reversal in P5).
    with engine.connect() as c:
        uniques = {r[0] for r in c.execute(text(
            "select conname from pg_constraint where conrelid = 'referral_pool_units'::regclass and contype = 'u'"))}
    assert {"uq_referral_pool_unit_recognition", "uq_referral_pool_unit_commission"} <= uniques


def test_units_are_unlimited_per_member_and_in_total(migrated):
    """10 001 units for one member: more than the retired seat model's capacity of 10 000, and no
    table or constraint bounds them. A round of 10 001 slots is equally unconstrained."""
    engine, Session = migrated
    s = seed(Session)
    member = s["members"][0]
    p = purchase(engine, member, s["deposits"][member][0], 10001)
    sql(engine, "insert into referral_pool_units (user_id, purchase_id, unit_index, source, status, amount, activated_at) "
                "select :u, :p, g, 'PAID', 'ACTIVE', 100, :t from generate_series(1, 10001) g", u=member, p=p, t=NOW)
    r = open_round(engine, 1, 10001)
    sql(engine, "insert into referral_pool_round_slots (round_id, unit_id, member_user_id) "
                "select :r, id, user_id from referral_pool_units where purchase_id = :p", r=r, p=p)
    assert sql(engine, "select count(*) from referral_pool_units where user_id = :u and status = 'ACTIVE'", u=member) == 10001
    assert sql(engine, "select count(*) from referral_pool_round_slots where round_id = :r", r=r) == 10001


# ---------------------------------------------------------------------------
# 4. Rounds, slots, assignments
# ---------------------------------------------------------------------------

def test_at_most_one_round_is_open_even_when_created_at_once(migrated):
    engine, _Session = migrated

    def create(i):
        try:
            open_round(engine, 100 + i, 1)
            return "created"
        except IntegrityError as exc:
            return f"sqlstate:{exc.orig.pgcode}"

    results = in_threads(6, create)
    assert sorted(results) == ["created"] + ["sqlstate:23505"] * 5, results
    first = sql(engine, "select id from referral_pool_rounds where status = 'OPEN'")
    assert refused(engine, "insert into referral_pool_rounds (round_number, status, opened_at, total_slots, "
                           "snapshot_sha256) values (1, 'COMPLETED', :t, 1, :h)", t=NOW, h="0" * 64) == "23514"
    sql(engine, "update referral_pool_rounds set status = 'CLOSED', completed_at = :t, void_slots = 1 where id = :i",
        t=NOW, i=first)
    open_round(engine, 200, 2)                                               # the next round may open now
    assert refused(engine, "update referral_pool_rounds set filled_slots = 3 where round_number = 200") == "23514"
    assert refused(engine, "insert into referral_pool_rounds (round_number, status, opened_at, total_slots, "
                           "snapshot_sha256, completed_at) values (200, 'CLOSED', :t, 1, :h, :t)",
                   t=NOW, h="0" * 64) == "23505"                             # round numbers are unique


def test_slots_and_assignments_one_slot_per_unit_and_round_one_assignment_per_slot_and_referral(migrated):
    engine, Session = migrated
    s = seed(Session)
    a, b = s["members"][0], s["members"][1]
    ref1, ref2 = s["referred"]
    pa, pb = purchase(engine, a, s["deposits"][a][0], 1), purchase(engine, b, s["deposits"][b][0], 1)
    ua, ub = unit(engine, a, pa, 1), unit(engine, b, pb, 1)
    r = open_round(engine, 1, 2)
    sa, sb = slot(engine, r, ua, a), slot(engine, r, ub, b)
    assert refused(engine, "insert into referral_pool_round_slots (round_id, unit_id, member_user_id) values (:r, :u, :m)",
                   r=r, u=ua, m=a) == "23505"                                # one slot per unit and round
    assert refused(engine, "update referral_pool_round_slots set status = 'FILLED' where id = :i", i=sa) == "23514"

    round_assignment(engine, ref1, a, r, sa, ua)
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                           "candidate_count, assigned_at, round_id, slot_id, unit_id) values (:r, :m, 'Q', 1, :t, :ro, :s, :u)",
                   r=ref2, m=a, t=NOW, ro=r, s=sa, u=ua) == "23505"          # the slot is taken
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                           "candidate_count, assigned_at, round_id, slot_id, unit_id) values (:r, :m, 'Q', 1, :t, :ro, :s, :u)",
                   r=ref1, m=b, t=NOW, ro=r, s=sb, u=ub) == "23505"          # the referral is already assigned
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                           "candidate_count, assigned_at, round_id, slot_id) values (:r, :m, 'Q', 1, :t, :ro, :s)",
                   r=ref2, m=b, t=NOW, ro=r, s=sb) == "23514"                # round refs come together
    assert refused(engine, "insert into referral_pool_assignments (referred_user_id, pool_member_user_id, method, "
                           "candidate_count, assigned_at, round_id, slot_id, unit_id) values (:m, :m, 'Q', 1, :t, :ro, :s, :u)",
                   m=b, t=NOW, ro=r, s=sb, u=ub) == "23514"                  # nobody is their own sponsor

    # A refunded unit's open slot becomes VOID; the filled slot and its assignment stay as they are.
    sql(engine, "update referral_pool_round_slots set status = 'VOID', voided_at = :t, void_reason = 'UNIT_REFUNDED' "
                "where id = :i", t=NOW, i=sb)
    sql(engine, "update referral_pool_round_slots set status = 'FILLED', filled_at = :t where id = :i", t=NOW, i=sa)
    sql(engine, "update referral_pool_rounds set filled_slots = 1, void_slots = 1, status = 'COMPLETED', "
                "completed_at = :t where id = :r", t=NOW, r=r)
    assert sql(engine, "select count(*) from referral_pool_assignments where round_id = :r", r=r) == 1


def test_two_assignments_racing_for_one_slot_one_wins(migrated):
    engine, Session = migrated
    s = seed(Session, members=1)
    member = s["members"][0]
    p = purchase(engine, member, s["deposits"][member][0], 1)
    u = unit(engine, member, p, 1)
    r = open_round(engine, 1, 1)
    sl = slot(engine, r, u, member)

    def take(i):
        try:
            round_assignment(engine, s["referred"][i], member, r, sl, u)
            return "assigned"
        except IntegrityError as exc:
            return f"sqlstate:{exc.orig.pgcode}"

    assert sorted(in_threads(2, take)) == ["assigned", "sqlstate:23505"]


# ---------------------------------------------------------------------------
# 5. Pending queue
# ---------------------------------------------------------------------------

def test_one_queue_row_per_referral_even_when_enqueued_at_once(migrated):
    engine, Session = migrated
    s = seed(Session, members=1)
    referred = s["referred"][0]

    def enqueue(_i):
        with engine.begin() as c:
            return c.execute(text("insert into referral_pool_pending (referred_user_id, enqueued_at) values (:r, :t) "
                                  "on conflict (referred_user_id) do nothing returning id"),
                             {"r": referred, "t": NOW}).scalar()

    results = in_threads(8, enqueue)
    assert sum(1 for r in results if r is not None) == 1, results
    row = sql(engine, "select id from referral_pool_pending where referred_user_id = :r", r=referred)
    assert sql(engine, "select status || '/' || trigger_event from referral_pool_pending where id = :i",
               i=row) == "WAITING/KYC_APPROVED"
    assert refused(engine, "update referral_pool_pending set status = 'ASSIGNED', resolved_at = :t where id = :i",
                   t=NOW, i=row) == "23514"                                  # assigned needs its assignment
    assert refused(engine, "update referral_pool_pending set status = 'CANCELLED' where id = :i", i=row) == "23514"
    assert refused(engine, "update referral_pool_pending set attempts = -1 where id = :i", i=row) == "23514"
    sql(engine, "update referral_pool_pending set status = 'CANCELLED', resolved_at = :t, "
                "resolution_reason = 'PERSONAL_INVITATION' where id = :i", t=NOW, i=row)


# ---------------------------------------------------------------------------
# 6. The retired seat model stays retired
# ---------------------------------------------------------------------------

def test_the_retired_seat_model_still_refuses_every_write(migrated):
    _engine, Session = migrated
    with Session() as db:
        for call in (lambda: retired_pool.reserve_for_purchase(db, None),
                     lambda: retired_pool.activate_from_deposit(db, None),
                     lambda: retired_pool.pick_pool_member(db, exclude_user_id=1),
                     lambda: retired_pool.record_assignment(db, referred_user_id=1, pick=None)):
            with pytest.raises(retired_pool.ReferralPoolRetired):
                call()
