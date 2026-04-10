import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.crud import user as crud_user
from app.schemas.user import UserCreate
from app.models.user import Role

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db() -> None:
    db = SessionLocal()
    try:
        # Plan comptable first: payment_accounting / admin COA must not be skipped if a later
        # step (roles, admin, products) fails or partially commits.
        try:
            ensure_chart_of_accounts(db)
        except Exception as e:
            logger.warning("ensure_chart_of_accounts (init): %s", e)

        # Création des rôles par défaut
        create_default_roles(db)

        # Création de l'administrateur par défaut
        create_admin_user(db)

        # Création des templates de concours par défaut
        create_default_contest_templates(db)

        # Création des localisations de base
        create_base_locations(db)

        # Création des types de produits avec commissions
        create_product_types(db)

    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
        raise
    finally:
        db.close()


def create_default_roles(db: Session) -> None:
    """Crée les rôles par défaut dans la base de données"""
    try:
        # Rôles standard
        roles = [
            {"name": "admin", "description": "Administrateur avec tous les droits"},
            {"name": "moderator", "description": "Modérateur de contenu"},
            {"name": "user", "description": "Utilisateur standard"}
        ]
        
        for role_data in roles:
            role = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not role:
                role = Role(**role_data)
                db.add(role)
                logger.info(f"Rôle '{role_data['name']}' créé")
        
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Les rôles existent déjà")


def create_admin_user(db: Session) -> None:
    """Crée un utilisateur administrateur par défaut"""
    try:
        admin_email = "infos@myhigh5.com"
        admin = crud_user.get_by_email(db, email=admin_email)
        
        if not admin:
            # Vérifier aussi si le username 'admin' existe déjà
            existing_user_by_name = crud_user.get_by_username(db, username="admin")
            if existing_user_by_name:
                logger.warning(f"L'utilisateur avec le username 'admin' existe déjà (ID: {existing_user_by_name.id}). Mise à jour de l'email si nécessaire ou saut de la création.")
                # Optionnel: on pourrait mettre à jour l'utilisateur ici, mais pour l'instant on log juste et on évite le crash
                if existing_user_by_name.email != admin_email:
                    logger.warning(f"Attention: Le compte 'admin' a un email différent: {existing_user_by_name.email}")
                return

            user_in = UserCreate(
                email=admin_email,
                password="admin123",  # À changer en production !
                full_name="Admin MyHigh5",
                username="admin",
                is_active=True,
                is_verified=True,
                is_admin=True
            )
            admin = crud_user.create(db, obj_in=user_in)
            logger.info(f"Utilisateur admin créé avec l'email: {admin_email}")
            
            # Ajout du rôle admin
            crud_user.add_user_role(db, user_id=admin.id, role_name="admin")
        else:
            logger.info(f"L'utilisateur admin ({admin_email}) existe déjà")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de l'utilisateur admin: {e}")


def create_default_contest_templates(db: Session) -> None:
    """Crée les templates de concours par défaut"""
    try:
        from app.models.contest import ContestTemplate
        
        templates = [
            {
                "name": "Beauty Contest",
                "description": "Concours de beauté avec restrictions géographiques",
                "contest_type": "beauty",
                "has_geo_restrictions": True,
                "has_gender_restrictions": True,
                "default_submission_days": 60,
                "default_voting_days": 60
            },
            {
                "name": "Handsome Contest",
                "description": "Concours pour hommes avec restrictions géographiques",
                "contest_type": "handsome",
                "has_geo_restrictions": True,
                "has_gender_restrictions": True,
                "default_submission_days": 60,
                "default_voting_days": 60
            },
            {
                "name": "Latest Hits",
                "description": "Concours de musique sans restriction géographique",
                "contest_type": "latest_hits",
                "has_geo_restrictions": False,
                "has_gender_restrictions": False,
                "default_submission_days": 30,
                "default_voting_days": 30
            }
        ]
        
        for template_data in templates:
            template = db.query(ContestTemplate).filter(
                ContestTemplate.name == template_data["name"]
            ).first()
            
            if not template:
                template = ContestTemplate(**template_data)
                db.add(template)
                logger.info(f"Template de concours '{template_data['name']}' créé")
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur lors de la création des templates de concours: {e}")


def create_base_locations(db: Session) -> None:
    """Crée les localisations de base (continents)"""
    try:
        from app.models.contest import Location, LocationLevel
        
        # Création des continents
        continents = [
            {"name": "Afrique", "level": LocationLevel.CONTINENT},
            {"name": "Asie", "level": LocationLevel.CONTINENT},
            {"name": "Europe", "level": LocationLevel.CONTINENT},
            {"name": "Amérique du Nord", "level": LocationLevel.CONTINENT},
            {"name": "Amérique du Sud", "level": LocationLevel.CONTINENT},
            {"name": "Océanie", "level": LocationLevel.CONTINENT},
            {"name": "Antarctique", "level": LocationLevel.CONTINENT}
        ]
        
        for continent_data in continents:
            continent = db.query(Location).filter(
                Location.name == continent_data["name"],
                Location.level == LocationLevel.CONTINENT
            ).first()
            
            if not continent:
                continent = Location(**continent_data)
                db.add(continent)
                logger.info(f"Continent '{continent_data['name']}' créé")
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur lors de la création des continents: {e}")


def create_product_types(db: Session) -> None:
    """Crée les types de produits avec configuration des commissions d'affiliation"""
    try:
        from app.models.payment import ProductType
        
        product_types = [
            # ============================================
            # FOUNDING MEMBERS
            # ============================================
            {
                "code": "founding_membership",
                "name": "Founding Membership",
                "description": "Adhésion au programme Founding Members (100$). Donne accès au pool mensuel et annuel.",
                "price": 100.00,
                "currency": "USD",
                "validity_days": 0,  # One-time fee
                "is_active": True,
                "is_consumable": False,
                "has_affiliate_commission": True,
                "affiliate_direct_amount": 20.00,   # 20$ par parrainage direct
                "affiliate_indirect_amount": 2.00,  # 2$ par parrainage indirect (N2-10)
            },
            {
                "code": "annual_membership",
                "name": "Annual Membership Fee",
                "description": "Cotisation annuelle des Founding Members (50$/an) pour maintenir le statut.",
                "price": 50.00,
                "currency": "USD",
                "validity_days": 365,
                "is_active": True,
                "is_consumable": False,
                "has_affiliate_commission": True,
                "affiliate_direct_amount": 10.00,   # 10$ par parrainage direct
                "affiliate_indirect_amount": 1.00,  # 1$ par parrainage indirect (N2-10)
            },
            # ============================================
            # KYC
            # ============================================
            {
                "code": "kyc",
                "name": "KYC Verification",
                "description": "Vérification d'identité KYC",
                "price": 10.00,
                "currency": "USD",
                "validity_days": 0,
                "is_active": True,
                "is_consumable": True,
                "has_affiliate_commission": True,
                "affiliate_direct_rate": 0.20,      # 20% du montant
                "affiliate_indirect_rate": 0.02,    # 2% du montant (N2-10)
            },
            # ============================================
            # EFM (Enhanced Features Membership)
            # ============================================
            {
                "code": "efm_membership",
                "name": "EFM Membership",
                "description": "Abonnement aux fonctionnalités avancées",
                "price": 9.99,
                "currency": "USD",
                "validity_days": 30,
                "is_active": True,
                "is_consumable": False,
                "has_affiliate_commission": True,
                "affiliate_direct_rate": 0.20,      # 20% du montant
                "affiliate_indirect_rate": 0.02,    # 2% du montant (N2-10)
            },
            # ============================================
            # CLUB MEMBERSHIP
            # ============================================
            {
                "code": "club_membership",
                "name": "Club Membership",
                "description": "Abonnement à un club",
                "price": 4.99,
                "currency": "USD",
                "validity_days": 30,
                "is_active": True,
                "is_consumable": False,
                "has_affiliate_commission": True,
                "affiliate_direct_rate": 0.20,      # 20% du montant
                "affiliate_indirect_rate": 0.02,    # 2% du montant (N2-10)
            },
            # ============================================
            # CONTEST PARTICIPATION
            # ============================================
            {
                "code": "contest_participation",
                "name": "Contest Participation",
                "description": "Participation à un concours payant",
                "price": 5.00,
                "currency": "USD",
                "validity_days": 0,
                "is_active": True,
                "is_consumable": True,
                "has_affiliate_commission": True,
                "affiliate_direct_rate": 0.20,      # 20% du montant
                "affiliate_indirect_rate": 0.02,    # 2% du montant (N2-10)
            },
            # ============================================
            # SHOP PURCHASE
            # ============================================
            {
                "code": "shop_purchase",
                "name": "Shop Purchase",
                "description": "Achat en boutique",
                "price": 0.00,  # Variable selon le produit
                "currency": "USD",
                "validity_days": 0,
                "is_active": True,
                "is_consumable": True,
                "has_affiliate_commission": True,
                "affiliate_direct_rate": 0.20,      # 20% du montant
                "affiliate_indirect_rate": 0.02,    # 2% du montant (N2-10)
            },
        ]
        
        for product_data in product_types:
            product = db.query(ProductType).filter(
                ProductType.code == product_data["code"]
            ).first()
            
            if not product:
                product = ProductType(**product_data)
                db.add(product)
                logger.info(f"Type de produit '{product_data['code']}' créé avec commissions")
            else:
                # Mise à jour des commissions si le produit existe déjà
                for key, value in product_data.items():
                    if key.startswith("affiliate_") or key == "has_affiliate_commission":
                        setattr(product, key, value)
                logger.info(f"Commissions mises à jour pour '{product_data['code']}'")
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur lors de la création des types de produits: {e}")


def ensure_chart_of_accounts(db: Session) -> None:
    """Crée les comptes 1001, 4001, etc. si absents. Sans cela, les journaux de paiement échouent."""
    try:
        from sqlalchemy import inspect

        bind = db.get_bind()
        insp = inspect(bind)
        if not insp.has_table("chart_of_accounts"):
            logger.warning("Table chart_of_accounts absente — saut de l'init plan comptable")
            return

        from app.scripts.init_coa import init_chart_of_accounts

        init_chart_of_accounts(db)
    except Exception as e:
        msg = str(e)
        if "must be owner" in msg or "InsufficientPrivilege" in msg:
            logger.error(
                "Chart of accounts: le rôle PostgreSQL n'est pas propriétaire de chart_of_accounts — "
                "les ALTER TABLE échouent. Exécutez une fois en superuser / propriétaire (Neon: SQL Editor avec un rôle admin) "
                "le fichier backend/scripts/sql/fix_accounting_schema_privileged.sql, ou: "
                "ALTER TABLE chart_of_accounts OWNER TO <votre_role_app>; puis relancez ensure_chart_of_accounts."
            )
        logger.warning("Chart of accounts non initialisé: %s", e)


if __name__ == "__main__":
    logger.info("Création des données initiales")
    init_db()
    logger.info("Données initiales créées")
