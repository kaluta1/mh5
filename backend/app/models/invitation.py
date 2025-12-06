"""
Modèle pour les invitations de parrainage
"""
from typing import Optional
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from app.db.base_class import Base


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"      # En attente
    ACCEPTED = "accepted"    # Acceptée (inscrit)
    EXPIRED = "expired"      # Expirée
    CANCELLED = "cancelled"  # Annulée


class Invitation(Base):
    """Invitation de parrainage par email"""
    __tablename__ = "invitations"
    
    # Utilisateur qui envoie l'invitation
    inviter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Email du destinataire
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Message personnalisé (optionnel)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Code de parrainage utilisé
    referral_code: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Statut de l'invitation
    status: Mapped[InvitationStatus] = mapped_column(
        String(20), 
        default=InvitationStatus.PENDING,
        nullable=False
    )
    
    # Dates
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Utilisateur créé suite à l'invitation (si acceptée)
    invited_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("users.id"), 
        nullable=True
    )
    
    # Relations
    inviter: Mapped["User"] = relationship("User", foreign_keys=[inviter_id])
    invited_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_user_id])
    
    def __repr__(self):
        return f"<Invitation {self.id}: {self.email} by user {self.inviter_id}>"
