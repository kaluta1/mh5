from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.accounting import AccountType, EntryStatus


class AccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_code: str
    account_name: str
    account_type: AccountType
    description: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    normal_balance: str = "debit"
    statement_section: Optional[str] = None
    report_group: Optional[str] = None
    sort_order: int = 0
    is_contra_account: bool = False
    total_debit: float = 0.0
    total_credit: float = 0.0
    balance: float = 0.0
    opening_balance: float = 0.0


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account_code: str
    account_name: str
    description: Optional[str] = None
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_number: str
    entry_date: datetime
    description: str
    reference_number: Optional[str] = None
    source_document: Optional[str] = None
    event_type: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    source_ref: Optional[str] = None
    source_metadata: Optional[dict[str, Any]] = None
    total_debit: float
    total_credit: float
    status: EntryStatus
    created_by: Optional[int] = None
    posted_at: Optional[datetime] = None
    lines: List[JournalLineRead] = Field(default_factory=list)


class JournalEntryPage(BaseModel):
    items: List[JournalEntryRead] = Field(default_factory=list)
    total: int = 0
    skip: int = 0
    limit: int = 50


class TrialBalanceSummary(BaseModel):
    accounts: List[AccountSummary] = Field(default_factory=list)
    as_of_date: Optional[datetime] = None
    total_debits: float = 0.0
    total_credits: float = 0.0
    is_balanced: bool = False


class AccountingOverview(BaseModel):
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    total_revenue: float = 0.0
    total_contra_revenue: float = 0.0
    net_revenue: float = 0.0
    total_cost_of_sales: float = 0.0
    total_expenses: float = 0.0
    operating_income: float = 0.0
    wallet_liability: float = 0.0
    commission_payable: float = 0.0
    prize_payable: float = 0.0
    deferred_membership_revenue: float = 0.0
    deferred_service_revenue: float = 0.0
    journal_entry_count: int = 0
    latest_entry_at: Optional[datetime] = None


class ReconciliationLink(BaseModel):
    entry_id: int
    entry_number: str
    event_type: Optional[str] = None
    entry_date: datetime
    total_debit: float
    total_credit: float
    status: EntryStatus


class GeneralLedgerLine(BaseModel):
    entry_id: int
    entry_number: str
    entry_date: datetime
    account_code: str
    account_name: str
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    reference_number: Optional[str] = None
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    running_balance: float = 0.0


class GeneralLedgerReport(BaseModel):
    account_code: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    lines: List[GeneralLedgerLine] = Field(default_factory=list)


class StatementLine(BaseModel):
    account_code: str
    account_name: str
    amount: float
    statement_section: Optional[str] = None
    report_group: Optional[str] = None


class IncomeStatementReport(BaseModel):
    start_date: datetime
    end_date: datetime
    revenue: List[StatementLine] = Field(default_factory=list)
    contra_revenue: List[StatementLine] = Field(default_factory=list)
    net_revenue: float = 0.0
    cost_of_sales: List[StatementLine] = Field(default_factory=list)
    gross_profit: float = 0.0
    operating_expenses: List[StatementLine] = Field(default_factory=list)
    operating_income: float = 0.0


class BalanceSheetReport(BaseModel):
    as_of_date: datetime
    assets: List[StatementLine] = Field(default_factory=list)
    liabilities: List[StatementLine] = Field(default_factory=list)
    equity: List[StatementLine] = Field(default_factory=list)
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    is_balanced: bool = False


class ReconciliationSummaryItem(BaseModel):
    source_type: str
    source_id: str
    entry_count: int
    total_debit: float
    total_credit: float
    latest_entry_at: Optional[datetime] = None
    reference_number: Optional[str] = None
    description: Optional[str] = None


class ReconciliationReport(BaseModel):
    source_type: Optional[str] = None
    items: List[ReconciliationSummaryItem] = Field(default_factory=list)
