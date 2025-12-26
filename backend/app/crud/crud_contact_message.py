"""
CRUD operations pour les messages de contact
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from app.models.contact_message import ContactMessage


class CRUDContactMessage:
    
    def create(
        self,
        db: Session,
        *,
        obj_in: dict
    ) -> ContactMessage:
        """Créer un nouveau message de contact"""
        db_obj = ContactMessage(
            name=obj_in["name"],
            email=obj_in["email"].lower(),
            subject=obj_in["subject"],
            category=obj_in["category"],
            message=obj_in["message"],
            is_read=False,
            is_archived=False
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
    ) -> Optional[ContactMessage]:
        """Récupérer un message par ID"""
        return db.query(ContactMessage).filter(ContactMessage.id == id).first()
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        is_read: Optional[bool] = None,
        is_archived: Optional[bool] = None
    ) -> List[ContactMessage]:
        """Récupérer plusieurs messages avec filtres"""
        query = db.query(ContactMessage)
        
        if is_read is not None:
            query = query.filter(ContactMessage.is_read == is_read)
        
        if is_archived is not None:
            query = query.filter(ContactMessage.is_archived == is_archived)
        
        return query.order_by(desc(ContactMessage.created_at)).offset(skip).limit(limit).all()
    
    def update(
        self,
        db: Session,
        *,
        db_obj: ContactMessage,
        obj_in: dict
    ) -> ContactMessage:
        """Mettre à jour un message"""
        for field, value in obj_in.items():
            if value is not None:
                if field == "is_read" and value and not db_obj.is_read:
                    setattr(db_obj, "read_at", datetime.utcnow())
                setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(
        self,
        db: Session,
        *,
        id: int
    ) -> ContactMessage:
        """Supprimer un message"""
        obj = db.query(ContactMessage).filter(ContactMessage.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


crud_contact_message = CRUDContactMessage()

