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
)


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


class CRUDAccountingBundle:
    chart_of_accounts = CRUDChartOfAccounts()
    journal_entry = CRUDJournalEntry()
    revenue_transaction = _NotImplemented()
    financial_report = _NotImplemented()
    tax_configuration = _NotImplemented()
    audit_trail = _NotImplemented()


crud_accounting = CRUDAccountingBundle()
