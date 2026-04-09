from sqlalchemy.orm import Session
from decimal import Decimal
import logging
from typing import Optional, List, Dict
from datetime import datetime

from app.models.payment import Deposit
from app.models.affiliate import AffiliateCommission, CommissionType
from app.services.accounting_service import accounting_service

logger = logging.getLogger(__name__)


def _journal_entry_date(deposit: Deposit, entry_date: Optional[datetime]) -> datetime:
    if entry_date is not None:
        return entry_date
    return deposit.validated_at or deposit.created_at or datetime.utcnow()

class PaymentAccountingService:
    """
    Service de haut niveau pour gérer la comptabilité des paiements spécifiques
    (KYC, Membership, etc.) en utilisant le service comptable générique.
    """
    
    def process_kyc_payment_accounting(
        self, 
        db: Session, 
        deposit: Deposit, 
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
    ):
        """
        Cas d'usage 1: Paiement KYC (10$)
        Répartition:
        - 100% du montant -> Platform Wallet (Asset) / KYC Revenue (Income)
        - Commissions -> Commission Expense / Payable
        - Frais Provider (20%) -> Expense / Payable
        """
        dep_id = deposit.id
        amount = Decimal(str(deposit.amount))
        description = f"KYC Payment - Deposit #{dep_id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)
        
        # 1. Enregistrement du revenu (Encaissement)
        # Debit: Platform Wallet (1001), Credit: KYC Revenue (4001)
        income_lines = [
            {"account_code": "1001", "debit": float(amount), "credit": 0.0, "description": "Payment received"},
            {"account_code": "4001", "debit": 0.0, "credit": float(amount), "description": "KYC Revenue recognized"}
        ]
        
        try:
            accounting_service.create_journal_entry(
                db, 
                description=description + " (Income)", 
                lines=income_lines,
                date=jdate,
            )
            logger.info(f"Accounting: Income recorded for KYC deposit {dep_id}")
        except Exception as e:
            logger.error(f"Failed to record income for deposit {dep_id}: {e}")
            # On continue pour essayer d'enregistrer les dépenses ? Ou on stop ?
            # Idéalement transaction atomique globale.
        
        # 2. Enregistrement des commissions (Dépenses)
        if commissions:
            commission_lines = []
            total_comm_expense = Decimal("0.0")
            
            for comm in commissions:
                comm_amount = Decimal(str(comm.commission_amount))
                total_comm_expense += comm_amount
                
                # Debit: Commission Expense (5001) est fait globalement ou par ligne
                # Credit: Commission Payable L1 (2001) ou L2-10 (2002)
                payable_account = "2001" if comm.level == 1 else "2002"
                
                commission_lines.append({
                    "account_code": payable_account,
                    "debit": 0.0,
                    "credit": float(comm_amount),
                    "description": f"Commission Level {comm.level} to User #{comm.user_id}"
                })
            
            # Ajout de la ligne Debit globale pour les commissions
            commission_lines.insert(0, {
                "account_code": "5001",
                "debit": float(total_comm_expense),
                "credit": 0.0,
                "description": "Total Referral Commissions"
            })
            
            try:
                accounting_service.create_journal_entry(
                    db,
                    description=description + " (Commissions)",
                    lines=commission_lines,
                    date=jdate,
                )
                logger.info(f"Accounting: Commissions recorded for KYC deposit {dep_id}")
            except Exception as e:
                logger.error(f"Failed to record commissions for deposit {dep_id}: {e}")

        # 3. Enregistrement des frais de service (Provider Fee 20% = 2$)
        # Debit: Expense (5002), Credit: Payable (2003)
        # Note: Ce montant de 2$ est hardcodé ici pour l'exemple, mais pourrait venir d'une config
        provider_fee = amount * Decimal("0.20") # 20%
        
        fee_lines = [
            {"account_code": "5002", "debit": float(provider_fee), "credit": 0.0, "description": "KYC Provider Verification Cost"},
            {"account_code": "2003", "debit": 0.0, "credit": float(provider_fee), "description": "Liability to KYC Provider"}
        ]
        
        try:
            accounting_service.create_journal_entry(
                db,
                description=description + " (Provider Fees)",
                lines=fee_lines,
                date=jdate,
            )
            logger.info(f"Accounting: Provider fees recorded for KYC deposit {dep_id}")
        except Exception as e:
            logger.error(f"Failed to record fees for deposit {dep_id}: {e}")

    def process_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
    ):
        """
        Cas d'usage 2: Abonnement Annuel (50$)
        Répartition:
        - 100% -> Platform Wallet / Membership Revenue
        - Commissions -> Expense / Payable
        """
        amount = Decimal(str(deposit.amount))
        description = f"Membership Payment - Deposit #{deposit.id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)
        
        # 1. Income (Revenue)
        income_lines = [
            {"account_code": "1001", "debit": float(amount), "credit": 0.0, "description": "Payment received"},
            {"account_code": "4002", "debit": 0.0, "credit": float(amount), "description": "Membership Revenue recognized"}
        ]
        
        accounting_service.create_journal_entry(
            db,
            description=description + " (Income)",
            lines=income_lines,
            date=jdate,
        )
        
        # 2. Commissions
        if commissions:
            commission_lines = []
            total_comm = Decimal("0.0")
            
            for comm in commissions:
                c_amt = Decimal(str(comm.commission_amount))
                total_comm += c_amt
                payable_acc = "2001" if comm.level == 1 else "2002"
                
                commission_lines.append({
                    "account_code": payable_acc,
                    "debit": 0.0,
                    "credit": float(c_amt),
                    "description": f"Comm L{comm.level} User #{comm.user_id}"
                })
                
            commission_lines.insert(0, {
                "account_code": "5001",
                "debit": float(total_comm),
                "credit": 0.0,
                "description": "Total Commissions"
            })
            
            accounting_service.create_journal_entry(
                db,
                description=description + " (Commissions)",
                lines=commission_lines,
                date=jdate,
            )

        # 3. Founding Members pool (10% of gross) — contractual payable 2104; reduce 4002 recognition
        pool_amt = float(amount) * 0.10
        if pool_amt > 0:
            alloc_lines = [
                {
                    "account_code": "4002",
                    "debit": pool_amt,
                    "credit": 0.0,
                    "description": "Allocate 10% to Founding Members pool (payable)",
                },
                {
                    "account_code": "2104",
                    "debit": 0.0,
                    "credit": pool_amt,
                    "description": "Founding Members pool payable accrual",
                },
            ]
            accounting_service.create_journal_entry(
                db,
                description=description + " (Founding pool accrual)",
                lines=alloc_lines,
                date=jdate,
            )

        # 4. Annual membership: fixed Shufti pass-through ($2) when fee is standard $10 tier
        shufti_amt = 2.0 if float(amount) <= 12.0 else 0.0
        if shufti_amt > 0:
            shufti_lines = [
                {
                    "account_code": "4002",
                    "debit": shufti_amt,
                    "credit": 0.0,
                    "description": "KYC provider fee (Shufti) from annual membership gross",
                },
                {
                    "account_code": "2003",
                    "debit": 0.0,
                    "credit": shufti_amt,
                    "description": "Payable to KYC verification provider",
                },
            ]
            accounting_service.create_journal_entry(
                db,
                description=description + " (KYC provider payable)",
                lines=shufti_lines,
                date=jdate,
            )

    def process_founding_membership_payment_accounting(
        self,
        db: Session,
        deposit: Deposit,
        commissions: List[AffiliateCommission],
        entry_date: Optional[datetime] = None,
    ):
        """
        Founding membership (e.g. $100): gross to wallet / revenue, commissions, 10% pool accrual.
        """
        amount = Decimal(str(deposit.amount))
        description = f"Founding Membership Payment - Deposit #{deposit.id} - User #{deposit.user_id}"
        jdate = _journal_entry_date(deposit, entry_date)

        income_lines = [
            {"account_code": "1001", "debit": float(amount), "credit": 0.0, "description": "Payment received"},
            {"account_code": "4002", "debit": 0.0, "credit": float(amount), "description": "Founding membership revenue recognized"},
        ]
        accounting_service.create_journal_entry(
            db,
            description=description + " (Income)",
            lines=income_lines,
            date=jdate,
        )

        if commissions:
            commission_lines = []
            total_comm = Decimal("0.0")
            for comm in commissions:
                c_amt = Decimal(str(comm.commission_amount))
                total_comm += c_amt
                payable_acc = "2001" if comm.level == 1 else "2002"
                commission_lines.append(
                    {
                        "account_code": payable_acc,
                        "debit": 0.0,
                        "credit": float(c_amt),
                        "description": f"Comm L{comm.level} User #{comm.user_id}",
                    }
                )
            commission_lines.insert(
                0,
                {
                    "account_code": "5001",
                    "debit": float(total_comm),
                    "credit": 0.0,
                    "description": "Total commissions",
                },
            )
            accounting_service.create_journal_entry(
                db,
                description=description + " (Commissions)",
                lines=commission_lines,
                date=jdate,
            )

        pool_amt = float(amount) * 0.10
        if pool_amt > 0:
            accounting_service.create_journal_entry(
                db,
                description=description + " (Founding pool accrual)",
                lines=[
                    {
                        "account_code": "4002",
                        "debit": pool_amt,
                        "credit": 0.0,
                        "description": "Allocate 10% to Founding Members pool",
                    },
                    {
                        "account_code": "2104",
                        "debit": 0.0,
                        "credit": pool_amt,
                        "description": "Founding Members pool payable",
                    },
                ],
                date=jdate,
            )


payment_accounting = PaymentAccountingService()
