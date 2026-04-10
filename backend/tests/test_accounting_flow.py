import pytest
import logging
import sys

# PATCH: Update settings to use psycopg3 BEFORE app.db.session is imported
try:
    from app.core.config import settings
    # SQLALCHEMY_DATABASE_URI is a property, need to update DATABASE_URL
    if settings.DATABASE_URL.startswith("postgresql://"):
        settings.DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
except ImportError:
    pass

# Ensure all models are loaded to avoid SQLAlchemy mapper issues
import app.models

from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session

# from app.db.session import SessionLocal
# from app.db.session import SessionLocal
from app.models.user import User
from app.models.payment import Deposit, ProductType, DepositStatus
from app.models.affiliate import CommissionRule, CommissionType, AffiliateCommission
from app.models.accounting import JournalEntry, JournalLine, AccountType
from app.services.commission_distribution import process_payment_validation
from app.scripts.init_coa import init_chart_of_accounts
from app.scripts.init_commission_rules import init_commission_rules

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(scope="module")
def db():
    """Session de base de données pour les tests."""
    # Patch the database URL to use psycopg 3 if psycopg2 is missing
    from app.core.config import settings
    # SQLALCHEMY_DATABASE_URI is a property, need to update DATABASE_URL
    if settings.DATABASE_URL.startswith("postgresql://"):
        settings.DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestingSessionLocal()
    try:
        # Initialiser les données de base nécessaires
        init_chart_of_accounts(db)
        init_commission_rules(db)
        yield db
    finally:
        db.close()

def test_kyc_payment_accounting_flow(db: Session):
    """
    Test complet du flux comptable pour un paiement KYC.
    1. Création utilisateurs (User + Sponsor)
    2. Création dépôt (10$)
    3. Validation paiement
    4. Vérification commissions
    5. Vérification écritures comptables
    """
    logger.info("--- START TEST: KYC Payment Accounting Flow ---")
    
    # 1. Setup Users
    # Utiliser des emails uniques pour éviter les conflits
    timestamp = int(datetime.utcnow().timestamp())
    sponsor_email = f"sponsor_test_{timestamp}@example.com"
    user_email = f"user_test_{timestamp}@example.com"
    
    sponsor = User(email=sponsor_email, hashed_password="pw", is_active=True, full_name="Sponsor Test")
    db.add(sponsor)
    db.commit()
    db.refresh(sponsor)
    
    user = User(email=user_email, hashed_password="pw", is_active=True, full_name="User Test", sponsor_id=sponsor.id)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 2. Setup Product & Deposit
    # S'assurer que le produit KYC existe
    kyc_product = db.query(ProductType).filter(ProductType.code == "kyc").first()
    if not kyc_product:
        kyc_product = ProductType(code="kyc", name="KYC Verification", price=10.0, is_active=True)
        db.add(kyc_product)
    else:
        kyc_product.price = 10.0
    db.commit()
    db.refresh(kyc_product)
        
    deposit = Deposit(
        user_id=user.id,
        product_type_id=kyc_product.id,
        amount=10.0,
        status=DepositStatus.PENDING,
        external_payment_id=f"PAY-{timestamp}"
    )
    db.add(deposit)
    db.commit()
    db.refresh(deposit)
    
    # 3. Process Payment Validation
    logger.info(f"Processing validation for deposit {deposit.id}")
    success = process_payment_validation(db, deposit)
    assert success is True, "Payment validation failed"
    
    # 4. Verify Commissions
    # Règle KYC: 10% direct ($1.00 sur dépôt $10)
    commissions = db.query(AffiliateCommission).filter(AffiliateCommission.deposit_id == deposit.id).all()
    assert len(commissions) >= 1, "Should create at least one commission for sponsor"
    
    sponsor_comm = next((c for c in commissions if c.user_id == sponsor.id), None)
    assert sponsor_comm is not None, "Sponsor commission missing"
    assert float(sponsor_comm.commission_amount) == 1.0, f"Commission should be 1.0, got {sponsor_comm.commission_amount}"
    
    # 5. Verify Accounting (Journal Entries)
    # On cherche l'entrée liée à ce dépôt (description contient Deposit ID)
    # Income Entry
    income_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%KYC Payment - Deposit #{deposit.id}%(Income)%")
    ).first()
    
    assert income_entry is not None, "Income Journal Entry missing"
    assert len(income_entry.lines) == 2, "Income entry should have 2 lines"
    assert income_entry.total_debit == 10.0
    assert income_entry.total_credit == 10.0
    
    # Commission Entry
    comm_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%KYC Payment - Deposit #{deposit.id}%(Commissions)%")
    ).first()
    
    assert comm_entry is not None, "Commission Journal Entry missing"
    # Vérifier que le total débit correspond à la somme des commissions
    total_commissions = sum(float(c.commission_amount) for c in commissions)
    assert comm_entry.total_debit == total_commissions
    
    # Provider Fee Entry (20% -> $2.00 sur dépôt $10)
    fee_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%KYC Payment - Deposit #{deposit.id}%(Provider Fees)%")
    ).first()
    
    assert fee_entry is not None, "Provider Fee Journal Entry missing"
    assert fee_entry.total_debit == 2.0
    
    logger.info("--- TEST PASSED: All accounting entries verified ---")

def test_membership_payment_accounting_flow(db: Session):
    """
    Test flux comptable pour Abonnement Annuel (50$)
    Règle: 10% direct ($5.00), 1% indirect ($0.50)
    """
    logger.info("--- START TEST: Membership Payment Accounting Flow ---")
    
    timestamp = int(datetime.utcnow().timestamp()) + 1
    sponsor_email = f"sponsor_mem_{timestamp}@example.com"
    user_email = f"user_mem_{timestamp}@example.com"
    
    sponsor = User(email=sponsor_email, hashed_password="pw", is_active=True, full_name="Sponsor Mem")
    db.add(sponsor)
    db.commit()
    db.refresh(sponsor)

    user = User(email=user_email, hashed_password="pw", is_active=True, full_name="User Mem", sponsor_id=sponsor.id)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Product
    # code 'annual_membership'
    product = db.query(ProductType).filter(ProductType.code == "annual_membership").first()
    if not product:
        product = ProductType(code="annual_membership", name="Annual Membership", price=50.0, is_active=True)
        db.add(product)
        db.commit()
        
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=50.0,
        status=DepositStatus.PENDING,
        payment_method="crypto",
        external_payment_id=f"PAY-MEM-{timestamp}"
    )
    db.add(deposit)
    db.commit()
    db.refresh(deposit)

    user.is_founding_member = False
    db.commit()

    assert process_payment_validation(db, deposit) is True

    income_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit.id}%(Income)%")
    ).first()
    assert income_entry is not None
    assert income_entry.total_debit == 50.0

    comm_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit.id}%(Commissions)%")
    ).first()
    assert comm_entry is not None
    assert comm_entry.total_debit >= 5.0

    pool_entry = db.query(JournalEntry).filter(
        JournalEntry.description.like(f"%Membership Payment - Deposit #{deposit.id}%(Founding pool accrual)%")
    ).first()
    assert pool_entry is not None
    assert abs(pool_entry.total_debit - 5.0) < 0.001

    logger.info("--- TEST PASSED: Membership accounting verified ---")


if __name__ == "__main__":
    # Manually run tests if executed as script
    # Patch settings first
    from app.core.config import settings
    if settings.DATABASE_URL.startswith("postgresql://"):
        settings.DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
        settings.SQLALCHEMY_DATABASE_URI # Access property to ensure it uses the updated URL if cached? No it's dynamic.
        
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        init_chart_of_accounts(db)
        init_commission_rules(db)
        
        test_kyc_payment_accounting_flow(db)
        test_membership_payment_accounting_flow(db)
        
        print("\nALL TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
