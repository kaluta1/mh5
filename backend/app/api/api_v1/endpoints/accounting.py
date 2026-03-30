from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.models.accounting import AccountType, JournalEntry, JournalLine
from app.schemas.accounting import (
    AccountingOverview,
    AccountSummary,
    BalanceSheetReport,
    GeneralLedgerReport,
    IncomeStatementReport,
    JournalEntryPage,
    JournalEntryRead,
    JournalLineRead,
    ReconciliationLink,
    ReconciliationReport,
    TrialBalanceSummary,
)
from app.services.accounting_posting import accounting_posting_service


router = APIRouter()


def _sync_accounting(db: Session, as_of_date: Optional[datetime] = None) -> None:
    result = accounting_posting_service.sync_operational_sources(db, as_of_date=as_of_date)
    if result.seeded_accounts or result.created_entries:
        db.commit()


def _serialize_line(line: JournalLine) -> JournalLineRead:
    return JournalLineRead(
        id=line.id,
        account_id=line.account_id,
        account_code=line.account.account_code,
        account_name=line.account.account_name,
        description=line.description,
        debit_amount=float(line.debit_amount or 0),
        credit_amount=float(line.credit_amount or 0),
        reference_id=line.reference_id,
        reference_type=line.reference_type,
    )


def _serialize_entry(entry: JournalEntry) -> JournalEntryRead:
    return JournalEntryRead(
        id=entry.id,
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        description=entry.description,
        reference_number=entry.reference_number,
        source_document=entry.source_document,
        event_type=entry.event_type,
        source_type=entry.source_type,
        source_id=entry.source_id,
        source_ref=entry.source_ref,
        source_metadata=entry.source_metadata,
        total_debit=float(entry.total_debit or 0),
        total_credit=float(entry.total_credit or 0),
        status=entry.status,
        created_by=entry.created_by,
        posted_at=entry.posted_at,
        lines=[_serialize_line(line) for line in entry.lines],
    )


@router.get("/chart-of-accounts", response_model=List[AccountSummary])
def get_chart_of_accounts(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    account_type: Optional[AccountType] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    as_of_date: Optional[datetime] = Query(None),
):
    effective_sync_date = as_of_date or end_date
    _sync_accounting(db, effective_sync_date)
    accounts = accounting_posting_service.get_account_rows(
        db,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
    )
    if account_type:
        accounts = [account for account in accounts if account["account_type"] == account_type]
    return accounts


@router.get("/journal-entries", response_model=JournalEntryPage)
def get_journal_entries(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    skip: int = 0,
    limit: int = Query(50, le=200),
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    _sync_accounting(db, end_date)
    query = db.query(JournalEntry).options(
        joinedload(JournalEntry.lines).joinedload(JournalLine.account)
    )
    if source_type:
        query = query.filter(JournalEntry.source_type == source_type)
    if source_id:
        query = query.filter(JournalEntry.source_id == source_id)
    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    total = query.count()
    items = (
        query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return JournalEntryPage(items=[_serialize_entry(item) for item in items], total=total, skip=skip, limit=limit)


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
):
    _sync_accounting(db)
    entry = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account))
        .filter(JournalEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return _serialize_entry(entry)


@router.get("/trial-balance", response_model=TrialBalanceSummary)
def get_trial_balance(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    as_of_date: Optional[datetime] = Query(None),
):
    _sync_accounting(db, as_of_date)
    return accounting_posting_service.get_trial_balance(db, as_of_date=as_of_date)


@router.get("/general-ledger", response_model=GeneralLedgerReport)
def get_general_ledger(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    account_code: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    _sync_accounting(db, end_date)
    return accounting_posting_service.get_general_ledger(
        db,
        account_code=account_code,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/income-statement", response_model=IncomeStatementReport)
def get_income_statement(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
):
    _sync_accounting(db, end_date)
    return accounting_posting_service.get_income_statement(db, start_date=start_date, end_date=end_date)


@router.get("/balance-sheet", response_model=BalanceSheetReport)
def get_balance_sheet(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    as_of_date: datetime = Query(...),
):
    _sync_accounting(db, as_of_date)
    return accounting_posting_service.get_balance_sheet(db, as_of_date=as_of_date)


@router.get("/summary", response_model=AccountingOverview)
def get_accounting_summary(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    _sync_accounting(db, end_date)
    return accounting_posting_service.get_accounting_summary(
        db,
        period_start=start_date,
        period_end=end_date,
    )


@router.get("/reconciliation-report", response_model=ReconciliationReport)
def get_reconciliation_report(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
    source_type: Optional[str] = Query(None),
):
    _sync_accounting(db)
    return accounting_posting_service.get_reconciliation_report(db, source_type=source_type)


@router.get("/reconciliation/{source_type}/{source_id}", response_model=List[ReconciliationLink])
def get_reconciliation_links(
    source_type: str,
    source_id: str,
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin_user),
):
    _sync_accounting(db)
    entries = accounting_posting_service.build_reconciliation_map(db, source_type, [source_id]).get(source_id, [])
    return [
        ReconciliationLink(
            entry_id=entry.id,
            entry_number=entry.entry_number,
            event_type=entry.event_type,
            entry_date=entry.entry_date,
            total_debit=float(entry.total_debit or 0),
            total_credit=float(entry.total_credit or 0),
            status=entry.status,
        )
        for entry in entries
    ]
