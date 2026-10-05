from typing import Any, Dict, Optional, Union, List
import secrets
import string
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.redaction import describe_exception, safe_traceback
from app.core.security import get_password_hash, verify_password
from app.models.user import User, Role
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)

_DUMMY_PASSWORD_HASH: Optional[str] = None


def _dummy_password_hash() -> str:
    """A real bcrypt hash of a random value nobody knows (computed once)."""
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = get_password_hash(secrets.token_urlsafe(32))
    return _DUMMY_PASSWORD_HASH


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
            is_active=True,
            is_verified=False,
            is_admin=False,
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

    def create_with_sponsor(self, db: Session, obj_in: UserCreate, sponsor_code: Optional[str] = None,
                            before_commit=None, require_email_verification: bool = False) -> User:
        """Crée un utilisateur avec un parrain optionnel et le rôle 'user' par défaut.

        ``before_commit(db, user)`` runs inside the same transaction, after sponsor
        assignment and before commit, so registration safety state commits or
        rolls back together with the user.
        """
        # Générer un code de parrainage unique
        referral_code = self._generate_unique_referral_code(db)
        
        # Personal referral (validated); the sponsor itself is set by the central
        # sponsor-assignment service below, inside this same transaction.
        personal_sponsor = self.get_by_referral_code(db, sponsor_code) if sponsor_code else None
        
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
            is_active=True,
            is_verified=False,
            is_admin=False,
            avatar_url=obj_in.avatar_url,
            bio=obj_in.bio,
            first_name=obj_in.first_name,
            last_name=obj_in.last_name,
            continent=obj_in.continent,
            region=obj_in.region,
            country=obj_in.country,
            city=obj_in.city,
            personal_referral_code=referral_code,
            role_id=role_id,
            # Public registration passes True: the account cannot sign in
            # until its address is verified (see User.email_verification_required).
            email_verification_required=bool(require_email_verification),
        )
        dob = getattr(obj_in, "date_of_birth", None)
        if dob is not None:
            db_obj.date_of_birth = dob if isinstance(dob, datetime) else datetime(dob.year, dob.month, dob.day)
        db.add(db_obj)
        db.flush()

        from app.services.new_model_ledger import active_new_model_version
        from app.services.sponsor_assignment import PERSONAL_REFERRAL, assign_at_registration

        if active_new_model_version(db) is not None:
            # NEW_V2: a valid personal referral, else no sponsor (the Referral Pool is retired).
            assign_at_registration(db, db_obj, personal_sponsor)
        elif personal_sponsor and personal_sponsor.is_active is not False and personal_sponsor.is_deleted is not True:
            db_obj.sponsor_id = personal_sponsor.id
            db_obj.sponsor_source = PERSONAL_REFERRAL
        if before_commit is not None:
            before_commit(db, db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def set_sponsor(self, db: Session, user_id: int, sponsor_code: str) -> Optional[User]:
        """Définit le parrain d'un utilisateur via son code de parrainage."""
        user = self.get(db, user_id)
        if not user:
            return None
        
        sponsor = self.get_by_referral_code(db, sponsor_code)
        if not sponsor:
            return None

        from app.services.affiliate_hierarchy import AffiliateHierarchyError, validate_sponsor_assignment
        try:
            user = validate_sponsor_assignment(db, user_id=user_id, sponsor_id=sponsor.id)
        except AffiliateHierarchyError:
            db.rollback()
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
    
    def get_direct_referrals_detailed(
        self, db: Session, user_id: int,
        skip: int = 0, limit: int = 10,
        level_filter: int = None, status_filter: str = None,
        search_query: str = None, kyc_status_filter: str = None
    ) -> dict:
        """
        The member-facing affiliate list: ONLY the users whose direct sponsor is
        ``user_id`` (users.sponsor_id == user_id). Nothing below them is read,
        counted or returned, and a referral's own referral count is not exposed.
        """
        from app.services.affiliate_hierarchy import ACTIVE_AFFILIATE_LEVELS

        data = self._referral_listing(
            db, user_id, skip=skip, limit=limit, level_filter=level_filter,
            status_filter=status_filter, search_query=search_query,
            kyc_status_filter=kyc_status_filter, max_levels=ACTIVE_AFFILIATE_LEVELS,
        )
        for row in data["referrals"]:
            row.pop("referrals_count", None)
        return data

    def get_sponsor_tree_for_admin(
        self, db: Session, user_id: int,
        skip: int = 0, limit: int = 10,
        level_filter: int = None, status_filter: str = None,
        search_query: str = None, kyc_status_filter: str = None
    ) -> dict:
        """
        ADMIN / AUDIT ONLY: the stored sponsor tree below a user, up to the
        depth of the retired 10-level program. It describes historical
        relationships; it is not the active affiliate program (level 1 only)
        and must never be served to a member or used to compute commissions.
        """
        from app.services.affiliate_hierarchy import MAX_AFFILIATE_LEVELS

        return self._referral_listing(
            db, user_id, skip=skip, limit=limit, level_filter=level_filter,
            status_filter=status_filter, search_query=search_query,
            kyc_status_filter=kyc_status_filter, max_levels=MAX_AFFILIATE_LEVELS,
        )

    def _referral_listing(
        self, db: Session, user_id: int,
        skip: int = 0, limit: int = 10,
        level_filter: int = None, status_filter: str = None,
        search_query: str = None, kyc_status_filter: str = None,
        max_levels: int = 1,
    ) -> dict:
        """Referrals of ``user_id`` down to ``max_levels`` hops of users.sponsor_id."""
        from app.models.affiliate import AffiliateCommission, CommissionStatus
        from app.models.payment import Deposit, DepositStatus
        from app.models.kyc import KYCVerification, KYCStatus
        from sqlalchemy import func
        
        all_referrals = []
        
        def get_referrals_at_level(sponsor_ids: List[int], current_level: int):
            """Récupère les referrals d'un niveau donné"""
            if current_level > max_levels or not sponsor_ids:
                return [], []
            
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
        for level in range(1, max_levels + 1):
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
        
        if "date_of_birth" in update_data:
            # DOB changes are safety-relevant: only app.services.dob_service may apply them.
            raise ValueError("date_of_birth must be changed through dob_service")

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
            normalized_username = (username or "").strip()
            if not normalized_username:
                return None

            from sqlalchemy import func

            return db.query(User).filter(
                func.lower(User.username) == normalized_username.lower()
            ).first()
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
                # Spend the same time as a real password check, so the response
                # time does not tell an unknown identifier from a wrong password.
                verify_password(password, _dummy_password_hash())
                logger.debug("Authentication failed: unknown identifier")
                return None
            
            # Verify password
            if not verify_password(password, user.hashed_password):
                logger.debug("Authentication failed: invalid password (user %s)", user.id)
                return None
            
            logger.debug("Authentication successful (user %s)", user.id)
            return user
            
        except OperationalError as e:
            # Database connection error. Privacy: messages would carry the bound
            # login identifier, so only safe metadata is logged.
            logger.error("Database connection error during authentication: %s", describe_exception(e))
            logger.error("Please check your internet connection and DATABASE_URL configuration")
            # Re-raise to be handled by get_db() dependency
            raise
        except SQLAlchemyError as e:
            # Other database errors
            logger.error("Database error during authentication: %s\n%s", describe_exception(e), safe_traceback(e))
            # Re-raise to be handled by get_db() dependency
            raise
        except Exception as e:
            # Unexpected errors
            logger.error("Unexpected error during authentication: %s\n%s", describe_exception(e), safe_traceback(e))
            raise

    def is_active(self, user: User) -> bool:
        return user.is_active

    def is_admin(self, user: User) -> bool:
        return user.is_admin

    def reset_password(self, db: Session, user: User, new_password: str) -> User:
        """Réinitialiser le mot de passe d'un utilisateur.

        Goes through the one place that changes a password, so every earlier
        access token and reset link stops working with it."""
        from app.services import auth_security

        auth_security.set_password(db, user, new_password, action=auth_security.AUDIT_PASSWORD_CHANGED)
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
