from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class VerificationType(str, enum.Enum):
    SELFIE = "selfie"
    SELFIE_WITH_PET = "selfie_with_pet"
    SELFIE_WITH_DOCUMENT = "selfie_with_document"
    VOICE = "voice"
    VIDEO = "video"
    BRAND = "brand"
    CONTENT = "content"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MediaType(str, enum.Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class UserVerification(Base):
    """Modèle pour les vérifications utilisateur (selfie, voix, vidéo, etc.)"""
    __tablename__ = "user_verifications"
    
    # Utilisateur
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Type de vérification
    verification_type: Mapped[str] = mapped_column(
        SQLEnum(VerificationType, name="user_verification_type", create_constraint=False),
        nullable=False,
        index=True
    )
    
    # Média
    media_url: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(
        SQLEnum(MediaType, name="verification_media_type", create_constraint=False),
        nullable=False
    )
    media_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Clé Uploadthing
    
    # Métadonnées du fichier
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Statut
    status: Mapped[str] = mapped_column(
        SQLEnum(VerificationStatus, name="user_verification_status", create_constraint=False),
        nullable=False,
        default=VerificationStatus.PENDING,
        index=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Contexte optionnel (concours, contestant)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id", ondelete="SET NULL"), nullable=True)
    contestant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contestants.id", ondelete="SET NULL"), nullable=True)
    
    # Révision admin
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], backref="verifications")
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])
