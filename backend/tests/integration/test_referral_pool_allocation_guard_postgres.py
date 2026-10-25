"""Multi-Unit Referral Pool, P15 D4-C: the minimum pool before allocation, on a real PostgreSQL server
(opt-in RUN_POSTGRES_TESTS=1; one DISPOSABLE database per test; SYNTHETIC).

Proved: with fewer than 5 distinct eligible holders or fewer than 10 eligible ACTIVE units, no round
opens and nobody is assigned (the referral waits, POOL_BELOW_MINIMUM), also through the worker's
queue pass; ineligible holders and suspended units do not count; at exactly 5 holders / 10 units
allocation works normally; an OPEN round stops being drawn from when the pool shrinks below the
minimum and resumes when it recovers; the production values are fixed in code at 5 and 10.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

from app.models.business_model import ReferralPoolAssignment, ReferralPoolPending, ReferralPoolRound
from app.services import referral_pool_allocation as alloc
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_allocation_postgres import (  # noqa: F401
    add_units, assert_counters, assign, holder, pool, received, referral, set_allocation,
)
from tests.integration.test_referral_pool_units_postgres import NOW, set_kyc, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]


@pytest.fixture
def real_minimum(monkeypatch):
    monkeypatch.setattr(alloc, "MIN_ALLOCATION_HOLDERS", 5)
    monkeypatch.setattr(alloc, "MIN_ALLOCATION_UNITS", 10)


def nothing_allocated(Session, referred: int) -> None:
    with Session() as db:
        assert db.query(ReferralPoolRound).count() == 0
        assert db.query(ReferralPoolAssignment).count() == 0
        p = db.query(ReferralPoolPending).filter_by(referred_user_id=referred).one()
        assert (p.status, p.last_error) == ("WAITING", alloc.BELOW_MINIMUM)


def test_the_production_minimum_is_fixed_in_code_at_5_holders_and_10_units():
    source = pathlib.Path(alloc.__file__).read_text(encoding="utf-8")
    assert re.search(r"^MIN_ALLOCATION_HOLDERS = 5$", source, re.M)
    assert re.search(r"^MIN_ALLOCATION_UNITS = 10$", source, re.M)


def test_one_holder_with_one_unit_allocates_nobody(pool, real_minimum):
    Session = pool                                             # production today: unit 1 of user 71 only
    holder(Session, 1)
    r = referral(Session)
    assert (assign(Session, r).outcome, assign(Session, r).reason) == (alloc.WAITING, alloc.BELOW_MINIMUM)
    nothing_allocated(Session, r)


def test_four_holders_with_twelve_units_are_not_enough(pool, real_minimum):
    Session = pool
    for _ in range(4):
        holder(Session, 3)
    r = referral(Session)
    assert assign(Session, r).reason == alloc.BELOW_MINIMUM
    nothing_allocated(Session, r)


def test_five_holders_with_nine_units_are_not_enough_and_the_tenth_unit_opens_allocation(pool, real_minimum):
    Session = pool
    holders = [holder(Session, n) for n in (1, 2, 2, 2, 2)]   # 5 holders, 9 units
    r = referral(Session)
    assert assign(Session, r).reason == alloc.BELOW_MINIMUM
    nothing_allocated(Session, r)
    add_units(Session, holders[0], 1)                          # 10 units
    result = assign(Session, r)
    assert result.outcome == alloc.ASSIGNED and result.sponsor_id in holders
    with Session() as db:
        assert db.query(ReferralPoolRound).one().total_slots == 10
    assert_counters(Session)


def test_ineligible_holders_do_not_count(pool, real_minimum):
    Session = pool
    holders = [holder(Session, 2) for _ in range(5)]          # 5 holders, 10 units
    set_kyc(Session, holders[0], False)                        # 4 eligible holders, 8 eligible units
    r = referral(Session)
    assert assign(Session, r).reason == alloc.BELOW_MINIMUM
    nothing_allocated(Session, r)
    set_kyc(Session, holders[0], True)
    result = assign(Session, r)
    assert result.outcome == alloc.ASSIGNED and result.sponsor_id in holders


def test_an_open_round_is_not_drawn_from_once_the_pool_shrinks_below_the_minimum(pool, real_minimum):
    Session = pool
    holders = [holder(Session, 2) for _ in range(5)]
    first = referral(Session)
    assert assign(Session, first).outcome == alloc.ASSIGNED   # round 1 opens with 10 slots
    set_kyc(Session, holders[1], False)                        # the pool shrinks to 4 eligible holders
    second = referral(Session)
    assert assign(Session, second).reason == alloc.BELOW_MINIMUM
    with Session() as db:
        assert db.query(ReferralPoolAssignment).count() == 1
        assert db.query(ReferralPoolRound).one().status == "OPEN"
    set_kyc(Session, holders[1], True)
    assert assign(Session, second).outcome == alloc.ASSIGNED
    assert_counters(Session)


def test_allocation_off_assigns_nobody_even_above_the_minimum(pool, real_minimum):
    Session = pool                                             # 6 holders / 12 units, switch OFF (production)
    for _ in range(6):
        holder(Session, 2)
    r = referral(Session)
    set_allocation(Session, False)
    assert assign(Session, r).outcome == alloc.DISABLED
    assert [x.outcome for x in alloc.process_pending(Session, now=NOW)] == [alloc.DISABLED]
    with Session() as db:
        assert alloc.open_round_if_needed(db, now=NOW) is None
        db.rollback()
        assert db.query(ReferralPoolRound).count() == 0 and db.query(ReferralPoolAssignment).count() == 0
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=r).one().status == "WAITING"


def test_the_worker_queue_pass_respects_the_minimum(pool, real_minimum):
    Session = pool
    for _ in range(4):
        holder(Session, 3)
    waiting = [referral(Session) for _ in range(3)]
    results = alloc.process_pending(Session, now=NOW)
    assert [(r.outcome, r.reason) for r in results] == [(alloc.WAITING, alloc.BELOW_MINIMUM)] * 3
    with Session() as db:
        assert db.query(ReferralPoolAssignment).count() == 0 and db.query(ReferralPoolRound).count() == 0
        assert {p.status for p in db.query(ReferralPoolPending).filter(ReferralPoolPending.referred_user_id.in_(waiting))} == {"WAITING"}


def test_at_the_minimum_every_holder_gets_their_share_of_a_round(pool, real_minimum):
    Session = pool
    holders = [holder(Session, 2) for _ in range(5)]
    for _ in range(10):
        r = referral(Session)
        assert assign(Session, r).outcome == alloc.ASSIGNED
    assert received(Session, holders) == {h: 2 for h in holders}
    assert_counters(Session)
