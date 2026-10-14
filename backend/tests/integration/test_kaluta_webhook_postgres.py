"""Kaluta webhook under real concurrency, on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. SQLite serialises writes and
ignores row locks, so "the same delivery arriving several times at once is
applied once" can only be proven here. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from app.crud import crud_kyc
from app.models.email import EmailDelivery
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, VerificationProvider
from app.models.user import User
from app.services import kyc_provider_dispatch as dispatch
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

WORKERS = 8


def open_verification(Session, name: str) -> tuple:
    with Session() as db:
        user = User(email=f"{name}@example.com", username=name, hashed_password="x", is_active=True, is_deleted=False,
                    date_of_birth=datetime(1990, 1, 1), personal_referral_code=name.upper(), email_verified=True)
        db.add(user)
        db.flush()
        row = KYCVerification(user_id=user.id, status=KYCStatus.IN_PROGRESS, provider=VerificationProvider.KALUTA,
                              reference_id=f"mh5_{user.id}_{name}", external_verification_id="sess-1", attempts_count=1,
                              verification_url="https://kalutakyc.com/verify/sess-1",
                              expires_at=datetime.utcnow() + timedelta(hours=24))
        db.add(row)
        db.commit()
        return row.id, row.reference_id


def payload(event: str, reference: str, status: str, **fields) -> dict:
    return {"event": event, "timestamp": "2026-10-13T12:00:00Z",
            "session": {"id": "sess-1", "external_id": reference, "status": status, **fields}}


def outcomes(Session, body: dict) -> list:
    def work(_i):
        with Session() as db:
            return dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=body, ip="203.0.113.9")

    results = in_threads(WORKERS, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    return sorted(results)


def test_the_same_approval_delivered_at_once_is_applied_once(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "approved")
    body = payload("session.approved", reference, "approved", overall_score=87, scores={"document": 92, "face": 88},
                   identity={"first_name": "Jane", "last_name": "Doe"})
    assert outcomes(Session, body) == [dispatch.APPLIED] + [dispatch.DUPLICATE] * (WORKERS - 1)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        assert row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS and row.identity_verified is True
        trail = db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == verification_id).all()
        assert [a.action for a in trail].count("shufti_identity_accepted") == 1        # the transition itself, once
        assert sum(a.details.startswith("applied") for a in trail) == 1
        assert sum(a.details.startswith("duplicate") for a in trail) == WORKERS - 1
        assert db.query(EmailDelivery).filter(EmailDelivery.user_id == row.user_id).count() == 1   # one email


def test_the_same_rejection_delivered_at_once_is_applied_once(pg):
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "rejected")
    body = payload("session.rejected", reference, "rejected", rejection_reason="Face does not match the document")
    assert outcomes(Session, body) == [dispatch.APPLIED] + [dispatch.DUPLICATE] * (WORKERS - 1)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        assert row.status == KYCStatus.REJECTED and row.rejection_details.startswith("kaluta:session:")
        assert db.query(EmailDelivery).filter(EmailDelivery.user_id == row.user_id).count() == 1


def test_an_approval_and_a_rejection_racing_leave_one_decision(pg):
    """Whichever the database takes first stands; the other is recorded and changes nothing."""
    _engine, Session = pg
    verification_id, reference = open_verification(Session, "race")
    bodies = [payload("session.approved", reference, "approved"), payload("session.rejected", reference, "rejected")]

    def work(i):
        with Session() as db:
            return dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=bodies[i % 2])

    results = in_threads(WORKERS, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        # A rejection first leaves room for the provider's own retry approval (the same reference): identity accepted.
        assert row.status in (KYCStatus.PENDING_PROOF_OF_ADDRESS, KYCStatus.REJECTED)
        assert row.identity_verified is (row.status == KYCStatus.PENDING_PROOF_OF_ADDRESS)
        assert results.count(dispatch.APPLIED) in (1, 2)


# ---------------------------------------------------------------------------
# The member KYC fee: requests arriving together
# ---------------------------------------------------------------------------

def test_kyc_payments_asked_for_at_once_create_one_deposit(pg):
    """What payments.create does for a KYC payment: refusal check under the
    member's row lock, then the deposit, then commit."""
    from decimal import Decimal

    from app.models.payment import Deposit, DepositStatus, ProductType
    from app.services import kyc_fee

    _engine, Session = pg
    with Session() as db:
        user = User(email="payer@example.com", username="payer", hashed_password="x", is_active=True, is_deleted=False,
                    date_of_birth=datetime(1990, 1, 1), personal_referral_code="PAYER", email_verified=True)
        product = ProductType(code="kyc", name="KYC", price=Decimal("10.00"), currency="USD", is_active=True)
        db.add_all([user, product])
        db.commit()
        user_id, product_id = user.id, product.id

    def work(i):
        with Session() as db:
            refusal = kyc_fee.payment_refusal(db, user_id, lock=True)
            if refusal:
                db.rollback()
                return refusal[0]
            db.add(Deposit(user_id=user_id, product_type_id=product_id, amount=Decimal("10.00"), currency="USD",
                           order_id=f"kyc-race-{i}", status=DepositStatus.PENDING))
            db.commit()
            return "created"

    results = in_threads(WORKERS, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(results) == ["KYC_PAYMENT_IN_PROGRESS"] * (WORKERS - 1) + ["created"]
    with Session() as db:
        assert db.query(Deposit).filter(Deposit.user_id == user_id).count() == 1


def test_a_fee_change_and_its_audit_row_are_one_change_when_two_administrators_save_at_once(pg):
    from decimal import Decimal

    from app.models.accounting import AuditTrail
    from app.models.payment import ProductType
    from app.services import kyc_fee, payment_config

    _engine, Session = pg
    with Session() as db:
        db.add(ProductType(code="kyc", name="KYC", price=Decimal("10.00"), currency="USD", is_active=True))
        db.commit()

    class Admin:                                                          # authorisation is covered by the unit tests
        id = None

    def work(i):
        with Session() as db:
            try:
                return kyc_fee.set_member_fee(db, Admin(), f"{i + 1}.00", password="x", expected_amount="10.00")["amount"]
            except kyc_fee.KycFeeError as exc:
                db.rollback()
                return exc.code

    import pytest as _pytest
    patch = _pytest.MonkeyPatch()
    patch.setattr(payment_config, "has_permission", lambda *_a, **_k: True)
    patch.setattr(payment_config, "require_reauth", lambda *_a, **_k: None)
    try:
        results = in_threads(WORKERS, work)
    finally:
        patch.undo()
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(r for r in results if r == "STALE") == ["STALE"] * (WORKERS - 1)
    with Session() as db:
        assert db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).count() == 1
        won = [r for r in results if r != "STALE"][0]
        assert f"{Decimal(str(db.query(ProductType).one().price)):.2f}" == won
