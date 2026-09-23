"""The old business model (10-level affiliate + Founding Members) is retired for future
activity while every historical row stays intact and readable."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api import deps
from app.core.config import settings
from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionRule, CommissionStatus, CommissionType
from app.models.fmr import MemberFmpBalance, MemberFmpLedger
from app.models.founding_pool import FoundingPoolSnapshot, FoundingPoolSnapshotLine
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import fmr_service
from app.services.commission_distribution import distribute_commissions, process_payment_validation
from app.services.financial_balances import get_commission_balance
from app.services.founding_pool_service import (
    approve_founding_pool_snapshot,
    post_founding_pool_snapshot,
    prepare_founding_pool_month,
)
from app.services.legacy_business_model import (
    LEGACY_FOUNDING_PRODUCT_CODES,
    LegacyBusinessModelRetiredError,
    founding_pool_rate,
    is_legacy_founding_product,
    legacy_business_model_enabled,
)
from app.services.payment_accounting import payment_accounting
from app.services.payment_accounting_backfill import backfill_missing_founding_pool_accruals

pytestmark = pytest.mark.unit

ACCOUNTS = {
    "1001": AccountType.ASSET,
    "1200": AccountType.ASSET,
    "2001": AccountType.LIABILITY,
    "2002": AccountType.LIABILITY,
    "2003": AccountType.LIABILITY,
    "2104": AccountType.LIABILITY,
    "2105": AccountType.LIABILITY,
    "2110": AccountType.LIABILITY,
    "2111": AccountType.LIABILITY,
    "2113": AccountType.LIABILITY,
    "4001": AccountType.REVENUE,
    "4002": AccountType.REVENUE,
    "5001": AccountType.EXPENSE,
}


@pytest.fixture(autouse=True)
def _retired(monkeypatch):
    # Production default: flag absent -> retired. Pin it so a developer env cannot leak in.
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False)


def _user(db, email, *, sponsor_id=None, is_admin=False) -> User:
    row = User(
        email=email,
        hashed_password="not-used",
        username=email.split("@")[0],
        is_active=True,
        is_deleted=False,
        is_admin=is_admin,
        sponsor_id=sponsor_id,
        usdt_wallet_address="0x" + "1" * 40,
    )
    db.add(row)
    db.flush()
    return row


def _accounts(db) -> None:
    for code, kind in ACCOUNTS.items():
        db.add(ChartOfAccounts(account_code=code, account_name=f"Account {code}", account_type=kind, is_active=True))
    db.flush()


def _product(db, code, price, validity_days=0) -> ProductType:
    row = ProductType(code=code, name=code, price=price, currency="USD", validity_days=validity_days)
    db.add(row)
    db.flush()
    db.add(
        CommissionRule(
            product_code=code,
            commission_type=CommissionType.KYC_PAYMENT,
            direct_percentage=10,
            indirect_percentage=1,
            max_levels=10,
            is_active=True,
        )
    )
    db.flush()
    return row


def _chain(db, depth: int = 4) -> User:
    """Payer at the bottom of a `depth`-level sponsor chain; returns the payer."""
    sponsor = None
    for i in range(depth):
        sponsor = _user(db, f"s{i}@test.com", sponsor_id=sponsor.id if sponsor else None)
    return _user(db, "payer@test.com", sponsor_id=sponsor.id)


def _deposit(db, user, product, amount) -> Deposit:
    row = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=amount,
        currency="USD",
        order_id=f"order-{product.code}-{user.id}",
        external_payment_id=f"np-{product.code}-{user.id}",
        status=DepositStatus.VALIDATED,
    )
    db.add(row)
    db.flush()
    return row


def _lines_by_account(db) -> dict[str, list[JournalLine]]:
    out: dict[str, list[JournalLine]] = {}
    for code, line in db.query(ChartOfAccounts.account_code, JournalLine).join(
        JournalLine, JournalLine.account_id == ChartOfAccounts.id
    ):
        out.setdefault(code, []).append(line)
    return out


def _assert_every_journal_balanced(db) -> None:
    for entry in db.query(JournalEntry).all():
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        assert sum(Decimal(str(l.debit_amount)) for l in lines) == sum(Decimal(str(l.credit_amount)) for l in lines)


def test_missing_env_flag_means_retired_in_a_fresh_process():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    env.pop("LEGACY_BUSINESS_MODEL_ENABLED", None)
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print(settings.LEGACY_BUSINESS_MODEL_ENABLED)"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "False"


def test_flag_defaults_to_retired_and_efm_is_not_a_founding_product():
    assert legacy_business_model_enabled() is False
    assert founding_pool_rate() == Decimal("0")
    # K: EFM ($9.99 / 30-day) is distinct from the $100 Founding products.
    assert LEGACY_FOUNDING_PRODUCT_CODES == {"founding_membership", "mfm_membership"}
    assert is_legacy_founding_product("efm_membership") is False
    assert is_legacy_founding_product("MFM_MEMBERSHIP") is True


def test_new_payment_creates_no_multi_level_commissions_and_keeps_users(db):
    _accounts(db)
    kyc = _product(db, "kyc", 10)
    payer = _chain(db, depth=4)
    sponsor_before = {u.id: u.sponsor_id for u in db.query(User).all()}
    deposit = _deposit(db, payer, kyc, 10)

    # D/E: neither the engine nor the payment pipeline walks the hierarchy any more.
    assert distribute_commissions(db, deposit, "kyc", commit=False) == []
    assert process_payment_validation(db, deposit, defer_commit=True) is True
    db.commit()
    assert db.query(AffiliateCommission).count() == 0

    # A: users and sponsor relationships are untouched; the payment itself still posts (I).
    assert {u.id: u.sponsor_id for u in db.query(User).all()} == sponsor_before
    lines = _lines_by_account(db)
    assert sum(Decimal(str(l.debit_amount)) for l in lines["1001"]) == Decimal("10.00")
    assert sum(Decimal(str(l.credit_amount)) for l in lines["2113"]) == Decimal("10.00")


def test_kyc_recognition_accrues_no_founding_pool_but_posts_existing_commissions(db):
    _accounts(db)
    kyc = _product(db, "kyc", 10)
    payer = _chain(db, depth=2)
    deposit = _deposit(db, payer, kyc, 10)
    payment_accounting.process_kyc_cash_receipt_accounting(db, deposit, journal_commit=False)
    # A pre-retirement commission that already exists must still be accounted for.
    legacy = AffiliateCommission(
        user_id=payer.sponsor_id,
        source_user_id=payer.id,
        deposit_id=deposit.id,
        commission_type=CommissionType.KYC_PAYMENT,
        level=1,
        base_amount=10,
        commission_amount=1,
        status=CommissionStatus.APPROVED,
    )
    db.add(legacy)
    db.flush()

    payment_accounting.process_kyc_verification_performed_accounting(db, deposit, [legacy], journal_commit=False)
    db.commit()

    lines = _lines_by_account(db)
    assert "2104" not in lines  # F
    assert sum(Decimal(str(l.credit_amount)) for l in lines["4001"]) == Decimal("8.00")  # 10 - 2 Shufti
    assert sum(Decimal(str(l.credit_amount)) for l in lines["2001"]) == Decimal("1.00")
    _assert_every_journal_balanced(db)


@pytest.mark.parametrize(
    ("code", "amount", "deferred", "revenue"),
    [
        ("annual_membership", Decimal("50"), "2110", Decimal("50.00")),
        ("efm_membership", Decimal("9.99"), "2111", Decimal("9.99")),
    ],
)
def test_membership_payments_post_without_founding_pool_or_points(db, code, amount, deferred, revenue):
    _accounts(db)
    product = _product(db, code, amount, validity_days=30)
    payer = _chain(db, depth=3)
    deposit = _deposit(db, payer, product, amount)

    assert process_payment_validation(db, deposit, defer_commit=True) is True  # I
    db.commit()

    lines = _lines_by_account(db)
    assert "2104" not in lines  # F
    assert sum(Decimal(str(l.credit_amount)) for l in lines["4002"]) == revenue
    assert sum(Decimal(str(l.credit_amount)) for l in lines[deferred]) == amount
    assert db.query(AffiliateCommission).count() == 0
    assert db.query(MemberFmpLedger).count() == 0  # K: EFM never earns Founding points
    assert db.get(Deposit, deposit.id).expires_at is not None
    _assert_every_journal_balanced(db)


def test_historical_commissions_and_founding_records_remain_readable(db):
    sponsor = _user(db, "hist-sponsor@test.com")
    payer = _user(db, "hist-payer@test.com", sponsor_id=sponsor.id)
    kyc = ProductType(code="kyc", name="kyc", price=10, currency="USD")
    db.add(kyc)
    db.flush()
    deposit = _deposit(db, payer, kyc, 10)
    db.add_all(
        [
            AffiliateCommission(
                user_id=sponsor.id, source_user_id=payer.id, deposit_id=deposit.id,
                commission_type=CommissionType.KYC_PAYMENT, level=1, base_amount=10,
                commission_amount=Decimal("1.00"), status=CommissionStatus.APPROVED,
            ),
            AffiliateCommission(
                user_id=sponsor.id, source_user_id=payer.id, deposit_id=None, reference_id="legacy-l5",
                commission_type=CommissionType.KYC_PAYMENT, level=5, base_amount=10,
                commission_amount=Decimal("0.10"), status=CommissionStatus.PAID,
            ),
            MemberFmpLedger(user_id=sponsor.id, source_type="FOUNDING_JOIN", source_id=deposit.id, points=Decimal("1")),
            MemberFmpBalance(user_id=sponsor.id, total_fmp=Decimal("1")),
        ]
    )
    snap = FoundingPoolSnapshot(period_year=2026, period_month=8, accrued_pool_amount=12.5, member_count=1, status="posted")
    db.add(snap)
    db.flush()
    db.add(FoundingPoolSnapshotLine(snapshot_id=snap.id, user_id=sponsor.id, share_amount=12.5, weight_ratio=1))
    db.commit()

    # B: balances derived from history are unchanged by the retirement.
    balance = get_commission_balance(db, sponsor.id)
    assert balance.available == Decimal("1.00")
    assert balance.paid_lifetime == Decimal("0.10")
    assert balance.earned_lifetime == Decimal("1.10")
    # C: Founding history stays queryable.
    assert fmr_service.get_user_total_fmp(db, sponsor.id) == Decimal("1")
    assert db.query(FoundingPoolSnapshotLine).filter_by(user_id=sponsor.id).one().share_amount == Decimal("12.50")


def test_founding_points_and_distribution_writers_are_retired(db):
    sponsor = _user(db, "fmp-sponsor@test.com")
    payer = _user(db, "fmp-payer@test.com", sponsor_id=sponsor.id)
    assert fmr_service.record_founding_join_fmp(db, payer.id, 1) is False
    assert fmr_service.record_referral_kyc_fmp(db, verified_user_id=payer.id, kyc_verification_id=1) is False
    assert db.query(MemberFmpLedger).count() == 0

    # G: no new month-end allocation, approval or posting.
    with pytest.raises(LegacyBusinessModelRetiredError):
        prepare_founding_pool_month(db, year=2026, month=9, user_id=sponsor.id)
    with pytest.raises(LegacyBusinessModelRetiredError):
        approve_founding_pool_snapshot(db, 1, sponsor.id)
    with pytest.raises(LegacyBusinessModelRetiredError):
        post_founding_pool_snapshot(db, 1)
    with pytest.raises(LegacyBusinessModelRetiredError):
        backfill_missing_founding_pool_accruals(db, dry_run=False)
    assert db.query(FoundingPoolSnapshot).count() == 0


@pytest.fixture
def admin_client(client, db, app):
    admin = _user(db, "admin@test.com", is_admin=True)
    db.commit()
    app.dependency_overrides[deps.get_current_user] = lambda: admin
    yield client
    app.dependency_overrides.pop(deps.get_current_user, None)


def test_founding_enrollment_and_admin_writers_fail_clearly(admin_client, db):
    # H: purchase path.
    for code in ("founding_membership", "mfm_membership"):
        db.add(ProductType(code=code, name=code, price=100, currency="USD", validity_days=0))
    db.commit()
    for code in ("founding_membership", "mfm_membership"):
        response = admin_client.post(
            "/api/v1/payments/create",
            json={"product_code": code, "amount": "100.00", "currency": "USD"},
        )
        assert response.status_code == 410, response.text
    assert db.query(Deposit).count() == 0

    # H: admin grant of Founding products.
    target = _user(db, "grant-target@test.com")
    db.commit()
    for code in ("founding_membership", "mfm_membership"):
        response = admin_client.post(f"/api/v1/admin/users/{target.id}/grant-payment", json={"product_code": code})
        assert response.status_code == 410, response.text
    assert db.query(Deposit).count() == 0

    # G: Founding month-end and backfill endpoints.
    for path, body in (
        ("/api/v1/admin/accounting/founding-pool/prepare-month", {"year": 2026, "month": 9}),
        ("/api/v1/admin/accounting/founding-pool/1/approve", None),
        ("/api/v1/admin/accounting/founding-pool/1/post", None),
        ("/api/v1/admin/accounting/backfill-founding-pool-accruals?dry_run=true", None),
    ):
        response = admin_client.post(path, json=body)
        assert response.status_code == 410, (path, response.text)

    # Historical admin visibility stays available.
    assert admin_client.get("/api/v1/admin/accounting/founding-pool/snapshots").status_code == 200
