"""KYC is decided by the provider (Kaluta) only.

After the identity is accepted without the address (the provider's proof-of-address
step was off for that session), the member continues with a NEW provider session
for the same attempt, without paying again. Only that session's own signed result
decides: approved when the provider required and passed the proof of address;
rejected when it required it and it failed; nothing decided when it did not check
the address. No administrator and nothing the member types to MyHigh5 decides.
All values are synthetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from app.models.business_model import ReferralPoolEvent
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification
from app.models.payment import Deposit
from app.services import kyc_provider_dispatch as dispatch
from app.services import kyc_settings
from tests.unit.test_kaluta_kyc_integration import (  # noqa: F401  (fixtures: provider, no_real_network)
    FakeProvider, adult, approved, auth, deliver, event, kyc_rows, no_real_network, open_verification, person,
    provider, rejected,
)

pytestmark = pytest.mark.unit

STATUS = "/api/v1/kyc/status-detailed"
ADDRESS_START = "/api/v1/kyc/address/initiate"


def identity_accepted(client, db):
    """A member whose identity the provider accepted in a session without the proof-of-address step."""
    user = adult(db)
    v = open_verification(db, user, session="sess-id")
    assert deliver(client, approved(v, session="sess-id")).json()["result"] == "applied"
    db.expire_all()
    v = db.get(KYCVerification, v.id)
    assert v.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and not v.address_verified
    return user, v


def address_result(v, *, session, poa_required, poa=None, status="approved", name="session.approved"):
    return event(name, v, session=session, status=status, overall_score=80,
                 scores={"document": 90, "face": 88, "liveness": None, "poa": poa},
                 checks_required={"liveness": False, "proof_of_address": poa_required})


def pool_events(db, v):
    return sorted((e.event_type, e.dedupe_key) for e in db.query(ReferralPoolEvent)
                  .filter(ReferralPoolEvent.kyc_verification_id == v.id))


def start_address(client, monkeypatch, user, db):
    fake = FakeProvider(monkeypatch)
    answer = client.post(ADDRESS_START, headers=auth(user))
    assert answer.status_code == 200, answer.text
    db.expire_all()
    return fake, answer.json(), kyc_rows(db, user)[0]


def test_the_address_step_is_offered_by_the_provider_and_nothing_else_approves_it(client, db):
    user, v = identity_accepted(client, db)
    view = client.get(STATUS, headers=auth(user)).json()
    assert view["needs_proof_of_address"] is True
    assert view["address_step"] == {"provider": "kaluta", "session_open": False, "verification_url": None,
                                    "sessions_left": 1, "address_not_checked": False}
    # The self-declared proof of address is retired: typed text and an upload never approve.
    upload = client.post("/api/v1/kyc/proof-of-address", headers=auth(user),
                         data={"document_type": "utility_bill", "name_on_document": "Jane Doe",
                               "address_as_shown_on_document": "1 Synthetic Street, Testville"},
                         files={"document_front": ("bill.png", b"\x89PNG synthetic", "image/png")})
    assert upload.status_code == 410 and upload.json()["detail"]["code"] == "KYC_DECIDED_BY_PROVIDER"
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert pool_events(db, v) == []


def test_the_address_session_is_free_counted_and_handed_out_again_while_open(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    old_reference, deposits = v.reference_id, db.query(Deposit).count()
    fake, body, row = start_address(client, monkeypatch, user, db)
    assert body["reused"] is False and body["verification_url"] == "https://kalutakyc.com/verify/sess-1"
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.reference_id != old_reference
    assert row.external_verification_id == "sess-1" and row.attempts_count == 1
    assert db.query(Deposit).count() == deposits                         # no payment
    assert fake.requests[0]["json"]["external_id"] == row.reference_id
    again = client.post(ADDRESS_START, headers=auth(user))
    assert again.status_code == 200 and again.json()["reused"] is True and len(fake.requests) == 1
    view = client.get(STATUS, headers=auth(user)).json()["address_step"]
    assert view["session_open"] is True and view["verification_url"] == "https://kalutakyc.com/verify/sess-1"


def test_a_passed_provider_proof_of_address_approves_once_and_reaches_the_pool_worker_once(client, db, monkeypatch):
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    user, v = identity_accepted(client, db)
    _, _, row = start_address(client, monkeypatch, user, db)
    result = address_result(row, session="sess-1", poa_required=True, poa=85)
    assert deliver(client, result).json()["result"] == "applied"
    again = dict(result, event="session.verified")                        # the provider's alias, and a retry
    assert deliver(client, again).json()["result"] == "duplicate"
    assert deliver(client, result).json()["result"] == "duplicate"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.APPROVED and row.address_verified and row.processed_at is not None
    assert pool_events(db, v) == [("KYC_APPROVED", f"KYC_APPROVED:{v.id}:1")]


def test_a_failed_provider_proof_of_address_rejects_under_the_retry_policy(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    _, _, row = start_address(client, monkeypatch, user, db)
    assert deliver(client, address_result(row, session="sess-1", poa_required=True, poa=40)).json()["result"] == "applied"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.REJECTED and not row.address_verified and not row.identity_verified
    assert pool_events(db, v) == [("KYC_REJECTED", f"KYC_REJECTED:{v.id}:1")]
    # The existing policy: a new attempt (paid unless KYC is free) from the identity step.
    view = client.get(STATUS, headers=auth(user)).json()
    assert view["status"] == "rejected" and view["address_step"] is None


def test_a_provider_rejection_of_the_address_session_rejects(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    _, _, row = start_address(client, monkeypatch, user, db)
    assert deliver(client, rejected(row, session="sess-1")).json()["result"] == "applied"
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.REJECTED
    assert pool_events(db, v) == [("KYC_REJECTED", f"KYC_REJECTED:{v.id}:1")]


def test_an_address_session_the_provider_did_not_check_decides_nothing_and_opens_no_more(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    fake, _, row = start_address(client, monkeypatch, user, db)
    result = address_result(row, session="sess-1", poa_required=False)
    assert deliver(client, result).json()["result"] == "ignored"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and not row.address_verified
    assert pool_events(db, v) == []
    view = client.get(STATUS, headers=auth(user)).json()["address_step"]
    assert view == {"provider": "kaluta", "session_open": False, "verification_url": None,
                    "sessions_left": 0, "address_not_checked": True}
    refused = client.post(ADDRESS_START, headers=auth(user))
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "KYC_ADDRESS_CHECK_NOT_AVAILABLE"
    assert len(fake.requests) == 1                                         # no second paid provider session

    # Once the provider's step is switched on, an administrator allows ONE more session (not a decision).
    monkeypatch.setattr(kyc_settings, "authorize", lambda actor, password: None)
    admin = person(db, 40, admin=True)
    granted = kyc_settings.grant_session(db, admin, v.id, password="unused")
    assert granted["sessions_left"] == 1
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert client.post(ADDRESS_START, headers=auth(user)).status_code == 200 and len(fake.requests) == 2


def test_late_events_of_the_identity_session_never_decide_the_address_step(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    identity_reference = v.reference_id
    _, _, row = start_address(client, monkeypatch, user, db)
    late = address_result(row, session="sess-id", poa_required=True, poa=99)
    late["session"]["external_id"] = identity_reference
    assert deliver(client, late).json()["result"] in ("ignored", "unknown")
    late_rejection = rejected(row, session="sess-id")
    late_rejection["session"]["external_id"] = identity_reference
    deliver(client, late_rejection)
    db.expire_all()
    assert db.get(KYCVerification, v.id).status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    assert pool_events(db, v) == []


def test_an_address_session_opened_after_a_timeout_is_adopted_without_leaving_the_step(client, db, monkeypatch):
    user, v = identity_accepted(client, db)
    FakeProvider(monkeypatch, error=httpx.ReadTimeout("synthetic timeout"))
    assert client.post(ADDRESS_START, headers=auth(user)).status_code == 503
    db.expire_all()
    row = kyc_rows(db, user)[0]
    created = event("session.created", row, session="sess-late", status="created",
                    expires_at=(datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert deliver(client, created).json()["result"] == "applied"
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert (row.status, row.external_verification_id, row.verification_url) == (
        KYCStatus.PENDING_PROOF_OF_ADDRESS, "sess-late", "https://kalutakyc.com/verify/sess-late")
    again = client.post(ADDRESS_START, headers=auth(user))
    assert again.status_code == 200 and again.json()["verification_url"] == "https://kalutakyc.com/verify/sess-late"


def test_the_provider_verifying_identity_and_address_in_one_session_approves_directly(client, db, monkeypatch):
    monkeypatch.setattr("app.services.payment_accounting.payment_accounting.post_kyc_verification_recognition_for_user",
                        lambda *a, **k: True)
    user = adult(db)
    v = open_verification(db, user, session="sess-one")
    payload = address_result(v, session="sess-one", poa_required=True, poa=88)
    assert deliver(client, payload).json()["result"] == "applied"
    db.expire_all()
    row = db.get(KYCVerification, v.id)
    assert row.status == KYCStatus.APPROVED and row.address_verified
    assert pool_events(db, v) == [("KYC_APPROVED", f"KYC_APPROVED:{v.id}:1")]


def test_no_route_decides_or_overrides_a_kyc_by_hand(client, db):
    admin, member = person(db, 40, admin=True), adult(db)
    v = open_verification(db, member)
    for path in (f"/api/v1/kyc/admin/verification/{v.id}/approve", f"/api/v1/kyc/admin/verification/{v.id}/reject"):
        assert client.post(path, headers=auth(member)).status_code == 403          # an ordinary member: refused first
        gone = client.post(path, headers=auth(admin), data={"reason": "synthetic"})
        assert gone.status_code == 410 and gone.json()["detail"]["code"] == "KYC_DECIDED_BY_PROVIDER"
    for action in ("verify", "unverify"):
        assert client.put(f"/api/v1/admin/users/{member.id}/kyc/{action}", headers=auth(admin)).status_code == 410
    assert client.post("/api/v1/kyc/submit", headers=auth(member), json={}).status_code == 410
    assert client.post(f"/api/v1/kyc/verification/{v.id}/upload-document", headers=auth(member)).status_code == 410
    db.expire_all()
    row, user = db.get(KYCVerification, v.id), db.get(type(member), member.id)
    assert row.status == KYCStatus.IN_PROGRESS and not user.identity_verified
    assert db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == v.id,
                                        KYCAuditLog.performed_by_admin.is_(True)).count() == 0
