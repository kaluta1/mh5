"""A rejected identity is never verified, and the legacy Shufti Pro webhook decides
like every other KYC path, on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC; nothing
leaves the process (the Shufti signature check is faked).

The Shufti webhook takes the locks of every KYC decision (member, then verification),
decides on the row as it is then, ignores a delivery for a reference a new start has
replaced, and writes a rejection in one commit.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.api_v1.endpoints import kyc as kyc_endpoint
from app.crud import crud_kyc
from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider
from app.services import kyc_provider_dispatch as dispatch
from tests.integration.test_kaluta_webhook_postgres import open_verification, payload
from tests.integration.test_kyc_decision_race_postgres import after_first_commit, deliver
from tests.integration.test_kyc_state_consistency_postgres import (
    admin_decides, assert_consistent, outcome, seed_admin, state, while_first_commit_waits,
)
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

WORKERS = 8
ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))
HIGH_SCORES = {"document": 95, "face": 93}
# Shufti reports each service; here document and face passed although the whole verification was declined.
PASSED_SERVICES = {"document": "accepted", "face": "accepted"}


# ---------------------------------------------------------------------------
# 1. A provider rejection never leaves identity_verified True
# ---------------------------------------------------------------------------

def test_a_kaluta_webhook_rejection_with_high_scores_is_not_identity_verified(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "hiscorewh")
    body = payload("session.rejected", reference, "rejected", overall_score=94, scores=HIGH_SCORES,
                   rejection_reason="Document expired")
    assert deliver(Session, body) == dispatch.APPLIED
    row, user, _trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and row.identity_verified is False
    assert (row.document_verified, row.face_verified) == (True, True)       # what the provider reported, kept
    assert json.loads(row.provider_response)["scores"] == HIGH_SCORES       # the raw scores, kept for audit
    assert_consistent(row, user)


def test_a_polled_rejection_with_high_scores_is_not_identity_verified(pg, monkeypatch):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "hiscorepoll")

    async def provider_says_rejected(_verification):
        return {"is_valid": False, "is_completed": True, "is_accepted": False,
                "data": {"id": "sess-1", "external_id": reference, "status": "rejected",
                         "scores": HIGH_SCORES, "rejection_reason": "Document expired"}}

    monkeypatch.setattr(dispatch, "check_kyc_session_validity", provider_says_rejected)
    with Session() as db:
        verification = db.get(KYCVerification, verification_id)
        assert asyncio.run(dispatch.sync_verification_from_provider(
            db, crud_kyc=crud_kyc, verification=verification)) == {"status": "rejected"}
    row, user, _trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and row.identity_verified is False
    assert json.loads(row.provider_response)["scores"] == HIGH_SCORES
    assert_consistent(row, user)


# ---------------------------------------------------------------------------
# 2. The legacy Shufti Pro webhook
# ---------------------------------------------------------------------------

@pytest.fixture
def shufti(monkeypatch):
    """The Shufti webhook switched on, with its signature check faked."""
    monkeypatch.setattr(kyc_endpoint, "active_kyc_provider", lambda: "shufti_pro")
    monkeypatch.setattr(kyc_endpoint.shufti_pro_service, "verify_webhook_signature", lambda *_a, **_k: True)


def open_shufti(Session, name: str) -> tuple:
    verification_id, _kaluta_reference = open_verification(Session, name)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        row.provider = VerificationProvider.SHUFTI_PRO
        row.reference_id = f"SP-{name}"
        row.external_verification_id = row.reference_id
        db.commit()
        return verification_id, row.reference_id


def shufti_event(reference: str, event: str, **fields) -> dict:
    return {"reference": reference, "event": event, **fields}


def shufti_deliver(Session, body: dict) -> str:
    raw = json.dumps(body).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    def work():
        request = Request({"type": "http", "method": "POST", "path": "/api/v1/kyc/webhook/shufti-pro",
                           "headers": [(b"signature", b"synthetic")]}, receive)
        with Session() as db:
            return asyncio.run(kyc_endpoint.shufti_pro_webhook(request=request, db=db)).message
    return outcome(work)


def accepted(reference: str) -> dict:
    return shufti_event(reference, "verification.accepted", verification_result=PASSED_SERVICES)


def declined(reference: str) -> dict:
    return shufti_event(reference, "verification.declined", verification_result=PASSED_SERVICES,
                        declined_reason="Face does not match the document")


def test_a_shufti_rejection_is_one_commit_and_never_identity_verified(pg, shufti):
    _engine, Session = pg
    verification_id, reference = open_shufti(Session, "spdecl")
    assert shufti_deliver(Session, declined(reference)) == "Webhook processed successfully"
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.REJECTED and row.identity_verified is False
    assert row.rejection_reason == "Face does not match the document"
    assert "accepted" in (row.provider_response or "") and (row.document_verified, row.face_verified) == (True, True)
    assert trail.count("rejected") == 1
    assert_consistent(row, user)
    assert shufti_deliver(Session, declined(reference)) == "Webhook already processed"


def test_a_shufti_acceptance_right_after_its_rejection_commits_leaves_a_consistent_state(pg, shufti):
    """The acceptance lands exactly where the rejection used to commit twice."""
    _engine, Session = pg
    verification_id, reference = open_shufti(Session, "spgap")
    with Session() as db:
        fired = after_first_commit(db, lambda: shufti_deliver(Session, accepted(reference)))
        request_body = declined(reference)
        raw = json.dumps(request_body).encode("utf-8")

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
        assert asyncio.run(kyc_endpoint.shufti_pro_webhook(request=request, db=db)).message \
            == "Webhook processed successfully"
    # Shufti accepting after its own rejection stands (existing rule): one transition each, never half of one.
    assert fired[1] == "Webhook processed successfully"
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.rejection_reason is None
    assert_consistent(row, user)


def test_the_same_shufti_acceptance_delivered_twice_at_once_is_applied_once(pg, shufti):
    engine, Session = pg
    verification_id, reference = open_shufti(Session, "sptwice")
    started, box = while_first_commit_waits(engine, Session, lambda: shufti_deliver(Session, accepted(reference)))
    first = shufti_deliver(Session, accepted(reference))
    started[0].join(20)
    assert (first, box) == ("Webhook processed successfully", ["Webhook already processed"])
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and trail.count("shufti_identity_accepted") == 1
    assert_consistent(row, user)


def test_a_shufti_rejection_waiting_on_an_admin_approval_sees_it(pg, shufti):
    engine, Session = pg
    admin_id = seed_admin(Session)
    verification_id, reference = open_shufti(Session, "spadmin")
    started, box = while_first_commit_waits(engine, Session, lambda: shufti_deliver(Session, declined(reference)))
    assert admin_decides(Session, verification_id, admin_id, "approve") == "200"
    started[0].join(20)
    assert box == ["Stale webhook ignored"]                         # an approved verification is not rejected
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.APPROVED and "rejected" not in trail
    assert_consistent(row, user)


@pytest.mark.parametrize("event", ["accepted", "declined"])
def test_a_shufti_decision_for_a_reference_replaced_by_a_new_start_changes_nothing(pg, shufti, monkeypatch, event):
    _engine, Session = pg
    verification_id, reference = open_shufti(Session, f"spstale{event[:3]}")
    found = crud_kyc.kyc_verification.get_by_reference

    def found_then_restarted(db, *, reference_id):
        row = found(db, reference_id=reference_id)
        # The member starts again right after the delivery found the verification: a new reference.
        with Session() as other:
            restarted = other.get(KYCVerification, verification_id)
            restarted.reference_id = f"{reference}-NEW"
            restarted.external_verification_id = restarted.reference_id
            restarted.status = KYCStatus.PENDING
            other.commit()
        return row

    monkeypatch.setattr(crud_kyc.kyc_verification, "get_by_reference", found_then_restarted)
    body = accepted(reference) if event == "accepted" else declined(reference)
    assert shufti_deliver(Session, body) == "Stale webhook ignored"
    row, user, trail = state(Session, verification_id)
    assert row.status == KYCStatus.PENDING and row.reference_id == f"{reference}-NEW" and trail == []
    assert row.rejection_reason is None and user.identity_verified is not True


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_shufti_and_admin_decisions_at_once_always_leave_a_consistent_state(pg, shufti, round_):
    _engine, Session = pg
    admin_id = seed_admin(Session, f"spadmin{round_}")
    verification_id, reference = open_shufti(Session, f"spmix{round_}")
    actors = [lambda: shufti_deliver(Session, declined(reference)),
              lambda: shufti_deliver(Session, accepted(reference)),
              lambda: admin_decides(Session, verification_id, admin_id, "approve"),
              lambda: admin_decides(Session, verification_id, admin_id, "reject"),
              lambda: shufti_deliver(Session, accepted(reference))]
    results = in_threads(WORKERS, lambda i: actors[(i + round_) % len(actors)]())
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("sqlstate:")], results
    row, user, trail = state(Session, verification_id)
    assert_consistent(row, user)
    assert trail.count("approved") <= 1
    if "approved" in trail:
        assert row.status == KYCStatus.APPROVED                     # nothing moves an approval
