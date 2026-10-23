"""KYC decisions (approval / rejection) under real concurrency, on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC.

A decision is one transaction: the verification row and the member's flags are
written together, under the verification's row lock, so a second event can only
ever see the state before it or the state after it, never half of it. The
interleaving tests put the second event exactly in the gap a decision used to
leave open (after its first commit), instead of hoping the scheduler finds it.
"""
from __future__ import annotations

import asyncio
import os
import threading

import pytest
from sqlalchemy import event

from app.crud import crud_kyc
from app.models.email import EmailDelivery
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification
from app.models.user import User
from app.services import kyc_provider_dispatch as dispatch
from tests.integration.test_kaluta_webhook_postgres import open_verification, payload
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

WORKERS = 8
ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))


def deliver(Session, body: dict) -> str:
    with Session() as db:
        return dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=body, ip="203.0.113.9")


def approved(reference: str) -> dict:
    return payload("session.approved", reference, "approved", overall_score=87, scores={"document": 92, "face": 88})


def rejected(reference: str) -> dict:
    return payload("session.rejected", reference, "rejected", rejection_reason="Face does not match the document")


def state(Session, verification_id: int) -> tuple:
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        user = db.get(User, row.user_id)
        return row, user


def assert_consistent(row, user) -> None:
    """What every decision must leave behind, whichever event won."""
    accepted = row.status in (KYCStatus.PENDING_PROOF_OF_ADDRESS, KYCStatus.APPROVED)
    assert row.identity_verified is accepted, (row.status, row.identity_verified)
    assert user.identity_verified is accepted, (row.status, user.identity_verified)
    if row.status == KYCStatus.REJECTED:
        assert row.rejection_reason and row.rejection_details.startswith("kaluta:session:")
        assert user.address_verified is False and row.address_verified is False
    if accepted:
        assert row.rejection_reason is None and row.rejection_details is None


def after_first_commit(db, action):
    """Run `action` (in another thread, with its own session) once, right after
    `db` commits for the first time; the caller of `db` continues afterwards."""
    fired = []

    def hook(_session):
        if fired:
            return
        fired.append(True)
        box: list = []
        t = threading.Thread(target=lambda: box.append(action()))
        t.start()
        t.join(timeout=20)
        assert not t.is_alive(), "the interleaved event is blocked by a lock that should be free"
        fired.append(box[0] if box else None)

    event.listen(db, "after_commit", hook)
    return fired


# ---------------------------------------------------------------------------
# The gap: an approval arriving right after the rejection's first commit
# ---------------------------------------------------------------------------

def test_an_approval_right_after_a_webhook_rejection_commits_leaves_a_consistent_state(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "gapwh")
    with Session() as db:
        fired = after_first_commit(db, lambda: deliver(Session, approved(reference)))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=rejected(reference)) == dispatch.APPLIED
    # The provider's own retry approval after its rejection stands (existing rule).
    assert fired[1] == dispatch.APPLIED
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)


def test_an_approval_right_after_a_polled_rejection_commits_leaves_a_consistent_state(pg, monkeypatch):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "gappoll")

    async def provider_says_rejected(_verification):
        return {"is_valid": True, "is_completed": True, "is_accepted": False,
                "data": {"id": "sess-1", "status": "rejected", "rejection_reason": "Blurred document"}}

    monkeypatch.setattr(dispatch, "check_kyc_session_validity", provider_says_rejected)
    with Session() as db:
        verification = db.get(KYCVerification, verification_id)
        fired = after_first_commit(db, lambda: deliver(Session, approved(reference)))
        result = asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=verification))
    assert result == {"status": "rejected"} and fired[1] == dispatch.APPLIED
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)


def test_a_rejection_right_after_an_approval_commits_is_ignored(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "gapok")
    with Session() as db:
        fired = after_first_commit(db, lambda: deliver(Session, rejected(reference)))
        assert dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=approved(reference)) == dispatch.APPLIED
    assert fired[1] == dispatch.IGNORED
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.verified_first_name is None
    assert row.identity_confidence_score == 87
    assert_consistent(row, user)


# ---------------------------------------------------------------------------
# Orders, duplicates, replays (existing rules, now checked for consistency)
# ---------------------------------------------------------------------------

def test_rejection_then_approval_is_the_providers_retry(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "ra")
    assert deliver(Session, rejected(reference)) == dispatch.APPLIED
    assert_consistent(*state(Session, verification_id))
    assert deliver(Session, approved(reference)) == dispatch.APPLIED
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)


def test_approval_then_a_late_rejection_changes_nothing(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "ar")
    assert deliver(Session, approved(reference)) == dispatch.APPLIED
    assert deliver(Session, rejected(reference)) == dispatch.IGNORED
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)


def test_duplicates_and_replays_are_idempotent(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "dup")
    assert deliver(Session, rejected(reference)) == dispatch.APPLIED
    assert deliver(Session, rejected(reference)) == dispatch.DUPLICATE
    assert deliver(Session, approved(reference)) == dispatch.APPLIED
    for body in (approved(reference), approved(reference)):
        assert deliver(Session, body) == dispatch.DUPLICATE
    assert deliver(Session, rejected(reference)) == dispatch.IGNORED                # delayed rejection
    old = payload("session.rejected", "mh5_0_an_earlier_reference", "rejected")
    old["session"]["id"] = "sess-1"
    assert deliver(Session, old) == dispatch.IGNORED                                # earlier reference
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)
    with Session() as db:
        trail = [a.action for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id)]
        assert trail.count("rejected") == 1 and trail.count("shufti_identity_accepted") == 1
        assert db.query(EmailDelivery).filter(EmailDelivery.user_id == row.user_id).count() == 2


# ---------------------------------------------------------------------------
# Many events at once, repeated
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("round_", range(ROUNDS))
def test_mixed_events_at_once_always_leave_a_consistent_state(pg, round_):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, f"mix{round_}")
    bodies = [rejected(reference), approved(reference),
              payload("session.document_submitted", reference, "processing"), rejected(reference)]
    results = in_threads(WORKERS, lambda i: deliver(Session, bodies[(i + round_) % len(bodies)]))
    assert not [r for r in results if isinstance(r, Exception)], results
    row, user = state(Session, verification_id)
    # Two approvals were delivered: whichever came first, identity ends accepted (existing rules).
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert_consistent(row, user)
    with Session() as db:
        trail = [a.action for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id)]
        assert trail.count("shufti_identity_accepted") == 1 and trail.count("rejected") <= 1


# ---------------------------------------------------------------------------
# A decision that fails is not half-applied, and nobody is told about it
# ---------------------------------------------------------------------------

def test_a_rejection_that_fails_to_commit_changes_nothing_and_sends_nothing(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "fail")

    class Boom(Exception):
        pass

    with Session() as db:
        def refuse(session, _ctx, _instances):
            if any(isinstance(o, KYCVerification) and o.status == KYCStatus.REJECTED for o in session.dirty):
                raise Boom()

        event.listen(db, "before_flush", refuse)
        with pytest.raises(Boom):
            dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=rejected(reference))
        db.rollback()
    row, user = state(Session, verification_id)
    assert row.status == KYCStatus.IN_PROGRESS and row.rejection_reason is None
    assert user.identity_verified is not True
    with Session() as db:
        assert db.query(EmailDelivery).filter(EmailDelivery.user_id == row.user_id).count() == 0
        assert db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id).count() == 0
    # The provider retries the delivery; it then applies normally.
    assert deliver(Session, rejected(reference)) == dispatch.APPLIED
    assert_consistent(*state(Session, verification_id))
