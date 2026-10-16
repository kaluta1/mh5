"""Phase 1 financial controls on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. SQLite has no row locks, no
triggers of this kind and no transactional DDL, so these can only be proven
here:

* migrations f9b1c3d5e7a9 -> a8c0e2f4b6d8 -> b7d9f1a3c5e7 against the schema
  production runs today (e6f7a8b9c0d1), with production-like rows (a sponsor
  cycle, historical commissions): additive, repeatable, reversible, and they
  stop without changing anything on data that violates a guard;
* the sponsor-cycle trigger, including two changes racing each other;
* two administrators deciding the same manual payment, or the same held
  commission, at the same moment.

Everything is SYNTHETIC.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.financial_controls import CommissionPayoutReview, ManualPaymentConfirmation
from app.models.payment import Deposit, DepositStatus
from app.models.user import User
from app.services import admin_security as sec
from app.services import commission_payout_hold as hold
from app.services import manual_payment_service as mps
from app.services import payment_config as pc
from tests.integration.test_payments_postgres import _settings, in_threads, migrate, pg, seed_ledger  # noqa: F401
from tests.unit.test_admin_security_hardening import PASSWORD, person

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MANUAL_PAYMENTS = "f9b1c3d5e7a9_manual_payment_confirmations.py"
PAYOUT_REVIEWS = "a8c0e2f4b6d8_commission_payout_reviews.py"
GUARDS = "b7d9f1a3c5e7_referral_and_commission_guards.py"
CHAIN = (MANUAL_PAYMENTS, PAYOUT_REVIEWS, GUARDS)
CHECKS = ("ck_users_sponsor_not_self", "ck_affiliate_commissions_amount_positive",
          "ck_affiliate_commissions_level_range", "ck_affiliate_commissions_new_model_level_one")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_production_schema(engine) -> None:
    """The model schema, taken back to e6f7a8b9c0d1 as production has it: no new
    tables, no guards, and uq_affiliate_commissions_source_user missing."""
    with engine.begin() as c:
        c.execute(text("DROP TABLE manual_payment_confirmations"))
        c.execute(text("DROP TABLE commission_payout_reviews"))
        c.execute(text("ALTER TABLE users DROP CONSTRAINT ck_users_sponsor_not_self"))
        for name in CHECKS[1:]:
            c.execute(text(f"ALTER TABLE affiliate_commissions DROP CONSTRAINT {name}"))
        c.execute(text("DROP INDEX uq_affiliate_commissions_source_user"))


def upgrade_all(engine) -> None:
    for filename in CHAIN:
        migrate(engine, filename, "upgrade")


def downgrade_all(engine) -> None:
    for filename in reversed(CHAIN):
        migrate(engine, filename, "downgrade")


def user(db, name, sponsor_id=None) -> int:
    row = User(email=f"{name}@example.com", username=name, hashed_password="x", is_active=True, is_deleted=False,
               sponsor_id=sponsor_id, personal_referral_code=name.upper(), date_of_birth=datetime(1990, 1, 1))
    db.add(row)
    db.commit()
    return row.id


def set_sponsor(engine, member_id, sponsor_id) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE users SET sponsor_id = :s WHERE id = :m"), {"s": sponsor_id, "m": member_id})


def legacy_commission(db, beneficiary_id, payer_id, *, level=1, amount="1.00") -> int:
    row = AffiliateCommission(user_id=beneficiary_id, source_user_id=payer_id,
                              commission_type=CommissionType.KYC_PAYMENT, level=level, base_amount=Decimal("10.00"),
                              commission_amount=Decimal(amount), status=CommissionStatus.APPROVED,
                              transaction_date=datetime(2026, 7, 6))
    db.add(row)
    db.commit()
    return row.id


def production_like_rows(engine, Session) -> dict:
    """A historical sponsor loop (a -> b -> c -> a, as 9 -> 71 -> 11 -> 9), a member
    under it, and historical multi-level commissions."""
    with Session() as db:
        a = user(db, "loop_a")
        b = user(db, "loop_b", a)
        c = user(db, "loop_c", b)
        under = user(db, "under", c)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET sponsor_id = :c WHERE id = :a"), {"a": a, "c": c})
    with Session() as db:
        commissions = [legacy_commission(db, c, under, level=1, amount="1.00"),
                       legacy_commission(db, b, under, level=2, amount="0.50"),
                       legacy_commission(db, a, under, level=3, amount="0.10")]
    return {"a": a, "b": b, "c": c, "under": under, "commissions": commissions}


def data_fingerprint(engine) -> tuple:
    with engine.connect() as c:
        return (tuple(c.execute(text("select id, sponsor_id from users order by id")).fetchall()),
                tuple(c.execute(text("select id, user_id, level, commission_amount, status from "
                                     "affiliate_commissions order by id")).fetchall()))


def guards(engine) -> dict:
    with engine.connect() as c:
        return {
            "tables": sorted(r[0] for r in c.execute(text(
                "select table_name from information_schema.tables where table_schema = 'public' and table_name in "
                "('manual_payment_confirmations', 'commission_payout_reviews')"))),
            "checks": sorted(r[0] for r in c.execute(text(
                "select conname from pg_constraint where conname = any(:n)"), {"n": list(CHECKS)})),
            "indexes": sorted(r[0] for r in c.execute(text(
                "select indexname from pg_indexes where indexname in ('uq_affiliate_commissions_deposit_user', "
                "'uq_affiliate_commissions_source_user')"))),
            "trigger": [r[0] for r in c.execute(text(
                "select tgname from pg_trigger where tgname = 'trg_users_sponsor_no_cycle'"))],
            "function": [r[0] for r in c.execute(text(
                "select proname from pg_proc where proname = 'mh5_users_sponsor_no_cycle'"))],
        }


UPGRADED = {
    "tables": ["commission_payout_reviews", "manual_payment_confirmations"],
    "checks": sorted(CHECKS),
    "indexes": ["uq_affiliate_commissions_deposit_user", "uq_affiliate_commissions_source_user"],
    "trigger": ["trg_users_sponsor_no_cycle"],
    "function": ["mh5_users_sponsor_no_cycle"],
}
DOWNGRADED = {"tables": [], "checks": [], "trigger": [], "function": [],
              "indexes": ["uq_affiliate_commissions_deposit_user", "uq_affiliate_commissions_source_user"]}


def is_cycle_refusal(exc) -> bool:
    return isinstance(exc, DBAPIError) and "sponsor cycle" in str(exc.orig)


# ---------------------------------------------------------------------------
# migrations
# ---------------------------------------------------------------------------

def test_the_chain_is_additive_repeatable_and_reversible_on_production_like_data(pg):
    engine, Session = pg
    to_production_schema(engine)
    production_like_rows(engine, Session)
    before = data_fingerprint(engine)
    assert guards(engine)["indexes"] == ["uq_affiliate_commissions_deposit_user"]      # as production

    upgrade_all(engine)
    assert guards(engine) == UPGRADED
    assert data_fingerprint(engine) == before                                          # no row changed
    with engine.connect() as c:
        assert c.execute(text("select count(*) from manual_payment_confirmations")).scalar() == 0
        assert c.execute(text("select count(*) from commission_payout_reviews")).scalar() == 0

    upgrade_all(engine)                                                                # re-run: no-op
    assert guards(engine) == UPGRADED and data_fingerprint(engine) == before

    downgrade_all(engine)
    assert guards(engine) == DOWNGRADED and data_fingerprint(engine) == before
    downgrade_all(engine)                                                              # re-run: no-op
    upgrade_all(engine)
    assert guards(engine) == UPGRADED and data_fingerprint(engine) == before


def test_downgrade_never_drops_a_decision_record(pg):
    engine, Session = pg
    to_production_schema(engine)
    rows = production_like_rows(engine, Session)
    upgrade_all(engine)
    with Session() as db:
        admin = person(db, "reviewer", admin=True)
        db.add(CommissionPayoutReview(commission_id=rows["commissions"][0], decision="CANCEL",
                                      reason="Synthetic decision", decided_by=admin.id))
        db.commit()
    migrate(engine, GUARDS, "downgrade")
    with pytest.raises(DBAPIError, match="holds decisions"):
        migrate(engine, PAYOUT_REVIEWS, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select count(*) from commission_payout_reviews")).scalar() == 1


@pytest.mark.parametrize("violation, message", [
    ("UPDATE users SET sponsor_id = id WHERE username = 'under'", "ck_users_sponsor_not_self"),
    ("UPDATE affiliate_commissions SET commission_amount = 0 WHERE level = 3", "ck_affiliate_commissions_amount_positive"),
    ("UPDATE affiliate_commissions SET level = 11 WHERE level = 3", "ck_affiliate_commissions_level_range"),
    ("UPDATE affiliate_commissions SET business_model_version = 'NEW_V2' WHERE level = 2",
     "ck_affiliate_commissions_new_model_level_one"),
    ("UPDATE affiliate_commissions SET source_type = 'DEPOSIT', source_id = 1, user_id = "
     "(SELECT user_id FROM affiliate_commissions WHERE level = 1) WHERE level IN (1, 2)",
     "duplicate \\(source_type, source_id, user_id\\)"),
])
def test_the_guard_migration_stops_on_violating_data_and_changes_nothing(pg, violation, message):
    engine, Session = pg
    to_production_schema(engine)
    production_like_rows(engine, Session)
    migrate(engine, MANUAL_PAYMENTS, "upgrade")
    migrate(engine, PAYOUT_REVIEWS, "upgrade")
    with engine.begin() as c:
        c.execute(text(violation))
    before, schema = data_fingerprint(engine), guards(engine)
    with pytest.raises(DBAPIError, match=message):
        migrate(engine, GUARDS, "upgrade")
    assert data_fingerprint(engine) == before and guards(engine) == schema           # nothing created


# ---------------------------------------------------------------------------
# sponsor-cycle trigger
# ---------------------------------------------------------------------------

def test_the_trigger_refuses_a_cycle_and_ignores_a_historical_loop_elsewhere(pg):
    engine, Session = pg
    to_production_schema(engine)
    rows = production_like_rows(engine, Session)
    upgrade_all(engine)
    with Session() as db:
        x = user(db, "x")
        y = user(db, "y", x)
        z = user(db, "z", y)

    with pytest.raises(DBAPIError, match="sponsor cycle"):
        set_sponsor(engine, x, z)                                     # x -> z -> y -> x
    with pytest.raises(DBAPIError, match="sponsor cycle|ck_users_sponsor_not_self"):   # the trigger runs first
        set_sponsor(engine, x, x)
    set_sponsor(engine, x, rows["under"])                             # ancestors loop, but not through x
    with Session() as db:                                             # a registration under the loop
        user(db, "newcomer", rows["a"])
    with pytest.raises(DBAPIError, match="sponsor cycle"):
        set_sponsor(engine, rows["under"], z)                         # z -> y -> x -> under
    set_sponsor(engine, rows["a"], None)                              # the correction: break the loop
    with pytest.raises(DBAPIError, match="sponsor cycle"):
        set_sponsor(engine, rows["a"], rows["c"])                     # and it cannot be put back
    with engine.connect() as c:
        assert c.execute(text("select sponsor_id from users where id = :a"), {"a": rows["a"]}).scalar() is None


def test_two_sponsor_changes_racing_cannot_close_a_cycle_together(pg):
    engine, Session = pg
    upgrade_all(engine)                                               # no-op on the model schema, adds the trigger
    with Session() as db:
        ids = [user(db, "p"), user(db, "q")]

    for _round in range(5):
        set_sponsor(engine, ids[0], None)
        set_sponsor(engine, ids[1], None)

        def change(i):
            with engine.begin() as c:
                c.execute(text("UPDATE users SET sponsor_id = :s WHERE id = :m"), {"s": ids[1 - i], "m": ids[i]})
                c.execute(text("select pg_sleep(0.2)"))               # hold the transaction open
            return "changed"

        results = in_threads(2, change)
        assert results.count("changed") == 1, results
        assert sum(is_cycle_refusal(r) for r in results) == 1, results
        with engine.connect() as c:
            sponsors = dict(c.execute(text("select id, sponsor_id from users where id = any(:i)"), {"i": ids}).all())
        assert sorted(v is None for v in sponsors.values()) == [False, True]


# ---------------------------------------------------------------------------
# two administrators at the same moment
# ---------------------------------------------------------------------------

def cashiers(Session, *names) -> list[int]:
    with Session() as db:
        return [person(db, n, admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,)).id for n in names]


def recorded_request(Session, maker_id) -> tuple[int, int, int]:
    with Session() as db:
        seed_ledger(db)
        sponsor = user(db, "sponsor")
        member = user(db, "member", sponsor)
        out = mps.record(db, db.get(User, maker_id), member, product_code="annual_membership",
                         reason="Bank ref 2026-10-16/91", password=PASSWORD)
        return out.request.id, member, sponsor


def outcome(fn):
    try:
        return fn()
    except mps.ManualPaymentError as exc:
        return exc.code


def test_two_checkers_confirming_the_same_payment_at_once_credit_it_once(pg):
    engine, Session = pg
    maker, *checkers = cashiers(Session, "maker", "checker_1", "checker_2")
    request_id, member, sponsor = recorded_request(Session, maker)

    def confirm(i):
        with Session() as db:
            return outcome(lambda: mps.confirm(db, db.get(User, checkers[i]), request_id, password=PASSWORD,
                                               evidence_reference=f"TX-0xrace{i}").status)

    assert sorted(in_threads(2, confirm)) == ["ALREADY_DECIDED", "granted"]
    with Session() as db:
        request = db.get(ManualPaymentConfirmation, request_id)
        deposit = db.get(Deposit, request.deposit_id)
        commissions = db.query(AffiliateCommission).all()
        assert (request.status, deposit.status, request.decided_by in checkers) == \
            ("CONFIRMED", DepositStatus.VALIDATED, True)
        assert [(c.user_id, c.commission_amount) for c in commissions] == [(sponsor, Decimal("10.00"))]
        assert db.query(JournalEntry).filter(JournalEntry.source_id == deposit.id).count() >= 1
        entries = db.query(JournalEntry).count()
    # Nothing is posted a second time by a late repeat.
    with Session() as db:
        assert outcome(lambda: mps.confirm(db, db.get(User, checkers[0]), request_id, password=PASSWORD,
                                           evidence_reference="TX-0xrace9")) == "ALREADY_DECIDED"
        assert (db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) == (entries, 1)


@pytest.mark.parametrize("attempt", range(3))
def test_a_confirmation_and_a_cancellation_at_once_leave_one_consistent_outcome(pg, attempt):
    engine, Session = pg
    maker, checker = cashiers(Session, "maker", "checker")
    request_id, _member, _sponsor = recorded_request(Session, maker)

    def act(i):
        with Session() as db:
            if i == 0:
                return outcome(lambda: mps.confirm(db, db.get(User, checker), request_id, password=PASSWORD,
                                                   evidence_reference="TX-0xboth").status)
            return outcome(lambda: mps.cancel(db, db.get(User, maker), request_id, password=PASSWORD,
                                              reason="Withdrawn by the maker").status)

    results = in_threads(2, act)
    assert sorted(results) in (["ALREADY_DECIDED", "granted"], ["ALREADY_DECIDED", "cancelled"]), results
    with Session() as db:
        request = db.get(ManualPaymentConfirmation, request_id)
        deposit = db.get(Deposit, request.deposit_id)
        credited = db.query(AffiliateCommission).filter(AffiliateCommission.deposit_id == deposit.id).count()
        if "granted" in results:
            assert (request.status, deposit.status, credited) == ("CONFIRMED", DepositStatus.VALIDATED, 1)
        else:
            assert (request.status, deposit.status, credited) == ("CANCELLED", DepositStatus.FAILED, 0)
            assert db.query(JournalEntry).count() == 0


def test_two_processors_reviewing_the_same_held_commission_at_once_record_one_decision(pg):
    engine, Session = pg
    with Session() as db:
        beneficiary = user(db, "beneficiary")
        payer = user(db, "payer", beneficiary)
        commission_id = legacy_commission(db, beneficiary, payer)
        admins = [person(db, f"proc_{i}", admin=True, permissions=(pc.PERMISSION_PROCESS,)).id for i in range(2)]

    def review(i):
        with Session() as db:
            try:
                return hold.review(db, db.get(User, admins[i]), commission_id, decision=("RELEASE", "CANCEL")[i],
                                   reason="Synthetic concurrent decision", password=PASSWORD).decision
            except hold.CommissionReviewError as exc:
                return exc.code

    results = in_threads(2, review)
    assert sorted(results) in (["ALREADY_DECIDED", "RELEASE"], ["ALREADY_DECIDED", "CANCEL"]), results
    with Session() as db:
        decisions = db.query(CommissionPayoutReview).all()
        assert [d.decision for d in decisions] == [r for r in results if r != "ALREADY_DECIDED"]
        row = db.get(AffiliateCommission, commission_id)
        assert (row.status, row.commission_amount) == (CommissionStatus.APPROVED, Decimal("1.00"))   # untouched


# ---------------------------------------------------------------------------
# the hold, on PostgreSQL
# ---------------------------------------------------------------------------

def test_null_and_legacy_stamped_commissions_are_both_held_until_released(pg):
    from app.services import cashout_service as cs
    from app.services.financial_balances import get_commission_balance

    engine, Session = pg
    with Session() as db:
        beneficiary = user(db, "holder")
        payer = user(db, "holder_payer", beneficiary)
        unstamped = legacy_commission(db, beneficiary, payer, amount="1.00")
        stamped = legacy_commission(db, beneficiary, payer, level=2, amount="0.10")
        db.get(AffiliateCommission, stamped).business_model_version = "LEGACY_V1"
        current = AffiliateCommission(user_id=beneficiary, source_user_id=payer, level=1,
                                      commission_type=CommissionType.KYC_PAYMENT, base_amount=Decimal("50.00"),
                                      commission_amount=Decimal("10.00"), status=CommissionStatus.APPROVED,
                                      transaction_date=datetime(2026, 10, 1), business_model_version="NEW_V2")
        db.add(current)
        db.commit()
        current_id = current.id
        admin = person(db, "releaser", admin=True, permissions=(pc.PERMISSION_PROCESS,)).id

    with Session() as db:
        assert [r.id for r in cs.available_rows(db, beneficiary)] == [current_id]
        db.rollback()
        balance = get_commission_balance(db, beneficiary)
        assert (balance.available, balance.held) == (Decimal("10.00"), Decimal("1.10"))
        assert sorted(r["commission_id"] for r in hold.held_view(db)) == sorted([unstamped, stamped])
    with Session() as db:
        hold.review(db, db.get(User, admin), stamped, decision="RELEASE", reason="Synthetic release decision",
                    password=PASSWORD)
    with Session() as db:
        assert sorted(r.id for r in cs.available_rows(db, beneficiary)) == sorted([current_id, stamped])
        db.rollback()
        assert get_commission_balance(db, beneficiary).held == Decimal("1.00")


# ---------------------------------------------------------------------------
# historical accrual correction (F1): locking, re-validation, idempotency
# ---------------------------------------------------------------------------

def accrual_world(Session, *, deposits=2) -> dict:
    """Historical KYC payments whose commission journals were never posted: level 1 1.00, level 2 0.10."""
    from app.models.payment import ProductType

    with Session() as db:
        seed_ledger(db)
        top = user(db, "acc_top")
        mid = user(db, "acc_mid", top)
        kyc = db.query(ProductType).filter(ProductType.code == "kyc").one()
        out = {"deposits": [], "commissions": {}, "mid": mid, "top": top}
        for i in range(deposits):
            payer = user(db, f"acc_payer{i}", mid)
            dep = Deposit(user_id=payer, product_type_id=kyc.id, amount=Decimal("10.00"), currency="USD",
                          status=DepositStatus.VALIDATED, order_id=f"hist-{i}", business_model_version=None)
            db.add(dep)
            db.flush()
            rows = []
            for level, beneficiary, amount in ((1, mid, "1.00"), (2, top, "0.10")):
                c = AffiliateCommission(user_id=beneficiary, source_user_id=payer, deposit_id=dep.id, level=level,
                                        commission_type=CommissionType.KYC_PAYMENT, base_amount=Decimal("10.00"),
                                        commission_amount=Decimal(amount), status=CommissionStatus.APPROVED,
                                        transaction_date=datetime(2026, 7, 6))
                db.add(c)
                db.flush()
                rows.append(c.id)
            out["deposits"].append(dep.id)
            out["commissions"][dep.id] = rows
        db.commit()
    return out


def accrual_entries(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select source_id, total_debit from journal_entries where source_type = 'LEGACY_COMMISSIONS' "
            "and posting_type = 'COMMISSION_ACCRUAL_CORRECTION' order by source_id"))]


def accrual_audits(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select user_id, (new_values->>'deposit_id')::int, new_values->>'amount' from audit_trails "
            "where action = 'LEGACY_COMMISSION_ACCRUAL_POSTED' order by id"))]


def run_accruals(Session, deposit_ids, expected, actor_id=None):
    from app.scripts import reconcile_legacy_commissions as script

    with Session() as db:
        try:
            result = script.post_missing_accruals(db, deposit_ids, expected=expected, actor_id=actor_id)
            db.commit()
            return result
        except script.CorrectionRefused as exc:
            db.rollback()
            return f"refused: {exc}"


def test_accruals_are_posted_once_audited_and_a_rerun_writes_nothing(pg):
    engine, Session = pg
    world = accrual_world(Session)
    deps = world["deposits"]
    with Session() as db:
        actor = person(db, "acc_actor", admin=True).id
    expected = {d: Decimal("1.10") for d in deps}
    first = run_accruals(Session, deps, expected, actor)
    assert [p["deposit_id"] for p in first["accruals_posted"]] == deps and first["already_posted"] == []
    assert accrual_entries(engine) == [(d, Decimal("1.10")) for d in deps]
    assert accrual_audits(engine) == [(actor, d, "1.10") for d in deps]
    for _ in range(2):
        again = run_accruals(Session, deps, expected, actor)
        assert again["accruals_posted"] == [] and again["already_posted"] == deps
    assert accrual_entries(engine) == [(d, Decimal("1.10")) for d in deps] and len(accrual_audits(engine)) == 2


def test_concurrent_accrual_runs_post_each_entry_exactly_once(pg):
    engine, Session = pg
    deps = accrual_world(Session, deposits=3)["deposits"]
    expected = {d: Decimal("1.10") for d in deps}
    results = in_threads(4, lambda i: run_accruals(Session, deps, expected))
    posted = [r["accruals_posted"] for r in results if isinstance(r, dict)]
    assert len(posted) == 4, results                                  # nobody failed: the others waited
    assert sorted(p["deposit_id"] for run in posted for p in run) == deps   # each deposit by exactly one run
    assert accrual_entries(engine) == [(d, Decimal("1.10")) for d in deps]
    assert len(accrual_audits(engine)) == 3
    with engine.connect() as c:
        assert c.execute(text("select count(*) from (select entry_id from journal_lines group by entry_id "
                              "having sum(debit_amount) <> sum(credit_amount)) x")).scalar() == 0


def test_a_commission_changed_while_the_correction_waits_is_seen_and_refused(pg):
    """Another transaction holds a commission row and marks it PAID; the correction waits for the lock,
    re-reads the row and refuses the whole batch."""
    import threading
    import time

    engine, Session = pg
    world = accrual_world(Session)
    deps = world["deposits"]
    target = world["commissions"][deps[1]][0]
    started = threading.Event()

    def work(i):
        if i == 0:
            with engine.begin() as c:
                c.execute(text("update affiliate_commissions set status = 'PAID' where id = :i"), {"i": target})
                started.set()
                time.sleep(1.0)                                       # the correction is now waiting
            return "paid"
        started.wait(5)
        return run_accruals(Session, deps, {d: Decimal("1.10") for d in deps})

    results = in_threads(2, work)
    assert results[0] == "paid"
    assert isinstance(results[1], str) and results[1].startswith("refused:") and "PAID" in results[1], results
    assert accrual_entries(engine) == [] and accrual_audits(engine) == []     # all or nothing


@pytest.mark.parametrize("case, change, message", [
    ("new_v2_deposit", "update deposits set business_model_version = 'NEW_V2' where id = :d", "NEW_V2 payment"),
    ("not_validated", "update deposits set status = 'pending' where id = :d", "not a validated"),
    ("reversed", "update deposits set admin_notes = 'Provider refund reconciled at x' where id = :d", "not a validated"),
    ("reserved", "update affiliate_commissions set payout_reference = 'intent:x' where deposit_id = :d and level = 1",
     "reserved"),
    ("wrong_payer", "update affiliate_commissions set source_user_id = (select min(id) from users) "
                    "where deposit_id = :d and level = 2", "not generated by the payer"),
    ("duplicate_level", "update affiliate_commissions set level = 1 where deposit_id = :d and level = 2",
     "two commissions"),
    ("new_v2_commission", "update affiliate_commissions set business_model_version = 'NEW_V2' "
                          "where deposit_id = :d and level = 1", "NEW_V2 commission"),
])
def test_invalid_source_data_refuses_the_whole_batch(pg, case, change, message):
    engine, Session = pg
    deps = accrual_world(Session)["deposits"]
    with engine.begin() as c:
        c.execute(text(change), {"d": deps[1]})
    result = run_accruals(Session, deps, {d: Decimal("1.10") for d in deps})
    assert isinstance(result, str) and message in result, (case, result)
    assert accrual_entries(engine) == [] and accrual_audits(engine) == []       # not even the valid deposit


@pytest.mark.parametrize("variant, message", [
    ("wrong_amount", "differs from the approved"),
    ("missing_deposit", "name exactly the deposits"),
    ("extra_deposit", "name exactly the deposits"),
])
def test_the_approved_amounts_must_match_exactly(pg, variant, message):
    engine, Session = pg
    deps = accrual_world(Session)["deposits"]
    approved = {d: Decimal("1.10") for d in deps}
    if variant == "wrong_amount":
        approved[deps[0]] = Decimal("1.20")
    elif variant == "missing_deposit":
        approved.pop(deps[1])
    else:
        approved[999999] = Decimal("1.10")
    result = run_accruals(Session, deps, approved)
    assert isinstance(result, str) and message in result, result
    assert accrual_entries(engine) == []


def test_the_command_line_refuses_an_apply_without_actor_deposits_or_approved_amounts(pg, capsys):
    from app.scripts import reconcile_legacy_commissions as script

    engine, Session = pg
    deps = accrual_world(Session)["deposits"]
    d = str(deps[0])
    cases = ((["post-missing-accruals", "--apply", "--deposit", d, "--expect", f"{d}=1.10"], "--actor-id"),
             (["post-missing-accruals", "--apply", "--actor-id", "1"], "--expect"),
             (["post-missing-accruals", "--apply", "--actor-id", "1", "--deposit", d], "--expect"),
             (["post-missing-accruals", "--deposit", d, "--expect", "x=y"], "DEPOSIT=AMOUNT"),
             (["fix-duplicate-journal", "--deposit", d, "--apply"], "--actor-id"),
             (["execute-cancellations", "--apply"], "--actor-id"))
    for argv, expected_text in cases:
        assert script.main(argv) == 2, argv
        assert expected_text in capsys.readouterr().out, argv
    assert accrual_entries(engine) == []
