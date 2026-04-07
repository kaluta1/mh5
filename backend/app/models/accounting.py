from typing import Optional, List, Any
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Enum as SQLEnum, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator
from datetime import datetime
import enum
from app.db.base_class import Base


class AccountTypeColumn(TypeDecorator):
    """Maps DB account_type (PostgreSQL enum or varchar) to AccountType without PG-specific ENUM binding."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, AccountType):
            return value.value
        return AccountType(str(value)).value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return AccountType(str(value))


class AccountType(str, enum.Enum):
    """Labels match PostgreSQL enum `accounttype` from migration 002_add_myfav_models."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

    @classmethod
    def _missing_(cls, value: Any) -> Any:
        """Accept API / JSON lowercase names (e.g. 'asset') as well as DB labels."""
        if isinstance(value, str):
            u = value.strip().upper()
            for m in cls:
                if m.value == u or m.name == u:
                    return m
        raise ValueError(f"{value!r} is not a valid {cls.__qualname__}")


class EntryStatus(str, enum.Enum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


class ReportType(str, enum.Enum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    TRIAL_BALANCE = "trial_balance"
    GENERAL_LEDGER = "general_ledger"


class ChartOfAccounts(Base):
    __tablename__ = "chart_of_accounts"
    account_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # DB may be PostgreSQL enum `accounttype` (002) or varchar; TypeDecorator reads/writes as text
    account_type: Mapped[AccountType] = mapped_column(AccountTypeColumn(), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)

    # Denormalized cache; prefer computing from journal_lines via AccountingService.get_balance
    # Column name in DB (002_add_myfav_models): "balance"
    balance: Mapped[float] = mapped_column("balance", Numeric(15, 2), default=0.0, nullable=True)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relations
    parent: Mapped[Optional["ChartOfAccounts"]] = relationship(
        "ChartOfAccounts", remote_side="ChartOfAccounts.id", back_populates="children"
    )
    children: Mapped[List["ChartOfAccounts"]] = relationship("ChartOfAccounts", back_populates="parent")
    journal_lines: Mapped[List["JournalLine"]] = relationship("JournalLine", back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    entry_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    
    # Totaux (doivent être équilibrés)
    total_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    
    status: Mapped[EntryStatus] = mapped_column(
        SQLEnum(EntryStatus, values_callable=lambda x: [e.value for e in x], native_enum=False, length=20),
        default=EntryStatus.POSTED,
    )

    # Métadonnées (created_at / updated_at from Base)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    lines: Mapped[List["JournalLine"]] = relationship("JournalLine", back_populates="entry")
    creator: Mapped[Optional["User"]] = relationship("User")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    
    debit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    credit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", back_populates="journal_lines")


class FinancialReport(Base):
    __tablename__ = "financial_reports"
    report_type: Mapped[ReportType] = mapped_column(
        SQLEnum(ReportType, values_callable=lambda x: [e.value for e in x], native_enum=False, length=40),
        nullable=False,
    )
    
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Données du rapport stockées en JSON
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    generated_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    generated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relations
    generator: Mapped[Optional["User"]] = relationship("User")


class RevenueTransaction(Base):
    __tablename__ = "revenue_transactions"
    
    # Source de revenus
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ad_revenue, membership, shop, etc.
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Montants
    gross_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    
    # Distribution des commissions
    participant_share: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    affiliate_commissions: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    founding_member_share: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    transaction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    
    # Relations
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry")


class TaxConfiguration(Base):
    __tablename__ = "tax_configurations"
    
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(50), nullable=False)  # GST, HST, PST, etc.
    rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # Ex: 0.1300 pour 13%
    
    # Comptes comptables associés
    tax_payable_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    tax_expense_account_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    
    # Applicabilité géographique
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    province_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    
    effective_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    tax_payable_account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", foreign_keys=[tax_payable_account_id])
    tax_expense_account: Mapped[Optional["ChartOfAccounts"]] = relationship("ChartOfAccounts", foreign_keys=[tax_expense_account_id])


class AuditTrail(Base):
    __tablename__ = "audit_trails"
    
    # Référence à l'objet modifié
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Type d'action
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATE, UPDATE, DELETE
    
    # Données avant/après modification
    old_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Métadonnées
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped[Optional["User"]] = relationship("User")
