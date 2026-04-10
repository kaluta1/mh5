from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Optional
from datetime import datetime
from decimal import Decimal
import logging
import uuid

from app.models.accounting import (
    JournalEntry,
    JournalLine,
    ChartOfAccounts,
    AccountType,
)
from app.services.journal_entry_status import posted_status_literal_for_db

logger = logging.getLogger(__name__)

class AccountingError(Exception):
    pass

class AccountingService:
    def __init__(self):
        pass
    
    def get_account_by_code(self, db: Session, code: str) -> Optional[ChartOfAccounts]:
        return db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first()

    def create_journal_entry(
        self,
        db: Session,
        description: str,
        lines: List[Dict[str, any]],
        date: datetime = None,
        commit: bool = True
    ) -> JournalEntry:
        """
        Crée une entrée de journal (Journal Entry) avec plusieurs lignes (Journal Lines).
        Vérifie que Débit = Crédit.
        
        lines format: [
            {"account_code": "1001", "debit": 10.0, "credit": 0.0, "description": "optional"},
            ...
        ]
        """
        if date is None:
            date = datetime.utcnow()
            
        # 1. Valider l'équilibre Débit / Crédit
        total_debit = sum(Decimal(str(line.get("debit", 0.0))) for line in lines)
        total_credit = sum(Decimal(str(line.get("credit", 0.0))) for line in lines)
        
        if total_debit != total_credit:
            raise AccountingError(f"Journal Entry unbalanced: Debit={total_debit}, Credit={total_credit}")
            
        # 2. Créer l'entête du journal — numéro unique (évite collisions sur même seconde)
        entry_number = f"JE-{int(date.timestamp())}-{uuid.uuid4().hex[:12]}"
        
        entry = JournalEntry(
            entry_number=entry_number,
            entry_date=date,
            description=description,
            total_debit=float(total_debit),
            total_credit=float(total_credit),
            status=posted_status_literal_for_db(db),
        )
        db.add(entry)
        try:
            db.flush()  # Pour avoir l'ID
        except Exception:
            db.rollback()
            raise
        
        # 3. Créer les lignes
        for line_data in lines:
            account_code = line_data["account_code"]
            account = self.get_account_by_code(db, account_code)
            
            if not account:
                raise AccountingError(f"Account not found: {account_code}")
                
            debit = float(line_data.get("debit", 0.0))
            credit = float(line_data.get("credit", 0.0))
            
            # Mise à jour des soldes du compte (dénormalisation pour perf)
            # Actif/Dépense augmentent au Débit. Passif/Revenu/Capitaux augmentent au Crédit.
            # On stocke souvent le "solde naturel" ou un solde signé.
            # Ici on met à jour simplement credit_balance et total_liabilities (champs existants du modèle)
            # Note: Le modèle existant a des champs bizarres (total_liabilities, credit_balance). 
            # On va assumer une mise à jour logique simple ici, ou laisser le reporting le faire.
            
            line = JournalLine(
                entry_id=entry.id,
                account_id=account.id,
                debit_amount=debit,
                credit_amount=credit,
                description=line_data.get("description", description)
            )
            db.add(line)
            
        if commit:
            try:
                db.commit()
                db.refresh(entry)
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating journal entry: {e}")
                raise e
                
        return entry

    def get_balance(self, db: Session, account_code: str) -> Dict[str, float]:
        """Calcule le solde d'un compte à la volée depuis le grand livre"""
        account = self.get_account_by_code(db, account_code)
        if not account:
            return {"debit": 0.0, "credit": 0.0, "balance": 0.0}
            
        result = db.query(
            func.sum(JournalLine.debit_amount).label("total_debit"),
            func.sum(JournalLine.credit_amount).label("total_credit")
        ).filter(JournalLine.account_id == account.id).first()
        
        total_debit = result.total_debit or 0.0
        total_credit = result.total_credit or 0.0
        
        # Solde selon le type de compte
        if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
            balance = total_debit - total_credit
        else:
            balance = total_credit - total_debit
            
        return {
            "debit": float(total_debit),
            "credit": float(total_credit),
            "balance": float(balance)
        }

accounting_service = AccountingService()
