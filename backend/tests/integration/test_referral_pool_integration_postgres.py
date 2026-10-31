"""Multi-Unit Referral Pool, P6: KYC, sponsor and anti-abuse integration on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.

KYC decisions go through the real crud_kyc approve/reject paths: they write a pool event in
their own transaction (outbox) and take no pool lock; the worker handles events afterwards.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.crud import crud_kyc
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission
from app.models.business_model import (
    ReferralPoolAssignment, ReferralPoolEvent, ReferralPoolMembership, ReferralPoolPending, ReferralPoolRiskReview,
    ReferralPoolRound, ReferralPoolRoundSlot, ReferralPoolUnit, RevenueRecognition,
)
from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider
from app.models.login_log import LoginLog
from app.models.user import User
from app.services import payment_config
from app.services import referral_pool_allocation as alloc
from app.services import referral_pool_integration as integration
from app.services import referral_pool_risk as risk
from app.services import referral_pool_units as units
from app.services.affiliate_hierarchy import AffiliateHierarchyError, validate_sponsor_assignment
from app.services.sponsor_assignment import assign_at_registration, inviter_eligible
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401
from tests.integration.test_referral_pool_allocation_postgres import (  # noqa: F401
    add_units, assert_counters, holder, pool, received, referral, set_allocation,
)
from tests.integration.test_referral_pool_units_postgres import NOW, member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def unverified(Session, *, identity=None, sponsor: int | None = None, source: str = "PERSONAL_REFERRAL") -> tuple:
    """(member, verification): a member whose KYC is in progress (not yet approved)."""
    user_id = member(Session, kyc=False)
    with Session() as db:
        u = db.get(User, user_id)
        if sponsor is not None:
            u.sponsor_id, u.sponsor_source = sponsor, source
        first, last, born = identity or (f"F{uuid.uuid4().hex[:6]}", f"L{uuid.uuid4().hex[:6]}", datetime(1990, 1, 1))
        v = KYCVerification(user_id=user_id, status=KYCStatus.IN_PROGRESS, provider=VerificationProvider.KALUTA,
                            reference_id=f"ref-{uuid.uuid4().hex[:10]}", attempts_count=1, submitted_at=NOW,
                            verified_first_name=first, verified_last_name=last, verified_date_of_birth=born)
        db.add(v)
        db.commit()
        return user_id, v.id


def approve(Session, verification_id: int) -> None:
    with Session() as db:
        crud_kyc.kyc_verification.approve_verification(db, verification_id=verification_id)


def reject(Session, verification_id: int) -> None:
    with Session() as db:
        crud_kyc.kyc_verification.reject_verification(db, verification_id=verification_id, reason="Synthetic rejection")


def new_attempt(Session, verification_id: int) -> None:
    with Session() as db:
        v = db.get(KYCVerification, verification_id)
        v.status, v.attempts_count = KYCStatus.IN_PROGRESS, v.attempts_count + 1
        db.commit()


def lapsed_holder(Session, n: int, **kw) -> tuple:
    """(member, verification): bought n units while KYC-approved, then rejected (units suspended),
    now on a new attempt awaiting approval."""
    user_id, v = unverified(Session, **kw)
    approve(Session, v)
    work(Session)
    add_units(Session, user_id, n)
    reject(Session, v)
    work(Session)
    new_attempt(Session, v)
    return user_id, v


def events(Session, user_id: int) -> list:
    with Session() as db:
        return [(e.event_type, e.status) for e in db.query(ReferralPoolEvent).filter_by(user_id=user_id)
                .order_by(ReferralPoolEvent.id)]


def work(Session):
    return integration.process_events(Session, now=NOW)


def pending_of(Session, user_id: int):
    with Session() as db:
        p = db.query(ReferralPoolPending).filter_by(referred_user_id=user_id).first()
        return (p.status, p.resolution_reason) if p else None


def unit_status(Session, user_id: int) -> set:
    with Session() as db:
        return {u.status for u in db.query(ReferralPoolUnit).filter_by(user_id=user_id)}


@pytest.fixture
def reviewer(world, monkeypatch):
    _engine, Session = world
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    return member(Session)


# ---------------------------------------------------------------------------
# 1. KYC decisions reach the pool after they commit
# ---------------------------------------------------------------------------

def test_an_approval_writes_one_event_that_queues_the_member_and_syncs_units(pool):
    Session = pool
    fresh, fv = unverified(Session)
    approve(Session, fv)
    assert events(Session, fresh) == [("KYC_APPROVED", "PENDING")]          # nothing done inside the KYC commit
    assert pending_of(Session, fresh) is None
    work(Session)
    assert events(Session, fresh) == [("KYC_APPROVED", "DONE")]
    assert pending_of(Session, fresh) == ("WAITING", None)

    user_id, v = lapsed_holder(Session, 2)                                  # units suspended by a rejection
    assert unit_status(Session, user_id) == {"SUSPENDED"}
    approve(Session, v)
    assert unit_status(Session, user_id) == {"SUSPENDED"}                   # not inside the approval
    work(Session)
    assert [e[0] for e in events(Session, user_id)] == ["KYC_APPROVED", "KYC_REJECTED", "KYC_APPROVED"]
    assert unit_status(Session, user_id) == {"ACTIVE"}


def test_an_approval_that_rolls_back_leaves_no_event(pool):
    Session = pool
    user_id, v = unverified(Session)
    with Session() as db:
        verification = db.get(KYCVerification, v)
        verification.status = KYCStatus.APPROVED
        integration.record_kyc_decision(db, verification, approved=True)
        db.rollback()                                                       # the decision did not happen
    assert events(Session, user_id) == []
    work(Session)
    assert pending_of(Session, user_id) is None


def test_rejection_suspends_units_and_voids_open_slots_reapproval_restores(pool):
    Session = pool
    user_id, v = unverified(Session)
    approve(Session, v)
    work(Session)
    add_units(Session, user_id, 2)
    other = holder(Session, 1)
    with Session() as db:                                                  # opens the round (3 slots), one filled
        alloc.assign(db, referral(Session), now=NOW)
        db.commit()
    reject(Session, v)
    work(Session)
    assert unit_status(Session, user_id) == {"SUSPENDED"}
    with Session() as db:
        open_slots = db.query(ReferralPoolRoundSlot).filter_by(member_user_id=user_id, status="OPEN").count()
        assert open_slots == 0
    new_attempt(Session, v)
    approve(Session, v)
    work(Session)
    assert unit_status(Session, user_id) == {"ACTIVE"}
    assert other and events(Session, user_id)[-1] == ("KYC_APPROVED", "DONE")
    assert_counters(Session)


def test_duplicate_approval_callbacks_write_one_event_and_queue_once(pool):
    Session = pool
    user_id, v = unverified(Session)
    approve(Session, v)
    approve(Session, v)                                                     # the same decision delivered again
    assert events(Session, user_id) == [("KYC_APPROVED", "PENDING")]
    work(Session)
    work(Session)
    with Session() as db:
        assert db.query(ReferralPoolPending).filter_by(referred_user_id=user_id).count() == 1


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_concurrent_kyc_decisions_workers_and_allocation_never_deadlock(pool, round_):
    Session = pool
    holder(Session, 3)
    people = [lapsed_holder(Session, 1) for _ in range(2)] + [unverified(Session) for _ in range(2)]

    def act(i):
        try:
            kind = (i + round_) % 4
            if kind == 0:
                approve(Session, people[i % 4][1])
            elif kind == 1:
                work(Session)
            elif kind == 2:
                alloc.process_pending(Session, now=NOW)
            else:
                integration.sweep_eligibility(Session, now=NOW)
            return "ok"
        except Exception as exc:  # noqa: BLE001 - a deadlock would surface here
            return f"error:{type(exc).__name__}:{getattr(getattr(exc, 'orig', None), 'pgcode', '')}"

    results = in_threads(8, act)
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("error")], results
    for _ in range(2):
        integration.run_once(Session, now=NOW)
    with Session() as db:
        assert db.query(ReferralPoolEvent).filter(ReferralPoolEvent.status != "DONE").count() == 0
    assert_counters(Session)


def test_a_kyc_approval_takes_no_pool_lock(pool):
    """The pool mutex is held by another transaction for the whole approval: the approval
    finishes anyway (it would wait, then time out, if it touched any pool row lock)."""
    Session = pool
    user_id, v = lapsed_holder(Session, 1)
    holding, done = threading.Event(), threading.Event()

    def hold_mutex():
        with Session() as db:
            units.lock_pool(db)
            holding.set()
            done.wait(20)
            db.rollback()

    t = threading.Thread(target=hold_mutex)
    t.start()
    assert holding.wait(10)
    with Session() as db:
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        crud_kyc.kyc_verification.approve_verification(db, verification_id=v)
    done.set()
    t.join(20)
    assert events(Session, user_id)[-1] == ("KYC_APPROVED", "PENDING")


# ---------------------------------------------------------------------------
# 2. Personal invitations and existing sponsors
# ---------------------------------------------------------------------------

def test_a_valid_personal_inviter_takes_precedence(pool):
    Session = pool
    inviter = member(Session)                                               # KYC-approved
    user_id, v = unverified(Session, sponsor=inviter)
    approve(Session, v)
    work(Session)
    assert pending_of(Session, user_id) is None
    with Session() as db:
        assert db.get(User, user_id).sponsor_id == inviter


def test_organic_registrations_get_a_unit_weighted_pool_sponsor_once_after_kyc(pool):
    """Owner rules 2026-10-26, end to end: no invitation at registration -> NONE; KYC approval -> the
    worker -> a pool sponsor drawn per eligible ACTIVE unit (3 units : 1 unit = 3 : 1 of a round),
    REFERRAL_POOL, permanent; an invited newcomer keeps the inviter; a later unit change moves nobody."""
    Session = pool
    big, small = holder(Session, 3), holder(Session, 1)
    newcomers = []
    for _ in range(4):
        user_id, v = unverified(Session)
        with Session() as db:
            u = db.get(User, user_id)
            u.sponsor_id, u.sponsor_source = None, None
            db.commit()
            assert assign_at_registration(db, db.get(User, user_id), None) == "NONE"
            db.commit()
        approve(Session, v)
        newcomers.append(user_id)
    invited, iv = unverified(Session, sponsor=small)
    approve(Session, iv)
    integration.run_once(Session, now=NOW)
    with Session() as db:
        got = [(db.get(User, n).sponsor_id, db.get(User, n).sponsor_source) for n in newcomers]
        assert {src for _s, src in got} == {"REFERRAL_POOL"}
        assert sorted(s for s, _src in got) == sorted([big, big, big, small])
        assert db.get(User, invited).sponsor_id == small and db.get(User, invited).sponsor_source == "PERSONAL_REFERRAL"
    add_units(Session, small, 5)                                            # weights change later: nobody moves
    integration.run_once(Session, now=NOW)
    with Session() as db:
        assert [(db.get(User, n).sponsor_id, db.get(User, n).sponsor_source) for n in newcomers] == got
    assert_counters(Session)


def test_an_unverified_inviter_creates_no_sponsor_at_registration_or_by_code(pool):
    Session = pool
    unverified_inviter = member(Session, kyc=False)
    newcomer = member(Session)
    with Session() as db:
        u = db.get(User, newcomer)
        u.sponsor_id, u.sponsor_source = None, None
        db.commit()
        assert assign_at_registration(db, db.get(User, newcomer), db.get(User, unverified_inviter)) == "NONE"
        db.commit()
        assert db.get(User, newcomer).sponsor_id is None
    late = member(Session)
    with Session() as db:
        with pytest.raises(AffiliateHierarchyError, match="identity-verified"):
            validate_sponsor_assignment(db, user_id=late, sponsor_id=unverified_inviter)
        db.rollback()
        assert inviter_eligible(db, db.get(User, member(Session))) is True


def test_a_historical_invalid_sponsor_is_kept_and_reported_not_replaced(pool):
    Session = pool
    holder(Session, 2)
    stale_inviter = member(Session, kyc=False)
    user_id, v = unverified(Session, sponsor=stale_inviter)
    approve(Session, v)
    work(Session)
    assert pending_of(Session, user_id) is None                             # SPONSOR_PRESENT: never pooled
    with Session() as db:
        assert db.get(User, user_id).sponsor_id == stale_inviter
        report = integration.invalid_personal_sponsors(db)
        assert {"user_id": user_id, "sponsor_id": stale_inviter, "source": "PERSONAL_REFERRAL"} in report


def test_a_pool_sponsor_cannot_be_replaced_by_a_later_invitation(pool):
    Session = pool
    sponsor = holder(Session, 1)
    inviter = member(Session)
    user_id, v = unverified(Session)
    approve(Session, v)
    integration.run_once(Session, now=NOW)
    with Session() as db:
        assert db.get(User, user_id).sponsor_id == sponsor
        with pytest.raises(AffiliateHierarchyError, match="reassignment"):
            validate_sponsor_assignment(db, user_id=user_id, sponsor_id=inviter)
        db.rollback()


def test_the_worker_queue_is_fifo_and_a_failing_referral_does_not_stop_it(pool, monkeypatch):
    Session = pool
    holder(Session, 3)
    first = referral(Session, at=NOW + timedelta(minutes=1))
    broken = referral(Session, at=NOW + timedelta(minutes=2))
    last = referral(Session, at=NOW + timedelta(minutes=3))
    real = alloc.assign

    def flaky(db, referred_user_id, **kw):
        if referred_user_id == broken:
            raise RuntimeError("synthetic failure")
        return real(db, referred_user_id, **kw)

    monkeypatch.setattr(alloc, "assign", flaky)
    results = alloc.process_pending(Session, now=NOW)
    assert [r.outcome for r in results] == [alloc.ASSIGNED, alloc.ERROR, alloc.ASSIGNED]
    with Session() as db:
        p = db.query(ReferralPoolPending).filter_by(referred_user_id=broken).one()
        assert (p.status, p.attempts, p.last_error.startswith("RuntimeError")) == ("WAITING", 1, True)
    monkeypatch.setattr(alloc, "assign", real)
    assert alloc.process_pending(Session, now=NOW)[0].outcome == alloc.ASSIGNED          # retried next pass
    assert first and last


def test_a_failing_event_is_retried_then_failed_and_recoverable(pool, monkeypatch):
    Session = pool
    user_id, v = unverified(Session)
    approve(Session, v)
    monkeypatch.setattr(integration, "handle_event", lambda db, e, now=None: (_ for _ in ()).throw(RuntimeError("x")))
    for _ in range(integration.MAX_ATTEMPTS):
        work(Session)                                                       # one attempt per pass, no tight loop
    with Session() as db:
        e = db.query(ReferralPoolEvent).filter_by(user_id=user_id).one()
        assert (e.status, e.attempts) == ("FAILED", integration.MAX_ATTEMPTS) and "RuntimeError" in e.last_error
        integration.retry_failed_event(db, e.id)
        db.commit()
    monkeypatch.undo()
    work(Session)
    assert events(Session, user_id) == [("KYC_APPROVED", "DONE")]


def test_with_allocation_off_events_are_handled_but_nobody_is_assigned(pool):
    Session = pool
    holder(Session, 2)
    set_allocation(Session, False)
    user_id, v = unverified(Session)
    approve(Session, v)
    integration.run_once(Session, now=NOW)
    assert pending_of(Session, user_id) == ("WAITING", None)
    with Session() as db:
        assert db.get(User, user_id).sponsor_id is None
        assert db.query(ReferralPoolAssignment).count() == 0


# ---------------------------------------------------------------------------
# 3. Second accounts
# ---------------------------------------------------------------------------

def test_a_duplicate_verified_identity_blocks_both_accounts_until_cleared(pool, reviewer):
    Session = pool
    holder(Session, 2)
    same = ("Jane", "Doe", datetime(1985, 3, 4))
    a, va = unverified(Session, identity=same)
    b, vb = unverified(Session, identity=(" jane ", "DOE", datetime(1985, 3, 4)))
    approve(Session, va)
    work(Session)
    add_units(Session, a, 1)
    assert unit_status(Session, a) == {"ACTIVE"}                            # alone so far
    approve(Session, vb)
    work(Session)
    with Session() as db:
        rows = db.query(ReferralPoolRiskReview).filter_by(signal=risk.DUPLICATE_IDENTITY).all()
        assert {r.user_id for r in rows} == {a, b} and all(r.blocking and r.status == "OPEN" for r in rows)
        assert len({r.evidence_hash for r in rows}) == 1 and "jane" not in (rows[0].related_user_ids or "").lower()
        assert units.member_eligibility(db, db.get(User, a)).reason == "RISK_REVIEW"
    integration.sweep_eligibility(Session, now=NOW)
    assert unit_status(Session, a) == {"SUSPENDED"}
    assert alloc.process_pending(Session, now=NOW) == [alloc.Result(alloc.CANCELLED, "RISK_REVIEW")]
    with Session() as db:
        assert db.get(User, b).sponsor_id is None
        for row in db.query(ReferralPoolRiskReview).filter_by(signal=risk.DUPLICATE_IDENTITY).all():
            risk.decide(db, db.get(User, reviewer), row.id, risk.CLEARED, note="Twins, verified by phone",
                        password="x", now=NOW)
    integration.run_once(Session, now=NOW)
    assert unit_status(Session, a) == {"ACTIVE"}
    with Session() as db:
        assert db.get(User, b).sponsor_id is not None                       # re-queued and assigned


def test_a_shared_wallet_or_login_ip_is_recorded_and_never_blocks(pool):
    Session = pool
    a, va = unverified(Session)
    b = member(Session)
    with Session() as db:
        db.get(User, a).usdt_wallet_address = "0xSharedSyntheticWallet"
        db.get(User, b).usdt_wallet_address = " 0xsharedsyntheticwallet "
        db.add(LoginLog(user_id=a, ip_address="203.0.113.77"))
        db.add(LoginLog(user_id=b, ip_address="203.0.113.77"))
        db.commit()
    approve(Session, va)
    work(Session)
    with Session() as db:
        signals = {(r.user_id, r.signal, r.blocking) for r in db.query(ReferralPoolRiskReview)}
        assert {(a, risk.SHARED_WALLET, False), (b, risk.SHARED_WALLET, False),
                (a, risk.SHARED_IP, False), (b, risk.SHARED_IP, False)} <= signals
        assert not risk.is_blocked(db, a) and units.member_eligibility(db, db.get(User, a)).eligible
    assert pending_of(Session, a) == ("WAITING", None)
    with Session() as db:                                                  # the database refuses an IP ban
        with pytest.raises(IntegrityError):
            db.add(ReferralPoolRiskReview(user_id=a, signal=risk.SHARED_IP, evidence_hash="f" * 64, blocking=True))
            db.flush()
        db.rollback()


# ---------------------------------------------------------------------------
# 4. Money stays put
# ---------------------------------------------------------------------------

def test_kyc_and_sponsor_changes_never_duplicate_revenue_or_commission(pool):
    Session = pool
    inviter = member(Session)
    buyer, v = unverified(Session, sponsor=inviter)
    approve(Session, v)
    work(Session)
    add_units(Session, buyer, 3)                                            # earned at once (3 x $100, 3 x $20)
    reject(Session, v)
    work(Session)
    new_attempt(Session, v)
    approve(Session, v)
    work(Session)
    integration.sweep_eligibility(Session, now=NOW)
    with Session() as db:
        ids = [u.id for u in db.query(ReferralPoolUnit).filter_by(user_id=buyer)]
        assert db.query(RevenueRecognition).filter(RevenueRecognition.source_type == "REFERRAL_POOL_UNIT",
                                                   RevenueRecognition.source_id.in_(ids)).count() == 3
        rows = db.query(AffiliateCommission).filter(AffiliateCommission.source_type == "REFERRAL_POOL_UNIT",
                                                    AffiliateCommission.source_id.in_(ids)).all()
        assert len(rows) == 3 and {c.user_id for c in rows} == {inviter}
        assert db.query(AffiliateCashoutRequest).count() == 0               # nothing paid out


def test_worker_passes_leave_historical_assignments_unchanged(pool):
    Session = pool
    legacy_member, legacy_referral = member(Session), member(Session)
    with Session() as db:
        seat = ReferralPoolMembership(user_id=legacy_member, status="ACTIVE", seat_number=1, entitlement_source="PAID",
                                      joined_at=NOW, assignment_eligible=True, assignments_count=1)
        db.add(seat)
        db.flush()
        db.add(ReferralPoolAssignment(referred_user_id=legacy_referral, pool_member_user_id=legacy_member,
                                      membership_id=seat.id, method="FAIR_RANDOM_V1", candidate_count=2,
                                      min_assignment_count=0, assigned_at=NOW))
        db.commit()
    holder(Session, 2)
    user_id, v = unverified(Session)
    approve(Session, v)
    for _ in range(2):
        integration.run_once(Session, now=NOW)
    with Session() as db:
        legacy = db.query(ReferralPoolAssignment).filter_by(referred_user_id=legacy_referral).one()
        assert (legacy.pool_member_user_id, legacy.slot_id, legacy.round_id) == (legacy_member, None, None)
    assert_counters(Session)


def test_the_worker_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("REFERRAL_POOL_WORKER_ENABLED", raising=False)
    assert integration.worker_enabled() is False
    monkeypatch.setenv("REFERRAL_POOL_WORKER_ENABLED", "true")
    assert integration.worker_enabled() is True
    from app.services.scheduler_manager import scheduler_manager

    assert "referral-pool" in scheduler_manager.list_tasks()


def test_the_events_and_reviews_migration_goes_down_and_up_to_the_model_schema(pg):
    from tests.integration.test_payments_postgres import load_migration, migrate
    from tests.integration.test_referral_pool_multiunit_schema_postgres import tables

    engine, _Session = pg
    name = "c1e3a5b7d9f2_referral_pool_events_and_risk_reviews.py"
    module = load_migration(name)
    assert (module.revision, module.down_revision) == ("c1e3a5b7d9f2", "a7c9e1f3b5d2")

    def shape():
        with engine.connect() as c:
            return sorted(tuple(r) for r in c.execute(text(
                "select cl.relname, con.conname, pg_get_constraintdef(con.oid) from pg_constraint con "
                "join pg_class cl on cl.oid = con.conrelid "
                "where cl.relname in ('referral_pool_events', 'referral_pool_risk_reviews')")))

    model = shape()
    migrate(engine, name, "downgrade")
    assert not {"referral_pool_events", "referral_pool_risk_reviews"} & tables(engine)
    migrate(engine, name, "upgrade")
    migrate(engine, name, "upgrade")                                      # re-run: a no-op
    migrate(engine, "e2a4c6e8f0b1_referral_pool_signup_trigger.py", "upgrade")   # SIGNED_UP (2026-10-31)
    assert shape() == model


# ---------------------------------------------------------------------------
# Owner rules 2026-10-31: a sponsorless sign-up is queued at once (no KYC, no e-mail confirmation)
# ---------------------------------------------------------------------------

def signup(Session, personal_sponsor: int | None = None) -> int:
    """A brand-new account (no KYC, e-mail NOT confirmed) through the registration sponsor rule."""
    user_id = member(Session, kyc=False)
    with Session() as db:
        u = db.get(User, user_id)
        u.sponsor_id, u.sponsor_source, u.email_verified = None, None, False
        db.flush()
        assign_at_registration(db, u, db.get(User, personal_sponsor) if personal_sponsor else None)
        db.commit()
    return user_id


def financial_counts(Session) -> tuple:
    with Session() as db:
        return tuple(db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in (
            "deposits", "affiliate_commissions", "kyc_verifications", "affiliate_cashout_requests",
            "referral_pool_purchases", "referral_pool_units"))


def test_a_sponsorless_signup_gets_a_pool_sponsor_without_kyc_or_email_confirmation(pool):
    Session = pool
    h = holder(Session, 1)
    before = financial_counts(Session)
    newcomer = signup(Session)
    assert [e[0] for e in events(Session, newcomer)] == ["SIGNED_UP"]
    integration.run_once(Session, now=NOW)
    with Session() as db:
        u = db.get(User, newcomer)
        assert (u.sponsor_id, u.sponsor_source, u.email_verified, u.identity_verified) == (h, "REFERRAL_POOL", False, False)
        assert crud_kyc.kyc_verification.get_by_user(db, user_id=newcomer) is None          # KYC not approved or created
    assert financial_counts(Session) == before                     # no purchase, commission, payout or KYC row made
    assert_counters(Session)


def test_a_personal_referral_link_keeps_the_direct_sponsor_and_never_enters_the_pool(pool):
    Session = pool
    holder(Session, 3)
    inviter = member(Session)                                               # a valid (KYC-approved) inviter
    invited = signup(Session, personal_sponsor=inviter)
    assert events(Session, invited) == []
    integration.run_once(Session, now=NOW)
    assert pending_of(Session, invited) is None
    with Session() as db:
        assert (db.get(User, invited).sponsor_id, db.get(User, invited).sponsor_source) == (inviter, "PERSONAL_REFERRAL")


def test_duplicate_signup_events_and_worker_passes_assign_once(pool):
    Session = pool
    holder(Session, 2)
    newcomer = signup(Session)
    with Session() as db:
        integration.record_signup(db, db.get(User, newcomer))                 # a repeated callback: deduplicated
        db.commit()
    assert len(events(Session, newcomer)) == 1
    for _ in range(3):
        integration.run_once(Session, now=NOW)
    with Session() as db:
        assert db.query(ReferralPoolAssignment).filter_by(referred_user_id=newcomer).count() == 1
        assert alloc.enqueue(db, newcomer, trigger=alloc.SIGNED_UP, now=NOW) ==             alloc.Result(alloc.NOT_QUEUED, "ALREADY_POOL_ASSIGNED")
        db.rollback()
    assert_counters(Session)


def test_units_weight_the_allocation_1_2_3_of_6_and_a_single_holder_takes_all(pool):
    Session = pool
    solo = holder(Session, 1)
    first = [signup(Session) for _ in range(3)]
    integration.run_once(Session, now=NOW)
    assert received(Session, [solo]) == {solo: 3}                           # the only holder receives every one
    a, b = holder(Session, 2), holder(Session, 3)                           # solo 1 : a 2 : b 3 = 1/6 : 2/6 : 3/6
    with Session() as db:
        assert db.query(ReferralPoolRound).filter_by(status="OPEN").count() == 0
    rest = [signup(Session) for _ in range(12)]                              # two full rounds of 6 slots
    integration.run_once(Session, now=NOW)
    got = received(Session, [solo, a, b])
    assert (got[solo] - 3, got[a], got[b]) == (2, 4, 6)
    with Session() as db:
        assert {db.get(User, n).sponsor_source for n in first + rest} == {"REFERRAL_POOL"}
    assert_counters(Session)


def test_a_dsm_member_keeps_the_imported_sponsor_and_is_never_pool_assigned(pool):
    Session = pool
    holder(Session, 2)
    dsm_sponsor = member(Session, kyc=False)
    with_sponsor, without_sponsor = member(Session, kyc=False), member(Session, kyc=False)
    with Session() as db:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS legacy_import"))
        db.execute(text("CREATE TABLE IF NOT EXISTS legacy_import.dsm_members (dsm_id int, mh5_user_id int)"))
        db.execute(text("INSERT INTO legacy_import.dsm_members VALUES (1, :a), (2, :b)"),
                   {"a": with_sponsor, "b": without_sponsor})
        db.get(User, with_sponsor).sponsor_id, db.get(User, with_sponsor).sponsor_source = dsm_sponsor, "DSM_IMPORT"
        db.get(User, without_sponsor).sponsor_id = None
        db.commit()
    for user_id in (with_sponsor, without_sponsor):
        with Session() as db:
            integration.record_signup(db, db.get(User, user_id))           # even if queued, the pool refuses them
            db.commit()
    integration.run_once(Session, now=NOW)
    with Session() as db:
        assert (db.get(User, with_sponsor).sponsor_id, db.get(User, with_sponsor).sponsor_source) == (dsm_sponsor, "DSM_IMPORT")
        assert db.get(User, without_sponsor).sponsor_id is None              # left for the owner-approved restoration
        assert db.query(ReferralPoolAssignment).count() == 0
        assert alloc.enqueue(db, without_sponsor, trigger=alloc.SIGNED_UP, now=NOW) ==             alloc.Result(alloc.NOT_QUEUED, "DSM_IMPORTED")
        db.rollback()


def test_the_signup_trigger_migration_goes_down_and_up(pg):
    from tests.integration.test_payments_postgres import load_migration, migrate

    engine, _Session = pg
    name = "e2a4c6e8f0b1_referral_pool_signup_trigger.py"
    module = load_migration(name)
    assert (module.revision, module.down_revision) == ("e2a4c6e8f0b1", "d1f3a5b7c9e2")

    def checks():
        with engine.connect() as c:
            return dict(c.execute(text(
                "select conname, pg_get_constraintdef(oid) from pg_constraint where conname in "
                "('ck_referral_pool_event_type', 'ck_referral_pool_pending_trigger')")).all())

    model = checks()
    assert "SIGNED_UP" in model["ck_referral_pool_event_type"] and "SIGNED_UP" in model["ck_referral_pool_pending_trigger"]
    migrate(engine, name, "downgrade")
    assert not any("SIGNED_UP" in v for v in checks().values())
    migrate(engine, name, "upgrade")
    migrate(engine, name, "upgrade")                                      # re-run: a no-op
    assert checks() == model
