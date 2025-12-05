from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.api import deps
from app.crud import crud_accounting
from app.schemas.accounting import (
    ChartOfAccounts, ChartOfAccountsCreate,
    JournalEntry, JournalEntryCreate,
    FinancialReport, FinancialReportCreate,
    RevenueTransaction, RevenueTransactionCreate,
    TaxConfiguration, TaxConfigurationCreate,
    AuditTrail
)

router = APIRouter()


@router.get("/chart-of-accounts", response_model=List[ChartOfAccounts])
def get_chart_of_accounts(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    account_type: Optional[str] = None
):
    """
    Récupérer le plan comptable (admin seulement).
    """
    accounts = crud_accounting.chart_of_accounts.get_accounts_by_type(
        db=db, account_type=account_type
    )
    return accounts


@router.post("/chart-of-accounts", response_model=ChartOfAccounts, status_code=status.HTTP_201_CREATED)
def create_account(
    *,
    db: Session = Depends(deps.get_db),
    account_in: ChartOfAccountsCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Créer un nouveau compte comptable (admin seulement).
    """
    account = crud_accounting.chart_of_accounts.create(db=db, obj_in=account_in)
    return account


@router.post("/journal-entries", response_model=JournalEntry, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    *,
    db: Session = Depends(deps.get_db),
    entry_in: JournalEntryCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Créer une écriture comptable (admin seulement).
    """
    entry = crud_accounting.journal_entry.create_with_lines(
        db=db, obj_in=entry_in, created_by=current_user.id
    )
    return entry


@router.get("/journal-entries", response_model=List[JournalEntry])
def get_journal_entries(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
):
    """
    Récupérer les écritures comptables avec filtres (admin seulement).
    """
    entries = crud_accounting.journal_entry.get_filtered_entries(
        db=db,
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id
    )
    return entries


@router.get("/journal-entries/{entry_id}", response_model=JournalEntry)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Récupérer une écriture comptable par ID (admin seulement).
    """
    entry = crud_accounting.journal_entry.get_with_lines(db=db, id=entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Écriture comptable non trouvée"
        )
    return entry


@router.post("/revenue-transactions", response_model=RevenueTransaction, status_code=status.HTTP_201_CREATED)
def record_revenue_transaction(
    *,
    db: Session = Depends(deps.get_db),
    transaction_in: RevenueTransactionCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Enregistrer une transaction de revenus (admin seulement).
    """
    transaction = crud_accounting.revenue_transaction.create_with_accounting(
        db=db, obj_in=transaction_in
    )
    return transaction


@router.get("/revenue-transactions", response_model=List[RevenueTransaction])
def get_revenue_transactions(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
    transaction_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Récupérer les transactions de revenus (admin seulement).
    """
    transactions = crud_accounting.revenue_transaction.get_filtered_transactions(
        db=db,
        skip=skip,
        limit=limit,
        transaction_type=transaction_type,
        start_date=start_date,
        end_date=end_date
    )
    return transactions


@router.get("/financial-reports", response_model=List[FinancialReport])
def get_financial_reports(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    report_type: Optional[str] = None,
    period_year: Optional[int] = None
):
    """
    Récupérer les rapports financiers (admin seulement).
    """
    reports = crud_accounting.financial_report.get_reports_by_type(
        db=db, report_type=report_type, period_year=period_year
    )
    return reports


@router.post("/financial-reports", response_model=FinancialReport, status_code=status.HTTP_201_CREATED)
def generate_financial_report(
    *,
    db: Session = Depends(deps.get_db),
    report_in: FinancialReportCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Générer un rapport financier (admin seulement).
    """
    report = crud_accounting.financial_report.generate_report(
        db=db, obj_in=report_in, generated_by=current_user.id
    )
    return report


@router.get("/balance-sheet")
def get_balance_sheet(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    as_of_date: Optional[date] = None
):
    """
    Générer le bilan comptable (admin seulement).
    """
    if not as_of_date:
        as_of_date = date.today()
    
    balance_sheet = crud_accounting.financial_report.generate_balance_sheet(
        db=db, as_of_date=as_of_date
    )
    return balance_sheet


@router.get("/income-statement")
def get_income_statement(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Générer l'état des résultats (admin seulement).
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 1, 1)  # Début d'année
    
    income_statement = crud_accounting.financial_report.generate_income_statement(
        db=db, start_date=start_date, end_date=end_date
    )
    return income_statement


@router.get("/cash-flow")
def get_cash_flow_statement(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Générer l'état des flux de trésorerie (admin seulement).
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 1, 1)
    
    cash_flow = crud_accounting.financial_report.generate_cash_flow_statement(
        db=db, start_date=start_date, end_date=end_date
    )
    return cash_flow


@router.get("/tax-config", response_model=List[TaxConfiguration])
def get_tax_configurations(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Récupérer les configurations fiscales (admin seulement).
    """
    configs = crud_accounting.tax_configuration.get_active_configs(db=db)
    return configs


@router.post("/tax-config", response_model=TaxConfiguration, status_code=status.HTTP_201_CREATED)
def create_tax_configuration(
    *,
    db: Session = Depends(deps.get_db),
    config_in: TaxConfigurationCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Créer une configuration fiscale (admin seulement).
    """
    config = crud_accounting.tax_configuration.create(db=db, obj_in=config_in)
    return config


@router.get("/audit-trail", response_model=List[AuditTrail])
def get_audit_trail(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
    table_name: Optional[str] = None,
    action_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """
    Récupérer la piste d'audit (admin seulement).
    """
    audit_records = crud_accounting.audit_trail.get_filtered_audit(
        db=db,
        skip=skip,
        limit=limit,
        table_name=table_name,
        action_type=action_type,
        start_date=start_date,
        end_date=end_date
    )
    return audit_records


@router.get("/revenue-summary")
def get_revenue_summary(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by: str = "month"  # month, quarter, year
):
    """
    Récupérer un résumé des revenus par période (admin seulement).
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 1, 1)
    
    summary = crud_accounting.revenue_transaction.get_revenue_summary(
        db=db,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by
    )
    return summary


@router.get("/affiliate-revenue")
def get_affiliate_revenue_report(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Récupérer le rapport des revenus d'affiliation (admin seulement).
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 1, 1)
    
    report = crud_accounting.revenue_transaction.get_affiliate_revenue_report(
        db=db, start_date=start_date, end_date=end_date
    )
    return report


@router.get("/contest-revenue")
def get_contest_revenue_report(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_superuser),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Récupérer le rapport des revenus des concours (admin seulement).
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 1, 1)
    
    report = crud_accounting.revenue_transaction.get_contest_revenue_report(
        db=db, start_date=start_date, end_date=end_date
    )
    return report


@router.post("/reconcile", status_code=status.HTTP_201_CREATED)
def reconcile_accounts(
    *,
    db: Session = Depends(deps.get_db),
    reconciliation_data: dict,  # {"account_id": int, "statement_date": str, "statement_balance": float}
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Effectuer un rapprochement bancaire (admin seulement).
    """
    result = crud_accounting.journal_entry.reconcile_account(
        db=db,
        account_id=reconciliation_data["account_id"],
        statement_date=reconciliation_data["statement_date"],
        statement_balance=reconciliation_data["statement_balance"],
        reconciled_by=current_user.id
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result
