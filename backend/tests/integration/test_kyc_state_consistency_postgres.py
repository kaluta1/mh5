"""KYC state consistency between provider decisions, administrator decisions, the
status poll and proof of address, on a real PostgreSQL server.

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
    def work():
        with Session() as db:
            admin = db.get(User, admin_id)
            try:
                if verb == "approve":
                    kyc_endpoint.approve_kyc_verification(db=db, verification_id=verification_id,
                                                          background_tasks=BackgroundTasks(), current_user=admin)
                else:
                    kyc_endpoint.reject_kyc_verification(db=db, verification_id=verification_id,
                                                         background_tasks=BackgroundTasks(), current_user=admin,
                                                         reason="The photo is too dark to read", details=None)
            except HTTPException:
                db.rollback()
                raise
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
# 2. Administrator decisions against provider decisions
# ---------------------------------------------------------------------------

def test_an_admin_approval_waiting_on_a_provider_rejection_sees_it(pg):
    engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_verification(Session, "adrej")
    with Session() as db:
        started, box = while_first_commit_waits(engine, db, lambda: admin_decides(Session, verification_id, admin_id,
                                                                                  "approve"))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=rejected(reference)) == dispatch.APPLIED
    started[0].join(20)
    assert box == ["400"]                                       # the rejection stands; nothing is overwritten
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and "approved" not in trail
    assert_consistent(row, user)


def test_an_admin_rejection_waiting_on_a_provider_approval_sees_it(pg):
    engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_verification(Session, "adok")
    with Session() as db:
        started, box = while_first_commit_waits(engine, db, lambda: admin_decides(Session, verification_id, admin_id,
                                                                                  "reject"))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc,
                                              payload=approved_with_address(reference)) == dispatch.APPLIED
    started[0].join(20)
    assert box == ["400"]                                       # an approved verification cannot be rejected
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and "rejected" not in trail
    assert_consistent(row, user)


def test_two_admin_approvals_at_once_approve_once(pg):
    engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, _reference = open_verification(Session, "adtwice")
    # The second approval arrives while the first is about to commit.
    started, box = while_first_commit_waits(engine, Session, lambda: admin_decides(Session, verification_id, admin_id,
                                                                                   "approve"))
    first = admin_decides(Session, verification_id, admin_id, "approve")
    started[0].join(20)
    assert (first, box) == ("200", ["400"])
    results = in_threads(4, lambda _i: admin_decides(Session, verification_id, admin_id, "approve"))
    assert results == ["400"] * 4, results
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and trail.count("approved") == 1
    assert_consistent(row, user)


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_admin_and_provider_decisions_at_once_always_leave_a_consistent_state(pg, round_):
    _engine, Session = pg
    admin_id = seed_admin(Session, f"kycadmin{round_}")
    verification_id, reference = open_verification(Session, f"admix{round_}")
    actors = [lambda: deliver(Session, rejected(reference)),
              lambda: deliver(Session, approved(reference)),
              lambda: admin_decides(Session, verification_id, admin_id, "approve"),
              lambda: admin_decides(Session, verification_id, admin_id, "reject")]
    results = in_threads(WORKERS, lambda i: (i % len(actors), outcome(actors[(i + round_) % len(actors)])))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert not [r for _i, r in results if str(r).startswith("sqlstate:")], results
    row, user, trail = state(Session, verification_id)
    assert_consistent(row, user)
    assert trail.count("approved") <= 1
    # An administrator's decision is final against the provider's later events.
    if "approved" in trail:
        assert row.status == KYCStatus.APPROVED
    elif row.status == KYCStatus.REJECTED and not (row.rejection_details or "").startswith("kaluta:session:"):
        assert row.rejection_reason == "The photo is too dark to read"


# ---------------------------------------------------------------------------
# 3. Proof of address: one commit, decided on the row as it is now
# ---------------------------------------------------------------------------

def test_a_provider_approval_with_the_address_leaves_no_gap_for_an_admin_rejection(pg):
    _engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_verification(Session, "poagap")
    with Session() as db:
        fired = after_first_commit(db, lambda: admin_decides(Session, verification_id, admin_id, "reject"))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc,
                                              payload=approved_with_address(reference)) == dispatch.APPLIED
    assert fired[1] == "400"                                    # the first commit already holds the approval
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and "rejected" not in trail
    assert trail.count("shufti_identity_accepted") == 1 and trail.count("proof_of_address_approved") == 1
    assert_consistent(row, user)


@pytest.fixture
def proof_of_address(monkeypatch, pg):
    """The proof-of-address endpoint with its file store and matcher faked.
    `during_upload` runs while the files are being stored (no lock is held there)."""
    _engine, Session = pg
    during_upload: list = []

    async def store(_upload, user_id):
        await asyncio.sleep(0.02)
        for action in during_upload:
            action()
        return {"url": f"local://kyc/{user_id}/proof.pdf"}

    monkeypatch.setattr(kyc_endpoint, "store_kyc_proof_file", store)
    monkeypatch.setattr(kyc_endpoint, "evaluate_proof_of_address", lambda **_k: (True, None))
    monkeypatch.setattr(kyc_endpoint, "_guard_kyc_initiation", lambda *_a, **_k: None)

    def submit(user_id: int) -> str:
        def work():
            with Session() as db:
                user = db.get(User, user_id)
                try:
                    answer = asyncio.run(kyc_endpoint.submit_proof_of_address(
                        db=db, current_user=user, document_type=DocumentType.UTILITY_BILL,
                        name_on_document="Jane Doe", address_as_shown_on_document=ADDRESS,
                        document_front=object(), document_back=None))
                except HTTPException:
                    db.rollback()
                    raise
                return answer["status"]
        return outcome(work)

    return submit, during_upload


def identity_accepted(Session, name: str) -> tuple:
    verification_id, _reference = open_verification(Session, name)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        row.status = KYCStatus.PENDING_PROOF_OF_ADDRESS
        row.identity_verified = row.document_verified = row.face_verified = True
        row.verified_address = ADDRESS
        user = db.get(User, row.user_id)
        user.identity_verified = True
        db.commit()
        return verification_id, row.user_id


def test_an_admin_rejection_during_the_upload_is_not_overwritten_by_the_proof_of_address(pg, proof_of_address):
    _engine, Session = pg
    submit, during_upload = proof_of_address
    admin_id = seed_admin(Session)
    verification_id, user_id = identity_accepted(Session, "poarej")
    during_upload.append(lambda: admin_decides(Session, verification_id, admin_id, "reject"))
    assert submit(user_id) == "400"
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and "proof_of_address_approved" not in trail
    assert_consistent(row, user)
    with Session() as db:
        assert db.query(KYCDocument).filter(KYCDocument.verification_id == verification_id).count() == 0


def test_proof_of_address_submitted_twice_at_once_approves_once(pg, proof_of_address):
    engine, Session = pg
    submit, _during_upload = proof_of_address
    verification_id, user_id = identity_accepted(Session, "poatwice")
    # The second submission arrives while the first is about to commit.
    started, box = while_first_commit_waits(engine, Session, lambda: submit(user_id))
    first = submit(user_id)
    started[0].join(20)
    assert (first, box) == ("approved", ["400"])
    results = in_threads(4, lambda _i: submit(user_id))
    assert results == ["400"] * 4, results
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and trail.count("proof_of_address_approved") == 1
    assert_consistent(row, user)
    with Session() as db:
        documents = db.query(KYCDocument).filter(KYCDocument.verification_id == verification_id).all()
        assert len(documents) == 1 and documents[0].is_verified is True


def test_a_proof_of_address_that_fails_to_commit_leaves_no_document_and_no_approval(pg, proof_of_address):
    engine, Session = pg
    submit, _during_upload = proof_of_address
    verification_id, user_id = identity_accepted(Session, "poafail")

    class Boom(Exception):
        pass

    def refuse(session, _ctx, _instances):
        if any(isinstance(o, KYCVerification) and o.status == KYCStatus.APPROVED for o in session.dirty):
            raise Boom()

    event.listen(Session, "before_flush", refuse)
    try:
        with pytest.raises(Boom):
            submit(user_id)
    finally:
        event.remove(Session, "before_flush", refuse)
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and trail == []
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
              lambda n: admin_decides(Session, verification_id, admin_id, "approve")]
    results = in_threads(WORKERS, lambda i: outcome(lambda: actors[(i + round_) % len(actors)](i)))
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("sqlstate:")], results
    with Session() as db:
        assert db.query(Deposit).filter(Deposit.user_id == user_id).count() <= 1   # never charged twice
    row, user, _trail = state(Session, verification_id)
    assert_consistent(row, user)
