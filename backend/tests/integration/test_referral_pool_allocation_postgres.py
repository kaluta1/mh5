"""Multi-Unit Referral Pool, P4: quota rounds and the random draw on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.

Every scenario ends with `assert_counters`: each round's counters equal its slots, each
FILLED slot has exactly one assignment, each assignment fills exactly one slot, and a round
is COMPLETED exactly when nothing is left to fill.
"""
from __future__ import annotations

import os
import uuid
from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func

from app.models.business_model import (
    ReferralPoolAssignment, ReferralPoolConfig, ReferralPoolMembership, ReferralPoolPending, ReferralPoolRound,
    ReferralPoolRoundSlot, ReferralPoolUnit,
)
from app.models.user import User
from app.services import affiliate_rate_policy
from app.services import referral_pool_allocation as alloc
from app.services import referral_pool_units as units
from app.services.affiliate_hierarchy import AffiliateHierarchyError, validate_sponsor_assignment
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401
from tests.integration.test_referral_pool_units_postgres import (  # noqa: F401
    NOW, activate, buy, confirm, member, set_kyc, unit_id_list, world,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def pool(world):
    _engine, Session = world
    set_allocation(Session, True)
    return Session


def set_allocation(Session, on: bool) -> None:
    with Session() as db:
        db.query(ReferralPoolConfig).one().allocation_enabled = on
        db.commit()


def holder(Session, n: int) -> int:
    """A KYC-approved adult holding n active units."""
    user_id = member(Session)
    add_units(Session, user_id, n)
    return user_id


def add_units(Session, user_id: int, n: int) -> int:
    purchase_id, deposit_id = buy(Session, user_id, n)
    confirm(Session, deposit_id)
    activate(Session, deposit_id)
    return purchase_id


def referral(Session, *, at: datetime | None = None) -> int:
    """A KYC-approved member without a sponsor, queued."""
    user_id = member(Session)
    with Session() as db:
        assert alloc.enqueue_after_kyc(db, user_id, now=at or NOW).outcome == alloc.WAITING
        db.commit()
    return user_id


def assign(Session, referred_id: int) -> alloc.Result:
    with Session() as db:
        result = alloc.assign(db, referred_id, now=NOW)
        db.commit()
        return result


def sponsor_of(Session, user_id: int):
    with Session() as db:
        u = db.get(User, user_id)
        return u.sponsor_id, u.sponsor_source


def received(Session, holder_ids) -> dict:
    with Session() as db:
        counts = dict(db.query(ReferralPoolAssignment.pool_member_user_id, func.count())
                      .filter(ReferralPoolAssignment.slot_id.isnot(None))
                      .group_by(ReferralPoolAssignment.pool_member_user_id).all())
    return {h: counts.get(h, 0) for h in holder_ids}


def assert_counters(Session) -> None:
    with Session() as db:
        for r in db.query(ReferralPoolRound).all():
            slots = Counter(s for (s,) in db.query(ReferralPoolRoundSlot.status).filter_by(round_id=r.id))
            assert (r.filled_slots, r.void_slots, r.total_slots) == \
                (slots["FILLED"], slots["VOID"], sum(slots.values())), (r.round_number, slots)
            assigned = db.query(ReferralPoolAssignment).filter_by(round_id=r.id).count()
            assert assigned == slots["FILLED"], (r.round_number, assigned, slots)
            assert (r.status == "COMPLETED") == (slots["OPEN"] == 0), (r.round_number, r.status, slots)
        for a in db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.slot_id.isnot(None)):
            s = db.get(ReferralPoolRoundSlot, a.slot_id)
            assert (s.status, s.unit_id, s.member_user_id, s.round_id) == ("FILLED", a.unit_id, a.pool_member_user_id,
                                                                          a.round_id)
            u = db.get(User, a.referred_user_id)
            assert (u.sponsor_id, u.sponsor_source) == (a.pool_member_user_id, "REFERRAL_POOL")
        assert db.query(ReferralPoolRound).filter_by(status="OPEN").count() <= 1


# ---------------------------------------------------------------------------
# 1. Rounds and quotas
# ---------------------------------------------------------------------------

def test_one_unit_one_slot_per_round_and_the_unit_is_never_consumed(pool):
    Session = pool
    h = holder(Session, 1)
    first, second = referral(Session), referral(Session)
    assert assign(Session, first).sponsor_id == h
    assert assign(Session, second).sponsor_id == h                       # the next round, same unit
    with Session() as db:
        rounds = db.query(ReferralPoolRound).order_by(ReferralPoolRound.round_number).all()
        assert [(r.round_number, r.total_slots, r.status) for r in rounds] == [(1, 1, "COMPLETED"), (2, 1, "COMPLETED")]
        assert db.query(ReferralPoolUnit).filter_by(user_id=h).one().status == "ACTIVE"
    assert_counters(Session)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_holders_of_1_3_and_6_units_receive_exactly_1_3_and_6_of_a_10_slot_round(pool, round_):
    Session = pool
    a, b, c = holder(Session, 1), holder(Session, 3), holder(Session, 6)
    referrals = [referral(Session, at=NOW + timedelta(seconds=i)) for i in range(10)]
    results = alloc.process_pending(Session, now=NOW)
    assert [r.outcome for r in results] == [alloc.ASSIGNED] * 10
    assert received(Session, (a, b, c)) == {a: 1, b: 3, c: 6}
    with Session() as db:
        r1 = db.query(ReferralPoolRound).one()
        assert (r1.total_slots, r1.filled_slots, r1.void_slots, r1.status) == (10, 10, 0, "COMPLETED")
        assert {u.status for u in db.query(ReferralPoolUnit)} == {"ACTIVE"}
    # The 11th referral opens the second round with the same 10 slots.
    assert assign(Session, referral(Session)).outcome == alloc.ASSIGNED
    with Session() as db:
        assert db.query(ReferralPoolRound).filter_by(round_number=2).one().total_slots == 10
    assert len(set(referrals)) == 10
    assert_counters(Session)


def test_the_draw_uses_secrets(pool, monkeypatch):
    Session = pool
    holder(Session, 3)
    r = referral(Session)
    calls = []
    real = alloc.secrets.randbelow
    monkeypatch.setattr(alloc.secrets, "randbelow", lambda n: calls.append(n) or real(n))
    assert assign(Session, r).outcome == alloc.ASSIGNED
    assert calls == [3]                                                  # a choice among all 3 open slots


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_concurrent_workers_assign_each_referral_and_each_slot_once(pool, round_):
    Session = pool
    holders = [holder(Session, n) for n in (1, 2, 3)]
    referrals = [referral(Session, at=NOW + timedelta(seconds=i)) for i in range(9)]
    results = in_threads(6, lambda _i: alloc.process_pending(Session, now=NOW))
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        assert db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.referred_user_id.in_(referrals)).count() == 9
        assert db.query(ReferralPoolPending).filter_by(status="ASSIGNED").count() == 9
    # 6 slots per round: round 1 complete (1, 2, 3), round 2 half filled.
    got = received(Session, holders)
    assert sum(got.values()) == 9 and all(got[h] >= n for h, n in zip(holders, (1, 2, 3)))
    assert_counters(Session)


def test_concurrent_draws_for_different_referrals(pool):
    Session = pool
    holder(Session, 4)
    holder(Session, 4)
    referrals = [referral(Session) for _ in range(8)]
    results = in_threads(8, lambda i: assign(Session, referrals[i]).outcome)
    assert results == [alloc.ASSIGNED] * 8, results
    assert_counters(Session)


def test_concurrent_round_opening_creates_one_round(pool):
    Session = pool
    holder(Session, 2)

    def open_(_i):
        with Session() as db:
            r = alloc.open_round_if_needed(db, now=NOW)
            db.commit()
            return r.id

    ids = in_threads(6, open_)
    assert len(set(ids)) == 1
    with Session() as db:
        assert db.query(ReferralPoolRound).count() == 1
    assert_counters(Session)


def test_no_eligible_unit_keeps_the_referral_waiting_and_opens_no_round(pool):
    Session = pool
    r = referral(Session)
    for _ in range(3):
        assert assign(Session, r) == alloc.Result(alloc.WAITING, "NO_ELIGIBLE_UNIT")
    with Session() as db:
        assert db.query(ReferralPoolRound).count() == 0                   # never an empty round
        p = db.query(ReferralPoolPending).filter_by(referred_user_id=r).one()
        assert (p.status, p.attempts, p.last_error) == ("WAITING", 3, "NO_ELIGIBLE_UNIT")
    h = holder(Session, 1)
    assert assign(Session, r).sponsor_id == h                            # a unit arrived: assigned


# ---------------------------------------------------------------------------
# 2. Queue
# ---------------------------------------------------------------------------

def test_the_queue_is_first_in_first_out(pool):
    Session = pool
    holder(Session, 2)
    late = referral(Session, at=NOW + timedelta(minutes=3))
    first = referral(Session, at=NOW + timedelta(minutes=1))
    second = referral(Session, at=NOW + timedelta(minutes=2))
    with Session() as db:
        assert alloc.waiting_in_order(db) == [first, second, late]
    results = alloc.process_pending(Session, now=NOW)
    assert [r.outcome for r in results] == [alloc.ASSIGNED, alloc.ASSIGNED, alloc.ASSIGNED]
    with Session() as db:
        rounds = {a.referred_user_id: a.round_id for a in db.query(ReferralPoolAssignment)}
        first_round = db.query(ReferralPoolRound).filter_by(round_number=1).one().id
    assert rounds[first] == rounds[second] == first_round != rounds[late]   # the round went to the first two
    assert_counters(Session)


def test_retries_and_duplicate_enqueues_are_idempotent(pool):
    Session = pool
    holder(Session, 2)
    r = referral(Session)
    with Session() as db:
        assert alloc.enqueue_after_kyc(db, r, now=NOW).outcome == alloc.WAITING     # queued twice: one row
        db.commit()
    first = assign(Session, r)
    again = assign(Session, r)
    assert first.outcome == alloc.ASSIGNED
    assert (again.outcome, again.assignment_id, again.sponsor_id) == (alloc.ALREADY_ASSIGNED, first.assignment_id,
                                                                     first.sponsor_id)
    with Session() as db:
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=r).count() == 1
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=r).one().attempts == 1
        assert alloc.enqueue_after_kyc(db, r, now=NOW) == alloc.Result(alloc.NOT_QUEUED, "ALREADY_POOL_ASSIGNED")
        db.rollback()
    results = in_threads(6, lambda _i: assign(Session, r).outcome)
    assert results == [alloc.ALREADY_ASSIGNED] * 6
    assert_counters(Session)


# ---------------------------------------------------------------------------
# 3. Eligibility, refunds and new units during a round
# ---------------------------------------------------------------------------

def test_a_suspension_during_an_open_round_voids_only_the_open_slots(pool):
    Session = pool
    a, b = holder(Session, 2), holder(Session, 2)
    assert assign(Session, referral(Session)).outcome == alloc.ASSIGNED      # round 1 opened (4 slots), 1 filled
    set_kyc(Session, a, approved=False)
    with Session() as db:
        units.sync_member_eligibility(db, a, now=NOW)
        db.commit()
    for _ in range(3):
        assign(Session, referral(Session))
    with Session() as db:
        r1 = db.query(ReferralPoolRound).filter_by(round_number=1).one()
        assert r1.status == "COMPLETED" and r1.filled_slots + r1.void_slots == 4 and r1.void_slots >= 1
        later = db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.round_id != r1.id).all()
        assert all(x.pool_member_user_id == b for x in later)              # a's units are out of round 2
    assert_counters(Session)


def test_a_holder_no_longer_eligible_at_the_draw_is_skipped_and_suspended(pool):
    """KYC withdrawn without a sync: the draw itself finds out, suspends, and draws again."""
    Session = pool
    a, b = holder(Session, 3), holder(Session, 1)
    with Session() as db:
        assert alloc.open_round_if_needed(db, now=NOW).total_slots == 4
        db.commit()
    set_kyc(Session, a, approved=False)
    for _ in range(2):
        assign(Session, referral(Session))
    # Round 1: a's three slots are voided when one is drawn, b's slot is filled. Round 2: only b.
    assert received(Session, (a, b)) == {a: 0, b: 2}
    with Session() as db:
        assert {u.status for u in db.query(ReferralPoolUnit).filter_by(user_id=a)} == {"SUSPENDED"}
    assert_counters(Session)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_refunds_suspensions_and_draws_at_once_stay_consistent(pool, round_):
    Session = pool
    a, b = member(Session), holder(Session, 3)
    purchase = add_units(Session, a, 3)
    referrals = [referral(Session, at=NOW + timedelta(seconds=i)) for i in range(6)]

    def act(i):
        with Session() as db:
            try:
                kind = (i + round_) % 4
                if kind == 0:
                    units.refund_units(db, purchase_id=purchase, quantity=1, reference=f"z{round_}-{i}", now=NOW)
                elif kind == 1:
                    units.suspend_member_units(db, b, "test", now=NOW)
                elif kind == 2:
                    units.restore_member_units(db, b, now=NOW)
                else:
                    alloc.assign(db, referrals[i % len(referrals)], now=NOW)
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
    alloc.process_pending(Session, now=NOW)
    assert_counters(Session)
    with Session() as db:
        stale = (db.query(ReferralPoolRoundSlot).join(ReferralPoolUnit, ReferralPoolUnit.id == ReferralPoolRoundSlot.unit_id)
                 .filter(ReferralPoolRoundSlot.status == "OPEN", ReferralPoolUnit.status != "ACTIVE").count())
        assert stale == 0


def test_units_bought_or_restored_during_a_round_join_the_next_round(pool):
    Session = pool
    a, b, c = holder(Session, 2), member(Session), holder(Session, 1)
    set_kyc(Session, c, approved=False)
    with Session() as db:
        units.sync_member_eligibility(db, c, now=NOW)
        db.commit()
    assert assign(Session, referral(Session)).outcome == alloc.ASSIGNED          # round 1: a's 2 slots only
    add_units(Session, b, 2)                                                    # bought during round 1
    set_kyc(Session, c, approved=True)
    with Session() as db:
        units.sync_member_eligibility(db, c, now=NOW)                           # restored during round 1
        db.commit()
    assert assign(Session, referral(Session)).sponsor_id == a                   # round 1's last slot is a's
    with Session() as db:
        r1 = db.query(ReferralPoolRound).filter_by(round_number=1).one()
        assert (r1.total_slots, r1.status) == (2, "COMPLETED")
    assign(Session, referral(Session))
    with Session() as db:
        r2 = db.query(ReferralPoolRound).filter_by(round_number=2).one()
        members = Counter(m for (m,) in db.query(ReferralPoolRoundSlot.member_user_id).filter_by(round_id=r2.id))
        assert members == {a: 2, b: 2, c: 1}
    assert_counters(Session)


def test_unlimited_units_make_an_equally_large_round(pool):
    Session = pool
    big = holder(Session, 2000)
    small = holder(Session, 1)
    for _ in range(20):
        assign(Session, referral(Session))
    with Session() as db:
        r1 = db.query(ReferralPoolRound).one()
        assert (r1.total_slots, r1.filled_slots) == (2001, 20)
    assert sum(received(Session, (big, small)).values()) == 20
    assert_counters(Session)


# ---------------------------------------------------------------------------
# 4. Sponsor integrity
# ---------------------------------------------------------------------------

def test_a_valid_personal_invitation_takes_precedence_and_a_pool_sponsor_is_final(pool):
    Session = pool
    holder(Session, 2)
    inviter = member(Session)
    invited = member(Session)
    with Session() as db:
        u = db.get(User, invited)
        u.sponsor_id, u.sponsor_source = inviter, "PERSONAL_REFERRAL"
        db.commit()
        assert alloc.enqueue_after_kyc(db, invited, now=NOW) == alloc.Result(alloc.NOT_QUEUED, "PERSONAL_INVITATION")
        db.rollback()

    # Queued, then a join code arrives before the draw: the invitation wins, the wait ends.
    joiner = referral(Session)
    with Session() as db:
        validate_sponsor_assignment(db, user_id=joiner, sponsor_id=inviter)
        u = db.get(User, joiner)
        u.sponsor_id, u.sponsor_source = inviter, "JOIN_CODE"
        db.commit()
    assert assign(Session, joiner) == alloc.Result(alloc.CANCELLED, "PERSONAL_INVITATION")
    assert sponsor_of(Session, joiner) == (inviter, "JOIN_CODE")

    # Pool-assigned: a later code cannot replace the pool sponsor.
    pooled = referral(Session)
    pool_sponsor = assign(Session, pooled).sponsor_id
    with Session() as db:
        with pytest.raises(AffiliateHierarchyError, match="reassignment"):
            validate_sponsor_assignment(db, user_id=pooled, sponsor_id=inviter)
        db.rollback()
    assert sponsor_of(Session, pooled) == (pool_sponsor, "REFERRAL_POOL")
    assert_counters(Session)


def test_an_invalid_personal_sponsor_is_left_alone_and_never_replaced(pool):
    Session = pool
    holder(Session, 1)
    unverified_inviter = member(Session, kyc=False)                       # later deactivated: no longer valid
    invited = member(Session)
    with Session() as db:
        u = db.get(User, invited)
        u.sponsor_id, u.sponsor_source = unverified_inviter, "PERSONAL_REFERRAL"
        db.get(User, unverified_inviter).is_active = False
        db.commit()
        assert alloc.enqueue_after_kyc(db, invited, now=NOW) == alloc.Result(alloc.NOT_QUEUED, "SPONSOR_PRESENT")
        assert not alloc.valid_personal_inviter(db, db.get(User, invited))
        db.rollback()
    assert sponsor_of(Session, invited) == (unverified_inviter, "PERSONAL_REFERRAL")


def test_the_referred_member_needs_neither_kyc_nor_a_confirmed_email(pool):
    """Owner rule 2026-10-31: the sponsor relationship needs no KYC or e-mail confirmation of the
    referred member (KYC still governs commissions and cash-out; a unit HOLDER must be eligible)."""
    Session = pool
    h = holder(Session, 2)
    no_kyc = member(Session, kyc=False)
    with Session() as db:
        db.get(User, no_kyc).email_verified = False
        assert alloc.enqueue(db, no_kyc, trigger=alloc.SIGNED_UP, now=NOW).outcome == alloc.WAITING
        db.commit()
    assert assign(Session, no_kyc).outcome == alloc.ASSIGNED
    assert sponsor_of(Session, no_kyc) == (h, "REFERRAL_POOL")
    queued = referral(Session)
    set_kyc(Session, queued, approved=False)                                # KYC rejected before the draw
    assert assign(Session, queued).outcome == alloc.ASSIGNED                # the sponsor is still assigned
    with Session() as db:
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=no_kyc).one().trigger_event == "SIGNED_UP"
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=queued).one().trigger_event == "KYC_APPROVED"
    assert_counters(Session)


def test_an_ineligible_holder_receives_nobody(pool):
    Session = pool
    h = holder(Session, 1)
    set_kyc(Session, h, approved=False)                                     # the HOLDER still needs KYC
    r = referral(Session)
    assert assign(Session, r).outcome == alloc.WAITING
    assert sponsor_of(Session, r) == (None, None)


def test_no_self_referral_and_no_cycle_through_the_downline(pool):
    Session = pool
    x = referral(Session)                    # waiting, and also a unit holder
    add_units(Session, x, 2)
    y = member(Session)                      # invited by x, holds units
    with Session() as db:
        u = db.get(User, y)
        u.sponsor_id, u.sponsor_source = x, "PERSONAL_REFERRAL"
        db.commit()
    add_units(Session, y, 2)
    assert assign(Session, x) == alloc.Result(alloc.WAITING, "NO_ELIGIBLE_SLOT")   # only x's and y's slots
    z = holder(Session, 1)                   # joins the NEXT round
    assert assign(Session, x) == alloc.Result(alloc.WAITING, "NO_ELIGIBLE_SLOT")   # round 1 still has only those
    others = [referral(Session) for _ in range(4)]
    assert {assign(Session, o).sponsor_id for o in others} <= {x, y}               # round 1 completes
    assert assign(Session, x).sponsor_id == z                                       # round 2: z is x's only choice
    with Session() as db:
        assert db.query(ReferralPoolAssignment).filter(
            ReferralPoolAssignment.referred_user_id == ReferralPoolAssignment.pool_member_user_id).count() == 0
    assert_counters(Session)


def test_allocation_switched_off_opens_nothing_assigns_nothing_and_keeps_the_queue(pool):
    Session = pool
    holder(Session, 2)
    r = referral(Session)
    set_allocation(Session, False)
    assert assign(Session, r).outcome == alloc.DISABLED
    with Session() as db:
        assert alloc.open_round_if_needed(db, now=NOW) is None
        db.rollback()
        assert db.query(ReferralPoolRound).count() == 0
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=r).one().status == "WAITING"
    assert alloc.process_pending(Session, now=NOW)[0].outcome == alloc.DISABLED
    assert sponsor_of(Session, r) == (None, None)
    set_allocation(Session, True)
    assert assign(Session, r).outcome == alloc.ASSIGNED


def test_historical_assignments_stay_and_pool_referrals_never_count_for_the_40_percent(pool):
    Session = pool
    h = holder(Session, 2)
    legacy_member, legacy_referral = member(Session), member(Session)
    with Session() as db:
        seat = ReferralPoolMembership(user_id=legacy_member, status="ACTIVE", seat_number=1, entitlement_source="PAID",
                                      joined_at=NOW, assignment_eligible=True, assignments_count=1)
        db.add(seat)
        db.flush()
        seat_id = seat.id
        db.add(ReferralPoolAssignment(referred_user_id=legacy_referral, pool_member_user_id=legacy_member,
                                      membership_id=seat_id, method="FAIR_RANDOM_V1", candidate_count=3,
                                      min_assignment_count=0, assigned_at=NOW))
        u = db.get(User, legacy_referral)
        u.sponsor_id, u.sponsor_source = legacy_member, "REFERRAL_POOL"
        db.commit()
        assert alloc.enqueue_after_kyc(db, legacy_referral, now=NOW).outcome == alloc.NOT_QUEUED
        db.rollback()
    pooled = referral(Session)
    assert assign(Session, pooled).sponsor_id == h
    with Session() as db:
        legacy = db.query(ReferralPoolAssignment).filter_by(referred_user_id=legacy_referral).one()
        assert (legacy.membership_id, legacy.slot_id, legacy.pool_member_user_id) == (seat_id, None, legacy_member)
        # The pooled referral is KYC-approved, yet does not count toward h's 40% qualification.
        assert affiliate_rate_policy.qualifying_referral_count(db, db.get(User, h)) == 0
    assert_counters(Session)
