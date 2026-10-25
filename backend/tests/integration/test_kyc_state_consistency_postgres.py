"""KYC state consistency between provider decisions, the retired administrator
routes, the status poll and the provider's proof-of-address step, on a real
PostgreSQL server. KYC is decided by the provider only.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC; the KYC
provider is a fake and nothing leaves the process.

Every KYC decision is taken under the same two locks (member, then verification),
on the row as it is then, and is written in one commit. The interleaving tests put
the second actor exactly where a decision used to leave a gap: inside a provider
call, between two commits, or while the first decision waits to commit.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from app.api.api_v1.endpoints import kyc as kyc_endpoint
from app.crud import crud_kyc
from app.models.kyc import DocumentType, KYCAuditLog, KYCDocument, KYCStatus, KYCVerification
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import kyc_fee
from app.services import kyc_provider_dispatch as dispatch
from tests.integration.test_kaluta_webhook_postgres import open_verification, payload
from tests.integration.test_kyc_decision_race_postgres import after_first_commit, approved, deliver, rejected
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

WORKERS = 8
ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))
ADDRESS = "12 Synthetic Street, Testville"


def outcome(work):
    """What a call ended with: its value, an HTTP status, or a database error by SQLSTATE (40P01 = deadlock)."""
    try:
        return work()
    except HTTPException as exc:
        return str(exc.status_code)
    except DBAPIError as exc:
        return f"sqlstate:{getattr(exc.orig, 'pgcode', None)}"


def seed_admin(Session, name: str = "kycadmin") -> int:
    with Session() as db:
        admin = User(email=f"{name}@example.com", username=name, hashed_password="x", is_active=True, is_deleted=False,
                     date_of_birth=datetime(1980, 1, 1), personal_referral_code=name.upper(), email_verified=True,
                     is_admin=True)
        db.add(admin)
        db.commit()
        return admin.id


def admin_decides(Session, verification_id: int, admin_id: int, verb: str) -> str:
    """The retired administrator route: refused (410) for everybody, and it touches nothing."""
    def work():
        with Session() as db:
            admin = db.get(User, admin_id)
            route = (kyc_endpoint.approve_kyc_verification if verb == "approve"
                     else kyc_endpoint.reject_kyc_verification)
            route(current_user=admin)
            return "200"
    return outcome(work)


def approved_with_address(reference: str) -> dict:
    return payload("session.approved", reference, "approved", checks_required={"proof_of_address": True},
                   overall_score=90, scores={"document": 90, "face": 90, "poa": 90})


def state(Session, verification_id: int) -> tuple:
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        user = db.get(User, row.user_id)
        trail = [a.action for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id)]
        return row, user, trail


def assert_consistent(row, user) -> None:
    """The verification and the member's flags always describe the same state."""
    if row.status == KYCStatus.APPROVED:
        assert (row.identity_verified, row.address_verified) == (True, True), row.status
        assert (user.identity_verified, user.address_verified) == (True, True), row.status
        assert row.rejection_reason is None
    elif row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS:
        assert (row.identity_verified, row.address_verified) == (True, False), row.status
        assert (user.identity_verified, user.address_verified) == (True, False), row.status
    elif row.status == KYCStatus.REJECTED:
        assert row.address_verified is False and row.rejection_reason
        assert (user.identity_verified, user.address_verified) == (False, False), row.status
    else:
        assert user.identity_verified is not True and user.address_verified is not True, row.status


def while_first_commit_waits(engine, db, action):
    """Start `action` (another thread, own session) when `db` (a session, or the
    sessionmaker: then the first commit of any session) is about to commit for
    the first time, and let that commit go on only once the action waits on a
    row lock (or has finished). Returns (thread, box); join the thread afterwards."""
    box: list = []
    started: list = []

    def lock_waiters() -> int:
        with engine.connect() as conn:
            return conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                     "AND wait_event_type = 'Lock'")).scalar()

    def hook(_session):
        if started:
            return
        t = threading.Thread(target=lambda: box.append(action()))
        started.append(t)
        t.start()
        deadline = time.monotonic() + 10
        while t.is_alive() and lock_waiters() == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert time.monotonic() < deadline, "the second actor neither waited on a lock nor finished"

    event.listen(db, "before_commit", hook)
    return started, box


# ---------------------------------------------------------------------------
# 1. A poll answer about a replaced session never decides the new one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("session_saved", [True, False], ids=["new-session-saved", "new-reference-only"])
@pytest.mark.parametrize("answer", ["approved", "rejected", "expired"])
def test_a_poll_answer_about_a_replaced_session_never_decides_the_new_one(pg, monkeypatch, answer, session_saved):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, f"st{answer[:3]}{int(session_saved)}")
    new_reference = f"{reference}_restarted"

    async def provider_answers(_verification):
        # While the provider is asked about sess-1, the member starts again: a new
        # reference at once, its new session saved when the provider confirms it.
        with Session() as other:
            row = other.get(KYCVerification, verification_id)
            row.reference_id = new_reference
            row.status = KYCStatus.PENDING
            row.verification_url = None
            row.expires_at = None
            if session_saved:
                row.external_verification_id = "sess-2"
                row.verification_url = "https://kalutakyc.com/verify/sess-2"
                row.status = KYCStatus.IN_PROGRESS
                row.expires_at = datetime.utcnow() + timedelta(hours=24)
            other.commit()
        return {"is_valid": False, "is_completed": True, "is_accepted": answer == "approved",
                "expired": answer == "expired",
                "data": {"id": "sess-1", "external_id": reference, "status": answer,
                         "rejection_reason": "Blurred document"}}

    monkeypatch.setattr(dispatch, "check_kyc_session_validity", provider_answers)
    with Session() as db:
        verification = db.get(KYCVerification, verification_id)
        assert asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc,
                                                                    verification=verification)) is None
    row, user, trail = state(Session, verification_id)
    assert row.reference_id == new_reference and trail == []
    assert row.status == (KYCStatus.IN_PROGRESS if session_saved else KYCStatus.PENDING)
    assert row.rejection_reason is None and row.identity_verified is not True and user.identity_verified is not True
    assert (row.expires_at is None) is (not session_saved)          # the new session was not marked as ended


def test_a_poll_answer_about_the_current_session_still_applies(pg, monkeypatch):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "stcur")

    async def provider_answers(_verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": True,
                "data": {"id": "sess-1", "external_id": reference, "status": "approved"}}

    monkeypatch.setattr(dispatch, "check_kyc_session_validity", provider_answers)
    with Session() as db:
        verification = db.get(KYCVerification, verification_id)
        result = asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=verification))
    assert result["needs_proof_of_address"] is True
    row, user, _trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)


# ---------------------------------------------------------------------------
# 2. The retired administrator routes against provider decisions
# ---------------------------------------------------------------------------

def test_a_retired_admin_route_waiting_on_a_provider_decision_changes_nothing(pg):
    engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_verification(Session, "adrej")
    with Session() as db:
        started, box = while_first_commit_waits(engine, db, lambda: admin_decides(Session, verification_id, admin_id,
                                                                                  "approve"))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=rejected(reference)) == dispatch.APPLIED
    started[0].join(20)
    assert box == ["410"]
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and "approved" not in trail
    assert_consistent(row, user)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_provider_decisions_at_once_always_leave_a_consistent_state(pg, round_):
    _engine, Session = pg
    admin_id = seed_admin(Session, f"kycadmin{round_}")
    verification_id, reference = open_verification(Session, f"admix{round_}")
    actors = [lambda: deliver(Session, rejected(reference)),
              lambda: deliver(Session, approved(reference)),
              lambda: deliver(Session, approved_with_address(reference)),
              lambda: admin_decides(Session, verification_id, admin_id, "reject")]
    results = in_threads(WORKERS, lambda i: (i % len(actors), outcome(actors[(i + round_) % len(actors)])))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert not [r for _i, r in results if str(r).startswith("sqlstate:")], results
    assert not [r for _i, r in results if r == "200"], results          # no administrator decided anything
    row, user, trail = state(Session, verification_id)
    assert_consistent(row, user)
    with Session() as db:                                                  # nothing was decided by an administrator
        assert db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id,
                                            KYCAuditLog.performed_by_admin.is_(True)).count() == 0
    assert trail.count("proof_of_address_approved") <= 1
    assert pool_events(Session, verification_id) in ([], ["KYC_APPROVED"], ["KYC_REJECTED"])


# ---------------------------------------------------------------------------
# 3. The provider's proof-of-address step: one commit, decided on the row as it is now
# ---------------------------------------------------------------------------

def pool_events(Session, verification_id: int) -> list:
    with Session() as db:
        return sorted(r[0] for r in db.execute(text(
            "SELECT event_type FROM referral_pool_events WHERE kyc_verification_id = :v"), {"v": verification_id}))


def test_a_provider_approval_with_the_address_leaves_no_gap(pg):
    _engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_verification(Session, "poagap")
    with Session() as db:
        fired = after_first_commit(db, lambda: admin_decides(Session, verification_id, admin_id, "reject"))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc,
                                              payload=approved_with_address(reference)) == dispatch.APPLIED
    assert fired[1] == "410"
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and "rejected" not in trail
    assert trail.count("shufti_identity_accepted") == 1 and trail.count("proof_of_address_approved") == 1
    assert_consistent(row, user)
    assert pool_events(Session, verification_id) == ["KYC_APPROVED"]


def in_address_step(Session, name: str) -> tuple:
    """Identity accepted by the provider without the address, then a provider address session
    asked for under a new reference (what POST /kyc/address/initiate records)."""
    verification_id, reference = open_verification(Session, name)
    assert deliver(Session, approved(reference)) == dispatch.APPLIED
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
        db.add(KYCAuditLog(verification_id=row.id, action=dispatch.ADDRESS_SESSION_STARTED, details="synthetic",
                           old_status=row.status.value, new_status=row.status.value, performed_by_admin=False,
                           timestamp=datetime.utcnow() + timedelta(seconds=1)))
        row.reference_id = f"{reference}_address"
        row.external_verification_id = "sess-addr"
        row.verification_url = "https://kalutakyc.com/verify/sess-addr"
        db.commit()
        return verification_id, row.reference_id


def address_approved(reference: str) -> dict:
    body = approved_with_address(reference)
    body["session"]["id"] = "sess-addr"
    return body


def test_the_address_session_approval_delivered_at_once_approves_once_with_one_pool_event(pg, monkeypatch):
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    _engine, Session = pg
    verification_id, reference = in_address_step(Session, "addronce")
    results = in_threads(WORKERS, lambda _i: outcome(lambda: deliver(Session, address_approved(reference))))
    assert sorted(results) == [dispatch.APPLIED] + [dispatch.DUPLICATE] * (WORKERS - 1), results
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and trail.count("proof_of_address_approved") == 1
    assert_consistent(row, user)
    assert pool_events(Session, verification_id) == ["KYC_APPROVED"]


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_an_address_approval_and_rejection_at_once_leave_one_decision(pg, monkeypatch, round_):
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    _engine, Session = pg
    verification_id, reference = in_address_step(Session, f"addrmix{round_}")
    rejection = rejected(reference)
    rejection["session"]["id"] = "sess-addr"
    actors = [lambda: deliver(Session, address_approved(reference)), lambda: deliver(Session, rejection)]
    results = in_threads(WORKERS, lambda i: outcome(actors[(i + round_) % len(actors)]))
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("sqlstate:")], results
    row, user, _trail = state(Session, verification_id)
    assert row.status in (KYCStatus.APPROVED, KYCStatus.REJECTED)
    assert_consistent(row, user)
    assert pool_events(Session, verification_id) == ["KYC_" + row.status.value.upper()]


def test_the_retired_proof_of_address_upload_changes_nothing(pg):
    _engine, Session = pg
    verification_id, _reference = in_address_step(Session, "poaretired")
    with pytest.raises(HTTPException) as refused:
        kyc_endpoint.submit_proof_of_address()
    assert refused.value.status_code == 410
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and "proof_of_address_approved" not in trail
    assert_consistent(row, user)
    with Session() as db:
        assert db.query(KYCDocument).filter(KYCDocument.verification_id == verification_id).count() == 0


# ---------------------------------------------------------------------------
# 4. A KYC payment against decisions on the same member (lock review, no change)
# ---------------------------------------------------------------------------

def create_kyc_payment(Session, user_id: int, n: int) -> str:
    def work():
        with Session() as db:
            refusal = kyc_fee.payment_refusal(db, user_id, lock=True)
            if refusal:
                db.rollback()
                return refusal[0]
            product = db.query(ProductType).filter(ProductType.code == kyc_fee.PRODUCT_CODE).one()
            db.add(Deposit(user_id=user_id, product_type_id=product.id, amount=Decimal("10.00"), currency="USD",
                           order_id=f"kyc-race-{user_id}-{n}-{time.monotonic_ns()}", status=DepositStatus.PENDING))
            db.commit()
            return "created"
    return outcome(work)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_kyc_payments_and_decisions_on_one_member_never_deadlock(pg, round_):
    _engine, Session = pg
    admin_id = seed_admin(Session, f"payadmin{round_}")
    verification_id, reference = open_verification(Session, f"paymix{round_}")
    with Session() as db:
        if db.query(ProductType).filter(ProductType.code == kyc_fee.PRODUCT_CODE).first() is None:
            db.add(ProductType(code=kyc_fee.PRODUCT_CODE, name="KYC", price=Decimal("10.00"), currency="USD",
                               is_active=True))
            db.commit()
        user_id = db.get(KYCVerification, verification_id).user_id
    assert deliver(Session, rejected(reference)) == dispatch.APPLIED    # a new attempt now needs a new payment
    actors = [lambda n: create_kyc_payment(Session, user_id, n),
              lambda n: deliver(Session, approved(reference)),
              lambda n: create_kyc_payment(Session, user_id, n),
              lambda n: deliver(Session, approved_with_address(reference))]
    results = in_threads(WORKERS, lambda i: outcome(lambda: actors[(i + round_) % len(actors)](i)))
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("sqlstate:")], results
    with Session() as db:
        assert db.query(Deposit).filter(Deposit.user_id == user_id).count() <= 1   # never charged twice
    row, user, _trail = state(Session, verification_id)
    assert_consistent(row, user)
