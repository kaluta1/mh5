"""
CRUD operations pour les logs de connexion
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime

from app.models.login_log import LoginLog


class CRUDLoginLog:
    
    def create(
        self,
        db: Session,
        *,
        obj_in: dict
    ) -> LoginLog:
        """Créer un nouveau log de connexion"""
        db_obj = LoginLog(
            user_id=obj_in["user_id"],
            ip_address=obj_in.get("ip_address"),
            user_agent=obj_in.get("user_agent"),
            device_info=obj_in.get("device_info"),
            location_info=obj_in.get("location_info"),
            login_at=obj_in.get("login_at", datetime.utcnow()),
            is_successful=obj_in.get("is_successful", True),
            failure_reason=obj_in.get("failure_reason")
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
    ) -> Optional[LoginLog]:
        """Récupérer un log par ID"""
        return db.query(LoginLog).filter(LoginLog.id == id).first()
    
    def get_by_user(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 10,
        successful_only: Optional[bool] = None
    ) -> List[LoginLog]:
        """Récupérer les logs d'un utilisateur"""
        query = db.query(LoginLog).filter(LoginLog.user_id == user_id)
        
        if successful_only is not None:
            query = query.filter(LoginLog.is_successful == successful_only)
        
        return query.order_by(desc(LoginLog.login_at)).offset(skip).limit(limit).all()
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 10,
        user_id: Optional[int] = None,
        is_successful: Optional[bool] = None,
        ip_address: Optional[str] = None
    ) -> List[LoginLog]:
        """Récupérer plusieurs logs avec filtres"""
        query = db.query(LoginLog)
        
        if user_id is not None:
            query = query.filter(LoginLog.user_id == user_id)
        
        if is_successful is not None:
            query = query.filter(LoginLog.is_successful == is_successful)
        
        if ip_address is not None:
            query = query.filter(LoginLog.ip_address == ip_address)
        
        return query.order_by(desc(LoginLog.login_at)).offset(skip).limit(limit).all()
    
    def get_recent_logins(
        self,
        db: Session,
        *,
        user_id: int,
        hours: int = 24
    ) -> List[LoginLog]:
        """Récupérer les connexions récentes d'un utilisateur (dernières X heures)"""
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        return db.query(LoginLog).filter(
            and_(
                LoginLog.user_id == user_id,
                LoginLog.login_at >= cutoff_time,
                LoginLog.is_successful == True
            )
        ).order_by(desc(LoginLog.login_at)).all()
    
    def get_last_login(
        self,
        db: Session,
        *,
        user_id: int
    ) -> Optional[LoginLog]:
        """Récupérer la dernière connexion réussie d'un utilisateur"""
        return db.query(LoginLog).filter(
            and_(
                LoginLog.user_id == user_id,
                LoginLog.is_successful == True
            )
        ).order_by(desc(LoginLog.login_at)).first()
    
    def count_by_user(
        self,
        db: Session,
        *,
        user_id: int,
        is_successful: Optional[bool] = None
    ) -> int:
        """Compter les logs d'un utilisateur"""
        query = db.query(LoginLog).filter(LoginLog.user_id == user_id)
        
        if is_successful is not None:
            query = query.filter(LoginLog.is_successful == is_successful)
        
        return query.count()
    
    def delete(
        self,
        db: Session,
        *,
        id: int
    ) -> LoginLog:
        """Supprimer un log"""
        obj = db.query(LoginLog).filter(LoginLog.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj
    
    def delete_old_logs(
        self,
        db: Session,
        *,
        days: int = 90
    ) -> int:
        """Supprimer les logs plus anciens que X jours"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted_count = db.query(LoginLog).filter(
            LoginLog.login_at < cutoff_date
        ).delete()
        
        db.commit()
        return deleted_count


crud_login_log = CRUDLoginLog()

