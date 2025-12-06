"""
CRUD operations for Deposits, Payment Methods, Product Types
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
import uuid

from app.models.payment import Deposit, PaymentMethod, ProductType, DepositStatus
from app.schemas.deposit import DepositCreate, DepositUpdate


def generate_reference() -> str:
    """Génère une référence unique pour un dépôt"""
    return f"DEP-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


class CRUDDeposit:
    
    def create_with_reference(
        self, 
        db: Session, 
        *, 
        obj_in: DepositCreate,
        product_type: ProductType
    ) -> Deposit:
        """Crée un dépôt avec une référence générée et calcule l'expiration"""
        # Calculer la date d'expiration basée sur le produit
        expires_at = datetime.utcnow() + timedelta(days=product_type.validity_days)
        
        db_obj = Deposit(
            user_id=obj_in.user_id,
            product_type_id=obj_in.product_type_id,
            payment_method_id=obj_in.payment_method_id,
            amount=obj_in.amount,
            currency=obj_in.currency or "USD",
            reference=generate_reference(),
            tx_hash=obj_in.tx_hash,
            from_address=obj_in.from_address,
            status=DepositStatus.PENDING
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_reference(self, db: Session, *, reference: str) -> Optional[Deposit]:
        """Récupère un dépôt par sa référence"""
        return db.query(Deposit).filter(Deposit.reference == reference).first()
    
    def get_by_order_id(self, db: Session, *, order_id: str) -> Optional[Deposit]:
        """Récupère un dépôt par son order_id"""
        return db.query(Deposit).filter(Deposit.order_id == order_id).first()
    
    def get_by_user(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Deposit]:
        """Récupère les dépôts d'un utilisateur"""
        return db.query(Deposit).filter(
            Deposit.user_id == user_id
        ).order_by(Deposit.created_at.desc()).offset(skip).limit(limit).all()
    
    def get_valid_deposit_for_product(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        product_code: str
    ) -> Optional[Deposit]:
        """
        Récupère un dépôt valide et non utilisé pour un produit spécifique.
        Utilisé pour vérifier si l'utilisateur a payé pour un service.
        """
        product_type = db.query(ProductType).filter(ProductType.code == product_code).first()
        if not product_type:
            return None
        
        now = datetime.utcnow()
        
        return db.query(Deposit).filter(
            and_(
                Deposit.user_id == user_id,
                Deposit.product_type_id == product_type.id,
                Deposit.status == DepositStatus.VALIDATED,
                Deposit.is_used == False,
                # Soit pas d'expiration, soit pas encore expiré
                (Deposit.expires_at.is_(None) | (Deposit.expires_at > now))
            )
        ).order_by(Deposit.validated_at.asc()).first()  # FIFO: utiliser le plus ancien d'abord
    
    def count_valid_deposits_for_product(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        product_code: str
    ) -> int:
        """Compte le nombre de dépôts valides et non utilisés pour un produit"""
        product_type = db.query(ProductType).filter(ProductType.code == product_code).first()
        if not product_type:
            return 0
        
        now = datetime.utcnow()
        
        return db.query(Deposit).filter(
            and_(
                Deposit.user_id == user_id,
                Deposit.product_type_id == product_type.id,
                Deposit.status == DepositStatus.VALIDATED,
                Deposit.is_used == False,
                (Deposit.expires_at.is_(None) | (Deposit.expires_at > now))
            )
        ).count()
    
    def validate_deposit(
        self, 
        db: Session, 
        *, 
        deposit: Deposit,
        product_type: ProductType,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Deposit:
        """Valide un dépôt"""
        deposit.status = DepositStatus.VALIDATED
        deposit.validated_at = datetime.utcnow()
        deposit.expires_at = datetime.utcnow() + timedelta(days=product_type.validity_days)
        if admin_id:
            deposit.validated_by = admin_id
        if notes:
            deposit.admin_notes = notes
        db.commit()
        db.refresh(deposit)
        return deposit
    
    def reject_deposit(
        self, 
        db: Session, 
        *, 
        deposit: Deposit,
        admin_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Deposit:
        """Rejette un dépôt"""
        deposit.status = DepositStatus.REJECTED
        if admin_id:
            deposit.validated_by = admin_id
        if reason:
            deposit.admin_notes = reason
        db.commit()
        db.refresh(deposit)
        return deposit
    
    def mark_as_used(self, db: Session, *, deposit: Deposit) -> Deposit:
        """Marque un dépôt comme utilisé"""
        deposit.is_used = True
        deposit.used_at = datetime.utcnow()
        db.commit()
        db.refresh(deposit)
        return deposit
    
    def get_pending_deposits(
        self, 
        db: Session, 
        *, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Deposit]:
        """Récupère les dépôts en attente de validation (pour admin)"""
        return db.query(Deposit).filter(
            Deposit.status == DepositStatus.PENDING
        ).order_by(Deposit.created_at.asc()).offset(skip).limit(limit).all()


class CRUDPaymentMethod:
    
    def get_by_code(self, db: Session, *, code: str) -> Optional[PaymentMethod]:
        return db.query(PaymentMethod).filter(PaymentMethod.code == code).first()
    
    def get_active(self, db: Session) -> List[PaymentMethod]:
        return db.query(PaymentMethod).filter(PaymentMethod.is_active == True).all()
    
    def get_by_category(self, db: Session, *, category: str) -> List[PaymentMethod]:
        return db.query(PaymentMethod).filter(
            and_(PaymentMethod.category == category, PaymentMethod.is_active == True)
        ).all()


class CRUDProductType:
    
    def get_by_code(self, db: Session, *, code: str) -> Optional[ProductType]:
        return db.query(ProductType).filter(ProductType.code == code).first()
    
    def get_active(self, db: Session) -> List[ProductType]:
        return db.query(ProductType).filter(ProductType.is_active == True).all()


deposit = CRUDDeposit()
payment_method = CRUDPaymentMethod()
product_type = CRUDProductType()
