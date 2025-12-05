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
        # Création des rôles par défaut
        create_default_roles(db)
        
        # Création de l'administrateur par défaut
        create_admin_user(db)
        
        # Création des templates de concours par défaut
        create_default_contest_templates(db)
        
        # Création des localisations de base
        create_base_locations(db)
        
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
        admin_email = "admin@myfav.com"
        admin = crud_user.get_by_email(db, email=admin_email)
        
        if not admin:
            user_in = UserCreate(
                email=admin_email,
                password="admin123",  # À changer en production !
                full_name="Admin MyFav",
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
        from app.models.contest import Location
        
        # Création des continents
        continents = [
            {"name": "Afrique", "level": "continent"},
            {"name": "Asie", "level": "continent"},
            {"name": "Europe", "level": "continent"},
            {"name": "Amérique du Nord", "level": "continent"},
            {"name": "Amérique du Sud", "level": "continent"},
            {"name": "Océanie", "level": "continent"},
            {"name": "Antarctique", "level": "continent"}
        ]
        
        for continent_data in continents:
            continent = db.query(Location).filter(
                Location.name == continent_data["name"],
                Location.level == "continent"
            ).first()
            
            if not continent:
                continent = Location(**continent_data)
                db.add(continent)
                logger.info(f"Continent '{continent_data['name']}' créé")
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur lors de la création des continents: {e}")


if __name__ == "__main__":
    logger.info("Création des données initiales")
    init_db()
    logger.info("Données initiales créées")
