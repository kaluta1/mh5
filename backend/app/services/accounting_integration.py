"""
Accounting Integration Service
Automatically creates accounting entries when payments are validated and commissions are distributed.
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import logging
import uuid

from app.models.accounting import (
    ChartOfAccounts, JournalEntry, JournalLine, RevenueTransaction,
    AccountType,
)
from app.services.journal_entry_status import posted_status_literal_for_db
from app.models.payment import Deposit
from app.models.affiliate import AffiliateCommission

logger = logging.getLogger(__name__)


# Default account codes (should be configured in database)
DEFAULT_ACCOUNTS = {
    "crypto_asset": "1010",  # Crypto Asset (USDT)
    "revenue_membership": "4000",  # Membership Revenue
    "revenue_kyc": "4010",  # KYC Service Revenue
    "commission_expense": "5000",  # Commission Expense
    "commission_payable": "2000",  # Commission Payable (Liability)
}


def get_or_create_account(
    db: Session,
    account_code: str,
    account_name: str,
    account_type: AccountType,
    parent_id: Optional[int] = None
) -> ChartOfAccounts:
    """
    Get an account by code, or create it if it doesn't exist.
    """
    account = db.query(ChartOfAccounts).filter(
        ChartOfAccounts.account_code == account_code
    ).first()
    
    if not account:
        account = ChartOfAccounts(
            account_code=account_code,
            account_name=account_name,
            account_type=account_type,
            parent_id=parent_id,
            is_active=True
        )
        db.add(account)
        db.flush()
        logger.info(f"Created account: {account_code} - {account_name}")
    
    return account


def generate_entry_number() -> str:
    """Generate a unique journal entry number"""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"JE-{timestamp}-{unique_id}"


def record_payment_in_accounting(
    db: Session,
    deposit: Deposit,
    commissions: List[AffiliateCommission],
    created_by: Optional[int] = None
) -> Optional[JournalEntry]:
    """
    Record a validated payment in the accounting system.
    
    Creates:
    1. Journal Entry with:
       - Debit: Crypto Asset (amount received)
       - Credit: Revenue (net amount after commissions)
       - Debit: Commission Expense (total commissions)
       - Credit: Commission Payable (total commissions)
    
    2. Revenue Transaction record
    
    Args:
        db: Database session
        deposit: Validated deposit
        commissions: List of affiliate commissions created
        created_by: User ID who triggered the payment (optional)
    
    Returns:
        Created JournalEntry or None if failed
    """
    try:
        # Calculate amounts
        total_amount = float(deposit.amount)
        total_commissions = sum(float(c.commission_amount) for c in commissions)
        net_revenue = total_amount - total_commissions
        
        # Ensure product_type is loaded
        if not hasattr(deposit, 'product_type') or deposit.product_type is None:
            from app.models.payment import ProductType
            deposit.product_type = db.query(ProductType).filter(
                ProductType.id == deposit.product_type_id
            ).first()
        
        # Determine revenue account based on product type
        product_code = deposit.product_type.code if deposit.product_type else "unknown"
        if product_code in ["mfm_membership", "efm_membership", "annual_membership"]:
            revenue_account_code = DEFAULT_ACCOUNTS["revenue_membership"]
            revenue_account_name = "Membership Revenue"
        elif product_code == "kyc":
            revenue_account_code = DEFAULT_ACCOUNTS["revenue_kyc"]
            revenue_account_name = "KYC Service Revenue"
        else:
            revenue_account_code = DEFAULT_ACCOUNTS["revenue_membership"]
            revenue_account_name = "Other Revenue"
        
        # Get or create accounts
        crypto_account = get_or_create_account(
            db, DEFAULT_ACCOUNTS["crypto_asset"],
            "Crypto Asset - USDT", AccountType.ASSET
        )
        revenue_account = get_or_create_account(
            db, revenue_account_code, revenue_account_name, AccountType.REVENUE
        )
        
        # Create journal entry
        entry_number = generate_entry_number()
        entry_date = deposit.validated_at or datetime.utcnow()
        
        # Calculate total amounts for balanced entry
        total_debit = total_amount + total_commissions
        total_credit = total_amount + total_commissions
        
        journal_entry = JournalEntry(
            entry_number=entry_number,
            entry_date=entry_date,
            description=(
                f"USDT (BSC) on-chain inflow — {product_code}; "
                f"Deposit #{deposit.id} User #{deposit.user_id}"
            ),
            total_debit=total_debit,
            total_credit=total_credit,
            status=posted_status_literal_for_db(db),
            created_by=created_by
        )
        db.add(journal_entry)
        db.flush()
        
        # Create journal lines
        lines = []
        
        # 1. Debit: Crypto Asset (total amount received)
        lines.append(JournalLine(
            entry_id=journal_entry.id,
            account_id=crypto_account.id,
            debit_amount=total_amount,
            credit_amount=0.0,
            description=(
                f"USDT (BSC) received from on-chain deposit — User #{deposit.user_id}; "
                f"Deposit #{deposit.id}"
            )
        ))
        
        # 2. Credit: Revenue (gross amount - full payment amount)
        lines.append(JournalLine(
            entry_id=journal_entry.id,
            account_id=revenue_account.id,
            debit_amount=0.0,
            credit_amount=total_amount,  # Credit full revenue, not net
            description=f"Revenue from {product_code} - Deposit #{deposit.id}"
        ))
        
        # 3. Debit: Commission Expense (if commissions exist)
        if total_commissions > 0:
            commission_expense_account = get_or_create_account(
                db, DEFAULT_ACCOUNTS["commission_expense"],
                "Commission Expense", AccountType.EXPENSE
            )
            commission_payable_account = get_or_create_account(
                db, DEFAULT_ACCOUNTS["commission_payable"],
                "Commission Payable", AccountType.LIABILITY
            )
            
            lines.append(JournalLine(
                entry_id=journal_entry.id,
                account_id=commission_expense_account.id,
                debit_amount=total_commissions,
                credit_amount=0.0,
                description=f"Affiliate commissions for Deposit #{deposit.id}"
            ))
            
            # 4. Credit: Commission Payable
            lines.append(JournalLine(
                entry_id=journal_entry.id,
                account_id=commission_payable_account.id,
                debit_amount=0.0,
                credit_amount=total_commissions,
                description=f"Commission liability for Deposit #{deposit.id}"
            ))
        
        # Add all lines
        for line in lines:
            db.add(line)
        
        db.flush()
        
        # Create Revenue Transaction
        # Note: net_amount represents revenue after commissions are accounted for
        # but we record gross revenue in the journal entry
        revenue_transaction = RevenueTransaction(
            source_type=product_code,
            source_id=str(deposit.id),
            gross_amount=total_amount,
            platform_fee=0.0,  # No platform fee for direct payments
            net_amount=net_revenue,  # Net after commissions (for reporting purposes)
            participant_share=0.0,
            affiliate_commissions=total_commissions,
            founding_member_share=0.0,
            transaction_date=entry_date,
            journal_entry_id=journal_entry.id
        )
        db.add(revenue_transaction)
        
        db.commit()
        
        logger.info(
            f"Accounting entry created for deposit {deposit.id}: "
            f"Entry #{journal_entry.entry_number}, "
            f"Amount: ${total_amount}, Commissions: ${total_commissions}"
        )
        
        return journal_entry
        
    except Exception as e:
        logger.error(f"Error recording payment in accounting: {e}", exc_info=True)
        db.rollback()
        return None


def record_commission_payment_in_accounting(
    db: Session,
    commission: AffiliateCommission,
    created_by: Optional[int] = None
) -> Optional[JournalEntry]:
    """
    Record when a commission is paid out to an affiliate.
    
    Creates journal entry:
    - Debit: Commission Payable
    - Credit: Cash/Crypto Asset (or payment method used)
    
    Args:
        db: Database session
        commission: Commission being paid
        created_by: User ID processing the payment
    
    Returns:
        Created JournalEntry or None if failed
    """
    try:
        if not commission.paid_date:
            logger.warning(f"Commission {commission.id} has no paid_date, skipping accounting entry")
            return None
        
        # Get accounts
        commission_payable_account = get_or_create_account(
            db, DEFAULT_ACCOUNTS["commission_payable"],
            "Commission Payable", AccountType.LIABILITY
        )
        crypto_account = get_or_create_account(
            db, DEFAULT_ACCOUNTS["crypto_asset"],
            "Crypto Asset - USDT", AccountType.ASSET
        )
        
        # Create journal entry
        entry_number = generate_entry_number()
        amount = float(commission.commission_amount)
        
        journal_entry = JournalEntry(
            entry_number=entry_number,
            entry_date=commission.paid_date,
            description=f"Commission paid - Commission #{commission.id} - User {commission.user_id}",
            total_debit=amount,
            total_credit=amount,
            status=posted_status_literal_for_db(db),
            created_by=created_by
        )
        db.add(journal_entry)
        db.flush()
        
        # Debit: Commission Payable
        db.add(JournalLine(
            entry_id=journal_entry.id,
            account_id=commission_payable_account.id,
            debit_amount=amount,
            credit_amount=0.0,
            description=f"Commission payment for Commission #{commission.id}"
        ))
        
        # Credit: Crypto Asset (assuming paid in crypto)
        db.add(JournalLine(
            entry_id=journal_entry.id,
            account_id=crypto_account.id,
            debit_amount=0.0,
            credit_amount=amount,
            description=f"Commission payout to user {commission.user_id}"
        ))
        
        db.commit()
        
        logger.info(
            f"Commission payment recorded: Entry #{journal_entry.entry_number}, "
            f"Commission #{commission.id}, Amount: ${amount}"
        )
        
        return journal_entry
        
    except Exception as e:
        logger.error(f"Error recording commission payment in accounting: {e}", exc_info=True)
        db.rollback()
        return None
