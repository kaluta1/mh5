from sqlalchemy.orm import Session
from app.models.accounting import ChartOfAccounts, AccountType
import logging

logger = logging.getLogger(__name__)

def init_chart_of_accounts(db: Session):
    """
    Initialise le Plan Comptable (Chart of Accounts) par défaut.
    """
    # Liste initiale des comptes
    accounts = [
        # ASSETS (1000)
        {"code": "1000", "name": "Assets", "type": AccountType.ASSET, "parent": None},
        {"code": "1001", "name": "Platform Wallet", "type": AccountType.ASSET, "parent": "1000"},
        {"code": "1200", "name": "Accounts Receivable", "type": AccountType.ASSET, "parent": "1000"},
        
        # LIABILITIES (2000)
        {"code": "2000", "name": "Liabilities", "type": AccountType.LIABILITY, "parent": None},
        {"code": "2001", "name": "Commissions Payable L1", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2002", "name": "Commissions Payable L2-10", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2003", "name": "Service Fees Payable (KYC)", "type": AccountType.LIABILITY, "parent": "2000"},
        {"code": "2100", "name": "User Funds Payable", "type": AccountType.LIABILITY, "parent": "2000"},
        
        # EQUITY (3000)
        {"code": "3000", "name": "Equity", "type": AccountType.EQUITY, "parent": None},
        {"code": "3001", "name": "Retained Earnings", "type": AccountType.EQUITY, "parent": "3000"},
        
        # REVENUE (4000)
        {"code": "4000", "name": "Revenue", "type": AccountType.REVENUE, "parent": None},
        {"code": "4001", "name": "KYC Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        {"code": "4002", "name": "Membership Revenue", "type": AccountType.REVENUE, "parent": "4000"},
        
        # EXPENSES (5000)
        {"code": "5000", "name": "Expenses", "type": AccountType.EXPENSE, "parent": None},
        {"code": "5001", "name": "Commission Expense", "type": AccountType.EXPENSE, "parent": "5000"},
        {"code": "5002", "name": "KYC Provider Expense", "type": AccountType.EXPENSE, "parent": "5000"},
    ]
    
    # 1. Créer les comptes (Parents d'abord idéalement, mais ici on gère l'ordre manuellement)
    # On fait deux passes pour gérer les relations parent-enfant si besoin, 
    # mais simplifions en créant tout puis en liant si code présent.
    
    created_count = 0
    
    for acc_data in accounts:
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["code"]).first()
        if not existing:
            # Récupérer l'ID du parent si défini
            parent_id = None
            if acc_data["parent"]:
                parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == acc_data["parent"]).first()
                if parent:
                    parent_id = parent.id
            
            new_account = ChartOfAccounts(
                account_code=acc_data["code"],
                account_name=acc_data["name"],
                account_type=acc_data["type"],
                parent_id=parent_id,
                is_active=True
            )
            db.add(new_account)
            created_count += 1
            
    try:
        db.commit()
        if created_count > 0:
            logger.info(f"Initialized {created_count} accounts in Chart of Accounts")
    except Exception as e:
        logger.error(f"Error initializing CoA: {e}")
        db.rollback()
