from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.notification import Notification, NotificationType


class CRUDNotification:
    """CRUD operations for Notification model"""
    
    def create(
        self,
        db: Session,
        *,
        user_id: int,
        type: NotificationType,
        title: str,
        message: str,
        related_contestant_id: Optional[int] = None,
        related_comment_id: Optional[int] = None,
        related_contest_id: Optional[int] = None
    ) -> Notification:
        """Crée une nouvelle notification"""
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            related_contestant_id=related_contestant_id,
            related_comment_id=related_comment_id,
            related_contest_id=related_contest_id,
            is_read=False
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification
    
    def get_user_notifications(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False
    ) -> List[Notification]:
        """Récupère les notifications d'un utilisateur"""
        query = db.query(Notification).filter(Notification.user_id == user_id)
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        return query.order_by(Notification.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def mark_as_read(
        self,
        db: Session,
        notification_id: int,
        user_id: int
    ) -> Optional[Notification]:
        """Marque une notification comme lue"""
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        
        if notification:
            notification.is_read = True
            db.commit()
            db.refresh(notification)
        
        return notification
    
    def mark_all_as_read(
        self,
        db: Session,
        user_id: int
    ) -> int:
        """Marque toutes les notifications d'un utilisateur comme lues"""
        count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        
        db.commit()
        return count
    
    def get_unread_count(
        self,
        db: Session,
        user_id: int
    ) -> int:
        """Compte le nombre de notifications non lues pour un utilisateur"""
        return db.query(func.count(Notification.id))\
            .filter(
                Notification.user_id == user_id,
                Notification.is_read == False
            )\
            .scalar() or 0


# Instance globale
crud_notification = CRUDNotification()

