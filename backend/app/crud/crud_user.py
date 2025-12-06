from typing import Any, Dict, Optional, Union, List
import secrets
import string

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.user import User, Role
from app.schemas.user import UserCreate, UserUpdate


def generate_referral_code(length: int = 8) -> str:
    """Génère un code de parrainage unique alphanumerique."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class CRUDUser:
    def get(self, db: Session, id: int) -> Optional[User]:
        return db.query(User).filter(User.id == id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: UserCreate) -> User:
        # Générer un code de parrainage unique
        referral_code = self._generate_unique_referral_code(db)
        
        db_obj = User(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            username=obj_in.username,
            full_name=obj_in.full_name,
            is_active=obj_in.is_active,
            is_verified=obj_in.is_verified,
            is_admin=obj_in.is_admin,
            avatar_url=obj_in.avatar_url,
            bio=obj_in.bio,
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            continent=obj_in.continent,
            region=obj_in.region,
            country=obj_in.country,
            city=obj_in.city,
            personal_referral_code=referral_code
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def _generate_unique_referral_code(self, db: Session, max_attempts: int = 10) -> str:
        """Génère un code de parrainage unique en vérifiant qu'il n'existe pas déjà."""
        for _ in range(max_attempts):
            code = generate_referral_code()
            existing = db.query(User).filter(User.personal_referral_code == code).first()
            if not existing:
                return code
        # Si après max_attempts on n'a pas trouvé de code unique, générer un code plus long
        return generate_referral_code(length=12)
    
    def get_by_referral_code(self, db: Session, referral_code: str) -> Optional[User]:
        """Récupère un utilisateur par son code de parrainage."""
        return db.query(User).filter(User.personal_referral_code == referral_code).first()

    def create_with_sponsor(self, db: Session, obj_in: UserCreate, sponsor_code: Optional[str] = None) -> User:
        """Crée un utilisateur avec un parrain optionnel."""
        # Générer un code de parrainage unique
        referral_code = self._generate_unique_referral_code(db)
        
        # Trouver le parrain si un code est fourni
        sponsor_id = None
        if sponsor_code:
            sponsor = self.get_by_referral_code(db, sponsor_code)
            if sponsor:
                sponsor_id = sponsor.id
        
        db_obj = User(
            email=obj_in.email,
            hashed_password=get_password_hash(obj_in.password),
            username=obj_in.username,
            full_name=obj_in.full_name,
            is_active=obj_in.is_active,
            is_verified=obj_in.is_verified,
            is_admin=obj_in.is_admin,
            avatar_url=obj_in.avatar_url,
            bio=obj_in.bio,
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            continent=obj_in.continent,
            region=obj_in.region,
            country=obj_in.country,
            city=obj_in.city,
            personal_referral_code=referral_code,
            sponsor_id=sponsor_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def set_sponsor(self, db: Session, user_id: int, sponsor_code: str) -> Optional[User]:
        """Définit le parrain d'un utilisateur via son code de parrainage."""
        user = self.get(db, user_id)
        if not user:
            return None
        
        sponsor = self.get_by_referral_code(db, sponsor_code)
        if not sponsor or sponsor.id == user_id:
            return None
        
        user.sponsor_id = sponsor.id
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_referrals(self, db: Session, user_id: int, skip: int = 0, limit: int = 50) -> List[User]:
        """Récupère les filleuls directs d'un utilisateur."""
        return db.query(User).filter(User.sponsor_id == user_id).offset(skip).limit(limit).all()
    
    def get_referrals_with_commissions(self, db: Session, user_id: int, skip: int = 0, limit: int = 50) -> List[dict]:
        """Récupère les filleuls avec leurs commissions générées pour le parrain."""
        from app.models.affiliate import AffiliateCommission, CommissionStatus
        from app.models.payment import Deposit, DepositStatus
        from sqlalchemy import func
        
        referrals = db.query(User).filter(User.sponsor_id == user_id).offset(skip).limit(limit).all()
        
        result = []
        for referral in referrals:
            # Commissions générées par ce filleul pour le parrain
            commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
                AffiliateCommission.source_user_id == referral.id,
                AffiliateCommission.user_id == user_id,
                AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID])
            ).scalar() or 0.0
            
            # Vérifier si le filleul a payé le KYC
            kyc_payment = db.query(Deposit).filter(
                Deposit.user_id == referral.id,
                Deposit.status == DepositStatus.VALIDATED
            ).join(Deposit.product_type).filter_by(code="kyc").first()
            
            result.append({
                "id": referral.id,
                "username": referral.username,
                "email": referral.email,
                "first_name": referral.first_name,
                "last_name": referral.last_name,
                "full_name": referral.full_name,
                "avatar_url": referral.avatar_url,
                "country": referral.country,
                "city": referral.city,
                "created_at": referral.created_at.isoformat() if referral.created_at else None,
                "identity_verified": referral.identity_verified,
                "has_paid_kyc": kyc_payment is not None,
                "commissions_generated": float(commissions)
            })
        
        return result

    def count_referrals(self, db: Session, user_id: int) -> int:
        """Compte le nombre de filleuls directs d'un utilisateur."""
        return db.query(User).filter(User.sponsor_id == user_id).count()

    def update(self, db: Session, db_obj: User, obj_in: Union[UserUpdate, Dict[str, Any]]) -> User:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        
        if "password" in update_data and update_data["password"]:
            hashed_password = get_password_hash(update_data["password"])
            del update_data["password"]
            update_data["hashed_password"] = hashed_password
        
        for field in update_data:
            if hasattr(db_obj, field):
                setattr(db_obj, field, update_data[field])
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def authenticate(self, db: Session, email_or_username: str, password: str) -> Optional[User]:
        # Essayer d'abord par email
        user = self.get_by_email(db=db, email=email_or_username)
        
        # Si pas trouvé par email, essayer par username
        if not user:
            user = self.get_by_username(db=db, username=email_or_username)
        
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def is_active(self, user: User) -> bool:
        return user.is_active

    def is_admin(self, user: User) -> bool:
        return user.is_admin

    def reset_password(self, db: Session, user: User, new_password: str) -> User:
        """Réinitialiser le mot de passe d'un utilisateur"""
        hashed_password = get_password_hash(new_password)
        user.hashed_password = hashed_password
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_role_by_name(self, db: Session, name: str) -> Optional[Role]:
        return db.query(Role).filter(Role.name == name).first()

    def create_role(self, db: Session, name: str, description: Optional[str] = None) -> Role:
        db_obj = Role(name=name, description=description)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def add_user_role(self, db: Session, user_id: int, role_name: str) -> User:
        user = self.get(db=db, id=user_id)
        role = self.get_role_by_name(db=db, name=role_name)
        
        if not role:
            role = self.create_role(db=db, name=role_name)
        
        user.roles.append(role)
        db.commit()
        db.refresh(user)
        return user


user = CRUDUser()
