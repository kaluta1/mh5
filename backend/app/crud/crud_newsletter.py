"""
CRUD operations pour les abonnements à la newsletter
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from app.models.newsletter import NewsletterSubscription


class CRUDNewsletter:
    
    def create(
        self,
        db: Session,
        *,
        obj_in: dict
    ) -> NewsletterSubscription:
        """Créer un nouvel abonnement à la newsletter"""
        # Vérifier si l'email existe déjà
        existing = db.query(NewsletterSubscription).filter(
            NewsletterSubscription.email == obj_in["email"].lower()
        ).first()
        
        if existing:
            # Si l'abonnement existe mais est désactivé, le réactiver
            if not existing.is_active:
                existing.is_active = True
                existing.device_info = obj_in.get("device_info")
                existing.location_info = obj_in.get("location_info")
                existing.unsubscribed_at = None
                db.commit()
                db.refresh(existing)
                return existing
            # Sinon, retourner l'existant
            return existing
        
        db_obj = NewsletterSubscription(
            email=obj_in["email"].lower(),
            device_info=obj_in.get("device_info"),
            location_info=obj_in.get("location_info"),
            is_active=True,
            is_verified=False
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get(
        self,
        db: Session,
        *,
        id: int
    ) -> Optional[NewsletterSubscription]:
        """Récupérer un abonnement par ID"""
        return db.query(NewsletterSubscription).filter(NewsletterSubscription.id == id).first()
    
    def get_by_email(
        self,
        db: Session,
        *,
        email: str
    ) -> Optional[NewsletterSubscription]:
        """Récupérer un abonnement par email"""
        return db.query(NewsletterSubscription).filter(
            NewsletterSubscription.email == email.lower()
        ).first()
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None
    ) -> List[NewsletterSubscription]:
        """Récupérer plusieurs abonnements avec filtres"""
        query = db.query(NewsletterSubscription)
        
        if is_active is not None:
            query = query.filter(NewsletterSubscription.is_active == is_active)
        
        if is_verified is not None:
            query = query.filter(NewsletterSubscription.is_verified == is_verified)
        
        return query.order_by(desc(NewsletterSubscription.created_at)).offset(skip).limit(limit).all()
    
    def update(
        self,
        db: Session,
        *,
        db_obj: NewsletterSubscription,
        obj_in: dict
    ) -> NewsletterSubscription:
        """Mettre à jour un abonnement"""
        for field, value in obj_in.items():
            if value is not None:
                if field == "is_verified" and value and not db_obj.is_verified:
                    setattr(db_obj, "verified_at", datetime.utcnow())
                elif field == "is_active" and not value and db_obj.is_active:
                    setattr(db_obj, "unsubscribed_at", datetime.utcnow())
                setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def unsubscribe(
        self,
        db: Session,
        *,
        email: str
    ) -> Optional[NewsletterSubscription]:
        """Désinscrire un utilisateur"""
        subscription = self.get_by_email(db, email=email)
        if subscription:
            subscription.is_active = False
            subscription.unsubscribed_at = datetime.utcnow()
            db.commit()
            db.refresh(subscription)
        return subscription
    
    def verify(
        self,
        db: Session,
        *,
        email: str
    ) -> Optional[NewsletterSubscription]:
        """Vérifier un abonnement"""
        subscription = self.get_by_email(db, email=email)
        if subscription:
            subscription.is_verified = True
            subscription.verified_at = datetime.utcnow()
            db.commit()
            db.refresh(subscription)
        return subscription
    
    def delete(
        self,
        db: Session,
        *,
        id: int
    ) -> NewsletterSubscription:
        """Supprimer un abonnement"""
        obj = db.query(NewsletterSubscription).filter(NewsletterSubscription.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


crud_newsletter = CRUDNewsletter()

