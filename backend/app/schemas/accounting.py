from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.models.accounting import AccountType, EntryStatus


# Chart of Accounts schemas
class ChartOfAccountsBase(BaseModel):
    account_code: str
    account_name: str
    account_type: AccountType
    parent_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool = True
    is_system_account: bool = False


class ChartOfAccountsCreate(ChartOfAccountsBase):
    pass


class ChartOfAccountsUpdate(BaseModel):
    account_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ChartOfAccounts(ChartOfAccountsBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: float = 0.0
    created_at: Optional[datetime] = None


class ChartOfAccountsWithBalance(ChartOfAccounts):
    """Compte avec solde et sous-comptes"""
    sub_accounts: List['ChartOfAccounts'] = []
    total_balance: float = 0.0


# Journal Entry schemas (aligned with app.models.accounting.JournalEntry)
class JournalEntryBase(BaseModel):
    entry_date: datetime
    description: str
    total_debit: float
    total_credit: float


class JournalEntryCreate(JournalEntryBase):
    pass


class JournalEntryUpdate(BaseModel):
    description: Optional[str] = None


class JournalEntry(JournalEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_number: str
    created_by: Optional[int] = None
    status: Optional[str] = None
    posted_at: Optional[datetime] = None


class JournalEntryWithCreator(JournalEntry):
    """Écriture avec informations créateur"""
    creator_name: Optional[str] = None


# Journal Entry Line schemas (aligned with JournalLine)
class JournalEntryLineBase(BaseModel):
    entry_id: int
    account_id: int
    description: Optional[str] = None
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None


class JournalEntryLineCreate(JournalEntryLineBase):
    pass


class JournalEntryLineUpdate(BaseModel):
    description: Optional[str] = None
    debit_amount: Optional[float] = None
    credit_amount: Optional[float] = None


class JournalEntryLine(JournalEntryLineBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int


class JournalEntryLineWithAccount(JournalEntryLine):
    """Ligne d'écriture avec informations compte"""
    account_code: Optional[str] = None
    account_name: Optional[str] = None


# Revenue Transaction schemas (aligned with app.models.accounting.RevenueTransaction)
class RevenueTransactionBase(BaseModel):
    source_type: str
    source_id: Optional[str] = None
    gross_amount: float
    platform_fee: float
    net_amount: float
    participant_share: float = 0.0
    affiliate_commissions: float = 0.0
    founding_member_share: float = 0.0


class RevenueTransactionCreate(RevenueTransactionBase):
    pass


class RevenueTransactionUpdate(BaseModel):
    status: Optional[str] = None


class RevenueTransaction(RevenueTransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_date: Optional[datetime] = None
    journal_entry_id: Optional[int] = None


class RevenueTransactionWithUser(RevenueTransaction):
    """Transaction avec informations utilisateur"""
    user_name: Optional[str] = None
    user_email: Optional[str] = None


# Financial Report schemas (aligned with FinancialReport model)
class FinancialReportBase(BaseModel):
    report_type: str
    period_start: datetime
    period_end: datetime
    report_data: dict
    generated_by: Optional[int] = None


class FinancialReportCreate(FinancialReportBase):
    pass


class FinancialReport(FinancialReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    generated_date: Optional[datetime] = None


class FinancialReportWithGenerator(FinancialReport):
    """Rapport avec informations générateur"""
    generator_name: Optional[str] = None


# Tax Configuration schemas
class TaxConfigurationBase(BaseModel):
    tax_name: str
    tax_type: str
    rate: float
    tax_payable_account_id: int
    tax_expense_account_id: Optional[int] = None
    country_code: Optional[str] = None
    province_code: Optional[str] = None
    is_active: bool = True
    effective_date: datetime
    expiry_date: Optional[datetime] = None


class TaxConfigurationCreate(TaxConfigurationBase):
    pass


class TaxConfigurationUpdate(BaseModel):
    tax_rate: Optional[float] = None
    is_active: Optional[bool] = None
    expiry_date: Optional[datetime] = None


class TaxConfiguration(TaxConfigurationBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


class TaxConfigurationWithAccount(TaxConfiguration):
    """Configuration fiscale avec informations compte"""
    account_code: Optional[str] = None
    account_name: Optional[str] = None


# Audit Trail schemas
class AuditTrailBase(BaseModel):
    user_id: Optional[int] = None
    table_name: str
    record_id: int
    action: str  # CREATE, UPDATE, DELETE
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditTrailCreate(AuditTrailBase):
    pass


class AuditTrail(AuditTrailBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    timestamp: Optional[datetime] = None


class AuditTrailWithUser(AuditTrail):
    """Audit avec informations utilisateur"""
    user_name: Optional[str] = None
    user_email: Optional[str] = None


# Bank Reconciliation schemas
class BankReconciliationBase(BaseModel):
    account_id: int
    statement_date: datetime
    statement_balance: float
    book_balance: float
    reconciled_balance: float
    total_deposits_in_transit: float = 0.0
    total_outstanding_checks: float = 0.0
    bank_errors: float = 0.0
    book_errors: float = 0.0
    is_reconciled: bool = False


class BankReconciliationCreate(BankReconciliationBase):
    pass


class BankReconciliationUpdate(BaseModel):
    statement_balance: Optional[float] = None
    reconciled_balance: Optional[float] = None
    total_deposits_in_transit: Optional[float] = None
    total_outstanding_checks: Optional[float] = None
    bank_errors: Optional[float] = None
    book_errors: Optional[float] = None
    is_reconciled: Optional[bool] = None


class BankReconciliation(BankReconciliationBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    reconciled_by: Optional[int] = None
    reconciled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class BankReconciliationWithAccount(BankReconciliation):
    """Rapprochement avec informations compte"""
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    reconciler_name: Optional[str] = None


# Response schemas complexes
class TrialBalance(BaseModel):
    """Balance de vérification"""
    period_start: datetime
    period_end: datetime
    accounts: List[dict] = []  # {"account_code": str, "account_name": str, "debit": float, "credit": float}
    total_debits: float = 0.0
    total_credits: float = 0.0
    is_balanced: bool = False


class IncomeStatement(BaseModel):
    """État des résultats"""
    period_start: datetime
    period_end: datetime
    revenues: List[dict] = []
    expenses: List[dict] = []
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    net_income: float = 0.0
    gross_profit: float = 0.0


class BalanceSheet(BaseModel):
    """Bilan"""
    as_of_date: datetime
    assets: List[dict] = []
    liabilities: List[dict] = []
    equity: List[dict] = []
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    is_balanced: bool = False


class CashFlowStatement(BaseModel):
    """État des flux de trésorerie"""
    period_start: datetime
    period_end: datetime
    operating_activities: List[dict] = []
    investing_activities: List[dict] = []
    financing_activities: List[dict] = []
    net_cash_from_operations: float = 0.0
    net_cash_from_investing: float = 0.0
    net_cash_from_financing: float = 0.0
    net_change_in_cash: float = 0.0
    beginning_cash_balance: float = 0.0
    ending_cash_balance: float = 0.0


class TaxSummary(BaseModel):
    """Résumé fiscal"""
    period_start: datetime
    period_end: datetime
    total_revenue: float = 0.0
    taxable_income: float = 0.0
    tax_collected: float = 0.0
    tax_paid: float = 0.0
    tax_owing: float = 0.0
    tax_by_type: List[dict] = []


class AccountingDashboard(BaseModel):
    """Tableau de bord comptable"""
    current_assets: float = 0.0
    current_liabilities: float = 0.0
    working_capital: float = 0.0
    monthly_revenue: float = 0.0
    monthly_expenses: float = 0.0
    net_income_ytd: float = 0.0
    cash_balance: float = 0.0
    accounts_receivable: float = 0.0
    accounts_payable: float = 0.0
    pending_reconciliations: int = 0
