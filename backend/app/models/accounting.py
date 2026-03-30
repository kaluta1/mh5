from datetime import datetime
import enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


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
    account_type: Mapped[AccountType] = mapped_column(SQLEnum(AccountType), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)

    # Denormalized legacy balance columns kept for compatibility.
    total_liabilities: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    credit_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    normal_balance: Mapped[str] = mapped_column(String(10), default="debit", nullable=False)
    statement_section: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    report_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_contra_account: Mapped[bool] = mapped_column(Boolean, default=False)

    parent: Mapped[Optional["ChartOfAccounts"]] = relationship(
        "ChartOfAccounts",
        remote_side="ChartOfAccounts.id",
        back_populates="children",
    )
    children: Mapped[List["ChartOfAccounts"]] = relationship("ChartOfAccounts", back_populates="parent")
    journal_lines: Mapped[List["JournalLine"]] = relationship("JournalLine", back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("event_type", "source_type", "source_id", name="uq_journal_entries_event_source"),
        Index("ix_journal_entries_entry_date", "entry_date"),
        Index("ix_journal_entries_source", "source_type", "source_id"),
    )

    entry_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    threshold: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)

    total_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[EntryStatus] = mapped_column(SQLEnum(EntryStatus), default=EntryStatus.DRAFT)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    lines: Mapped[List["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])


class JournalLine(Base):
    __tablename__ = "journal_lines"
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)

    debit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    credit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
    account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", back_populates="journal_lines")


class FinancialReport(Base):
    __tablename__ = "financial_reports"
    report_type: Mapped[ReportType] = mapped_column(SQLEnum(ReportType), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    generated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    generator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[generated_by])


class RevenueTransaction(Base):
    __tablename__ = "revenue_transactions"
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ad_revenue, membership, shop, etc.
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gross_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    participant_share: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    affiliate_commissions: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    founding_member_share: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry")


class TaxConfiguration(Base):
    __tablename__ = "tax_configurations"
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(50), nullable=False)  # GST, HST, PST, etc.
    rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # Ex: 0.1300 pour 13%
    tax_payable_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=False)
    tax_expense_account_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("chart_of_accounts.id"), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    province_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_payable_account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts", foreign_keys=[tax_payable_account_id])
    tax_expense_account: Mapped[Optional["ChartOfAccounts"]] = relationship("ChartOfAccounts", foreign_keys=[tax_expense_account_id])


class AuditTrail(Base):
    __tablename__ = "audit_trails"
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATE, UPDATE, DELETE
    old_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
