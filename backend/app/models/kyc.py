from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum as SQLEnum, Text, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REQUIRES_REVIEW = "requires_review"


class DocumentType(str, enum.Enum):
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"
    UTILITY_BILL = "utility_bill"
    BANK_STATEMENT = "bank_statement"
    SELFIE = "selfie"
    ADDRESS_PROOF = "address_proof"


class VerificationProvider(str, enum.Enum):
    SHUFTI_PRO = "shufti_pro"
    JUMIO = "jumio"
    ONFIDO = "onfido"
    MANUAL = "manual"


class KYCVerification(Base):
    __tablename__ = "kyc_verifications"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Statut de vérification
    status: Mapped[KYCStatus] = mapped_column(SQLEnum(KYCStatus), default=KYCStatus.PENDING)
    provider: Mapped[VerificationProvider] = mapped_column(SQLEnum(VerificationProvider), default=VerificationProvider.SHUFTI_PRO)
    
    # Identifiants externes
    external_verification_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Informations personnelles vérifiées
    verified_first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verified_nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Résultats de vérification
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    address_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    document_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    face_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Scores de confiance (0-100)
    identity_confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_confidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    face_match_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Raisons de rejet
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Métadonnées
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Données brutes du provider
    provider_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="kyc_verifications")
    documents: Mapped[List["KYCDocument"]] = relationship("KYCDocument", back_populates="verification")


class KYCDocument(Base):
    __tablename__ = "kyc_documents"
    verification_id: Mapped[int] = mapped_column(Integer, ForeignKey("kyc_verifications.id"), nullable=False)
    
    # Type et informations du document
    document_type: Mapped[DocumentType] = mapped_column(SQLEnum(DocumentType), nullable=False)
    document_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    issuing_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Fichiers
    front_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    back_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    selfie_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Statut de vérification du document
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Métadonnées
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    verification: Mapped["KYCVerification"] = relationship("KYCVerification", back_populates="documents")


class KYCAuditLog(Base):
    __tablename__ = "kyc_audit_logs"
    verification_id: Mapped[int] = mapped_column(Integer, ForeignKey("kyc_verifications.id"), nullable=False)
    
    # Action et détails
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # submitted, approved, rejected, etc.
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Utilisateur qui a effectué l'action
    performed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    performed_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Métadonnées
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Relations
    verification: Mapped["KYCVerification"] = relationship("KYCVerification")
    performed_by: Mapped[Optional["User"]] = relationship("User")
