"""Multi-Unit Referral Pool, P3: the unit lifecycle on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC; no provider is called.

A verified purchase of N units creates exactly N units, once, whatever the number of payment
callbacks; units are refunded one by one or all together, idempotently per refund reference;
eligibility loss suspends units and voids their open slots without touching any assignment;
restored eligibility counts from the next round. Nothing here posts revenue or commission.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.business_model import (
    ReferralPoolAssignment, ReferralPoolConfig, ReferralPoolPurchase, ReferralPoolRound, ReferralPoolRoundSlot,
    ReferralPoolUnit, RevenueRecognition,
)
from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import referral_pool_units as units
from app.services.new_model_payments import process_new_model_deposit, reverse_new_model_deposit
from tests.integration.test_payments_postgres import in_threads, pg, seed_ledger  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))
NOW = datetime(2026, 10, 23, 12, 0, 0)


# ---------------------------------------------------------------------------
# world
# ---------------------------------------------------------------------------

@pytest.fixture
def world(pg):
    engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        cfg = db.query(ReferralPoolConfig).one()
        cfg.multiunit_sales_enabled = True                   # switched on for these tests only
        db.commit()
    return engine, Session


def member(Session, *, kyc: bool = True, born: datetime = datetime(1990, 1, 1)) -> int:
    tag = uuid.uuid4().hex[:8]
    with Session() as db:
        user = User(email=f"u{tag}@example.com", username=f"u{tag}", hashed_password="x", is_active=True,
                    is_deleted=False, date_of_birth=born, personal_referral_code=f"U{tag}".upper(),
                    email_verified=True, identity_verified=kyc, address_verified=kyc)
        db.add(user)
        db.flush()
        if kyc:
            db.add(KYCVerification(user_id=user.id, status=KYCStatus.APPROVED, provider=VerificationProvider.KALUTA,
                                   reference_id=f"ref-{tag}", attempts_count=1, submitted_at=NOW, processed_at=NOW,
                                   identity_verified=True, address_verified=True))
        db.commit()
        return user.id


def set_kyc(Session, user_id: int, approved: bool) -> None:
    with Session() as db:
        v = db.query(KYCVerification).filter(KYCVerification.user_id == user_id).one()
        v.status = KYCStatus.APPROVED if approved else KYCStatus.REJECTED
        u = db.get(User, user_id)
        u.identity_verified = approved
        db.commit()


def deposit(Session, user_id: int, quantity: int, *, amount: Decimal | None = None) -> int:
    with Session() as db:
        product = db.query(ProductType).filter(ProductType.code == units.PRODUCT_CODE).one()
        d = Deposit(user_id=user_id, product_type_id=product.id, amount=amount or Decimal("100.00") * quantity,
                    currency="USD", order_id=f"rpu-{uuid.uuid4().hex[:12]}", status=DepositStatus.PENDING,
                    business_model_version="NEW_V2")
        db.add(d)
        db.commit()
        return d.id


def buy(Session, user_id: int, quantity: int) -> tuple:
    """Checkout side (P7 will call this): a purchase recorded on a pending deposit."""
    deposit_id = deposit(Session, user_id, quantity)
    with Session() as db:
        p = units.create_purchase(db, user=db.get(User, user_id), deposit=db.get(Deposit, deposit_id), quantity=quantity)
        db.commit()
        return p.id, deposit_id


def confirm(Session, deposit_id: int) -> None:
    with Session() as db:
        d = db.get(Deposit, deposit_id)
        d.status, d.validated_at = DepositStatus.VALIDATED, NOW
        db.commit()


def activate(Session, deposit_id: int):
    """What a payment confirmation does: the deposit row locked, its cash held in 2100, then its
    units (and, since P5, their revenue and commission). An unconfirmed deposit is only asked."""
    with Session() as db:
        dep = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        if dep.status == DepositStatus.VALIDATED:
            process_new_model_deposit(db, dep)
        else:
            units.activate_purchase_for_deposit(db, dep, now=NOW)
        db.commit()
        p = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit_id).first()
        return p.status if p is not None else None


def unit_states(Session, purchase_id: int) -> list:
    with Session() as db:
        return [(u.unit_index, u.status) for u in db.query(ReferralPoolUnit)
                .filter(ReferralPoolUnit.purchase_id == purchase_id).order_by(ReferralPoolUnit.unit_index)]


def purchase_state(Session, purchase_id: int) -> tuple:
    with Session() as db:
        p = db.get(ReferralPoolPurchase, purchase_id)
        return p.status, p.refunded_quantity


def ledger_counts(Session, deposit_id: int) -> tuple:
    """(deposit journals, unit revenue recognitions, unit commissions) of this deposit."""
    with Session() as db:
        unit_ids = [u for (u,) in db.query(ReferralPoolUnit.id).join(
            ReferralPoolPurchase, ReferralPoolPurchase.id == ReferralPoolUnit.purchase_id).filter(
            ReferralPoolPurchase.deposit_id == deposit_id)] or [0]
        return (db.query(JournalEntry).filter(JournalEntry.source_type == "DEPOSIT", JournalEntry.source_id == deposit_id).count(),
                db.query(RevenueRecognition).filter(RevenueRecognition.source_type == "REFERRAL_POOL_UNIT",
                                                    RevenueRecognition.source_id.in_(unit_ids)).count(),
                db.query(AffiliateCommission).filter(AffiliateCommission.source_type == "REFERRAL_POOL_UNIT",
                                                     AffiliateCommission.source_id.in_(unit_ids)).count())


def refusal(work) -> str:
    try:
        work()
        return "ok"
    except units.UnitsError as exc:
        return exc.code


def open_round_with_slots(Session, unit_ids: list, number: int = 1) -> int:
    with Session() as db:
        r = ReferralPoolRound(round_number=number, status="OPEN", opened_at=NOW, total_slots=len(unit_ids),
                              snapshot_sha256="0" * 64)
        db.add(r)
        db.flush()
        for uid in unit_ids:
            u = db.get(ReferralPoolUnit, uid)
            db.add(ReferralPoolRoundSlot(round_id=r.id, unit_id=uid, member_user_id=u.user_id))
        db.commit()
        return r.id


def fill_slot(Session, round_id: int, unit_id: int, referred_id: int) -> int:
    """What the P4 engine will do: the slot is FILLED and the referral gets its sponsor."""
    with Session() as db:
        slot = db.query(ReferralPoolRoundSlot).filter_by(round_id=round_id, unit_id=unit_id).one()
        a = ReferralPoolAssignment(referred_user_id=referred_id, pool_member_user_id=slot.member_user_id,
                                   method="QUOTA_ROUND_V1", candidate_count=1, assigned_at=NOW,
                                   round_id=round_id, slot_id=slot.id, unit_id=unit_id)
        db.add(a)
        slot.status, slot.filled_at = "FILLED", NOW
        r = db.get(ReferralPoolRound, round_id)
        r.filled_slots += 1
        referred = db.get(User, referred_id)
        referred.sponsor_id, referred.sponsor_source = slot.member_user_id, "REFERRAL_POOL"
        db.commit()
        return a.id


def unit_id_list(Session, purchase_id: int) -> list:
    with Session() as db:
        return [u.id for u in db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase_id)
                .order_by(ReferralPoolUnit.unit_index)]


# ---------------------------------------------------------------------------
# 1. Activation
# ---------------------------------------------------------------------------

def test_one_unit_and_n_units_are_created_once_payment_is_confirmed(world):
    _engine, Session = world
    holder = member(Session)
    single, d1 = buy(Session, holder, 1)
    triple, d3 = buy(Session, holder, 3)
    assert activate(Session, d1) == units.P_PENDING and unit_states(Session, single) == []   # not paid: nothing
    confirm(Session, d1)
    confirm(Session, d3)
    assert activate(Session, d1) == units.P_PAID and activate(Session, d3) == units.P_PAID
    assert unit_states(Session, single) == [(1, "ACTIVE")]
    assert unit_states(Session, triple) == [(1, "ACTIVE"), (2, "ACTIVE"), (3, "ACTIVE")]
    with Session() as db:
        rows = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.user_id == holder).all()
        assert len(rows) == 4 and {r.amount for r in rows} == {Decimal("100.00")} and all(r.activated_at for r in rows)
    # One receipt for the deposit; since P5 each unit earns once (no sponsor here: no commission).
    assert ledger_counts(Session, d3) == (1, 3, 0)


def test_purchases_are_refused_unless_sales_are_on_and_the_buyer_is_an_eligible_adult(world):
    _engine, Session = world
    adult, no_kyc, minor = member(Session), member(Session, kyc=False), member(Session, born=datetime(2012, 5, 1))

    def attempt(user_id: int, quantity: int, amount=None):
        d = deposit(Session, user_id, quantity, amount=amount)
        with Session() as db:
            return refusal(lambda: units.create_purchase(db, user=db.get(User, user_id), deposit=db.get(Deposit, d),
                                                         quantity=quantity))

    assert attempt(no_kyc, 1) == "NOT_ELIGIBLE"
    assert attempt(minor, 1) == "NOT_ELIGIBLE"
    with Session() as db:
        assert units.member_eligibility(db, db.get(User, adult)) == units.Eligibility(True)
        assert units.member_eligibility(db, db.get(User, no_kyc)).reason == "KYC_REQUIRED"
        assert units.member_eligibility(db, db.get(User, minor)).reason == "ADULT_REQUIRED"
        gone = db.get(User, member(Session))
        gone.is_deleted = True
        assert units.member_eligibility(db, gone).reason == "ACCOUNT_UNAVAILABLE"
        db.rollback()
    assert attempt(adult, 2, amount=Decimal("150.00")) == "AMOUNT_MISMATCH"
    assert attempt(adult, 0) == "INVALID_QUANTITY"
    with Session() as db:
        db.query(ReferralPoolConfig).one().max_units_per_purchase = 5
        db.commit()
    assert attempt(adult, 6) == "PURCHASE_LIMIT" and attempt(adult, 5) == "ok"
    with Session() as db:
        db.query(ReferralPoolConfig).one().multiunit_sales_enabled = False
        db.commit()
    assert attempt(adult, 1) == "SALES_DISABLED"


def test_a_payment_that_does_not_match_its_purchase_is_held_without_units(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 2)
    with Session() as db:
        dep = db.get(Deposit, d)
        dep.amount, dep.status, dep.validated_at = Decimal("100.00"), DepositStatus.VALIDATED, NOW   # half paid
        db.commit()
    assert activate(Session, d) == units.P_HELD
    assert unit_states(Session, p) == []


def test_an_ineligible_holder_at_confirmation_gets_suspended_units_not_lost_ones(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 2)
    set_kyc(Session, holder, approved=False)            # KYC withdrawn between checkout and payment
    confirm(Session, d)
    assert activate(Session, d) == units.P_PAID
    assert unit_states(Session, p) == [(1, "SUSPENDED"), (2, "SUSPENDED")]
    set_kyc(Session, holder, approved=True)
    with Session() as db:
        assert units.sync_member_eligibility(db, holder, now=NOW) == (0, 2)
        db.commit()
    assert unit_states(Session, p) == [(1, "ACTIVE"), (2, "ACTIVE")]


def test_duplicate_payment_callbacks_at_once_create_each_unit_once(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 4)
    confirm(Session, d)
    results = in_threads(8, lambda _i: activate(Session, d))
    assert results == [units.P_PAID] * 8, results
    assert unit_states(Session, p) == [(i, "ACTIVE") for i in (1, 2, 3, 4)]


def test_the_payment_path_holds_the_cash_once_and_creates_units_once(world):
    """Financial idempotency boundary: process_new_model_deposit twice = one 2100 receipt,
    N units and N recognitions (P5); the buyer has no sponsor, so no commission."""
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 3)
    confirm(Session, d)
    for _ in range(2):
        with Session() as db:
            process_new_model_deposit(db, db.get(Deposit, d))
            db.commit()
    assert unit_states(Session, p) == [(1, "ACTIVE"), (2, "ACTIVE"), (3, "ACTIVE")]
    assert ledger_counts(Session, d) == (1, 3, 0)
    with Session() as db:
        entry = db.query(JournalEntry).filter(JournalEntry.source_type == "DEPOSIT", JournalEntry.source_id == d).one()
        assert entry.posting_type == "RECEIPT"


def test_a_purchase_made_while_sales_were_open_is_honoured_after_they_close(world):
    """P7: the sales switch stops NEW checkouts; a payment already taken still gets its units."""
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 2)
    confirm(Session, d)
    with Session() as db:
        db.query(ReferralPoolConfig).one().multiunit_sales_enabled = False
        db.commit()
    with Session() as db:
        process_new_model_deposit(db, db.get(Deposit, d))
        db.commit()
    assert unit_states(Session, p) == [(1, "ACTIVE"), (2, "ACTIVE")] and purchase_state(Session, p) == (units.P_PAID, 0)
    assert ledger_counts(Session, d) == (1, 2, 0)
    with Session() as db:                                # and no new checkout while closed
        d2 = deposit(Session, holder, 1)
        assert refusal(lambda: units.create_purchase(db, user=db.get(User, holder), deposit=db.get(Deposit, d2),
                                                     quantity=1)) == "SALES_DISABLED"


def test_units_are_unlimited_by_default(world):
    _engine, Session = world
    holder = member(Session)
    first, d1 = buy(Session, holder, 250)
    second, d2 = buy(Session, holder, 1)
    confirm(Session, d1)
    confirm(Session, d2)
    activate(Session, d1)
    activate(Session, d2)
    with Session() as db:
        cfg = db.query(ReferralPoolConfig).one()
        assert (cfg.max_units_per_member, cfg.max_units_per_purchase, cfg.max_active_units) == (None, None, None)
        assert db.query(ReferralPoolUnit).filter(ReferralPoolUnit.user_id == holder,
                                                 ReferralPoolUnit.status == "ACTIVE").count() == 251


def test_an_optional_member_limit_counts_paid_and_unpaid_purchases_and_never_holds_paid_money(world):
    _engine, Session = world
    holder = member(Session)
    _first, d1 = buy(Session, holder, 2)
    second, d2 = buy(Session, holder, 2)                 # both checked out before any limit existed
    with Session() as db:
        db.query(ReferralPoolConfig).one().max_units_per_member = 3
        db.commit()
    d3 = deposit(Session, holder, 1)
    with Session() as db:                                # 2 + 2 reserved already: a third checkout is refused
        assert refusal(lambda: units.create_purchase(db, user=db.get(User, holder), deposit=db.get(Deposit, d3),
                                                     quantity=1)) == "MEMBER_LIMIT"
    confirm(Session, d1)
    confirm(Session, d2)
    activate(Session, d1)
    assert activate(Session, d2) == units.P_PAID and len(unit_states(Session, second)) == 2   # paid: honoured


# ---------------------------------------------------------------------------
# 2. Refunds
# ---------------------------------------------------------------------------

def test_partial_then_full_refund_per_unit_idempotent_per_reference(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 3)
    confirm(Session, d)
    activate(Session, d)
    with Session() as db:
        refunded = units.refund_units(db, purchase_id=p, quantity=1, reference="refund-A", now=NOW)
        db.commit()
        assert [u.unit_index for u in refunded] == [3]
    with Session() as db:
        again = units.refund_units(db, purchase_id=p, quantity=1, reference="refund-A", now=NOW)
        db.commit()
        assert [u.unit_index for u in again] == [3]                    # the same refund, not a second one
    assert unit_states(Session, p) == [(1, "ACTIVE"), (2, "ACTIVE"), (3, "REFUNDED")]
    assert purchase_state(Session, p) == (units.P_PARTIAL, 1)
    with Session() as db:
        units.refund_deposit_units(db, d, reference="refund-B", now=NOW)
        db.commit()
    assert unit_states(Session, p) == [(1, "REFUNDED"), (2, "REFUNDED"), (3, "REFUNDED")]
    assert purchase_state(Session, p) == (units.P_REFUNDED, 3)
    with Session() as db:                                               # refunded units never come back
        assert units.restore_member_units(db, holder, now=NOW) == 0
        assert refusal(lambda: units.revoke_unit(db, unit_id_list(Session, p)[0], "test")) == "ALREADY_ENDED"
        assert refusal(lambda: units.refund_units(db, purchase_id=p, quantity=1, reference="refund-C")) \
            == "INVALID_QUANTITY"
        db.rollback()
    assert activate(Session, d) == units.P_REFUNDED and unit_states(Session, p)[0] == (1, "REFUNDED")


def test_a_provider_refund_of_the_deposit_refunds_every_unit(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 2)
    confirm(Session, d)
    with Session() as db:
        process_new_model_deposit(db, db.get(Deposit, d))
        db.commit()
    with Session() as db:
        reverse_new_model_deposit(db, db.get(Deposit, d), reason="Provider refund")
        db.commit()
    with Session() as db:
        reverse_new_model_deposit(db, db.get(Deposit, d), reason="Provider refund")   # replayed
        db.commit()
    assert unit_states(Session, p) == [(1, "REFUNDED"), (2, "REFUNDED")]
    assert purchase_state(Session, p) == (units.P_REFUNDED, 2)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_concurrent_refunds_never_refund_more_than_the_purchase(world, round_):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 3)
    confirm(Session, d)
    activate(Session, d)

    def refund(i):
        with Session() as db:
            try:
                # two requests share each reference: a replay of the same provider refund
                done = units.refund_units(db, purchase_id=p, quantity=1, reference=f"r{round_}-{i // 2}", now=NOW)
                db.commit()
                return f"ok:{done[0].unit_index}"
            except units.UnitsError as exc:
                db.rollback()
                return exc.code

    results = in_threads(8, refund)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert purchase_state(Session, p) == (units.P_REFUNDED, 3)
    assert sorted(set(r for r in results if r.startswith("ok"))) == ["ok:1", "ok:2", "ok:3"]
    assert results.count("INVALID_QUANTITY") == 2                       # the fourth reference finds nothing left


# ---------------------------------------------------------------------------
# 3. Eligibility, slots and history
# ---------------------------------------------------------------------------

def test_suspension_voids_open_slots_only_and_restoration_waits_for_the_next_round(world):
    _engine, Session = world
    holder, other, referred = member(Session), member(Session), member(Session)
    p, d = buy(Session, holder, 3)
    q, e = buy(Session, other, 1)
    for dep in (d, e):
        confirm(Session, dep)
        activate(Session, dep)
    mine, theirs = unit_id_list(Session, p), unit_id_list(Session, q)
    round_id = open_round_with_slots(Session, mine + theirs)
    assignment = fill_slot(Session, round_id, mine[0], referred)        # one of the holder's slots was filled

    set_kyc(Session, holder, approved=False)
    with Session() as db:
        assert units.sync_member_eligibility(db, holder, now=NOW) == (3, 0)
        db.commit()
    with Session() as db:
        slots = {s.unit_id: s.status for s in db.query(ReferralPoolRoundSlot).filter_by(round_id=round_id)}
        assert slots == {mine[0]: "FILLED", mine[1]: "VOID", mine[2]: "VOID", theirs[0]: "OPEN"}
        r = db.get(ReferralPoolRound, round_id)
        assert (r.status, r.filled_slots, r.void_slots) == ("OPEN", 1, 2)
        a = db.get(ReferralPoolAssignment, assignment)
        assert (a.pool_member_user_id, a.slot_id is not None) == (holder, True)            # history unchanged
        assert db.get(User, referred).sponsor_id == holder                                 # sponsor unchanged

    set_kyc(Session, holder, approved=True)
    with Session() as db:
        assert units.sync_member_eligibility(db, holder, now=NOW) == (0, 3)
        db.commit()
    assert unit_states(Session, p) == [(1, "ACTIVE"), (2, "ACTIVE"), (3, "ACTIVE")]
    with Session() as db:                                                # no slot added to the open round
        assert db.query(ReferralPoolRoundSlot).filter_by(round_id=round_id).count() == 4
        assert {s.status for s in db.query(ReferralPoolRoundSlot).filter(
            ReferralPoolRoundSlot.unit_id.in_(mine[1:]))} == {"VOID"}


def test_a_refund_keeps_the_assignment_and_closes_a_round_left_with_nothing_to_fill(world):
    _engine, Session = world
    holder, referred = member(Session), member(Session)
    p, d = buy(Session, holder, 2)
    confirm(Session, d)
    activate(Session, d)
    ids = unit_id_list(Session, p)
    round_id = open_round_with_slots(Session, ids)
    fill_slot(Session, round_id, ids[0], referred)
    with Session() as db:
        units.refund_deposit_units(db, d, reference="refund-all", now=NOW)
        db.commit()
    with Session() as db:
        r = db.get(ReferralPoolRound, round_id)
        assert (r.status, r.filled_slots, r.void_slots) == ("COMPLETED", 1, 1)
        assert db.query(ReferralPoolAssignment).filter_by(round_id=round_id).count() == 1
        assert db.get(User, referred).sponsor_id == holder


def test_an_administrators_suspension_is_not_lifted_by_eligibility(world):
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 1)
    confirm(Session, d)
    activate(Session, d)
    with Session() as db:
        units.suspend_member_units(db, holder, "under review", admin=True, now=NOW)
        db.commit()
    with Session() as db:
        assert units.sync_member_eligibility(db, holder, now=NOW) == (0, 0)
        db.commit()
    assert unit_states(Session, p) == [(1, "SUSPENDED")]
    with Session() as db:
        assert units.restore_member_units(db, holder, admin=True, now=NOW) == 1
        db.commit()
    assert unit_states(Session, p) == [(1, "ACTIVE")]


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_refunds_suspensions_restorations_and_activations_at_once_never_deadlock(world, round_):
    """Same holder, same open round: every lifecycle writer at once. No deadlock, and the end
    state is consistent: a refunded or suspended unit has no OPEN slot left."""
    _engine, Session = world
    holder = member(Session)
    p, d = buy(Session, holder, 4)
    q, e = buy(Session, holder, 2)
    confirm(Session, d)
    confirm(Session, e)
    activate(Session, d)
    round_id = open_round_with_slots(Session, unit_id_list(Session, p), number=round_ + 1)

    def act(i):
        with Session() as db:
            try:
                kind = (i + round_) % 4
                if kind == 0:
                    units.refund_units(db, purchase_id=p, quantity=1, reference=f"x{round_}-{i}", now=NOW)
                elif kind == 1:
                    units.suspend_member_units(db, holder, "test", now=NOW)
                elif kind == 2:
                    units.restore_member_units(db, holder, now=NOW)
                else:
                    dep = db.query(Deposit).filter(Deposit.id == e).with_for_update().one()   # as a payment callback
                    process_new_model_deposit(db, dep)
                db.commit()
                return "ok"
            except units.UnitsError as exc:
                db.rollback()
                return exc.code
            except Exception as exc:  # noqa: BLE001 - a deadlock would surface here
                db.rollback()
                return f"error:{type(exc).__name__}:{getattr(getattr(exc, 'orig', None), 'pgcode', '')}"

    results = in_threads(8, act)
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("error")], results
    with Session() as db:
        leftover = (db.query(ReferralPoolRoundSlot).join(ReferralPoolUnit, ReferralPoolUnit.id == ReferralPoolRoundSlot.unit_id)
                    .filter(ReferralPoolRoundSlot.round_id == round_id, ReferralPoolRoundSlot.status == "OPEN",
                            ReferralPoolUnit.status != "ACTIVE").count())
        assert leftover == 0
        r = db.get(ReferralPoolRound, round_id)
        counted = db.query(ReferralPoolRoundSlot).filter_by(round_id=round_id, status="VOID").count()
        assert r.void_slots == counted
        assert db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == q).count() == 2   # created once
