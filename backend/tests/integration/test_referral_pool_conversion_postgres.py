"""Multi-Unit Referral Pool, P10: owner-approved conversion of a historical seat into one unit, on a
real PostgreSQL server (opt-in RUN_POSTGRES_TESTS=1; one DISPOSABLE database per test; SYNTHETIC).

Proved: one approved membership -> exactly one HISTORICAL_CONVERSION unit; no journal entry, no
revenue recognition, no commission; a repeat or concurrent runs create nothing more; anything not
approved, not an active seat or not convertible is refused; current eligibility decides ACTIVE or
SUSPENDED and a later restore still earns nothing; historical assignments are untouched; the dry
run writes nothing; an audit row records the run.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.business_model import (
    ReferralPoolAssignment, ReferralPoolMembership, ReferralPoolUnit, RevenueRecognition,
)
from app.services import referral_pool_conversion as conversion
from app.services import referral_pool_units as units
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401
from tests.integration.test_referral_pool_units_postgres import member, set_kyc, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

NOW = datetime(2026, 10, 24, 12, 0)
ROUNDS = max(2, int(os.getenv("KYC_RACE_ROUNDS", "2")))


def seat(Session, user_id: int, *, status="ACTIVE", source="LEGACY_FOUNDING_MIGRATION", assignments=0) -> int:
    with Session() as db:
        m = ReferralPoolMembership(user_id=user_id, status=status, seat_number=user_id if status == "ACTIVE" else None,
                                   entitlement_source=source, joined_at=NOW, assignment_eligible=True,
                                   assignments_count=assignments)
        db.add(m)
        db.flush()
        for _ in range(assignments):
            db.add(ReferralPoolAssignment(referred_user_id=member(Session), pool_member_user_id=user_id, membership_id=m.id,
                                          method="FAIR_RANDOM_V1", candidate_count=3, min_assignment_count=0, assigned_at=NOW))
        db.commit()
        return m.id


def money_rows(Session) -> tuple:
    with Session() as db:
        return (db.query(JournalEntry).count(), db.query(AffiliateCommission).count(), db.query(RevenueRecognition).count())


def history_units(Session) -> list:
    with Session() as db:
        return [(u.user_id, u.legacy_membership_id, u.source, u.status, str(u.amount), u.purchase_id)
                for u in db.query(ReferralPoolUnit).order_by(ReferralPoolUnit.id)]


def run(Session, membership_id: int, approved=None, **kw):
    with Session() as db:
        return conversion.convert(db, membership_id, approved=approved if approved is not None else [membership_id],
                                  run_id="p10-test", now=NOW, **kw)


def test_an_approved_seat_becomes_exactly_one_unit_with_no_money_posted(world):
    _engine, Session = world
    holder = member(Session)
    mid = seat(Session, holder, assignments=2)
    with Session() as db:
        assignments_before = sorted((a.id, a.referred_user_id, a.pool_member_user_id, a.membership_id)
                                    for a in db.query(ReferralPoolAssignment))
    money_before = money_rows(Session)
    result = run(Session, mid, operator_id=holder)
    assert (result.outcome, result.unit_status) == (conversion.CREATED, units.ACTIVE)
    assert history_units(Session) == [(holder, mid, "HISTORICAL_CONVERSION", units.ACTIVE, "100.00", None)]
    assert money_rows(Session) == money_before                                   # $0 revenue, $0 commission
    with Session() as db:
        assert sorted((a.id, a.referred_user_id, a.pool_member_user_id, a.membership_id)
                      for a in db.query(ReferralPoolAssignment)) == assignments_before
        audit = db.query(AuditTrail).filter_by(action=conversion.AUDIT_ACTION).one()
        assert audit.record_id == result.unit_id and audit.new_values["run_id"] == "p10-test"
        assert audit.new_values["revenue"] == audit.new_values["commission"] == "0.00"
        assert db.get(ReferralPoolMembership, mid).status == "ACTIVE"            # the history row is untouched


def test_a_repeat_and_concurrent_runs_create_nothing_more(world):
    _engine, Session = world
    for _ in range(ROUNDS):
        mid = seat(Session, member(Session))
        results = in_threads(4, lambda i: run(Session, mid))
        assert not [r for r in results if isinstance(r, Exception)], results
        assert sorted(r.outcome for r in results) == [conversion.ALREADY_CONVERTED] * 3 + [conversion.CREATED]
        assert run(Session, mid).outcome == conversion.ALREADY_CONVERTED
        with Session() as db:
            assert db.query(ReferralPoolUnit).filter_by(legacy_membership_id=mid).count() == 1
            assert db.query(AuditTrail).filter_by(action=conversion.AUDIT_ACTION).filter(
                AuditTrail.record_id.in_([u.id for u in db.query(ReferralPoolUnit).filter_by(legacy_membership_id=mid)])
            ).count() == 1


def test_unapproved_or_unconvertible_records_are_refused(world):
    _engine, Session = world
    approved = seat(Session, member(Session))
    other = seat(Session, member(Session))
    refunded = seat(Session, member(Session), status="REFUNDED")
    admin_grant = seat(Session, member(Session), source="ADMIN_ADJUSTMENT")
    for mid, approved_ids, code in ((other, [approved], "NOT_APPROVED"), (refunded, [refunded], "NOT_A_SEAT"),
                                    (admin_grant, [admin_grant], "SOURCE_NOT_CONVERTIBLE"), (999999, [999999], "NOT_FOUND")):
        with pytest.raises(conversion.ConversionRefused) as info:
            run(Session, mid, approved=approved_ids)
        assert info.value.code == code
    with pytest.raises(conversion.ConversionRefused, match="run id"):
        with Session() as db:
            conversion.convert(db, approved, approved=[approved], run_id=" ")
    assert history_units(Session) == []


def test_a_holder_not_eligible_today_gets_a_suspended_unit_that_never_earns(world):
    _engine, Session = world
    holder = member(Session)
    mid = seat(Session, holder)
    set_kyc(Session, holder, False)
    money_before = money_rows(Session)
    result = run(Session, mid)
    assert result.unit_status == units.SUSPENDED
    set_kyc(Session, holder, True)
    with Session() as db:
        assert units.restore_member_units(db, holder) == 1                       # eligible again: ACTIVE
        db.commit()
    assert history_units(Session)[0][3] == units.ACTIVE
    assert money_rows(Session) == money_before                                   # restore earned nothing either


def test_the_dry_run_reports_and_writes_nothing(world):
    _engine, Session = world
    holder = member(Session)
    mid = seat(Session, holder)
    with Session() as db:
        planned = conversion.plan(db, [mid], approved=[mid])
    assert [(p.outcome, p.unit_status, p.user_id) for p in planned] == [(conversion.WOULD_CREATE, units.ACTIVE, holder)]
    assert history_units(Session) == []
    run(Session, mid)
    with Session() as db:
        assert conversion.plan(db, [mid], approved=[mid])[0].outcome == conversion.ALREADY_CONVERTED
