from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum as SQLEnum, Text, Boolean, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    # Shufti (ID+face) accepted; user must upload proof of address.
    PENDING_PROOF_OF_ADDRESS = "pending_proof_of_address"
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
    KALUTA = "kaluta"
    SHUFTI_PRO = "shufti_pro"  # legacy — set KYC_PROVIDER=shufti_pro to use
    JUMIO = "jumio"
    ONFIDO = "onfido"
    MANUAL = "manual"


class KYCVerification(Base):
    __tablename__ = "kyc_verifications"
    
    # Un seul enregistrement KYC par utilisateur (contrainte unique)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Statut de vérification
    status: Mapped[KYCStatus] = mapped_column(SQLEnum(KYCStatus), default=KYCStatus.PENDING)
    provider: Mapped[VerificationProvider] = mapped_column(SQLEnum(VerificationProvider), default=VerificationProvider.KALUTA)
    
    # Identifiants externes
    external_verification_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verification_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # URL Shufti Pro pour réutiliser
    
    # Nombre de tentatives (max 3)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    # Provider sessions opened for the CURRENT attempt (a session that ran out is
    # replaced inside the same attempt, up to a limit: each one may be charged to
    # MyHigh5 by the provider). Granted = extra sessions an administrator allowed.
    # Both go back to 0 when a new attempt starts.
    attempt_sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempt_sessions_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Informations personnelles vérifiées
    verified_first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verified_nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    residential_address_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
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


class KycSettings(Base):
    """KYC provider settings an administrator changes in the Admin Panel (one
    row, id = 1). The Kaluta API key and webhook secret are NOT here: they are
    kept as AES-256-GCM ciphertext in payment_credentials (provider "kaluta").
    NULL = not set in the Admin Panel; the server environment then decides."""
    __tablename__ = "kyc_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_kyc_settings_single_row"),)

    kaluta_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Incremented by every accepted change: a change made on a stale page is refused.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)


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
