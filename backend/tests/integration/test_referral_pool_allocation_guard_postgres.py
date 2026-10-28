"""Multi-Unit Referral Pool, owner rules of 2026-10-26, on a real PostgreSQL server (opt-in
RUN_POSTGRES_TESTS=1; one DISPOSABLE database per test; SYNTHETIC).

Proved: the minimum is 1 eligible holder with 1 eligible ACTIVE unit (the former 5/10 is gone), so
the first qualified holder receives every pool referral; with no eligible unit nobody is invented
as a sponsor (the referral waits, NO_ELIGIBLE_UNIT); ineligible holders never count; shares follow
the eligible ACTIVE units (5/3/2 receive 5/3/2 of a round); an existing sponsor is never replaced;
DSM-imported members are never pool-assigned; the switch off assigns nobody.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest
from sqlalchemy import text

from app.models.business_model import ReferralPoolAssignment, ReferralPoolPending, ReferralPoolRound
from app.models.user import User
from app.services import referral_pool_allocation as alloc
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_allocation_postgres import (  # noqa: F401
    add_units, assert_counters, assign, holder, pool, received, referral, set_allocation, sponsor_of,
)
from tests.integration.test_referral_pool_units_postgres import NOW, member, set_kyc, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]


def nothing_allocated(Session, referred: int, reason: str) -> None:
    with Session() as db:
        assert db.query(ReferralPoolRound).count() == 0
        assert db.query(ReferralPoolAssignment).count() == 0
        p = db.query(ReferralPoolPending).filter_by(referred_user_id=referred).one()
        assert (p.status, p.last_error) == ("WAITING", reason)


def dsm_mapping(Session, *user_ids: int) -> None:
    """The production mapping table's shape, reduced to what the pool reads."""
    with Session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS legacy_import"))
        db.execute(text("CREATE TABLE IF NOT EXISTS legacy_import.dsm_members (dsm_id integer PRIMARY KEY, "
                        "mh5_user_id integer, import_status text NOT NULL)"))
        for i, uid in enumerate(user_ids, start=1):
            db.execute(text("INSERT INTO legacy_import.dsm_members VALUES (:d, :u, 'CREATED')"), {"d": i, "u": uid})
        db.commit()


def test_the_production_minimum_is_fixed_in_code_at_1_holder_and_1_unit():
    source = pathlib.Path(alloc.__file__).read_text(encoding="utf-8")
    assert re.search(r"^MIN_ALLOCATION_HOLDERS = 1$", source, re.M)
    assert re.search(r"^MIN_ALLOCATION_UNITS = 1$", source, re.M)
    assert alloc.meets_minimum([(1, 71)]) and not alloc.meets_minimum([])


def test_the_first_holder_with_one_unit_receives_every_pool_referral(pool):
    Session = pool                                             # production today: unit 1 of the founder
    first = holder(Session, 1)
    referrals = [referral(Session) for _ in range(4)]
    for r in referrals:
        result = assign(Session, r)
        assert (result.outcome, result.sponsor_id) == (alloc.ASSIGNED, first)
        assert sponsor_of(Session, r) == (first, "REFERRAL_POOL")
    assert received(Session, [first]) == {first: 4}
    assert_counters(Session)


def test_no_eligible_unit_invents_no_sponsor_and_the_referral_waits(pool):
    Session = pool
    r = referral(Session)
    assert (assign(Session, r).outcome, assign(Session, r).reason) == (alloc.WAITING, "NO_ELIGIBLE_UNIT")
    nothing_allocated(Session, r, "NO_ELIGIBLE_UNIT")
    assert sponsor_of(Session, r)[0] is None
    h = holder(Session, 1)                                     # the first unit arrives: the wait ends
    assert assign(Session, r).sponsor_id == h


def test_an_ineligible_holder_does_not_count_until_eligible_again(pool):
    Session = pool
    h = holder(Session, 2)
    set_kyc(Session, h, False)
    r = referral(Session)
    assert assign(Session, r).outcome == alloc.WAITING
    nothing_allocated(Session, r, "NO_ELIGIBLE_UNIT")
    set_kyc(Session, h, True)
    assert assign(Session, r).sponsor_id == h
    assert_counters(Session)


def test_holders_of_5_3_and_2_units_receive_5_3_and_2_of_a_round(pool):
    Session = pool
    a, b, c = holder(Session, 5), holder(Session, 3), holder(Session, 2)
    for _ in range(10):
        assert assign(Session, referral(Session)).outcome == alloc.ASSIGNED
    assert received(Session, (a, b, c)) == {a: 5, b: 3, c: 2}
    assert_counters(Session)


def test_an_existing_sponsor_is_never_replaced(pool):
    Session = pool
    holder(Session, 3)
    kept, other = member(Session), member(Session)
    with Session() as db:
        u = db.get(User, kept)
        u.sponsor_id, u.sponsor_source = other, "DSM_IMPORT"
        db.commit()
        assert alloc.enqueue_after_kyc(db, kept, now=NOW).reason == "SPONSOR_PRESENT"
    assert sponsor_of(Session, kept) == (other, "DSM_IMPORT")


def test_dsm_imported_members_are_never_pool_assigned(pool):
    Session = pool
    holder(Session, 1)
    imported = member(Session)                                 # imported without a resolvable sponsor
    waiting = referral(Session)                                # queued before it was mapped
    dsm_mapping(Session, imported, waiting)
    with Session() as db:
        assert alloc.enqueue_after_kyc(db, imported, now=NOW).outcome == alloc.NOT_QUEUED
        assert alloc.enqueue_after_kyc(db, imported, now=NOW).reason == "DSM_IMPORTED"
        db.rollback()
    result = assign(Session, waiting)
    assert (result.outcome, result.reason) == (alloc.CANCELLED, "DSM_IMPORTED")
    assert sponsor_of(Session, imported)[0] is None and sponsor_of(Session, waiting)[0] is None
    with Session() as db:
        assert db.query(ReferralPoolAssignment).count() == 0


def test_allocation_off_assigns_nobody(pool):
    Session = pool
    holder(Session, 2)
    r = referral(Session)
    set_allocation(Session, False)
    assert assign(Session, r).outcome == alloc.DISABLED
    with Session() as db:
        assert db.query(ReferralPoolAssignment).count() == 0
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=r).one().status == "WAITING"


def test_a_new_account_on_a_retired_dsm_members_address_stays_excluded(pool):
    # Owner request 2026-10-29: a DSM-matched account is retired so its address can register again.
    # DSM record and sponsor stay on the retired row; the new account is linked to it explicitly and
    # keeps the DSM exclusion. A retired NON-DSM account's successor is an ordinary member.
    from app.services import account_retirement as ar

    Session = pool
    holder(Session, 1)
    old_dsm = member(Session, kyc=False)
    old_plain = member(Session, kyc=False)
    dsm_mapping(Session, old_dsm)
    with Session() as db:
        emails = {u.id: u.email for u in db.query(User).filter(User.id.in_([old_dsm, old_plain]))}
        for uid in (old_dsm, old_plain):
            ar.retire(db, uid, emails[uid].upper(), reason="owner request")
        db.commit()
    successors = {}
    for uid in (old_dsm, old_plain):
        new_id = member(Session)                               # KYC-approved, no sponsor
        with Session() as db:
            new = db.get(User, new_id)
            new.email = emails[uid]                            # the freed address
            assert ar.link_successor(db, new).user_id == uid
            db.commit()
        successors[uid] = new_id
    with Session() as db:
        assert alloc.dsm_imported(db, successors[old_dsm]) is True
        assert alloc.dsm_imported(db, successors[old_plain]) is False
        assert db.execute(text("SELECT mh5_user_id FROM legacy_import.dsm_members")).scalar() == old_dsm
        r = alloc.enqueue_after_kyc(db, successors[old_dsm], now=NOW)
        assert (r.outcome, r.reason) == (alloc.NOT_QUEUED, "DSM_IMPORTED")
        assert alloc.enqueue_after_kyc(db, successors[old_plain], now=NOW).outcome == alloc.WAITING
        db.rollback()
