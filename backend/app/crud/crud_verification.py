from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime

from app.models.verification import UserVerification, VerificationType, VerificationStatus
from app.schemas.verification import VerificationCreate, VerificationUpdate


class CRUDVerification:
    """CRUD operations for user verifications"""
    
    def create(self, db: Session, user_id: int, verification_in: VerificationCreate) -> UserVerification:
        """Créer une nouvelle vérification"""
        db_verification = UserVerification(
            user_id=user_id,
            verification_type=verification_in.verification_type.value,
            media_url=verification_in.media_url,
            media_type=verification_in.media_type.value,
            duration_seconds=verification_in.duration_seconds,
            file_size_bytes=verification_in.file_size_bytes,
            contest_id=verification_in.contest_id,
            contestant_id=verification_in.contestant_id,
            status=VerificationStatus.PENDING.value
        )
        db.add(db_verification)
        db.commit()
        db.refresh(db_verification)
        return db_verification
    
    def get(self, db: Session, verification_id: int) -> Optional[UserVerification]:
        """Récupérer une vérification par ID"""
        return db.query(UserVerification).filter(UserVerification.id == verification_id).first()
    
    def get_by_user(self, db: Session, user_id: int, verification_type: Optional[str] = None) -> List[UserVerification]:
        """Récupérer les vérifications d'un utilisateur"""
        query = db.query(UserVerification).filter(UserVerification.user_id == user_id)
        if verification_type:
            query = query.filter(UserVerification.verification_type == verification_type)
        return query.order_by(desc(UserVerification.created_at)).all()
    
    def get_latest_by_user_and_type(
        self, db: Session, user_id: int, verification_type: str
    ) -> Optional[UserVerification]:
        """Récupérer la dernière vérification d'un type pour un utilisateur"""
        return db.query(UserVerification).filter(
            and_(
                UserVerification.user_id == user_id,
                UserVerification.verification_type == verification_type
            )
        ).order_by(desc(UserVerification.created_at)).first()
    
    def get_user_verification_status(self, db: Session, user_id: int) -> dict:
        """Récupérer le statut de toutes les vérifications d'un utilisateur"""
        verifications = self.get_by_user(db, user_id)
        
        result = {
            "has_selfie": False,
            "has_voice": False,
            "has_video": False,
            "selfie_status": None,
            "voice_status": None,
            "video_status": None,
            "selfie_url": None,
            "voice_url": None,
            "video_url": None,
            "has_brand": False,
            "has_content": False,
            "brand_status": None,
            "content_status": None,
            "brand_url": None,
            "content_url": None,
        }
        
        for v in verifications:
            if v.verification_type in [VerificationType.SELFIE.value, 
                                        VerificationType.SELFIE_WITH_PET.value,
                                        VerificationType.SELFIE_WITH_DOCUMENT.value]:
                if not result["has_selfie"] or v.status == VerificationStatus.APPROVED.value:
                    result["has_selfie"] = True
                    result["selfie_status"] = v.status
                    result["selfie_url"] = v.media_url
            elif v.verification_type == VerificationType.VOICE.value:
                if not result["has_voice"] or v.status == VerificationStatus.APPROVED.value:
                    result["has_voice"] = True
                    result["voice_status"] = v.status
                    result["voice_url"] = v.media_url
            elif v.verification_type == VerificationType.VIDEO.value:
                if not result["has_video"] or v.status == VerificationStatus.APPROVED.value:
                    result["has_video"] = True
                    result["video_status"] = v.status
                    result["video_url"] = v.media_url
        
        return result
    
    def update_status(
        self, 
        db: Session, 
        verification_id: int, 
        status: VerificationStatus,
        reviewed_by: int,
        rejection_reason: Optional[str] = None
    ) -> Optional[UserVerification]:
        """Mettre à jour le statut d'une vérification (admin)"""
        verification = self.get(db, verification_id)
        if not verification:
            return None
        
        verification.status = status.value
        verification.reviewed_by = reviewed_by
        verification.reviewed_at = datetime.utcnow()
        if rejection_reason:
            verification.rejection_reason = rejection_reason
        
        db.commit()
        db.refresh(verification)
        return verification
    
    def get_pending(self, db: Session, skip: int = 0, limit: int = 50) -> List[UserVerification]:
        """Récupérer les vérifications en attente (admin)"""
        return db.query(UserVerification).filter(
            UserVerification.status == VerificationStatus.PENDING.value
        ).order_by(UserVerification.created_at).offset(skip).limit(limit).all()
    
    def count_pending(self, db: Session) -> int:
        """Compter les vérifications en attente"""
        return db.query(UserVerification).filter(
            UserVerification.status == VerificationStatus.PENDING.value
        ).count()
    
    def delete(self, db: Session, verification_id: int) -> bool:
        """Supprimer une vérification"""
        verification = self.get(db, verification_id)
        if not verification:
            return False
        db.delete(verification)
        db.commit()
        return True


verification_crud = CRUDVerification()
