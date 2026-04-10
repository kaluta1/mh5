"""
Accounting CRUD — partial implementation.

Payment flows use `app.services.accounting_service` directly (see `payment_accounting.py`).
Full financial_report / reconcile / revenue_transaction helpers are not implemented here;
extend as needed or call services from endpoints.
"""
from __future__ import annotations

from typing import Any, List, Optional
from datetime import date, datetime

from sqlalchemy.orm import Session
from sqlalchemy import exists, and_

from app.models.accounting import (
    ChartOfAccounts,
    JournalEntry,
    JournalLine,
    RevenueTransaction,
    FinancialReport,
    TaxConfiguration,
    AuditTrail,
    AccountType,
    ReportType,
)
from sqlalchemy import inspect as sa_inspect


class CRUDChartOfAccounts:
    def get_accounts_by_type(
        self, db: Session, account_type: Optional[str] = None
    ) -> List[ChartOfAccounts]:
        q = db.query(ChartOfAccounts).filter(ChartOfAccounts.is_active == True)
        if account_type:
            try:
                at = AccountType(account_type.lower())
                q = q.filter(ChartOfAccounts.account_type == at)
            except ValueError:
                return []
        return q.order_by(ChartOfAccounts.account_code.asc()).all()

    def create(self, db: Session, obj_in: Any) -> ChartOfAccounts:
        raise NotImplementedError("Create CoA via app/scripts/init_coa.py or SQL migration")


class CRUDJournalEntry:
    def create_with_lines(self, db: Session, obj_in: Any, created_by: int) -> JournalEntry:
        raise NotImplementedError("Use accounting_service.create_journal_entry for double-entry")

    def get_filtered_entries(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 10,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        account_id: Optional[int] = None,
    ) -> List[JournalEntry]:
        q = db.query(JournalEntry)
        if start_date:
            q = q.filter(JournalEntry.entry_date >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            q = q.filter(JournalEntry.entry_date <= datetime.combine(end_date, datetime.max.time()))
        if account_id:
            q = q.filter(
                exists().where(
                    and_(
                        JournalLine.entry_id == JournalEntry.id,
                        JournalLine.account_id == account_id,
                    )
                )
            )
        return q.order_by(JournalEntry.entry_date.desc()).offset(skip).limit(limit).all()

    def get_with_lines(self, db: Session, id: int) -> Optional[JournalEntry]:
        from sqlalchemy.orm import joinedload

        return (
            db.query(JournalEntry)
            .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account))
            .filter(JournalEntry.id == id)
            .first()
        )

    def reconcile_account(self, db: Session, **kwargs: Any) -> dict:
        return {"success": False, "error": "Bank reconcile not implemented"}


class _NotImplemented:
    def __getattr__(self, name: str):
        def _raise(*a: Any, **kw: Any):
            raise NotImplementedError(
                f"Accounting submodule method '{name}' is not implemented in crud_accounting"
            )

        return _raise


class CRUDFinancialReport:
    """Balance sheet, income statement, etc. from posted journals (see financial_report_service)."""

    def get_reports_by_type(
        self,
        db: Session,
        report_type: Optional[str] = None,
        period_year: Optional[int] = None,
    ) -> List[FinancialReport]:
        bind = db.get_bind()
        if not sa_inspect(bind).has_table("financial_reports"):
            return []
        q = db.query(FinancialReport)
        if report_type:
            try:
                rt = ReportType(report_type)
                q = q.filter(FinancialReport.report_type == rt)
            except ValueError:
                return []
        if period_year is not None:
            from sqlalchemy import extract

            q = q.filter(extract("year", FinancialReport.period_start) == period_year)
        return q.order_by(FinancialReport.generated_date.desc()).limit(200).all()

    def generate_report(self, db: Session, obj_in: Any, generated_by: int) -> FinancialReport:
        raise NotImplementedError(
            "Persisted report snapshots are not implemented; use GET balance-sheet / income-statement endpoints."
        )

    def generate_balance_sheet(self, db: Session, as_of_date: date) -> Any:
        from app.services.financial_report_service import generate_balance_sheet_payload

        return generate_balance_sheet_payload(db, as_of_date)

    def generate_income_statement(self, db: Session, start_date: date, end_date: date) -> Any:
        from app.services.financial_report_service import generate_income_statement_payload

        return generate_income_statement_payload(db, start_date, end_date)

    def generate_cash_flow_statement(self, db: Session, start_date: date, end_date: date) -> Any:
        from app.services.financial_report_service import generate_cash_flow_payload

        return generate_cash_flow_payload(db, start_date, end_date)

    def generate_trial_balance(self, db: Session, as_of_date: date) -> Any:
        from app.services.financial_report_service import generate_trial_balance_payload

        return generate_trial_balance_payload(db, as_of_date)

    def generate_general_ledger(
        self, db: Session, account_code: str, start_date: date, end_date: date
    ) -> Any:
        from app.services.financial_report_service import generate_general_ledger_payload

        return generate_general_ledger_payload(db, account_code, start_date, end_date)

    def generate_full_financial_report(
        self, db: Session, as_of: date, period_start: date, period_end: date
    ) -> Any:
        from app.services.financial_report_service import generate_full_financial_report_payload

        return generate_full_financial_report_payload(
            db, as_of=as_of, period_start=period_start, period_end=period_end
        )


class CRUDAccountingBundle:
    chart_of_accounts = CRUDChartOfAccounts()
    journal_entry = CRUDJournalEntry()
    revenue_transaction = _NotImplemented()
    financial_report = CRUDFinancialReport()
    tax_configuration = _NotImplemented()
    audit_trail = _NotImplemented()


crud_accounting = CRUDAccountingBundle()
