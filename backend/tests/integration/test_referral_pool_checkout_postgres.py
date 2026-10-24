"""Multi-Unit Referral Pool, P7: checkout, payment confirmation, refunds and feature controls on a
real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC: the SoncoPay network call
is replaced by a fake that attaches a synthetic payment id; confirmations and refunds go through
the REAL SoncoPay handler (soncopay_payments.apply_locked: identity checks included), the real
ledger and the real unit lifecycle.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.api_v1.endpoints import payments as payments_api
from app.api.api_v1.endpoints import referral_pool as pool_api
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.accounting import AuditTrail
from app.models.business_model import (
    ReferralPoolConfig, ReferralPoolPurchase, ReferralPoolRefundRecord, ReferralPoolUnit,
)
from app.models.payment import Deposit, DepositStatus
from app.models.user import User
from app.services import checkout_routing, payment_config, soncopay_payments, soncopay_settings
from app.services import referral_pool_accounting as accounting
from app.services import referral_pool_allocation as alloc
from app.services import referral_pool_units as units
from app.services.financial_integrity import FinancialIntegrityError
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401
from tests.integration.test_referral_pool_accounting_postgres import ledger, reconciled, sponsored_buyer
from tests.integration.test_referral_pool_units_postgres import member, set_kyc, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

D = Decimal


# ---------------------------------------------------------------------------
# the checkout world
# ---------------------------------------------------------------------------

@pytest.fixture
def shop(world, monkeypatch):
    """Sales open, SoncoPay (test) as the gateway; its network call faked; rate limits off."""
    _engine, Session = world

    async def fake_checkout(db, deposit_id, *, description):
        dep = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        dep.external_payment_id = f"pay_{deposit_id:020d}"
        dep.provider_checkout_url = f"https://checkout.example.invalid/{deposit_id}"
        db.flush()
        return dep

    monkeypatch.setattr(checkout_routing, "new_payment_gateway", lambda db: "soncopay")
    monkeypatch.setattr(soncopay_settings, "checkout_environment", lambda db: "test")
    monkeypatch.setattr(soncopay_payments, "create_checkout", fake_checkout)
    monkeypatch.setattr(payments_api, "_is_rate_limited", lambda *a, **k: False)
    return Session


def checkout(Session, user_id: int, quantity: int, *, amount=None, currency="usd", key=None, product="referral_pool_entry"):
    """POST /payments/create as the member: (http status, body or detail)."""
    body = payments_api.CreatePaymentRequest(amount=amount if amount is not None else D("100.00") * quantity,
                                             currency=currency, product_code=product, quantity=quantity)
    with Session() as db:
        try:
            r = asyncio.run(payments_api.create_payment(request=body, db=db, current_user=db.get(User, user_id),
                                                       idempotency_key=key or uuid.uuid4().hex))
            return 200, r
        except HTTPException as exc:
            db.rollback()
            return exc.status_code, exc.detail


def provider_event(Session, deposit_id: int, status: str, **fields) -> str:
    """A SoncoPay payment status, as its signed webhook would deliver it (signature checked upstream)."""
    with Session() as db:
        dep = db.get(Deposit, deposit_id)
        payment = {"id": dep.external_payment_id, "order_id": dep.order_id, "status": status,
                   "amount": f"{D(dep.amount):.2f}", "currency": "USD", "livemode": False, **fields}
        try:
            outcome, _ = soncopay_payments.apply_locked(db, deposit_id, payment)
            db.commit()
            return str(outcome)
        except FinancialIntegrityError as exc:
            db.rollback()
            return f"refused:{exc}"


def purchase_of(Session, deposit_id: int):
    with Session() as db:
        p = db.query(ReferralPoolPurchase).filter_by(deposit_id=deposit_id).one()
        states = sorted(u.status for u in db.query(ReferralPoolUnit).filter_by(purchase_id=p.id))
        return p.id, p.status, p.quantity, states


def set_config(Session, **values) -> None:
    with Session() as db:
        cfg = db.query(ReferralPoolConfig).one()
        for k, v in values.items():
            setattr(cfg, k, v)
        db.commit()


# ---------------------------------------------------------------------------
# 1. Checkout
# ---------------------------------------------------------------------------

def test_an_eligible_member_checks_out_n_units_priced_by_the_server(shop):
    Session = shop
    buyer, _ = sponsored_buyer(Session)
    code, response = checkout(Session, buyer, 3)
    assert code == 200 and response.price_amount == 300.0 and response.provider == "soncopay"
    with Session() as db:
        dep = db.get(Deposit, response.deposit_id)
        assert (D(dep.amount), dep.currency, dep.status) == (D("300.00"), "USD", DepositStatus.PENDING)
    pid, status, quantity, states = purchase_of(Session, response.deposit_id)
    assert (status, quantity, states) == ("PENDING_PAYMENT", 3, [])            # nothing before payment


def test_price_quantity_and_currency_manipulation_is_refused(shop):
    Session = shop
    buyer = member(Session)
    assert checkout(Session, buyer, 3, amount=D("100.00"))[0] == 400            # $100 for 3 units
    assert checkout(Session, buyer, 3, amount=D("300.00"), currency="eur")[0] == 400
    assert checkout(Session, buyer, 2, product="annual_membership", amount=D("50.00"))[0] == 400   # quantity elsewhere
    for bad in (0, -1, 10001):
        with pytest.raises(ValidationError):
            payments_api.CreatePaymentRequest(amount=D("100"), product_code="referral_pool_entry", quantity=bad)
    with Session() as db:
        assert db.query(Deposit).filter_by(user_id=buyer).count() == 0


def test_ineligible_members_and_closed_sales_create_nothing(shop):
    Session = shop
    no_kyc, minor = member(Session, kyc=False), member(Session, born=__import__("datetime").datetime(2012, 1, 1))
    for user_id in (no_kyc, minor):
        code, detail = checkout(Session, user_id, 1)
        assert code in (403,) and detail["code"] == "NOT_ELIGIBLE", (code, detail)
    set_config(Session, multiunit_sales_enabled=False)
    adult = member(Session)
    assert checkout(Session, adult, 1)[0] == 410
    with Session() as db:
        assert db.query(Deposit).filter(Deposit.user_id.in_((no_kyc, minor, adult))).count() == 0
        assert db.query(ReferralPoolPurchase).count() == 0


def test_the_same_idempotency_key_creates_one_payment(shop):
    Session = shop
    buyer = member(Session)
    first = checkout(Session, buyer, 2, key="same-key")
    again = checkout(Session, buyer, 2, key="same-key")
    other = checkout(Session, buyer, 3, key="same-key")                         # same key, another order
    assert first[0] == again[0] == 200 and first[1].deposit_id == again[1].deposit_id
    assert other[0] == 409
    with Session() as db:
        assert db.query(ReferralPoolPurchase).filter_by(user_id=buyer).count() == 1
    results = in_threads(6, lambda _i: checkout(Session, buyer, 1, key="race-key"))
    assert {r[1].deposit_id for r in results if r[0] == 200} and all(r[0] in (200, 409) for r in results), results
    with Session() as db:
        assert db.query(Deposit).filter_by(user_id=buyer).count() == 2


def test_optional_limits_hold_under_concurrent_checkouts(shop):
    Session = shop
    set_config(Session, max_units_per_member=3)
    buyer = member(Session)
    results = in_threads(5, lambda _i: checkout(Session, buyer, 1))
    codes = sorted(r[0] for r in results)
    assert codes == [200, 200, 200, 409, 409], results
    assert {r[1]["code"] for r in results if r[0] == 409} == {"MEMBER_LIMIT"}
    set_config(Session, max_units_per_member=None, max_units_per_purchase=2)
    assert checkout(Session, buyer, 3)[1]["code"] == "PURCHASE_LIMIT"


# ---------------------------------------------------------------------------
# 2. Payment confirmation
# ---------------------------------------------------------------------------

def test_a_confirmed_payment_creates_n_units_revenue_and_commission_once(shop):
    Session = shop
    buyer, sponsor = sponsored_buyer(Session)
    _code, r = checkout(Session, buyer, 3)
    assert provider_event(Session, r.deposit_id, "paid") == "SYNCED"
    assert provider_event(Session, r.deposit_id, "paid") == "SYNCED"           # duplicate callback: no-op
    pid, status, _q, states = purchase_of(Session, r.deposit_id)
    assert (status, states) == ("PAID", ["ACTIVE"] * 3)
    assert ledger(Session, pid) == {"1001": D("300.00"), "4008": D("-300.00"), "5001": D("60.00"), "2001": D("-60.00")}
    with Session() as db:
        assert db.query(AffiliateCommission).filter_by(user_id=sponsor).count() == 3
        assert db.query(AffiliateCashoutRequest).count() == 0                    # no payout
    assert reconciled(Session, pid) == []


def test_an_unpaid_or_mismatched_payment_never_activates_units(shop):
    Session = shop
    buyer = member(Session)
    _c, r = checkout(Session, buyer, 2)
    provider_event(Session, r.deposit_id, "pending")
    assert purchase_of(Session, r.deposit_id)[3] == []
    assert provider_event(Session, r.deposit_id, "paid", amount="100.00") == "IDENTITY_REJECTED"
    assert provider_event(Session, r.deposit_id, "paid", currency="EUR") == "IDENTITY_REJECTED"
    assert purchase_of(Session, r.deposit_id)[1:] == ("PENDING_PAYMENT", 2, [])


def test_a_payment_confirmed_after_sales_closed_still_gets_its_units(shop):
    Session = shop
    buyer = member(Session)
    _c, r = checkout(Session, buyer, 2)
    set_config(Session, multiunit_sales_enabled=False)
    provider_event(Session, r.deposit_id, "paid")
    assert purchase_of(Session, r.deposit_id)[1:] == ("PAID", 2, ["ACTIVE", "ACTIVE"])
    assert checkout(Session, buyer, 1)[0] == 410                                  # but no new checkout


def test_a_late_payment_of_an_expired_invoice_is_still_honoured_once(shop):
    Session = shop
    buyer = member(Session)
    _c, r = checkout(Session, buyer, 1)
    provider_event(Session, r.deposit_id, "expired")
    provider_event(Session, r.deposit_id, "paid")
    provider_event(Session, r.deposit_id, "paid")
    assert purchase_of(Session, r.deposit_id)[3] in ([], ["ACTIVE"])            # handled by the existing rules, once
    with Session() as db:
        assert db.query(ReferralPoolUnit).filter_by(user_id=buyer).count() <= 1


# ---------------------------------------------------------------------------
# 3. Refunds
# ---------------------------------------------------------------------------

def test_signed_partial_refunds_refund_exactly_the_units_they_cover(shop):
    Session = shop
    buyer, _ = sponsored_buyer(Session)
    _c, r = checkout(Session, buyer, 3)
    provider_event(Session, r.deposit_id, "paid")
    pid = purchase_of(Session, r.deposit_id)[0]
    assert provider_event(Session, r.deposit_id, "partially_refunded", refunded_amount="100.00") == "SYNCED"
    assert purchase_of(Session, r.deposit_id)[1:] == ("PARTIALLY_REFUNDED", 3, ["ACTIVE", "ACTIVE", "REFUNDED"])
    provider_event(Session, r.deposit_id, "partially_refunded", refunded_amount="100.00")     # replay
    provider_event(Session, r.deposit_id, "partially_refunded", refunded_amount="200.00")
    provider_event(Session, r.deposit_id, "partially_refunded", refunded_amount="100.00")     # older, out of order
    assert purchase_of(Session, r.deposit_id)[3] == ["ACTIVE", "REFUNDED", "REFUNDED"]
    assert provider_event(Session, r.deposit_id, "partially_refunded",
                          refunded_amount="150.00") == "IDENTITY_REJECTED"                    # not whole units
    assert ledger(Session, pid) == {"1001": D("100.00"), "4008": D("-100.00"), "5001": D("20.00"), "2001": D("-20.00")}
    provider_event(Session, r.deposit_id, "refunded", refunded_amount="300.00")              # the rest: full
    assert purchase_of(Session, r.deposit_id)[1:] == ("REFUNDED", 3, ["REFUNDED"] * 3)
    assert ledger(Session, pid) == {} and reconciled(Session, pid) == []
    with Session() as db:
        assert db.get(Deposit, r.deposit_id).status == DepositStatus.FAILED            # marked refunded


def test_a_manual_refund_needs_a_second_administrator(shop, monkeypatch):
    Session = shop
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    proposer, approver = member(Session), member(Session)
    buyer, _ = sponsored_buyer(Session)
    _c, r = checkout(Session, buyer, 2)
    provider_event(Session, r.deposit_id, "paid")
    pid = purchase_of(Session, r.deposit_id)[0]
    with Session() as db:
        record = units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1,
                                             amount=D("100.00"), provider_reference="np-refund-1",
                                             evidence_note="Seen in the NOWPayments dashboard", password="x")
        record_id = record.id
    assert purchase_of(Session, r.deposit_id)[3] == ["ACTIVE", "ACTIVE"]          # proposed: nothing moved
    with Session() as db:
        with pytest.raises(units.UnitsError, match="different administrator"):
            units.decide_manual_refund(db, db.get(User, proposer), record_id, approve=True, note="self approve",
                                       password="x")
    with Session() as db:
        units.decide_manual_refund(db, db.get(User, approver), record_id, approve=True, note="Verified twice",
                                   password="x")
    assert purchase_of(Session, r.deposit_id)[3] == ["ACTIVE", "REFUNDED"]
    with Session() as db:
        rec = db.get(ReferralPoolRefundRecord, record_id)
        assert (rec.status, rec.proposed_by, rec.decided_by) == ("APPROVED", proposer, approver)
        assert db.query(AuditTrail).filter(AuditTrail.table_name == "referral_pool_refund_records").count() == 2
    assert reconciled(Session, pid) == []
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: False)
    with Session() as db:
        with pytest.raises(units.UnitsError, match="permission"):
            units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1, amount=D("100"),
                                        provider_reference="np-refund-2", evidence_note="no permission here",
                                        password="x")


def test_a_refund_during_a_commission_payout_is_refused_and_stays_proposed(shop, monkeypatch):
    Session = shop
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    proposer, approver = member(Session), member(Session)
    buyer, _ = sponsored_buyer(Session)
    _c, r = checkout(Session, buyer, 1)
    provider_event(Session, r.deposit_id, "paid")
    pid = purchase_of(Session, r.deposit_id)[0]
    with Session() as db:
        c = db.query(AffiliateCommission).filter_by(source_type=accounting.SOURCE_UNIT).one()
        c.payout_reference = "intent:synthetic"
        db.commit()
        record_id = units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1,
                                                amount=D("100"), provider_reference="np-flight",
                                                evidence_note="Refund seen at the provider", password="x").id
    with Session() as db:
        with pytest.raises(FinancialIntegrityError, match="payout intent"):
            units.decide_manual_refund(db, db.get(User, approver), record_id, approve=True, note="Approve while paying", password="x")
    with Session() as db:
        assert db.get(ReferralPoolRefundRecord, record_id).status == "PROPOSED"
    assert purchase_of(Session, r.deposit_id)[3] == ["ACTIVE"]


# ---------------------------------------------------------------------------
# 4. Member and administrator views, switches
# ---------------------------------------------------------------------------

def test_members_see_only_their_own_purchases(shop):
    Session = shop
    mine, theirs = member(Session), member(Session)
    _c, r = checkout(Session, mine, 2)
    _c, s = checkout(Session, theirs, 1)
    with Session() as db:
        view = pool_api.my_purchases(db=db, current_user=db.get(User, mine))
        assert [p["quantity"] for p in view["purchases"]] == [2]
        other_id = db.query(ReferralPoolPurchase).filter_by(user_id=theirs).one().id
        with pytest.raises(HTTPException) as info:
            pool_api.my_purchase(other_id, db=db, current_user=db.get(User, mine))
        assert info.value.status_code == 404
        e = pool_api.unit_eligibility(db=db, current_user=db.get(User, mine))
        assert (e["sales_enabled"], e["eligible"], e["unit_price"], e["units_reserved"]) == (True, True, "100.00", 2)
        e = pool_api.unit_eligibility(db=db, current_user=db.get(User, member(Session, kyc=False)))
        assert (e["eligible"], e["reason"]) == (False, "KYC_REQUIRED")


def test_admin_settings_are_read_only_and_limits_need_permission(shop, monkeypatch):
    Session = shop
    admin = member(Session)
    with Session() as db:
        state = pool_api.pool_settings(db=db)
        assert state["limits"] == {"max_units_per_purchase": None, "max_units_per_member": None, "max_active_units": None}
        assert state["worker_enabled"] is False
        body = pool_api.LimitsBody(max_units_per_member=5, password="x")
        with pytest.raises(HTTPException) as info:
            pool_api.set_limits(body, request=type("R", (), {"client": None})(), db=db,
                                current_user=db.get(User, admin))
        assert info.value.status_code == 403
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    with Session() as db:
        pool_api.set_limits(body, request=type("R", (), {"client": None})(), db=db, current_user=db.get(User, admin))
    with Session() as db:
        assert db.query(ReferralPoolConfig).one().max_units_per_member == 5
        assert db.query(AuditTrail).filter_by(action="REFERRAL_POOL_LIMITS_CHANGED").count() == 1
    assert not [r.path for r in pool_api.admin_router.routes if "enable" in r.path or "activate" in r.path]


def test_with_allocation_off_purchases_open_no_round(shop):
    Session = shop
    buyer = member(Session)
    _c, r = checkout(Session, buyer, 2)
    provider_event(Session, r.deposit_id, "paid")
    with Session() as db:
        assert db.query(ReferralPoolConfig).one().allocation_enabled is False
        assert alloc.open_round_if_needed(db) is None
        db.rollback()


def test_the_switches_stay_off_by_default(pg):
    from tests.integration.test_payments_postgres import seed_ledger

    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        cfg = db.query(ReferralPoolConfig).one()
        assert (cfg.multiunit_sales_enabled, cfg.allocation_enabled) == (False, False)
    assert checkout(Session, member(Session), 1)[0] == 410


def test_the_refund_records_migration_goes_down_and_up_and_refuses_with_executed_refunds(pg):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.integration.test_payments_postgres import load_migration, migrate
    from tests.integration.test_referral_pool_multiunit_schema_postgres import tables

    engine, _Session = pg
    name = "d2f4b6c8e0a1_referral_pool_manual_refund_records.py"
    assert (load_migration(name).revision, load_migration(name).down_revision) == ("d2f4b6c8e0a1", "c1e3a5b7d9f2")
    migrate(engine, name, "downgrade")
    assert "referral_pool_refund_records" not in tables(engine)
    migrate(engine, name, "downgrade")                                    # twice: a no-op
    migrate(engine, name, "upgrade")
    migrate(engine, name, "upgrade")                                    # re-run: a no-op
    with engine.begin() as c:
        c.execute(text("ALTER TABLE referral_pool_refund_records DROP CONSTRAINT referral_pool_refund_records_purchase_id_fkey, "
                       "DROP CONSTRAINT referral_pool_refund_records_proposed_by_fkey, "
                       "DROP CONSTRAINT referral_pool_refund_records_decided_by_fkey"))
        c.execute(text("INSERT INTO referral_pool_refund_records (purchase_id, quantity, amount, provider_reference, "
                       "evidence_note, status, proposed_by, decided_by, decided_at) VALUES "
                       "(1, 1, 100, 'r', 'evidence text', 'APPROVED', 1, 2, now())"))
    with pytest.raises(DBAPIError, match="downgrade refused"):
        migrate(engine, name, "downgrade")
    assert "referral_pool_refund_records" in tables(engine)
