from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from datetime import datetime, timedelta

from app.models.user import User, UserStatus
from app.models.kyc import KYCVerification, KYCDocument, KYCAuditLog, KYCStatus, DocumentType
from app.schemas.kyc import (
    KYCVerificationCreate, KYCVerificationUpdate,
    KYCDocumentCreate, KYCDocumentUpdate,
    KYCAuditLogCreate, KYCStatistics
)


class CRUDKYCVerification:
    def get(self, db: Session, id: int) -> Optional[KYCVerification]:
        """Récupérer une vérification KYC par son ID"""
        return db.query(KYCVerification).filter(KYCVerification.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[KYCVerification]:
        """Récupérer plusieurs vérifications KYC"""
        return db.query(KYCVerification).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: KYCVerificationCreate) -> KYCVerification:
        """Créer une nouvelle vérification KYC"""
        db_obj = KYCVerification(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: KYCVerification, obj_in: KYCVerificationUpdate) -> KYCVerification:
        """Mettre à jour une vérification KYC"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> KYCVerification:
        """Supprimer une vérification KYC"""
        obj = db.query(KYCVerification).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_user(self, db: Session, *, user_id: int) -> Optional[KYCVerification]:
        """Récupérer la vérification KYC d'un utilisateur"""
        return db.query(KYCVerification).filter(
            KYCVerification.user_id == user_id
        ).order_by(desc(KYCVerification.submitted_at)).first()

    def get_by_reference(self, db: Session, *, reference_id: str) -> Optional[KYCVerification]:
        """Récupérer une vérification par référence externe"""
        return db.query(KYCVerification).filter(
            KYCVerification.reference_id == reference_id
        ).first()

    def get_by_external_id(self, db: Session, *, external_id: str) -> Optional[KYCVerification]:
        """Récupérer une vérification par ID externe du provider"""
        return db.query(KYCVerification).filter(
            KYCVerification.external_verification_id == external_id
        ).first()

    def get_by_status(self, db: Session, *, status: KYCStatus, skip: int = 0, limit: int = 10) -> List[KYCVerification]:
        """Récupérer les vérifications par statut"""
        return db.query(KYCVerification).filter(
            KYCVerification.status == status
        ).offset(skip).limit(limit).all()

    def get_pending_verifications(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[KYCVerification]:
        """Récupérer les vérifications en attente"""
        return db.query(KYCVerification).filter(
            KYCVerification.status.in_(
                [
                    KYCStatus.PENDING,
                    KYCStatus.IN_PROGRESS,
                    KYCStatus.PENDING_PROOF_OF_ADDRESS,
                    KYCStatus.REQUIRES_REVIEW,
                ]
            )
        ).order_by(KYCVerification.submitted_at).offset(skip).limit(limit).all()

    def get_expired_verifications(self, db: Session) -> List[KYCVerification]:
        """Récupérer les vérifications expirées"""
        now = datetime.utcnow()
        return db.query(KYCVerification).filter(
            and_(
                KYCVerification.expires_at < now,
                KYCVerification.status.in_([KYCStatus.PENDING, KYCStatus.IN_PROGRESS])
            )
        ).all()

    def mark_as_expired(self, db: Session, *, verification_id: int) -> KYCVerification:
        """Marquer une vérification comme expirée"""
        verification = self.get(db, verification_id)
        if verification:
            verification.status = KYCStatus.EXPIRED
            verification.processed_at = datetime.utcnow()
            db.commit()
            db.refresh(verification)
        return verification

    def apply_shufti_identity_accepted(
        self,
        db: Session,
        *,
        verification: KYCVerification,
        flags: Dict[str, bool],
        external_verification_id: Optional[str] = None,
        provider_response: Optional[str] = None,
        webhook_data: Optional[str] = None,
    ) -> KYCVerification:
        """Shufti ID+face passed — move to proof-of-address step; no revenue recognition yet."""
        verification.status = KYCStatus.PENDING_PROOF_OF_ADDRESS
        verification.identity_verified = bool(flags.get("identity_verified"))
        verification.document_verified = bool(flags.get("document_verified"))
        verification.face_verified = bool(flags.get("face_verified"))
        verification.address_verified = False
        if external_verification_id:
            verification.external_verification_id = external_verification_id
        if provider_response is not None:
            verification.provider_response = provider_response
        if webhook_data is not None:
            verification.webhook_data = webhook_data
        verification.processed_at = None

        u = db.query(User).filter(User.id == verification.user_id).first()
        if u:
            u.identity_verified = True
            u.address_verified = False

        db.add(verification)
        db.commit()
        db.refresh(verification)
        self._create_audit_log(
            db,
            verification.id,
            "shufti_identity_accepted",
            "Shufti ID+face accepted; proof of address required",
            None,
            False,
        )
        return verification

    def finalize_proof_of_address_auto(
        self, db: Session, *, verification_id: int, admin_user_id: Optional[int] = None
    ) -> KYCVerification:
        """Heuristic PoA passed — full KYC approved."""
        verification = self.get(db, verification_id)
        if not verification:
            return verification
        verification.status = KYCStatus.APPROVED
        verification.address_verified = True
        verification.processed_at = datetime.utcnow()

        u = db.query(User).filter(User.id == verification.user_id).first()
        if u:
            u.identity_verified = True
            u.address_verified = True
            u.verification_date = datetime.utcnow()
            if u.status == UserStatus.PENDING_VERIFICATION:
                u.status = UserStatus.ACTIVE

        db.add(verification)
        db.commit()
        db.refresh(verification)
        self._create_audit_log(
            db,
            verification_id,
            "proof_of_address_approved",
            "Proof of address validated (automatic)",
            admin_user_id,
            bool(admin_user_id),
        )
        return verification

    def approve_verification(self, db: Session, *, verification_id: int, admin_user_id: Optional[int] = None) -> KYCVerification:
        """Approuver une vérification KYC"""
        verification = self.get(db, verification_id)
        if verification:
            verification.status = KYCStatus.APPROVED
            verification.processed_at = datetime.utcnow()
            verification.address_verified = True
            verification.identity_verified = True

            # Mettre à jour le statut utilisateur
            if verification.user:
                verification.user.identity_verified = True
                verification.user.address_verified = True
                verification.user.verification_date = datetime.utcnow()
                if verification.user.status == UserStatus.PENDING_VERIFICATION:
                    verification.user.status = UserStatus.ACTIVE
            
            db.commit()
            db.refresh(verification)
            
            # Créer un log d'audit
            self._create_audit_log(
                db, verification_id, "approved", 
                "Vérification approuvée", 
                admin_user_id, True
            )
        
        return verification

    def reject_verification(self, db: Session, *, verification_id: int, reason: str, details: Optional[str] = None, admin_user_id: Optional[int] = None) -> KYCVerification:
        """Rejeter une vérification KYC"""
        verification = self.get(db, verification_id)
        if verification:
            verification.status = KYCStatus.REJECTED
            verification.rejection_reason = reason
            verification.rejection_details = details
            verification.processed_at = datetime.utcnow()
            verification.identity_verified = False
            verification.document_verified = False
            verification.face_verified = False
            verification.address_verified = False

            u = db.query(User).filter(User.id == verification.user_id).first()
            if u:
                u.identity_verified = False
                u.address_verified = False

            db.commit()
            db.refresh(verification)
            
            # Créer un log d'audit
            self._create_audit_log(
                db, verification_id, "rejected", 
                f"Vérification rejetée: {reason}", 
                admin_user_id, True
            )
        
        return verification

    def get_statistics(self, db: Session, *, days: int = 30) -> KYCStatistics:
        """Récupérer les statistiques KYC"""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Compter les vérifications par statut
        total = db.query(KYCVerification).filter(
            KYCVerification.submitted_at >= since_date
        ).count()
        
        pending = db.query(KYCVerification).filter(
            and_(
                KYCVerification.submitted_at >= since_date,
                KYCVerification.status.in_(
                    [
                        KYCStatus.PENDING,
                        KYCStatus.IN_PROGRESS,
                        KYCStatus.PENDING_PROOF_OF_ADDRESS,
                        KYCStatus.REQUIRES_REVIEW,
                    ]
                ),
            )
        ).count()
        
        approved = db.query(KYCVerification).filter(
            and_(
                KYCVerification.submitted_at >= since_date,
                KYCVerification.status == KYCStatus.APPROVED
            )
        ).count()
        
        rejected = db.query(KYCVerification).filter(
            and_(
                KYCVerification.submitted_at >= since_date,
                KYCVerification.status == KYCStatus.REJECTED
            )
        ).count()
        
        # Calculer le taux d'approbation
        processed = approved + rejected
        approval_rate = (approved / processed * 100) if processed > 0 else 0
        
        # Calculer le temps moyen de traitement
        avg_processing_time = db.query(
            func.avg(
                func.extract('epoch', KYCVerification.processed_at - KYCVerification.submitted_at) / 3600
            )
        ).filter(
            and_(
                KYCVerification.submitted_at >= since_date,
                KYCVerification.processed_at.isnot(None)
            )
        ).scalar()
        
        return KYCStatistics(
            total_verifications=total,
            pending_verifications=pending,
            approved_verifications=approved,
            rejected_verifications=rejected,
            approval_rate=approval_rate,
            average_processing_time_hours=avg_processing_time
        )

    def _create_audit_log(self, db: Session, verification_id: int, action: str, details: str, user_id: Optional[int] = None, is_admin: bool = False):
        """Créer un log d'audit"""
        audit_log = KYCAuditLog(
            verification_id=verification_id,
            action=action,
            details=details,
            performed_by_user_id=user_id,
            performed_by_admin=is_admin,
            timestamp=datetime.utcnow()
        )
        db.add(audit_log)
        db.commit()


class CRUDKYCDocument:
    def get(self, db: Session, id: int) -> Optional[KYCDocument]:
        """Récupérer un document KYC par son ID"""
        return db.query(KYCDocument).filter(KYCDocument.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[KYCDocument]:
        """Récupérer plusieurs documents KYC"""
        return db.query(KYCDocument).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: KYCDocumentCreate) -> KYCDocument:
        """Créer un nouveau document KYC"""
        db_obj = KYCDocument(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: KYCDocument, obj_in: KYCDocumentUpdate) -> KYCDocument:
        """Mettre à jour un document KYC"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> KYCDocument:
        """Supprimer un document KYC"""
        obj = db.query(KYCDocument).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_verification(self, db: Session, *, verification_id: int) -> List[KYCDocument]:
        """Récupérer les documents d'une vérification"""
        return db.query(KYCDocument).filter(
            KYCDocument.verification_id == verification_id
        ).all()

    def get_by_type(self, db: Session, *, verification_id: int, document_type: DocumentType) -> Optional[KYCDocument]:
        """Récupérer un document par type"""
        return db.query(KYCDocument).filter(
            and_(
                KYCDocument.verification_id == verification_id,
                KYCDocument.document_type == document_type
            )
        ).first()


class CRUDKYCAuditLog:
    def get(self, db: Session, id: int) -> Optional[KYCAuditLog]:
        """Récupérer un log d'audit par son ID"""
        return db.query(KYCAuditLog).filter(KYCAuditLog.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[KYCAuditLog]:
        """Récupérer plusieurs logs d'audit"""
        return db.query(KYCAuditLog).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: KYCAuditLogCreate) -> KYCAuditLog:
        """Créer un nouveau log d'audit"""
        db_obj = KYCAuditLog(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_verification(self, db: Session, *, verification_id: int) -> List[KYCAuditLog]:
        """Récupérer les logs d'une vérification"""
        return db.query(KYCAuditLog).filter(
            KYCAuditLog.verification_id == verification_id
        ).order_by(desc(KYCAuditLog.timestamp)).all()

    def get_by_user(self, db: Session, *, user_id: int, skip: int = 0, limit: int = 10) -> List[KYCAuditLog]:
        """Récupérer les logs d'un utilisateur"""
        return db.query(KYCAuditLog).filter(
            KYCAuditLog.performed_by_user_id == user_id
        ).order_by(desc(KYCAuditLog.timestamp)).offset(skip).limit(limit).all()


# Instances CRUD
kyc_verification = CRUDKYCVerification()
kyc_document = CRUDKYCDocument()
kyc_audit_log = CRUDKYCAuditLog()
