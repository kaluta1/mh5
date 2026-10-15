"""The Member KYC Verification Fee: one figure an authorised administrator sets.

0 = free KYC. A payment keeps the amount it was created with; a member is not
charged twice; a new attempt costs the fee in force when it is paid for.
Nothing about what the KYC provider charges MyHigh5 exists here.

Every member, administrator, payment and session is SYNTHETIC; no request
leaves the process (the KYC and payment providers are fakes).
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.api.api_v1.endpoints import payments
from app.core.config import settings
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.kyc import KYCAuditLog, KYCStatus
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import Permission, Role
from app.services import admin_security, kaluta_kyc, kyc_fee
from app.services import payment_config as pc
from tests.conftest import save_kaluta_settings
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import PASSWORD, member
from tests.unit.test_kaluta_kyc_integration import FakeProvider
from tests.unit.test_kyc_initiation_dispatch import ADDRESS, INITIATE, adult, kyc_paid, kyc_rows, no_real_network  # noqa: F401

pytestmark = pytest.mark.unit

FEE, ADMIN_FEE, STATUS, PAY = "/api/v1/kyc/fee", "/api/v1/kyc/admin/fee", "/api/v1/kyc/status-detailed", "/api/v1/payments/create"


@pytest.fixture(autouse=True)
def kyc_provider(monkeypatch, db, kaluta_settings_key):
    monkeypatch.setattr(settings, "KYC_PROVIDER", "kaluta")
    save_kaluta_settings(db, enabled=True, api_key="klt_test_synthetic_key_0001")
    return FakeProvider(monkeypatch)


@pytest.fixture
def invoices(monkeypatch):
    """The payment provider at the function boundary: records every invoice asked for."""
    asked = []

    async def create(**kwargs):
        asked.append(kwargs)
        return {"payment_id": f"pay-{len(asked)}", "payment_status": "waiting", "pay_address": "0x" + "c" * 40,
                "pay_amount": "10", "pay_currency": "usdtbsc", "price_amount": str(kwargs["price_amount"]),
                "price_currency": "usd", "order_id": kwargs["order_id"]}

    monkeypatch.setattr(payments, "now_create_payment", create)
    return asked


def product(db, price="10.00") -> ProductType:
    row = db.query(ProductType).filter(ProductType.code == "kyc").first()
    if row is None:
        row = ProductType(code="kyc", name="KYC", price=Decimal(price), currency="USD", is_active=True)
        db.add(row)
    row.price = Decimal(price)
    db.commit()
    return row


def role_holding(db, permissions) -> Role:
    """A role that explicitly holds exactly these permissions (any of them)."""
    name = "kyc_test_" + ("_".join(sorted(permissions)) or "none")
    role = db.query(Role).filter(Role.name == name).first()
    if role is None:
        role = Role(name=name, permissions=[
            db.query(Permission).filter(Permission.name == p).first() or Permission(name=p, category="admin")
            for p in permissions])
        db.add(role)
        db.flush()
    return role


def administrator(db, name="feeadmin", permissions=(admin_security.PERMISSION_MANAGE_KYC,)):
    user = member(db, name, admin=True, permissions=(), wallet=None)
    user.role_id = role_holding(db, permissions).id
    db.commit()
    return user


def set_fee(client, admin, amount, **extra):
    return client.put(ADMIN_FEE, headers=auth(admin), json={"amount": amount, "current_password": PASSWORD, **extra})


def pay(client, user, amount=10):
    return client.post(PAY, headers=auth(user), json={"amount": amount, "currency": "usd", "product_code": "kyc"})


def money(db) -> tuple:
    return db.query(Deposit).count(), db.query(JournalEntry).count(), db.query(AffiliateCommission).count()


def fee_notes(db, user) -> list:
    row = kyc_rows(db, user)[0]
    return [a.details for a in db.query(KYCAuditLog).filter(KYCAuditLog.verification_id == row.id,
                                                            KYCAuditLog.action == "kyc_attempt_fee").order_by(KYCAuditLog.id)]


# ===========================================================================
# 1. The administrator sets the fee
# ===========================================================================

def test_an_authorised_administrator_sets_the_fee_and_the_change_is_audited(client, db):
    row = product(db)
    admin = administrator(db)
    seen = client.get(ADMIN_FEE, headers=auth(admin)).json()
    assert (seen["amount"], seen["currency"], seen["is_free"], seen["can_change"], seen["last_change"]) == \
        ("10.00", "USD", False, True, None)
    answer = set_fee(client, admin, "7.50", expected_amount="10.00")
    assert answer.status_code == 200, answer.text
    assert answer.json()["amount"] == "7.50" and answer.json()["last_change"]["old_amount"] == "10.00"
    db.expire_all()
    assert Decimal(str(db.query(ProductType).filter(ProductType.code == "kyc").one().price)) == Decimal("7.50")
    trail = db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).all()
    assert [(t.table_name, t.record_id, t.old_values, t.new_values, t.user_id) for t in trail] == \
        [("product_types", row.id, {"price": "10.00"}, {"price": "7.50"}, admin.id)]
    # The same value again changes nothing and writes nothing.
    assert set_fee(client, admin, "7.50").status_code == 200
    assert db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).count() == 1


def test_only_the_explicit_permission_and_the_current_password_change_the_fee(client, db):
    product(db)
    plain = administrator(db, "plainadmin", permissions=())
    # Finance & Payments permissions do not include the KYC fee.
    finance = administrator(db, "financeadmin", permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_ACTIVATE))
    manager = administrator(db)
    ordinary = adult(db)
    assert client.put(ADMIN_FEE, json={"amount": "1"}).status_code in (401, 403)
    assert set_fee(client, ordinary, "1").status_code == 403
    assert client.get(ADMIN_FEE, headers=auth(ordinary)).status_code == 403
    for refused_admin in (plain, finance):
        refused = set_fee(client, refused_admin, "1")
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "FORBIDDEN"
        assert "manage_kyc_settings" in refused.json()["detail"]["message"]
        seen = client.get(ADMIN_FEE, headers=auth(refused_admin)).json()
        assert (seen["can_change"], seen["permission"]) == (False, "manage_kyc_settings")
    wrong = client.put(ADMIN_FEE, headers=auth(manager), json={"amount": "1", "current_password": "not-it"})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "REAUTH_REQUIRED"
    missing = client.put(ADMIN_FEE, headers=auth(manager), json={"amount": "1"})
    assert missing.status_code == 403
    db.expire_all()
    assert kyc_fee.member_fee(db) == (Decimal("10.00"), "USD")
    assert db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).count() == 0


@pytest.mark.parametrize("amount", ["-1", "abc", "", "1.999", "1000.01", "NaN", "Infinity", "1e3000"])
def test_a_fee_that_is_not_a_plain_amount_is_refused(client, db, amount):
    product(db)
    answer = set_fee(client, administrator(db), amount)
    assert answer.status_code == 422 and answer.json()["detail"]["code"] == "INVALID_VALUE"
    db.expire_all()
    assert kyc_fee.member_fee(db)[0] == Decimal("10.00")


def test_a_change_made_on_a_stale_figure_or_with_unknown_fields_is_refused(client, db):
    product(db)
    admin = administrator(db)
    assert set_fee(client, admin, "5", expected_amount="10.00").status_code == 200
    stale = set_fee(client, admin, "8", expected_amount="10.00")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE"
    for unknown in ("provider_cost_percent", "estimated_margin"):
        assert set_fee(client, admin, "8", **{unknown: "20"}).status_code == 422
    db.expire_all()
    assert kyc_fee.member_fee(db)[0] == Decimal("5.00")


def test_without_the_product_row_the_default_applies_and_nothing_can_be_set(client, db):
    assert db.query(ProductType).filter(ProductType.code == "kyc").first() is None
    assert kyc_fee.member_fee(db) == (kyc_fee.DEFAULT_FEE, "USD") and not kyc_fee.is_free(db)
    answer = set_fee(client, administrator(db), "0")
    assert answer.status_code == 409 and answer.json()["detail"]["code"] == "PRODUCT_MISSING"
    assert db.query(ProductType).count() == 0


# ===========================================================================
# 2. The member sees the fee before starting
# ===========================================================================

def test_a_member_sees_the_fee_before_starting(client, db):
    product(db, "7.50")
    user = adult(db)
    assert client.get(FEE).status_code in (401, 403)
    shown = client.get(FEE, headers=auth(user)).json()
    assert shown == {"amount": "7.50", "currency": "USD", "is_free": False, "retry_policy": kyc_fee.RETRY_POLICY}
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["status"], state["kyc_price"], state["kyc_currency"], state["kyc_is_free"], state["needs_payment"]) == \
        (None, 7.5, "USD", False, True)
    refused = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert refused.status_code == 402 and refused.json()["detail"]["price"] == 7.5

    product(db, "0")
    free = client.get(STATUS, headers=auth(user)).json()
    assert (free["kyc_price"], free["kyc_is_free"], free["needs_payment"]) == (0.0, True, False)
    assert client.get(FEE, headers=auth(user)).json()["is_free"] is True


# ===========================================================================
# 3. Free KYC
# ===========================================================================

def test_with_a_fee_of_zero_an_attempt_starts_without_a_payment_and_no_payment_can_be_made(client, db, invoices):
    product(db, "0")
    user = adult(db)
    before = money(db)
    started = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert started.status_code == 200, started.text
    row = kyc_rows(db, user)[0]
    assert (row.status, row.attempts_count) == (KYCStatus.IN_PROGRESS, 1)
    assert fee_notes(db, user) == ["Attempt 1: no fee (member KYC fee was 0; no paid KYC payment was used)"]
    refused = pay(client, user, 0)
    assert refused.status_code in (409, 422)
    assert pay(client, user, 10).status_code == 409 and pay(client, user, 10).json()["detail"]["code"] == "KYC_FEE_NOT_REQUIRED"
    assert money(db) == before and invoices == []                      # no deposit, journal, commission or invoice


def test_a_free_retry_after_a_rejection_still_counts_as_an_attempt(client, db):
    product(db, "0")
    user = adult(db)
    client.post(INITIATE, json=ADDRESS, headers=auth(user))
    row = kyc_rows(db, user)[0]
    row.status = KYCStatus.REJECTED
    db.commit()
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["can_restart"], state["needs_payment"], state["kyc_is_free"]) == (True, False, True)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    row = kyc_rows(db, user)[0]
    assert row.attempts_count == 2 and len(fee_notes(db, user)) == 2
    row.status, row.attempts_count = KYCStatus.REJECTED, row.max_attempts
    db.commit()
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 400      # the attempt limit still holds


# ===========================================================================
# 4. A payment keeps its amount when the fee changes
# ===========================================================================

def test_a_paid_unused_payment_keeps_its_amount_and_opens_the_attempt_after_the_fee_changes(client, db):
    product(db)
    admin, user = administrator(db), adult(db)
    paid = kyc_paid(db, user)                                            # 10.00 paid at the old fee
    assert set_fee(client, admin, "25").status_code == 200
    db.expire_all()
    assert Decimal(str(db.get(Deposit, paid.id).amount)) == Decimal("10.00")
    assert client.get(STATUS, headers=auth(user)).json()["needs_payment"] is False
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    paid = db.get(Deposit, paid.id)
    assert paid.is_used is True and Decimal(str(paid.amount)) == Decimal("10.00")
    assert fee_notes(db, user) == [f"Attempt 1: paid with deposit {paid.id}: 10.00 USD"]


def test_an_unpaid_invoice_keeps_the_amount_it_was_created_with(client, db, invoices):
    product(db)
    admin, user = administrator(db), adult(db)
    created = pay(client, user, 10)
    assert created.status_code == 200, created.text
    assert set_fee(client, admin, "25").status_code == 200
    db.expire_all()
    pending = db.query(Deposit).filter(Deposit.user_id == user.id).one()
    assert (pending.status, Decimal(str(pending.amount))) == (DepositStatus.PENDING, Decimal("10.00"))
    assert Decimal(str(invoices[0]["price_amount"])) == Decimal("10.00")
    # A new payment is priced at the new fee, and the old figure is refused.
    other = adult(db)
    assert pay(client, other, 10).status_code == 400
    assert pay(client, other, 25).status_code == 200 and Decimal(str(invoices[-1]["price_amount"])) == Decimal("25.00")


def test_a_free_attempt_never_uses_a_payment_the_member_already_made(client, db, invoices):
    product(db)
    user = adult(db)
    paid = kyc_paid(db, user)
    before = (paid.status, paid.amount, paid.validated_at, paid.expires_at)
    ledger = money(db)
    product(db, "0")
    started = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert started.status_code == 200, started.text
    db.expire_all()
    kept = db.get(Deposit, paid.id)
    # The payment record is exactly as it was: paid, unused, same amount.
    assert kept.is_used is False and kept.used_at is None
    assert (kept.status, kept.amount, kept.validated_at, kept.expires_at) == before
    assert fee_notes(db, user) == ["Attempt 1: no fee (member KYC fee was 0; no paid KYC payment was used)"]
    assert money(db) == ledger and invoices == []                       # nothing new booked, nothing invoiced
    # The member is not charged meanwhile ...
    assert pay(client, user, 10).json()["detail"]["code"] == "KYC_FEE_NOT_REQUIRED"
    # ... and the payment still opens a later attempt once KYC is paid again.
    row = kyc_rows(db, user)[0]
    row.status = KYCStatus.REJECTED
    db.commit()
    product(db, "10")
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["can_restart"], state["needs_payment"], state["available_payments"]) == (True, False, 1)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    assert db.get(Deposit, paid.id).is_used is True
    assert fee_notes(db, user)[-1] == f"Attempt 2: paid with deposit {paid.id}: 10.00 USD"
    assert pay(client, user, 10).json()["detail"]["code"] == "KYC_ATTEMPT_OPEN"     # no double charge
    assert db.query(Deposit).filter(Deposit.user_id == user.id).count() == 1


def test_an_open_attempt_is_not_charged_when_the_fee_is_raised(client, db):
    product(db, "0")
    user = adult(db)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(user)).json()
    product(db, "15")
    again = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert again.status_code == 200 and again.json()["reused"] is True
    assert again.json()["verification_url"] == first["verification_url"]
    # The NEXT attempt costs the fee in force then.
    row = kyc_rows(db, user)[0]
    row.status = KYCStatus.REJECTED
    db.commit()
    state = client.get(STATUS, headers=auth(user)).json()
    assert (state["needs_payment"], state["can_restart"], state["kyc_price"]) == (True, False, 15.0)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 402


# ===========================================================================
# 5. No duplicate charge
# ===========================================================================

def test_a_member_is_not_charged_for_an_attempt_they_already_hold_or_do_not_need(client, db, invoices):
    product(db)
    holder = adult(db)
    kyc_paid(db, holder)
    assert pay(client, holder).json()["detail"]["code"] == "KYC_ALREADY_PAID"

    open_attempt = adult(db)
    kyc_paid(db, open_attempt)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(open_attempt)).status_code == 200
    assert pay(client, open_attempt).json()["detail"]["code"] == "KYC_ATTEMPT_OPEN"
    row = kyc_rows(db, open_attempt)[0]
    for status, code in ((KYCStatus.PENDING_PROOF_OF_ADDRESS, "KYC_ALREADY_VERIFIED"), (KYCStatus.APPROVED, "KYC_ALREADY_VERIFIED")):
        row.status = status
        db.commit()
        assert pay(client, open_attempt).json()["detail"]["code"] == code
    row.status, row.attempts_count = KYCStatus.REJECTED, row.max_attempts
    db.commit()
    assert pay(client, open_attempt).json()["detail"]["code"] == "KYC_ATTEMPTS_EXHAUSTED"
    assert invoices == [] and db.query(Deposit).filter(Deposit.status == DepositStatus.PENDING).count() == 0

    # After a rejection, with attempts left and nothing paid: one new payment, and the same request twice is one invoice.
    row.attempts_count = 1
    db.commit()
    key = {"Idempotency-Key": "kyc-retry-0001"}
    first = client.post(PAY, headers={**auth(open_attempt), **key}, json={"amount": 10, "currency": "usd", "product_code": "kyc"})
    second = client.post(PAY, headers={**auth(open_attempt), **key}, json={"amount": 10, "currency": "usd", "product_code": "kyc"})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["deposit_id"] == second.json()["deposit_id"] and len(invoices) == 1


def test_a_second_invoice_is_not_opened_while_one_is_in_progress(client, db, invoices):
    product(db)
    user = adult(db)
    assert pay(client, user).status_code == 200
    again = pay(client, user)                                            # another dialog, another tab, no idempotency key
    assert again.status_code == 409 and again.json()["detail"]["code"] == "KYC_PAYMENT_IN_PROGRESS"
    assert len(invoices) == 1 and db.query(Deposit).filter(Deposit.user_id == user.id).count() == 1
    assert pay(client, adult(db)).status_code == 200                     # somebody else is not affected

    pending = db.query(Deposit).filter(Deposit.user_id == user.id).one()
    pending.status = DepositStatus.PARTIALLY_PAID                        # money arrived, not all of it
    pending.created_at = datetime.utcnow() - timedelta(days=2)
    db.commit()
    assert pay(client, user).json()["detail"]["code"] == "KYC_PAYMENT_IN_PROGRESS"
    # An invoice nobody paid stops counting once the existing one-hour policy has closed it.
    pending.status = DepositStatus.PENDING
    pending.created_at = datetime.utcnow() - kyc_fee.OPEN_INVOICE_WINDOW - timedelta(minutes=1)
    db.commit()
    assert pay(client, user).status_code == 200
    for closed in (DepositStatus.EXPIRED, DepositStatus.FAILED, DepositStatus.REJECTED):
        for row in db.query(Deposit).filter(Deposit.user_id == user.id):
            row.status, row.created_at = closed, datetime.utcnow()
        db.commit()
        assert kyc_fee.payment_refusal(db, user.id) is None


def test_a_paid_attempt_does_not_start_before_the_payment_is_confirmed(client, db, invoices, kyc_provider):
    product(db)
    user = adult(db)
    assert pay(client, user).status_code == 200                         # invoice created, nothing paid
    deposit = db.query(Deposit).filter(Deposit.user_id == user.id).one()
    for unconfirmed in (DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID, DepositStatus.EXPIRED,
                        DepositStatus.FAILED, DepositStatus.REJECTED):
        deposit.status = unconfirmed
        db.commit()
        refused = client.post(INITIATE, json=ADDRESS, headers=auth(user))
        assert refused.status_code == 402, unconfirmed
        assert client.get(STATUS, headers=auth(user)).json()["needs_payment"] is True
    assert kyc_rows(db, user) == [] and kyc_provider.requests == []      # no verification, no provider session
    deposit.status, deposit.validated_at = DepositStatus.VALIDATED, datetime.utcnow()
    db.commit()
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    assert len(kyc_provider.requests) == 1


def test_one_payment_opens_one_attempt(client, db):
    product(db)
    user = adult(db)
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    row = kyc_rows(db, user)[0]
    row.status = KYCStatus.REJECTED
    db.commit()
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 402      # the payment was used once
    kyc_paid(db, user)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(user)).status_code == 200
    db.expire_all()
    assert kyc_rows(db, user)[0].attempts_count == 2 and len(fee_notes(db, user)) == 2


# ===========================================================================
# 6. Scope
# ===========================================================================

def test_nothing_about_the_providers_cost_or_a_margin_exists_in_the_fee(client, db):
    product(db)
    admin = administrator(db)
    source = inspect.getsource(kyc_fee).lower()
    code_only = "\n".join(line for line in source.split('"""', 2)[2].splitlines() if not line.strip().startswith("#"))
    for word in ("provider_cost", "margin", "kaluta"):
        assert word not in code_only
    for answer in (client.get(ADMIN_FEE, headers=auth(admin)).json(), client.get(FEE, headers=auth(admin)).json()):
        assert not [k for k in answer if "cost" in k or "margin" in k]


def test_changing_the_fee_touches_no_payment_ledger_or_commission_row(client, db):
    product(db)
    admin, user = administrator(db), adult(db)
    kyc_paid(db, user)
    before = money(db), db.get(Deposit, db.query(Deposit).first().id).amount
    for amount in ("0", "3.25", "10"):
        assert set_fee(client, admin, amount).status_code == 200
    db.expire_all()
    assert (money(db), db.query(Deposit).first().amount) == before
    assert db.query(AuditTrail).filter(AuditTrail.action == kyc_fee.AUDIT_ACTION).count() == 3
