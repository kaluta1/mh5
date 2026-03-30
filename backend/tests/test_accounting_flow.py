from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base_class import Base
from app.models.accounting import ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.transaction import TransactionStatus, TransactionType, UserTransaction
from app.models.user import User
from app.services.accounting_posting import (
    AccountCode,
    CANONICAL_CHART_OF_ACCOUNTS,
    accounting_posting_service,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _create_user(db, email: str, sponsor_id: int | None = None) -> User:
    user = User(
        email=email,
        hashed_password="pw",
        is_active=True,
        full_name=email.split("@")[0],
        sponsor_id=sponsor_id,
    )
    db.add(user)
    db.flush()
    return user


def _create_product(
    db,
    code: str,
    price: float,
    *,
    validity_days: int = 365,
    is_consumable: bool = False,
) -> ProductType:
    product = ProductType(
        code=code,
        name=code.replace("_", " ").title(),
        price=price,
        currency="USD",
        validity_days=validity_days,
        is_consumable=is_consumable,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _entry_is_balanced(entry: JournalEntry) -> bool:
    debit = round(float(entry.total_debit or 0), 2)
    credit = round(float(entry.total_credit or 0), 2)
    return debit == credit


def _get_account(db, code: str) -> ChartOfAccounts:
    return db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).one()


def test_chart_of_accounts_seed_is_idempotent_and_finance_metadata_is_present(db):
    first_run_changes = accounting_posting_service.seed_chart_of_accounts(db)
    db.commit()

    second_run_changes = accounting_posting_service.seed_chart_of_accounts(db)
    db.commit()

    accounts = db.query(ChartOfAccounts).all()
    deferred_membership = _get_account(db, AccountCode.DEFERRED_MEMBERSHIP_REVENUE)
    contra_revenue = _get_account(db, AccountCode.SALES_RETURNS_AND_REFUNDS)

    assert first_run_changes >= len(CANONICAL_CHART_OF_ACCOUNTS)
    assert second_run_changes == 0
    assert len(accounts) == len(CANONICAL_CHART_OF_ACCOUNTS)
    assert deferred_membership.normal_balance == "credit"
    assert deferred_membership.statement_section == "current_liability"
    assert deferred_membership.report_group == "Deferred Revenue"
    assert contra_revenue.is_contra_account is True
    assert contra_revenue.normal_balance == "debit"


def test_membership_deposit_posts_deferral_release_and_statements(db):
    accounting_posting_service.seed_chart_of_accounts(db)

    sponsor = _create_user(db, "sponsor@example.com")
    user = _create_user(db, "member@example.com", sponsor_id=sponsor.id)
    membership = _create_product(db, "annual_membership", 60.0, validity_days=60)

    validated_at = datetime(2026, 1, 15, 10, 0, 0)
    deposit = Deposit(
        user_id=user.id,
        product_type_id=membership.id,
        amount=60.0,
        currency="USD",
        status=DepositStatus.VALIDATED,
        order_id="ORD-MEM-1",
        external_payment_id="TX-MEM-1",
        validated_at=validated_at,
    )
    db.add(deposit)
    db.flush()
    deposit.product_type = membership

    commission = AffiliateCommission(
        user_id=sponsor.id,
        source_user_id=user.id,
        product_type_id=membership.id,
        deposit_id=deposit.id,
        commission_type=CommissionType.ANNUAL_MEMBERSHIP_FEE,
        level=1,
        base_amount=60.0,
        commission_amount=6.0,
        status=CommissionStatus.APPROVED,
        transaction_date=validated_at,
    )
    db.add(commission)
    db.flush()

    _, created_count = accounting_posting_service.ensure_deposit_postings(
        db,
        deposit,
        commissions=[commission],
        as_of_date=datetime(2026, 1, 31, 23, 59, 59),
    )
    db.commit()

    entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "deposit", JournalEntry.source_id == str(deposit.id))
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        .all()
    )
    event_types = [entry.event_type for entry in entries]

    assert created_count == 4
    assert event_types == [
        "deposit_validated",
        "deposit_settled",
        "affiliate_commission_accrued",
        "membership_revenue_20260131",
    ]
    assert all(_entry_is_balanced(entry) for entry in entries)

    january_income_statement = accounting_posting_service.get_income_statement(
        db,
        start_date=datetime(2026, 1, 1, 0, 0, 0),
        end_date=datetime(2026, 1, 31, 23, 59, 59),
    )
    january_balance_sheet = accounting_posting_service.get_balance_sheet(
        db,
        as_of_date=datetime(2026, 1, 31, 23, 59, 59),
    )
    deferred_gl = accounting_posting_service.get_general_ledger(
        db,
        account_code=AccountCode.DEFERRED_MEMBERSHIP_REVENUE,
        start_date=datetime(2026, 1, 1, 0, 0, 0),
        end_date=datetime(2026, 1, 31, 23, 59, 59),
    )
    deposit_reconciliation = accounting_posting_service.build_reconciliation_map(db, "deposit", [str(deposit.id)])

    assert january_income_statement["net_revenue"] > 0
    assert january_income_statement["operating_income"] < january_income_statement["net_revenue"]
    assert january_balance_sheet["is_balanced"] is True
    assert january_balance_sheet["total_liabilities"] > 0
    assert len(deferred_gl["lines"]) == 2
    assert deferred_gl["opening_balance"] == 0.0
    assert deferred_gl["closing_balance"] > 0.0
    assert len(deposit_reconciliation[str(deposit.id)]) == 4


def test_kyc_revenue_is_deferred_until_service_is_used(db):
    accounting_posting_service.seed_chart_of_accounts(db)

    user = _create_user(db, "kyc@example.com")
    product = _create_product(db, "kyc", 10.0, validity_days=1, is_consumable=True)

    validated_at = datetime(2026, 2, 1, 9, 0, 0)
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=10.0,
        currency="USD",
        status=DepositStatus.VALIDATED,
        order_id="ORD-KYC-1",
        external_payment_id="TX-KYC-1",
        validated_at=validated_at,
        is_used=False,
    )
    db.add(deposit)
    db.flush()
    deposit.product_type = product

    _, initial_created = accounting_posting_service.ensure_deposit_postings(
        db,
        deposit,
        commissions=[],
        as_of_date=validated_at,
    )
    db.commit()

    initial_entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "deposit", JournalEntry.source_id == str(deposit.id))
        .all()
    )
    initial_event_types = {entry.event_type for entry in initial_entries}
    initial_balance_sheet = accounting_posting_service.get_balance_sheet(db, as_of_date=validated_at)

    deposit.is_used = True
    deposit.used_at = datetime(2026, 2, 2, 12, 0, 0)
    _, follow_up_created = accounting_posting_service.ensure_deposit_postings(
        db,
        deposit,
        commissions=[],
        as_of_date=deposit.used_at,
    )
    db.commit()

    used_entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "deposit", JournalEntry.source_id == str(deposit.id))
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc())
        .all()
    )
    used_event_types = {entry.event_type for entry in used_entries}
    used_income_statement = accounting_posting_service.get_income_statement(
        db,
        start_date=datetime(2026, 2, 1, 0, 0, 0),
        end_date=datetime(2026, 2, 28, 23, 59, 59),
    )

    assert initial_created == 3
    assert initial_event_types == {"deposit_validated", "deposit_settled", "kyc_vendor_fee_accrued"}
    assert initial_balance_sheet["total_liabilities"] > 0
    assert follow_up_created == 1
    assert "service_revenue_recognized" in used_event_types
    assert all(_entry_is_balanced(entry) for entry in used_entries)
    assert used_income_statement["net_revenue"] == 10.0


def test_prize_refund_and_commission_transactions_are_classified_and_reconcilable(db):
    accounting_posting_service.seed_chart_of_accounts(db)
    user = _create_user(db, "wallet-user@example.com")

    prize_transaction = UserTransaction(
        user_id=user.id,
        amount=25.0,
        currency="USD",
        transaction_type=TransactionType.PRIZE_PAYOUT,
        status=TransactionStatus.COMPLETED,
        description="Prize awarded to winner",
        reference="PRIZE-1",
        payment_method="wallet",
        payment_reference="WALLET-PRIZE-1",
        processed_at=datetime(2026, 3, 5, 12, 0, 0),
    )
    sales_refund = UserTransaction(
        user_id=user.id,
        amount=12.0,
        currency="USD",
        transaction_type=TransactionType.REFUND,
        status=TransactionStatus.COMPLETED,
        description="Membership refund for billing issue",
        reference="REFUND-1",
        payment_method="wallet",
        payment_reference="WALLET-REFUND-1",
        processed_at=datetime(2026, 3, 6, 12, 0, 0),
    )
    operating_refund = UserTransaction(
        user_id=user.id,
        amount=7.0,
        currency="USD",
        transaction_type=TransactionType.REFUND,
        status=TransactionStatus.COMPLETED,
        description="Manual goodwill adjustment",
        reference="REFUND-2",
        payment_method="wallet",
        payment_reference="WALLET-REFUND-2",
        processed_at=datetime(2026, 3, 7, 12, 0, 0),
    )
    wallet_commission = UserTransaction(
        user_id=user.id,
        amount=5.0,
        currency="USD",
        transaction_type=TransactionType.COMMISSION,
        status=TransactionStatus.COMPLETED,
        description="Affiliate commission credited",
        reference="COMM-1",
        payment_method="wallet",
        payment_reference="WALLET-COMM-1",
        processed_at=datetime(2026, 3, 8, 12, 0, 0),
    )
    db.add_all([prize_transaction, sales_refund, operating_refund, wallet_commission])
    db.commit()

    prize_entries, prize_created = accounting_posting_service.ensure_user_transaction_postings(db, prize_transaction)
    sales_refund_entries, sales_refund_created = accounting_posting_service.ensure_user_transaction_postings(db, sales_refund)
    operating_refund_entries, operating_refund_created = accounting_posting_service.ensure_user_transaction_postings(db, operating_refund)
    commission_entries, commission_created = accounting_posting_service.ensure_user_transaction_postings(db, wallet_commission)
    db.commit()

    all_entries = prize_entries + sales_refund_entries + operating_refund_entries + commission_entries
    reconciliation = accounting_posting_service.build_reconciliation_map(
        db,
        "transaction",
        [str(prize_transaction.id), str(sales_refund.id), str(operating_refund.id), str(wallet_commission.id)],
    )
    march_income_statement = accounting_posting_service.get_income_statement(
        db,
        start_date=datetime(2026, 3, 1, 0, 0, 0),
        end_date=datetime(2026, 3, 31, 23, 59, 59),
    )
    march_balance_sheet = accounting_posting_service.get_balance_sheet(
        db,
        as_of_date=datetime(2026, 3, 31, 23, 59, 59),
    )

    assert prize_created == 2
    assert sales_refund_created == 1
    assert operating_refund_created == 1
    assert commission_created == 1
    assert all(_entry_is_balanced(entry) for entry in all_entries)

    assert prize_entries[0].event_type == "prize_obligation_accrued"
    assert prize_entries[1].event_type == "prize_payout_settled"
    assert sales_refund_entries[0].lines[0].account.account_code == AccountCode.SALES_RETURNS_AND_REFUNDS
    assert operating_refund_entries[0].lines[0].account.account_code == AccountCode.NON_SALES_REFUND_EXPENSE
    assert commission_entries[0].lines[1].account.account_code == AccountCode.USER_WALLET_LIABILITY

    assert len(reconciliation[str(prize_transaction.id)]) == 2
    assert len(reconciliation[str(sales_refund.id)]) == 1
    assert len(reconciliation[str(operating_refund.id)]) == 1
    assert len(reconciliation[str(wallet_commission.id)]) == 1

    assert any(line["account_code"] == AccountCode.SALES_RETURNS_AND_REFUNDS for line in march_income_statement["contra_revenue"])
    assert any(line["account_code"] == AccountCode.PRIZE_EXPENSE for line in march_income_statement["cost_of_sales"])
    assert march_balance_sheet["is_balanced"] is True
