from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional
import calendar
import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.accounting import AccountType, ChartOfAccounts, EntryStatus, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.transaction import TransactionStatus, TransactionType, UserTransaction


MONEY_QUANTUM = Decimal("0.01")


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _as_datetime_end(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.max)


def _as_datetime_start(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min)


def _month_end(dt: datetime) -> datetime:
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return datetime(dt.year, dt.month, last_day, 23, 59, 59)


class NormalBalance:
    DEBIT = "debit"
    CREDIT = "credit"


class StatementSection:
    CURRENT_ASSET = "current_asset"
    CURRENT_LIABILITY = "current_liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    CONTRA_REVENUE = "contra_revenue"
    DIRECT_COST = "direct_cost"
    OPERATING_EXPENSE = "operating_expense"
    OTHER_GAIN_LOSS = "other_gain_loss"


class AccountCode:
    CURRENT_ASSETS = "1000"
    OPERATING_CASH = "1010"
    PROCESSOR_CLEARING = "1020"
    RESTRICTED_FUNDS = "1030"
    OTHER_RECEIVABLES = "1040"

    CURRENT_LIABILITIES = "2000"
    USER_WALLET_LIABILITY = "2010"
    COMMISSION_PAYABLE = "2020"
    PRIZE_PAYABLE = "2030"
    TAX_PAYABLE = "2040"
    KYC_VENDOR_PAYABLE = "2050"
    DEFERRED_MEMBERSHIP_REVENUE = "2060"
    DEFERRED_SERVICE_REVENUE = "2070"

    EQUITY = "3000"
    RETAINED_EARNINGS = "3100"

    REVENUE = "4000"
    KYC_REVENUE = "4010"
    MEMBERSHIP_REVENUE = "4020"
    CONTEST_ENTRY_REVENUE = "4030"
    ADVERTISING_REVENUE = "4040"
    CLUB_REVENUE = "4050"
    OTHER_REVENUE = "4060"
    SALES_RETURNS_AND_REFUNDS = "4090"

    DIRECT_COSTS = "5000"
    KYC_PROVIDER_FEES = "5010"
    PRIZE_EXPENSE = "5020"
    PAYOUT_PROCESSING_FEES = "5030"

    OPERATING_EXPENSES = "6000"
    COMMISSION_EXPENSE = "6010"
    PLATFORM_OPERATIONS = "6020"
    NON_SALES_REFUND_EXPENSE = "6030"
    FX_GAIN_LOSS = "6040"


@dataclass(frozen=True)
class AccountDefinition:
    code: str
    name: str
    account_type: AccountType
    parent: Optional[str]
    description: str
    normal_balance: str
    statement_section: str
    report_group: str
    sort_order: int
    is_contra_account: bool = False


@dataclass(frozen=True)
class ProductPolicy:
    initial_credit_account: str
    recognition_mode: str  # immediate, on_use, over_time
    recognized_revenue_account: str
    tax_account: Optional[str] = None
    vendor_fee_rate: Decimal = Decimal("0.00")


CANONICAL_CHART_OF_ACCOUNTS: List[AccountDefinition] = [
    AccountDefinition(AccountCode.CURRENT_ASSETS, "Current Assets", AccountType.ASSET, None, "Top-level current asset accounts.", NormalBalance.DEBIT, StatementSection.CURRENT_ASSET, "Current Assets", 1000),
    AccountDefinition(AccountCode.OPERATING_CASH, "Operating Cash / USDT Treasury", AccountType.ASSET, AccountCode.CURRENT_ASSETS, "Operating cash and on-platform treasury balances.", NormalBalance.DEBIT, StatementSection.CURRENT_ASSET, "Cash and Cash Equivalents", 1010),
    AccountDefinition(AccountCode.PROCESSOR_CLEARING, "Processor Clearing Receivable", AccountType.ASSET, AccountCode.CURRENT_ASSETS, "Amounts validated but still clearing from payment processors.", NormalBalance.DEBIT, StatementSection.CURRENT_ASSET, "Receivables", 1020),
    AccountDefinition(AccountCode.RESTRICTED_FUNDS, "Restricted / Frozen Funds", AccountType.ASSET, AccountCode.CURRENT_ASSETS, "Crypto or other funds validated but not yet released to operating treasury.", NormalBalance.DEBIT, StatementSection.CURRENT_ASSET, "Restricted Funds", 1030),
    AccountDefinition(AccountCode.OTHER_RECEIVABLES, "Affiliate / Other Receivables", AccountType.ASSET, AccountCode.CURRENT_ASSETS, "Receivables owed to the platform outside processor settlement.", NormalBalance.DEBIT, StatementSection.CURRENT_ASSET, "Receivables", 1040),

    AccountDefinition(AccountCode.CURRENT_LIABILITIES, "Current Liabilities", AccountType.LIABILITY, None, "Top-level current liability accounts.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Current Liabilities", 2000),
    AccountDefinition(AccountCode.USER_WALLET_LIABILITY, "User Wallet Liability", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Amounts owed to users in their platform wallets.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Wallet and User Balances", 2010),
    AccountDefinition(AccountCode.COMMISSION_PAYABLE, "Affiliate Commission Payable", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Approved affiliate commissions awaiting settlement.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Payables", 2020),
    AccountDefinition(AccountCode.PRIZE_PAYABLE, "Prize Payable", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Prize obligations accrued before wallet credit or cash payment.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Payables", 2030),
    AccountDefinition(AccountCode.TAX_PAYABLE, "Sales Tax / VAT Payable", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Indirect taxes collected and not yet remitted.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Taxes", 2040),
    AccountDefinition(AccountCode.KYC_VENDOR_PAYABLE, "KYC Vendor Payable", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Amounts owed to KYC verification providers.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Payables", 2050),
    AccountDefinition(AccountCode.DEFERRED_MEMBERSHIP_REVENUE, "Deferred Membership Revenue", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Membership cash collected before earning over the service period.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Deferred Revenue", 2060),
    AccountDefinition(AccountCode.DEFERRED_SERVICE_REVENUE, "Deferred Service Revenue", AccountType.LIABILITY, AccountCode.CURRENT_LIABILITIES, "Service cash collected before the underlying obligation is satisfied.", NormalBalance.CREDIT, StatementSection.CURRENT_LIABILITY, "Deferred Revenue", 2070),

    AccountDefinition(AccountCode.EQUITY, "Equity", AccountType.EQUITY, None, "Top-level equity accounts.", NormalBalance.CREDIT, StatementSection.EQUITY, "Equity", 3000),
    AccountDefinition(AccountCode.RETAINED_EARNINGS, "Retained Earnings", AccountType.EQUITY, AccountCode.EQUITY, "Accumulated profit retained in the business.", NormalBalance.CREDIT, StatementSection.EQUITY, "Retained Earnings", 3100),

    AccountDefinition(AccountCode.REVENUE, "Revenue", AccountType.REVENUE, None, "Top-level revenue accounts.", NormalBalance.CREDIT, StatementSection.REVENUE, "Revenue", 4000),
    AccountDefinition(AccountCode.KYC_REVENUE, "KYC Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Recognized revenue from KYC services.", NormalBalance.CREDIT, StatementSection.REVENUE, "Service Revenue", 4010),
    AccountDefinition(AccountCode.MEMBERSHIP_REVENUE, "Membership Revenue Recognized", AccountType.REVENUE, AccountCode.REVENUE, "Recognized membership revenue released from deferred revenue.", NormalBalance.CREDIT, StatementSection.REVENUE, "Membership Revenue", 4020),
    AccountDefinition(AccountCode.CONTEST_ENTRY_REVENUE, "Contest Entry Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Recognized contest entry fees.", NormalBalance.CREDIT, StatementSection.REVENUE, "Contest Revenue", 4030),
    AccountDefinition(AccountCode.ADVERTISING_REVENUE, "Advertising Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Recognized advertising and sponsorship revenue.", NormalBalance.CREDIT, StatementSection.REVENUE, "Advertising Revenue", 4040),
    AccountDefinition(AccountCode.CLUB_REVENUE, "Club Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Recognized fan club and membership revenue outside core subscriptions.", NormalBalance.CREDIT, StatementSection.REVENUE, "Club Revenue", 4050),
    AccountDefinition(AccountCode.OTHER_REVENUE, "Shop / Other Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Recognized non-core revenue streams.", NormalBalance.CREDIT, StatementSection.REVENUE, "Other Revenue", 4060),
    AccountDefinition(AccountCode.SALES_RETURNS_AND_REFUNDS, "Sales Returns / Refund Contra-Revenue", AccountType.REVENUE, AccountCode.REVENUE, "Refunds tied directly to revenue-producing sales.", NormalBalance.DEBIT, StatementSection.CONTRA_REVENUE, "Contra Revenue", 4090, True),

    AccountDefinition(AccountCode.DIRECT_COSTS, "Cost of Sales / Direct Costs", AccountType.EXPENSE, None, "Top-level direct cost accounts.", NormalBalance.DEBIT, StatementSection.DIRECT_COST, "Cost of Sales", 5000),
    AccountDefinition(AccountCode.KYC_PROVIDER_FEES, "KYC Provider Fees", AccountType.EXPENSE, AccountCode.DIRECT_COSTS, "Direct vendor fees for identity verification.", NormalBalance.DEBIT, StatementSection.DIRECT_COST, "Service Delivery Costs", 5010),
    AccountDefinition(AccountCode.PRIZE_EXPENSE, "Prize Expense Recognized", AccountType.EXPENSE, AccountCode.DIRECT_COSTS, "Prize expense recognized when winner obligations are accrued.", NormalBalance.DEBIT, StatementSection.DIRECT_COST, "Contest Costs", 5020),
    AccountDefinition(AccountCode.PAYOUT_PROCESSING_FEES, "Payment / Payout Processing Fees", AccountType.EXPENSE, AccountCode.DIRECT_COSTS, "Direct processor and payout fees.", NormalBalance.DEBIT, StatementSection.DIRECT_COST, "Processing Costs", 5030),

    AccountDefinition(AccountCode.OPERATING_EXPENSES, "Operating Expenses", AccountType.EXPENSE, None, "Top-level operating expense accounts.", NormalBalance.DEBIT, StatementSection.OPERATING_EXPENSE, "Operating Expenses", 6000),
    AccountDefinition(AccountCode.COMMISSION_EXPENSE, "Affiliate Commission Expense", AccountType.EXPENSE, AccountCode.OPERATING_EXPENSES, "Affiliate commission expense recognized on qualifying revenue.", NormalBalance.DEBIT, StatementSection.OPERATING_EXPENSE, "Sales and Marketing", 6010),
    AccountDefinition(AccountCode.PLATFORM_OPERATIONS, "Platform Operations Expense", AccountType.EXPENSE, AccountCode.OPERATING_EXPENSES, "General platform operating and administrative costs.", NormalBalance.DEBIT, StatementSection.OPERATING_EXPENSE, "General and Administrative", 6020),
    AccountDefinition(AccountCode.NON_SALES_REFUND_EXPENSE, "Non-Sales Refund / Adjustment Expense", AccountType.EXPENSE, AccountCode.OPERATING_EXPENSES, "Refunds and adjustments not tied directly to a revenue stream.", NormalBalance.DEBIT, StatementSection.OPERATING_EXPENSE, "General and Administrative", 6030),
    AccountDefinition(AccountCode.FX_GAIN_LOSS, "FX Gain / Loss", AccountType.EXPENSE, AccountCode.OPERATING_EXPENSES, "Foreign exchange remeasurement gains or losses.", NormalBalance.DEBIT, StatementSection.OTHER_GAIN_LOSS, "FX and Other", 6040),
]


PRODUCT_POLICIES: Dict[str, ProductPolicy] = {
    "kyc": ProductPolicy(
        initial_credit_account=AccountCode.DEFERRED_SERVICE_REVENUE,
        recognition_mode="on_use",
        recognized_revenue_account=AccountCode.KYC_REVENUE,
        vendor_fee_rate=Decimal("0.20"),
    ),
    "annual_membership": ProductPolicy(
        initial_credit_account=AccountCode.DEFERRED_MEMBERSHIP_REVENUE,
        recognition_mode="over_time",
        recognized_revenue_account=AccountCode.MEMBERSHIP_REVENUE,
    ),
    "mfm_membership": ProductPolicy(
        initial_credit_account=AccountCode.DEFERRED_MEMBERSHIP_REVENUE,
        recognition_mode="over_time",
        recognized_revenue_account=AccountCode.MEMBERSHIP_REVENUE,
    ),
    "efm_membership": ProductPolicy(
        initial_credit_account=AccountCode.DEFERRED_MEMBERSHIP_REVENUE,
        recognition_mode="over_time",
        recognized_revenue_account=AccountCode.MEMBERSHIP_REVENUE,
    ),
}


DEFAULT_PRODUCT_POLICY = ProductPolicy(
    initial_credit_account=AccountCode.OTHER_REVENUE,
    recognition_mode="immediate",
    recognized_revenue_account=AccountCode.OTHER_REVENUE,
)


@dataclass
class SyncResult:
    seeded_accounts: int = 0
    created_entries: int = 0


class AccountingPostingError(Exception):
    pass


class AccountingPostingService:
    def seed_chart_of_accounts(self, db: Session) -> int:
        account_by_code = {
            account.account_code: account
            for account in db.query(ChartOfAccounts).all()
        }
        changed_count = 0

        for definition in CANONICAL_CHART_OF_ACCOUNTS:
            parent_id = account_by_code[definition.parent].id if definition.parent else None
            account = account_by_code.get(definition.code)
            if not account:
                account = ChartOfAccounts(
                    account_code=definition.code,
                    account_name=definition.name,
                    account_type=definition.account_type,
                    parent_id=parent_id,
                    description=definition.description,
                    is_active=True,
                    normal_balance=definition.normal_balance,
                    statement_section=definition.statement_section,
                    report_group=definition.report_group,
                    sort_order=definition.sort_order,
                    is_contra_account=definition.is_contra_account,
                )
                db.add(account)
                db.flush()
                account_by_code[definition.code] = account
                changed_count += 1
                continue

            changed = False
            for field_name, value in (
                ("account_name", definition.name),
                ("account_type", definition.account_type),
                ("parent_id", parent_id),
                ("description", definition.description),
                ("normal_balance", definition.normal_balance),
                ("statement_section", definition.statement_section),
                ("report_group", definition.report_group),
                ("sort_order", definition.sort_order),
                ("is_contra_account", definition.is_contra_account),
            ):
                if getattr(account, field_name) != value:
                    setattr(account, field_name, value)
                    changed = True

            if not account.is_active:
                account.is_active = True
                changed = True

            if changed:
                changed_count += 1

        return changed_count

    def _get_product_policy(self, product_code: Optional[str]) -> ProductPolicy:
        if not product_code:
            return DEFAULT_PRODUCT_POLICY
        return PRODUCT_POLICIES.get(product_code, DEFAULT_PRODUCT_POLICY)

    def _build_entry_number(self, event_type: str) -> str:
        suffix = str(uuid.uuid4())[:8].upper()
        return f"JE-{event_type[:16].upper()}-{datetime.utcnow():%Y%m%d}-{suffix}"

    def _get_account(self, db: Session, account_code: str) -> ChartOfAccounts:
        account = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == account_code).first()
        if not account:
            self.seed_chart_of_accounts(db)
            db.flush()
            account = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == account_code).first()
        if not account:
            raise AccountingPostingError(f"Missing account code {account_code}")
        return account

    def _validate_lines(self, lines: Iterable[Dict[str, Any]]) -> tuple[Decimal, Decimal]:
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for line in lines:
            total_debit += _money(line.get("debit"))
            total_credit += _money(line.get("credit"))
        if total_debit != total_credit:
            raise AccountingPostingError(f"Journal entry is not balanced: debit={total_debit} credit={total_credit}")
        return total_debit, total_credit

    def _ensure_entry(
        self,
        db: Session,
        *,
        event_type: str,
        source_type: str,
        source_id: str,
        description: str,
        lines: List[Dict[str, Any]],
        entry_date: Optional[datetime] = None,
        created_by: Optional[int] = None,
        reference_number: Optional[str] = None,
        source_ref: Optional[str] = None,
        source_document: Optional[str] = None,
        source_metadata: Optional[dict] = None,
    ) -> tuple[JournalEntry, bool]:
        self.seed_chart_of_accounts(db)
        existing = db.query(JournalEntry).filter(
            JournalEntry.event_type == event_type,
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == str(source_id),
        ).first()
        if existing:
            return existing, False

        total_debit, total_credit = self._validate_lines(lines)
        entry = JournalEntry(
            entry_number=self._build_entry_number(event_type),
            entry_date=entry_date or datetime.utcnow(),
            description=description,
            reference_number=reference_number,
            source_document=source_document,
            event_type=event_type,
            source_type=source_type,
            source_id=str(source_id),
            source_ref=source_ref,
            source_metadata=source_metadata,
            total_debit=total_debit,
            total_credit=total_credit,
            status=EntryStatus.POSTED,
            created_by=created_by,
            posted_at=datetime.utcnow(),
        )
        db.add(entry)
        db.flush()

        for line in lines:
            account = self._get_account(db, line["account_code"])
            db.add(
                JournalLine(
                    entry_id=entry.id,
                    account_id=account.id,
                    debit_amount=_money(line.get("debit")),
                    credit_amount=_money(line.get("credit")),
                    description=line.get("description"),
                    reference_id=str(source_id),
                    reference_type=source_type,
                )
            )

        db.flush()
        return entry, True

    def create_entry(self, db: Session, **kwargs: Any) -> JournalEntry:
        entry, _ = self._ensure_entry(db, **kwargs)
        return entry

    def _get_deposit_product(self, db: Session, deposit: Deposit) -> Optional[ProductType]:
        product = getattr(deposit, "product_type", None)
        if product:
            return product
        return db.query(ProductType).filter(ProductType.id == deposit.product_type_id).first()

    def _deposit_holding_account(self, deposit: Deposit) -> str:
        if getattr(deposit, "crypto_currency", None):
            return AccountCode.RESTRICTED_FUNDS
        return AccountCode.PROCESSOR_CLEARING

    def _net_sale_amount(self, total_amount: Decimal, tax_amount: Decimal) -> Decimal:
        net_amount = total_amount - tax_amount
        return _money(net_amount if net_amount >= 0 else 0)

    def _explicit_tax_amount(self, source_metadata: Optional[dict]) -> Decimal:
        if not source_metadata:
            return Decimal("0.00")
        return _money(source_metadata.get("tax_amount", 0))

    def _build_membership_schedule(
        self,
        amount: Decimal,
        start_at: datetime,
        end_at: datetime,
        as_of_date: datetime,
    ) -> List[tuple[str, datetime, Decimal]]:
        recognize_until = min(as_of_date, end_at)
        if recognize_until <= start_at:
            return []

        total_seconds = Decimal(str((end_at - start_at).total_seconds()))
        if total_seconds <= 0:
            return []

        schedule: List[tuple[str, datetime, Decimal]] = []
        cursor = start_at
        recognized = Decimal("0.00")

        while cursor < recognize_until:
            period_end = min(_month_end(cursor), recognize_until, end_at)
            elapsed = Decimal(str((period_end - cursor).total_seconds()))
            if elapsed <= 0:
                break
            if period_end >= recognize_until:
                period_amount = amount - recognized
            else:
                period_amount = _money(amount * (elapsed / total_seconds))
                recognized += period_amount
            event_type = f"membership_revenue_{period_end:%Y%m%d}"
            schedule.append((event_type, period_end, _money(period_amount)))
            cursor = period_end + timedelta(seconds=1)

        return [(event_type, event_date, value) for event_type, event_date, value in schedule if value > 0]

    def _refund_account(self, transaction: UserTransaction) -> str:
        haystack = " ".join(
            filter(
                None,
                [
                    transaction.description or "",
                    transaction.reference or "",
                    transaction.payment_reference or "",
                ],
            )
        ).lower()
        if transaction.contest_id or any(token in haystack for token in ("deposit", "membership", "kyc", "entry", "contest")):
            return AccountCode.SALES_RETURNS_AND_REFUNDS
        return AccountCode.NON_SALES_REFUND_EXPENSE

    def ensure_deposit_postings(
        self,
        db: Session,
        deposit: Deposit,
        commissions: Optional[List[AffiliateCommission]] = None,
        created_by: Optional[int] = None,
        as_of_date: Optional[datetime] = None,
    ) -> tuple[JournalEntry, int]:
        if deposit.status != DepositStatus.VALIDATED:
            raise AccountingPostingError("Only validated deposits can be posted.")

        product = self._get_deposit_product(db, deposit)
        product_code = product.code if product else None
        policy = self._get_product_policy(product_code)
        posting_date = deposit.validated_at or deposit.created_at or datetime.utcnow()
        as_of = as_of_date or datetime.utcnow()
        commissions = commissions or []

        amount = _money(deposit.amount)
        tax_amount = self._explicit_tax_amount(getattr(deposit, "source_metadata", None))
        net_sale_amount = self._net_sale_amount(amount, tax_amount)
        total_commissions = sum((_money(item.commission_amount) for item in commissions), Decimal("0.00"))
        vendor_fee = _money(amount * policy.vendor_fee_rate)

        holding_account = self._deposit_holding_account(deposit)
        sale_entry, created_count = self._ensure_entry(
            db,
            event_type="deposit_validated",
            source_type="deposit",
            source_id=str(deposit.id),
            description=f"Validated {product_code or 'payment'} deposit #{deposit.id}",
            lines=[
                {
                    "account_code": holding_account,
                    "debit": amount,
                    "credit": 0,
                    "description": f"Validated funds recorded for deposit #{deposit.id}",
                },
                {
                    "account_code": policy.initial_credit_account,
                    "debit": 0,
                    "credit": net_sale_amount,
                    "description": f"Initial recognition for deposit #{deposit.id}",
                },
                *(
                    [
                        {
                            "account_code": AccountCode.TAX_PAYABLE,
                            "debit": 0,
                            "credit": tax_amount,
                            "description": f"Indirect tax collected for deposit #{deposit.id}",
                        }
                    ]
                    if tax_amount > 0
                    else []
                ),
            ],
            entry_date=posting_date,
            created_by=created_by,
            reference_number=deposit.order_id,
            source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
            source_document=product_code,
            source_metadata={
                "user_id": deposit.user_id,
                "product_code": product_code,
                "gross_amount": float(amount),
                "net_sale_amount": float(net_sale_amount),
                "tax_amount": float(tax_amount),
                "recognition_mode": policy.recognition_mode,
            },
        )

        _, created = self._ensure_entry(
            db,
            event_type="deposit_settled",
            source_type="deposit",
            source_id=str(deposit.id),
            description=f"Settlement to treasury for deposit #{deposit.id}",
            lines=[
                {
                    "account_code": AccountCode.OPERATING_CASH,
                    "debit": amount,
                    "credit": 0,
                    "description": f"Treasury funded for deposit #{deposit.id}",
                },
                {
                    "account_code": holding_account,
                    "debit": 0,
                    "credit": amount,
                    "description": f"Clearing / restricted balance released for deposit #{deposit.id}",
                },
            ],
            entry_date=posting_date,
            created_by=created_by,
            reference_number=deposit.order_id,
            source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
            source_document=product_code,
            source_metadata={"user_id": deposit.user_id, "product_code": product_code},
        )
        created_count += int(created)

        if total_commissions > 0:
            _, created = self._ensure_entry(
                db,
                event_type="affiliate_commission_accrued",
                source_type="deposit",
                source_id=str(deposit.id),
                description=f"Affiliate commissions accrued for deposit #{deposit.id}",
                lines=[
                    {
                        "account_code": AccountCode.COMMISSION_EXPENSE,
                        "debit": total_commissions,
                        "credit": 0,
                        "description": f"Commission expense for deposit #{deposit.id}",
                    },
                    {
                        "account_code": AccountCode.COMMISSION_PAYABLE,
                        "debit": 0,
                        "credit": total_commissions,
                        "description": f"Commission payable accrued for deposit #{deposit.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=deposit.order_id,
                source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
                source_document=product_code,
                source_metadata={
                    "user_id": deposit.user_id,
                    "commission_total": float(total_commissions),
                    "product_code": product_code,
                },
            )
            created_count += int(created)

        if vendor_fee > 0:
            _, created = self._ensure_entry(
                db,
                event_type="kyc_vendor_fee_accrued",
                source_type="deposit",
                source_id=str(deposit.id),
                description=f"KYC vendor fee accrued for deposit #{deposit.id}",
                lines=[
                    {
                        "account_code": AccountCode.KYC_PROVIDER_FEES,
                        "debit": vendor_fee,
                        "credit": 0,
                        "description": f"KYC vendor fee expense for deposit #{deposit.id}",
                    },
                    {
                        "account_code": AccountCode.KYC_VENDOR_PAYABLE,
                        "debit": 0,
                        "credit": vendor_fee,
                        "description": f"KYC vendor payable for deposit #{deposit.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=deposit.order_id,
                source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
                source_document=product_code,
                source_metadata={"user_id": deposit.user_id, "vendor_fee": float(vendor_fee)},
            )
            created_count += int(created)

        if policy.recognition_mode == "on_use" and deposit.is_used:
            recognition_date = deposit.used_at or posting_date
            _, created = self._ensure_entry(
                db,
                event_type="service_revenue_recognized",
                source_type="deposit",
                source_id=str(deposit.id),
                description=f"Service revenue recognized for deposit #{deposit.id}",
                lines=[
                    {
                        "account_code": policy.initial_credit_account,
                        "debit": net_sale_amount,
                        "credit": 0,
                        "description": f"Deferred service revenue released for deposit #{deposit.id}",
                    },
                    {
                        "account_code": policy.recognized_revenue_account,
                        "debit": 0,
                        "credit": net_sale_amount,
                        "description": f"KYC revenue recognized for deposit #{deposit.id}",
                    },
                ],
                entry_date=recognition_date,
                created_by=created_by,
                reference_number=deposit.order_id,
                source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
                source_document=product_code,
                source_metadata={"user_id": deposit.user_id, "recognition_mode": "on_use"},
            )
            created_count += int(created)

        if policy.recognition_mode == "over_time" and product:
            validity_days = max(int(getattr(product, "validity_days", 0) or 0), 1)
            start_at = posting_date
            end_at = posting_date + timedelta(days=validity_days)
            for event_type, recognition_date, recognition_amount in self._build_membership_schedule(
                net_sale_amount,
                start_at,
                end_at,
                as_of,
            ):
                _, created = self._ensure_entry(
                    db,
                    event_type=event_type,
                    source_type="deposit",
                    source_id=str(deposit.id),
                    description=f"Membership revenue recognized for deposit #{deposit.id}",
                    lines=[
                        {
                            "account_code": policy.initial_credit_account,
                            "debit": recognition_amount,
                            "credit": 0,
                            "description": f"Deferred membership revenue released for deposit #{deposit.id}",
                        },
                        {
                            "account_code": policy.recognized_revenue_account,
                            "debit": 0,
                            "credit": recognition_amount,
                            "description": f"Membership revenue recognized for deposit #{deposit.id}",
                        },
                    ],
                    entry_date=recognition_date,
                    created_by=created_by,
                    reference_number=deposit.order_id,
                    source_ref=deposit.external_payment_id or deposit.tx_hash or deposit.order_id,
                    source_document=product_code,
                    source_metadata={
                        "user_id": deposit.user_id,
                        "recognition_mode": "over_time",
                        "recognition_amount": float(recognition_amount),
                    },
                )
                created_count += int(created)

        return sale_entry, created_count

    def post_validated_deposit(
        self,
        db: Session,
        deposit: Deposit,
        commissions: Optional[List[AffiliateCommission]] = None,
        created_by: Optional[int] = None,
        as_of_date: Optional[datetime] = None,
    ) -> JournalEntry:
        entry, _ = self.ensure_deposit_postings(
            db,
            deposit,
            commissions=commissions,
            created_by=created_by,
            as_of_date=as_of_date,
        )
        return entry

    def ensure_affiliate_commission_settlement(
        self,
        db: Session,
        commission: AffiliateCommission,
        created_by: Optional[int] = None,
    ) -> tuple[Optional[JournalEntry], int]:
        if commission.status != CommissionStatus.PAID or not commission.paid_date:
            return None, 0

        amount = _money(commission.commission_amount)
        entry, created = self._ensure_entry(
            db,
            event_type="commission_settlement",
            source_type="affiliate_commission",
            source_id=str(commission.id),
            description=f"Affiliate commission payout #{commission.id}",
            lines=[
                {
                    "account_code": AccountCode.COMMISSION_PAYABLE,
                    "debit": amount,
                    "credit": 0,
                    "description": f"Commission payable settled for commission #{commission.id}",
                },
                {
                    "account_code": AccountCode.OPERATING_CASH,
                    "debit": 0,
                    "credit": amount,
                    "description": f"Cash disbursed for commission #{commission.id}",
                },
            ],
            entry_date=commission.paid_date,
            created_by=created_by,
            reference_number=commission.reference_id,
            source_ref=f"deposit:{commission.deposit_id}" if commission.deposit_id else None,
            source_document=commission.commission_type.value,
            source_metadata={
                "user_id": commission.user_id,
                "source_user_id": commission.source_user_id,
                "deposit_id": commission.deposit_id,
                "level": commission.level,
                "amount": float(amount),
            },
        )
        return entry, int(created)

    def post_affiliate_commission_settlement(
        self,
        db: Session,
        commission: AffiliateCommission,
        created_by: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        entry, _ = self.ensure_affiliate_commission_settlement(db, commission, created_by=created_by)
        return entry

    def ensure_user_transaction_postings(
        self,
        db: Session,
        transaction: UserTransaction,
        created_by: Optional[int] = None,
    ) -> tuple[List[JournalEntry], int]:
        if transaction.status != TransactionStatus.COMPLETED:
            return [], 0

        entries: List[JournalEntry] = []
        created_count = 0
        amount = _money(transaction.amount)
        posting_date = transaction.processed_at or transaction.created_at or datetime.utcnow()
        tx_type = transaction.transaction_type
        settlement_account = AccountCode.USER_WALLET_LIABILITY if (transaction.payment_method or "").lower() == "wallet" else AccountCode.OPERATING_CASH

        if tx_type == TransactionType.WITHDRAWAL:
            entry, created = self._ensure_entry(
                db,
                event_type="withdrawal_settled",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Withdrawal settled #{transaction.id}",
                lines=[
                    {
                        "account_code": AccountCode.USER_WALLET_LIABILITY,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Wallet liability reduced for withdrawal #{transaction.id}",
                    },
                    {
                        "account_code": AccountCode.OPERATING_CASH,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Cash paid out for withdrawal #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={"user_id": transaction.user_id, "contest_id": transaction.contest_id},
            )
            entries.append(entry)
            created_count += int(created)

        elif tx_type == TransactionType.ENTRY_FEE:
            entry, created = self._ensure_entry(
                db,
                event_type="contest_entry_fee_recognized",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Contest entry recognized #{transaction.id}",
                lines=[
                    {
                        "account_code": AccountCode.USER_WALLET_LIABILITY,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Wallet liability consumed for entry fee #{transaction.id}",
                    },
                    {
                        "account_code": AccountCode.CONTEST_ENTRY_REVENUE,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Contest entry revenue for transaction #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={"user_id": transaction.user_id, "contest_id": transaction.contest_id},
            )
            entries.append(entry)
            created_count += int(created)

        elif tx_type == TransactionType.PRIZE_PAYOUT:
            entry, created = self._ensure_entry(
                db,
                event_type="prize_obligation_accrued",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Prize obligation accrued #{transaction.id}",
                lines=[
                    {
                        "account_code": AccountCode.PRIZE_EXPENSE,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Prize expense accrued for transaction #{transaction.id}",
                    },
                    {
                        "account_code": AccountCode.PRIZE_PAYABLE,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Prize payable accrued for transaction #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={"user_id": transaction.user_id, "contest_id": transaction.contest_id},
            )
            entries.append(entry)
            created_count += int(created)

            entry, created = self._ensure_entry(
                db,
                event_type="prize_payout_settled",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Prize payout settled #{transaction.id}",
                lines=[
                    {
                        "account_code": AccountCode.PRIZE_PAYABLE,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Prize payable settled for transaction #{transaction.id}",
                    },
                    {
                        "account_code": settlement_account,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Prize transferred for transaction #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={
                    "user_id": transaction.user_id,
                    "contest_id": transaction.contest_id,
                    "settlement_account": settlement_account,
                },
            )
            entries.append(entry)
            created_count += int(created)

        elif tx_type == TransactionType.REFUND:
            refund_account = self._refund_account(transaction)
            entry, created = self._ensure_entry(
                db,
                event_type="refund_processed",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Refund processed #{transaction.id}",
                lines=[
                    {
                        "account_code": refund_account,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Refund recognized for transaction #{transaction.id}",
                    },
                    {
                        "account_code": settlement_account,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Refund transferred for transaction #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={
                    "user_id": transaction.user_id,
                    "contest_id": transaction.contest_id,
                    "classification": "contra_revenue" if refund_account == AccountCode.SALES_RETURNS_AND_REFUNDS else "expense",
                },
            )
            entries.append(entry)
            created_count += int(created)

        elif tx_type == TransactionType.COMMISSION:
            entry, created = self._ensure_entry(
                db,
                event_type="wallet_commission_credit",
                source_type="transaction",
                source_id=str(transaction.id),
                description=transaction.description or f"Commission credited #{transaction.id}",
                lines=[
                    {
                        "account_code": AccountCode.COMMISSION_PAYABLE,
                        "debit": amount,
                        "credit": 0,
                        "description": f"Commission payable reduced for transaction #{transaction.id}",
                    },
                    {
                        "account_code": AccountCode.USER_WALLET_LIABILITY,
                        "debit": 0,
                        "credit": amount,
                        "description": f"Commission credited to user wallet for transaction #{transaction.id}",
                    },
                ],
                entry_date=posting_date,
                created_by=created_by,
                reference_number=transaction.reference,
                source_ref=transaction.payment_reference,
                source_document=tx_type.value,
                source_metadata={"user_id": transaction.user_id, "contest_id": transaction.contest_id},
            )
            entries.append(entry)
            created_count += int(created)

        return entries, created_count

    def post_user_transaction(
        self,
        db: Session,
        transaction: UserTransaction,
        created_by: Optional[int] = None,
    ) -> Optional[JournalEntry]:
        entries, _ = self.ensure_user_transaction_postings(db, transaction, created_by=created_by)
        return entries[0] if entries else None

    def sync_operational_sources(self, db: Session, as_of_date: Optional[datetime] = None) -> SyncResult:
        result = SyncResult(seeded_accounts=self.seed_chart_of_accounts(db))
        as_of = as_of_date or datetime.utcnow()

        deposits = (
            db.query(Deposit)
            .options(joinedload(Deposit.product_type))
            .filter(Deposit.status == DepositStatus.VALIDATED)
            .all()
        )
        for deposit in deposits:
            commissions = db.query(AffiliateCommission).filter(AffiliateCommission.deposit_id == deposit.id).all()
            _, created = self.ensure_deposit_postings(db, deposit, commissions=commissions, as_of_date=as_of)
            result.created_entries += created

        paid_commissions = (
            db.query(AffiliateCommission)
            .filter(
                AffiliateCommission.status == CommissionStatus.PAID,
                AffiliateCommission.paid_date.isnot(None),
            )
            .all()
        )
        for commission in paid_commissions:
            _, created = self.ensure_affiliate_commission_settlement(db, commission)
            result.created_entries += created

        supported_types = [
            TransactionType.WITHDRAWAL,
            TransactionType.ENTRY_FEE,
            TransactionType.PRIZE_PAYOUT,
            TransactionType.REFUND,
            TransactionType.COMMISSION,
        ]
        transactions = (
            db.query(UserTransaction)
            .filter(
                UserTransaction.status == TransactionStatus.COMPLETED,
                UserTransaction.transaction_type.in_(supported_types),
            )
            .all()
        )
        for transaction in transactions:
            _, created = self.ensure_user_transaction_postings(db, transaction)
            result.created_entries += created

        db.flush()
        return result

    def _calculate_balance(self, account: ChartOfAccounts, debit_total: Decimal, credit_total: Decimal) -> Decimal:
        if account.normal_balance == NormalBalance.CREDIT:
            return _money(credit_total - debit_total)
        return _money(debit_total - credit_total)

    def get_account_rows(
        self,
        db: Session,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        as_of_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        self.seed_chart_of_accounts(db)
        effective_end = as_of_date or end_date
        accounts = db.query(ChartOfAccounts).order_by(ChartOfAccounts.sort_order.asc(), ChartOfAccounts.account_code.asc()).all()
        rows_by_id = {
            account.id: {
                "account": account,
                "opening_debit": Decimal("0.00"),
                "opening_credit": Decimal("0.00"),
                "period_debit": Decimal("0.00"),
                "period_credit": Decimal("0.00"),
            }
            for account in accounts
        }

        query = db.query(JournalLine, JournalEntry).join(JournalEntry, JournalLine.entry_id == JournalEntry.id).filter(
            JournalEntry.status == EntryStatus.POSTED
        )
        if effective_end:
            query = query.filter(JournalEntry.entry_date <= effective_end)

        for line, entry in query.all():
            row = rows_by_id.get(line.account_id)
            if not row:
                continue
            debit_amount = _money(line.debit_amount)
            credit_amount = _money(line.credit_amount)
            if start_date and entry.entry_date < start_date:
                row["opening_debit"] += debit_amount
                row["opening_credit"] += credit_amount
            else:
                row["period_debit"] += debit_amount
                row["period_credit"] += credit_amount

        output: List[Dict[str, Any]] = []
        for account in accounts:
            row = rows_by_id[account.id]
            opening_balance = self._calculate_balance(account, row["opening_debit"], row["opening_credit"])
            closing_debit = row["opening_debit"] + row["period_debit"]
            closing_credit = row["opening_credit"] + row["period_credit"]
            closing_balance = self._calculate_balance(account, closing_debit, closing_credit)
            output.append(
                {
                    "id": account.id,
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "account_type": account.account_type,
                    "description": account.description,
                    "parent_id": account.parent_id,
                    "is_active": account.is_active,
                    "normal_balance": account.normal_balance,
                    "statement_section": account.statement_section,
                    "report_group": account.report_group,
                    "sort_order": account.sort_order,
                    "is_contra_account": account.is_contra_account,
                    "opening_balance": float(opening_balance),
                    "total_debit": float(_money(row["period_debit"])),
                    "total_credit": float(_money(row["period_credit"])),
                    "balance": float(closing_balance),
                }
            )
        return output

    def get_trial_balance(self, db: Session, *, as_of_date: Optional[datetime] = None) -> Dict[str, Any]:
        effective_as_of = as_of_date or datetime.utcnow()
        accounts = self.get_account_rows(db, as_of_date=effective_as_of)
        return {
            "accounts": accounts,
            "as_of_date": effective_as_of,
            "total_debits": round(sum(account["total_debit"] for account in accounts), 2),
            "total_credits": round(sum(account["total_credit"] for account in accounts), 2),
            "is_balanced": round(sum(account["total_debit"] for account in accounts), 2)
            == round(sum(account["total_credit"] for account in accounts), 2),
        }

    def get_general_ledger(
        self,
        db: Session,
        *,
        account_code: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        effective_start = start_date or datetime(datetime.utcnow().year, 1, 1)
        effective_end = end_date or datetime.utcnow()
        account = self._get_account(db, account_code) if account_code else None

        opening_balance = Decimal("0.00")
        if account:
            account_rows = self.get_account_rows(db, start_date=effective_start, end_date=effective_end)
            for row in account_rows:
                if row["account_code"] == account.account_code:
                    opening_balance = _money(row["opening_balance"])
                    break

        query = (
            db.query(JournalLine, JournalEntry, ChartOfAccounts)
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
            .filter(
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.entry_date >= effective_start,
                JournalEntry.entry_date <= effective_end,
            )
            .order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc(), JournalLine.id.asc())
        )
        if account:
            query = query.filter(ChartOfAccounts.account_code == account.account_code)

        running_balance = opening_balance
        lines: List[Dict[str, Any]] = []
        for line, entry, line_account in query.all():
            line_debit = _money(line.debit_amount)
            line_credit = _money(line.credit_amount)
            if line_account.normal_balance == NormalBalance.CREDIT:
                running_balance = _money(running_balance + line_credit - line_debit)
            else:
                running_balance = _money(running_balance + line_debit - line_credit)
            lines.append(
                {
                    "entry_id": entry.id,
                    "entry_number": entry.entry_number,
                    "entry_date": entry.entry_date,
                    "account_code": line_account.account_code,
                    "account_name": line_account.account_name,
                    "description": line.description or entry.description,
                    "source_type": entry.source_type,
                    "source_id": entry.source_id,
                    "reference_number": entry.reference_number,
                    "debit_amount": float(line_debit),
                    "credit_amount": float(line_credit),
                    "running_balance": float(running_balance),
                }
            )

        return {
            "account_code": account.account_code if account else None,
            "start_date": effective_start,
            "end_date": effective_end,
            "opening_balance": float(opening_balance),
            "closing_balance": float(running_balance),
            "lines": lines,
        }

    def get_income_statement(
        self,
        db: Session,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        accounts = self.get_account_rows(db, start_date=start_date, end_date=end_date)

        def build_lines(section: str) -> List[Dict[str, Any]]:
            lines = []
            for account in accounts:
                if account["statement_section"] != section:
                    continue
                amount = abs(account["balance"])
                if amount == 0:
                    continue
                lines.append(
                    {
                        "account_code": account["account_code"],
                        "account_name": account["account_name"],
                        "amount": float(amount),
                        "statement_section": account["statement_section"],
                        "report_group": account["report_group"],
                    }
                )
            return lines

        revenue = build_lines(StatementSection.REVENUE)
        contra_revenue = build_lines(StatementSection.CONTRA_REVENUE)
        cost_of_sales = build_lines(StatementSection.DIRECT_COST)
        operating_expenses = build_lines(StatementSection.OPERATING_EXPENSE)

        total_revenue = sum(line["amount"] for line in revenue)
        total_contra = sum(line["amount"] for line in contra_revenue)
        net_revenue = total_revenue - total_contra
        gross_profit = net_revenue - sum(line["amount"] for line in cost_of_sales)
        operating_income = gross_profit - sum(line["amount"] for line in operating_expenses)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "revenue": revenue,
            "contra_revenue": contra_revenue,
            "net_revenue": round(net_revenue, 2),
            "cost_of_sales": cost_of_sales,
            "gross_profit": round(gross_profit, 2),
            "operating_expenses": operating_expenses,
            "operating_income": round(operating_income, 2),
        }

    def get_balance_sheet(self, db: Session, *, as_of_date: datetime) -> Dict[str, Any]:
        accounts = self.get_account_rows(db, as_of_date=as_of_date)

        def build_lines(section: str) -> List[Dict[str, Any]]:
            lines = []
            for account in accounts:
                if account["statement_section"] != section:
                    continue
                amount = account["balance"]
                if amount == 0:
                    continue
                lines.append(
                    {
                        "account_code": account["account_code"],
                        "account_name": account["account_name"],
                        "amount": float(amount),
                        "statement_section": account["statement_section"],
                        "report_group": account["report_group"],
                    }
                )
            return lines

        assets = build_lines(StatementSection.CURRENT_ASSET)
        liabilities = build_lines(StatementSection.CURRENT_LIABILITY)
        equity = build_lines(StatementSection.EQUITY)

        fiscal_year_start = datetime(as_of_date.year, 1, 1)
        current_period_result = self.get_income_statement(db, start_date=fiscal_year_start, end_date=as_of_date)["operating_income"]
        if current_period_result != 0:
            equity.append(
                {
                    "account_code": "current_period_earnings",
                    "account_name": "Current Period Earnings",
                    "amount": float(current_period_result),
                    "statement_section": StatementSection.EQUITY,
                    "report_group": "Current Earnings",
                }
            )

        total_assets = round(sum(line["amount"] for line in assets), 2)
        total_liabilities = round(sum(line["amount"] for line in liabilities), 2)
        total_equity = round(sum(line["amount"] for line in equity), 2)

        return {
            "as_of_date": as_of_date,
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "is_balanced": round(total_assets, 2) == round(total_liabilities + total_equity, 2),
        }

    def get_accounting_summary(
        self,
        db: Session,
        *,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        effective_end = period_end or datetime.utcnow()
        effective_start = period_start or datetime(effective_end.year, 1, 1)
        balance_sheet = self.get_balance_sheet(db, as_of_date=effective_end)
        income_statement = self.get_income_statement(db, start_date=effective_start, end_date=effective_end)
        trial_balance = self.get_trial_balance(db, as_of_date=effective_end)
        by_code = {account["account_code"]: account for account in trial_balance["accounts"]}

        return {
            "period_start": effective_start,
            "period_end": effective_end,
            "total_assets": balance_sheet["total_assets"],
            "total_liabilities": balance_sheet["total_liabilities"],
            "total_equity": balance_sheet["total_equity"],
            "total_revenue": round(sum(line["amount"] for line in income_statement["revenue"]), 2),
            "total_contra_revenue": round(sum(line["amount"] for line in income_statement["contra_revenue"]), 2),
            "net_revenue": income_statement["net_revenue"],
            "total_cost_of_sales": round(sum(line["amount"] for line in income_statement["cost_of_sales"]), 2),
            "total_expenses": round(sum(line["amount"] for line in income_statement["operating_expenses"]), 2),
            "operating_income": income_statement["operating_income"],
            "wallet_liability": by_code.get(AccountCode.USER_WALLET_LIABILITY, {}).get("balance", 0.0),
            "commission_payable": by_code.get(AccountCode.COMMISSION_PAYABLE, {}).get("balance", 0.0),
            "prize_payable": by_code.get(AccountCode.PRIZE_PAYABLE, {}).get("balance", 0.0),
            "deferred_membership_revenue": by_code.get(AccountCode.DEFERRED_MEMBERSHIP_REVENUE, {}).get("balance", 0.0),
            "deferred_service_revenue": by_code.get(AccountCode.DEFERRED_SERVICE_REVENUE, {}).get("balance", 0.0),
            "journal_entry_count": db.query(JournalEntry).count(),
            "latest_entry_at": db.query(JournalEntry.entry_date).order_by(JournalEntry.entry_date.desc()).limit(1).scalar(),
        }

    def build_reconciliation_map(
        self,
        db: Session,
        source_type: str,
        source_ids: List[str],
    ) -> Dict[str, List[JournalEntry]]:
        if not source_ids:
            return {}
        entries = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.source_type == source_type,
                JournalEntry.source_id.in_(source_ids),
            )
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
            .all()
        )
        reconciliation: Dict[str, List[JournalEntry]] = {source_id: [] for source_id in source_ids}
        for entry in entries:
            reconciliation.setdefault(entry.source_id or "", []).append(entry)
        return reconciliation

    def get_reconciliation_report(self, db: Session, *, source_type: Optional[str] = None) -> Dict[str, Any]:
        query = db.query(JournalEntry).filter(JournalEntry.status == EntryStatus.POSTED)
        if source_type:
            query = query.filter(JournalEntry.source_type == source_type)

        grouped: Dict[tuple[str, str], Dict[str, Any]] = {}
        for entry in query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).all():
            if not entry.source_type or not entry.source_id:
                continue
            key = (entry.source_type, entry.source_id)
            row = grouped.setdefault(
                key,
                {
                    "source_type": entry.source_type,
                    "source_id": entry.source_id,
                    "entry_count": 0,
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                    "latest_entry_at": entry.entry_date,
                    "reference_number": entry.reference_number,
                    "description": entry.description,
                },
            )
            row["entry_count"] += 1
            row["total_debit"] = round(row["total_debit"] + float(entry.total_debit or 0), 2)
            row["total_credit"] = round(row["total_credit"] + float(entry.total_credit or 0), 2)
            if entry.entry_date and (row["latest_entry_at"] is None or entry.entry_date > row["latest_entry_at"]):
                row["latest_entry_at"] = entry.entry_date

        items = sorted(
            grouped.values(),
            key=lambda item: item["latest_entry_at"] or datetime.min,
            reverse=True,
        )
        return {"source_type": source_type, "items": items}


accounting_posting_service = AccountingPostingService()
