"""
CRUD operations pour les invitations
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta

from app.models.invitation import Invitation, InvitationStatus


class CRUDInvitation:
    
    def create_invitation(
        self,
        db: Session,
        *,
        inviter_id: int,
        email: str,
        referral_code: str,
        message: Optional[str] = None,
        expires_days: int = 30
    ) -> Invitation:
        """Créer une nouvelle invitation"""
        db_obj = Invitation(
            inviter_id=inviter_id,
            email=email.lower(),
            referral_code=referral_code,
            message=message,
            status=InvitationStatus.PENDING,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=expires_days)
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_email_and_inviter(
        self,
        db: Session,
        *,
        email: str,
        inviter_id: int
    ) -> Optional[Invitation]:
        """Récupérer une invitation par email et inviteur"""
        return db.query(Invitation).filter(
            and_(
                Invitation.email == email.lower(),
                Invitation.inviter_id == inviter_id,
                Invitation.status == InvitationStatus.PENDING
            )
        ).first()
    
    def get_user_invitations(
        self,
        db: Session,
        *,
        user_id: int,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 10
    ) -> List[Invitation]:
        """Récupérer les invitations envoyées par un utilisateur"""
        query = db.query(Invitation).filter(Invitation.inviter_id == user_id)
        
        if status:
            query = query.filter(Invitation.status == status)
        
        return query.order_by(Invitation.sent_at.desc()).offset(skip).limit(limit).all()
    
    def get_pending_invitations(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 10
    ) -> List[Invitation]:
        """Récupérer les invitations en attente"""
        return self.get_user_invitations(
            db, user_id=user_id, status=InvitationStatus.PENDING, skip=skip, limit=limit
        )
    
    def get_accepted_invitations(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 10
    ) -> List[Invitation]:
        """Récupérer les invitations acceptées"""
        return self.get_user_invitations(
            db, user_id=user_id, status=InvitationStatus.ACCEPTED, skip=skip, limit=limit
        )
    
    def mark_as_accepted(
        self,
        db: Session,
        *,
        invitation_id: int,
        invited_user_id: int
    ) -> Optional[Invitation]:
        """Marquer une invitation comme acceptée"""
        invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
        if invitation:
            invitation.status = InvitationStatus.ACCEPTED
            invitation.accepted_at = datetime.utcnow()
            invitation.invited_user_id = invited_user_id
            db.commit()
            db.refresh(invitation)
        return invitation
    
    def mark_expired_invitations(self, db: Session) -> int:
        """Marquer les invitations expirées"""
        now = datetime.utcnow()
        result = db.query(Invitation).filter(
            and_(
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at < now
            )
        ).update({"status": InvitationStatus.EXPIRED})
        db.commit()
        return result
    
    def get_invitation_stats(
        self,
        db: Session,
        *,
        user_id: int
    ) -> dict:
        """Récupérer les statistiques d'invitation"""
        total = db.query(func.count(Invitation.id)).filter(
            Invitation.inviter_id == user_id
        ).scalar() or 0
        
        pending = db.query(func.count(Invitation.id)).filter(
            and_(
                Invitation.inviter_id == user_id,
                Invitation.status == InvitationStatus.PENDING
            )
        ).scalar() or 0
        
        accepted = db.query(func.count(Invitation.id)).filter(
            and_(
                Invitation.inviter_id == user_id,
                Invitation.status == InvitationStatus.ACCEPTED
            )
        ).scalar() or 0
        
        expired = db.query(func.count(Invitation.id)).filter(
            and_(
                Invitation.inviter_id == user_id,
                Invitation.status == InvitationStatus.EXPIRED
            )
        ).scalar() or 0
        
        conversion_rate = (accepted / total * 100) if total > 0 else 0.0
        
        return {
            "total_sent": total,
            "pending": pending,
            "accepted": accepted,
            "expired": expired,
            "conversion_rate": round(conversion_rate, 1)
        }
    
    def cancel_invitation(
        self,
        db: Session,
        *,
        invitation_id: int,
        user_id: int
    ) -> Optional[Invitation]:
        """Annuler une invitation"""
        invitation = db.query(Invitation).filter(
            and_(
                Invitation.id == invitation_id,
                Invitation.inviter_id == user_id,
                Invitation.status == InvitationStatus.PENDING
            )
        ).first()
        
        if invitation:
            invitation.status = InvitationStatus.CANCELLED
            db.commit()
            db.refresh(invitation)
        
        return invitation


invitation = CRUDInvitation()
