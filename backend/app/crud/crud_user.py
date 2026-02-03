from typing import Any, Dict, Optional, Union, List
import secrets
import string
import logging

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.security import get_password_hash, verify_password
from app.models.user import User, Role
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


def generate_referral_code(length: int = 8) -> str:
    """Génère un code de parrainage unique alphanumerique."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class CRUDUser:
    def get(self, db: Session, id: int) -> Optional[User]:
        return db.query(User).filter(User.id == id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Get user by email. Returns None if not found."""
        try:
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            logger.error(f"Error querying user by email '{email}': {e}", exc_info=True)
            raise

    def get_multi(self, db: Session, skip: int = 0, limit: int = 10) -> List[User]:
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
        """Crée un utilisateur avec un parrain optionnel et le rôle 'user' par défaut."""
        # Générer un code de parrainage unique
        referral_code = self._generate_unique_referral_code(db)
        
        # Trouver le parrain si un code est fourni
        sponsor_id = None
        if sponsor_code:
            sponsor = self.get_by_referral_code(db, sponsor_code)
            if sponsor:
                sponsor_id = sponsor.id
        
        # Récupérer le rôle par défaut 'user', créer s'il n'existe pas
        default_role = self.get_role_by_name(db, 'user')
        if not default_role:
            # Créer le rôle 'user' s'il n'existe pas
            default_role = self.create_role(db, name='user', description='Default user role')
        role_id = default_role.id
        
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
            sponsor_id=sponsor_id,
            role_id=role_id
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
    
    def get_top_sponsors(self, db: Session, limit: int = 10) -> List[dict]:
        """Récupère les meilleurs sponsors (ceux avec le plus de référents directs qui ont un dépôt KYC validé)."""
        from sqlalchemy import func
        from app.models.payment import Deposit, ProductType, DepositStatus
        
        # Créer une sous-requête pour obtenir les utilisateurs distincts qui ont un dépôt KYC validé
        kyc_users_subquery = db.query(
            User.id.label('user_id'),
            User.sponsor_id
        ).join(
            Deposit, User.id == Deposit.user_id
        ).join(
            ProductType, Deposit.product_type_id == ProductType.id
        ).filter(
            User.sponsor_id.isnot(None),
            ProductType.code == 'kyc',
            Deposit.status == DepositStatus.VALIDATED
        ).distinct().subquery()
        
        # Compter les référents KYC par sponsor
        referrals_subquery = db.query(
            kyc_users_subquery.c.sponsor_id,
            func.count(kyc_users_subquery.c.user_id).label('referrals_count')
        ).group_by(kyc_users_subquery.c.sponsor_id).subquery()
        
        # Joindre avec la table User pour obtenir les informations des sponsors
        top_sponsors = db.query(
            User.id,
            User.username,
            User.email,
            User.first_name,
            User.last_name,
            User.full_name,
            User.avatar_url,
            User.country,
            User.city,
            User.created_at,
            referrals_subquery.c.referrals_count
        ).join(
            referrals_subquery, User.id == referrals_subquery.c.sponsor_id
        ).order_by(
            referrals_subquery.c.referrals_count.desc()
        ).limit(limit).all()
        
        result = []
        for sponsor in top_sponsors:
            result.append({
                "id": sponsor.id,
                "username": sponsor.username,
                "email": sponsor.email,
                "first_name": sponsor.first_name,
                "last_name": sponsor.last_name,
                "full_name": sponsor.full_name,
                "avatar_url": sponsor.avatar_url,
                "country": sponsor.country,
                "city": sponsor.city,
                "created_at": sponsor.created_at.isoformat() if sponsor.created_at else None,
                "referrals_count": sponsor.referrals_count or 0
            })
        
        return result
    
    def get_top_mfm_sponsors(self, db: Session, limit: int = 10) -> List[dict]:
        """Récupère les meilleurs sponsors MFM (ceux avec le plus de référents directs qui ont acheté mfm_membership)."""
        from sqlalchemy import func
        from app.models.payment import Deposit, ProductType, DepositStatus
        
        # Créer une sous-requête pour obtenir les utilisateurs distincts qui ont acheté MFM
        mfm_users_subquery = db.query(
            User.id.label('user_id'),
            User.sponsor_id
        ).join(
            Deposit, User.id == Deposit.user_id
        ).join(
            ProductType, Deposit.product_type_id == ProductType.id
        ).filter(
            User.sponsor_id.isnot(None),
            ProductType.code == 'mfm_membership',
            Deposit.status == DepositStatus.VALIDATED
        ).distinct().subquery()
        
        # Compter les référents MFM par sponsor
        referrals_subquery = db.query(
            mfm_users_subquery.c.sponsor_id,
            func.count(mfm_users_subquery.c.user_id).label('referrals_count')
        ).group_by(mfm_users_subquery.c.sponsor_id).subquery()
        
        # Joindre avec la table User pour obtenir les informations des sponsors
        top_sponsors = db.query(
            User.id,
            User.username,
            User.email,
            User.first_name,
            User.last_name,
            User.full_name,
            User.avatar_url,
            User.country,
            User.city,
            User.created_at,
            referrals_subquery.c.referrals_count
        ).join(
            referrals_subquery, User.id == referrals_subquery.c.sponsor_id
        ).order_by(
            referrals_subquery.c.referrals_count.desc()
        ).limit(limit).all()
        
        result = []
        for sponsor in top_sponsors:
            result.append({
                "id": sponsor.id,
                "username": sponsor.username,
                "email": sponsor.email,
                "first_name": sponsor.first_name,
                "last_name": sponsor.last_name,
                "full_name": sponsor.full_name,
                "avatar_url": sponsor.avatar_url,
                "country": sponsor.country,
                "city": sponsor.city,
                "created_at": sponsor.created_at.isoformat() if sponsor.created_at else None,
                "referrals_count": sponsor.referrals_count or 0
            })
        
        return result
    
    def get_all_referrals_multilevel(
        self, db: Session, user_id: int, 
        skip: int = 0, limit: int = 10,
        level_filter: int = None, status_filter: str = None,
        search_query: str = None, kyc_status_filter: str = None
    ) -> dict:
        """
        Récupère tous les referrals (directs et indirects) jusqu'au niveau 10
        avec les commissions générées par chacun.
        """
        from app.models.affiliate import AffiliateCommission, CommissionStatus
        from app.models.payment import Deposit, DepositStatus
        from app.models.kyc import KYCVerification, KYCStatus
        from sqlalchemy import func
        
        all_referrals = []
        
        def get_referrals_at_level(sponsor_ids: List[int], current_level: int):
            """Récupère les referrals d'un niveau donné"""
            if current_level > 10 or not sponsor_ids:
                return []
            
            referrals = db.query(User).filter(User.sponsor_id.in_(sponsor_ids)).all()
            level_referrals = []
            next_level_sponsor_ids = []
            
            for referral in referrals:
                # Commissions générées par ce filleul pour le parrain principal
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
                
                # Récupérer le statut KYC
                kyc_verification = db.query(KYCVerification).filter(
                    KYCVerification.user_id == referral.id
                ).first()
                
                kyc_status = None
                if kyc_verification:
                    kyc_status = kyc_verification.status.value if kyc_verification.status else None
                elif kyc_payment:
                    kyc_status = "pending"  # A payé mais pas encore de vérification
                
                # Compter les filleuls de ce referral
                sub_referrals_count = db.query(func.count(User.id)).filter(
                    User.sponsor_id == referral.id
                ).scalar() or 0
                
                level_referrals.append({
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
                    "is_active": referral.is_active,
                    "level": current_level,
                    "has_paid_kyc": kyc_payment is not None,
                    "kyc_status": kyc_status,
                    "commissions_generated": float(commissions),
                    "referrals_count": sub_referrals_count
                })
                
                next_level_sponsor_ids.append(referral.id)
            
            return level_referrals, next_level_sponsor_ids
        
        # Parcourir tous les niveaux
        current_sponsor_ids = [user_id]
        for level in range(1, 11):
            level_referrals, next_ids = get_referrals_at_level(current_sponsor_ids, level)
            all_referrals.extend(level_referrals)
            current_sponsor_ids = next_ids
            if not next_ids:
                break
        
        # Filtres
        filtered_referrals = all_referrals
        
        if level_filter is not None:
            filtered_referrals = [r for r in filtered_referrals if r["level"] == level_filter]
        
        if status_filter:
            if status_filter == "active":
                filtered_referrals = [r for r in filtered_referrals if r["is_active"]]
            elif status_filter == "inactive":
                filtered_referrals = [r for r in filtered_referrals if not r["is_active"]]
        
        if search_query:
            search_lower = search_query.lower()
            filtered_referrals = [r for r in filtered_referrals if 
                (r["full_name"] and search_lower in r["full_name"].lower()) or
                (r["email"] and search_lower in r["email"].lower()) or
                (r["username"] and search_lower in r["username"].lower())
            ]
        
        # Filtre par statut KYC
        if kyc_status_filter:
            if kyc_status_filter == "none":
                # Pas de KYC (n'a pas payé)
                filtered_referrals = [r for r in filtered_referrals if r["kyc_status"] is None]
            else:
                filtered_referrals = [r for r in filtered_referrals if r["kyc_status"] == kyc_status_filter]
        
        total_count = len(filtered_referrals)
        
        # Pagination
        paginated = filtered_referrals[skip:skip + limit]
        
        # Stats par niveau
        level_stats = {}
        for r in all_referrals:
            lvl = r["level"]
            if lvl not in level_stats:
                level_stats[lvl] = {"count": 0, "commissions": 0}
            level_stats[lvl]["count"] += 1
            level_stats[lvl]["commissions"] += r["commissions_generated"]
        
        # Stats KYC
        kyc_stats = {
            "none": 0,
            "pending": 0,
            "in_progress": 0,
            "approved": 0,
            "rejected": 0,
            "expired": 0,
            "requires_review": 0
        }
        for r in all_referrals:
            status = r["kyc_status"] or "none"
            if status in kyc_stats:
                kyc_stats[status] += 1
        
        return {
            "referrals": paginated,
            "total": total_count,
            "total_all_levels": len(all_referrals),
            "level_stats": level_stats,
            "kyc_stats": kyc_stats
        }

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
        """Get user by username. Returns None if not found."""
        try:
            return db.query(User).filter(User.username == username).first()
        except Exception as e:
            logger.error(f"Error querying user by username '{username}': {e}", exc_info=True)
            raise

    def authenticate(self, db: Session, email_or_username: str, password: str) -> Optional[User]:
        """
        Authenticate a user by email or username and password.
        Returns None if authentication fails, or raises an exception on database errors.
        """
        try:
            # Essayer d'abord par email
            user = self.get_by_email(db=db, email=email_or_username)
            
            # Si pas trouvé par email, essayer par username
            if not user:
                user = self.get_by_username(db=db, username=email_or_username)
            
            if not user:
                logger.debug(f"Authentication failed: User not found for '{email_or_username}'")
                return None
            
            # Verify password
            if not verify_password(password, user.hashed_password):
                logger.debug(f"Authentication failed: Invalid password for user '{email_or_username}'")
                return None
            
            logger.debug(f"Authentication successful for user '{email_or_username}' (ID: {user.id})")
            return user
            
        except OperationalError as e:
            # Database connection error
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            logger.error(f"Database connection error during authentication: {error_msg}")
            logger.error("Please check your internet connection and DATABASE_URL configuration")
            # Re-raise to be handled by get_db() dependency
            raise
        except SQLAlchemyError as e:
            # Other database errors
            logger.error(f"Database error during authentication: {e}", exc_info=True)
            # Re-raise to be handled by get_db() dependency
            raise
        except Exception as e:
            # Unexpected errors
            logger.error(f"Unexpected error during authentication: {e}", exc_info=True)
            raise

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
        
        # User has a single role (role_id), not a list of roles
        user.role_id = role.id
        db.commit()
        db.refresh(user)
        return user


user = CRUDUser()
crud_user = user
