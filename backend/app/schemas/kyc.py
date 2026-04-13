from typing import Optional, List
from pydantic import BaseModel, Field, validator, ConfigDict
from datetime import datetime
from enum import Enum

from app.models.kyc import KYCStatus, DocumentType, VerificationProvider


# Schémas de base
class KYCVerificationBase(BaseModel):
    status: Optional[KYCStatus] = KYCStatus.PENDING
    provider: Optional[VerificationProvider] = VerificationProvider.SHUFTI_PRO
    reference_id: Optional[str] = None
    verified_first_name: Optional[str] = None
    verified_last_name: Optional[str] = None
    verified_date_of_birth: Optional[datetime] = None
    verified_nationality: Optional[str] = None
    verified_address: Optional[str] = None


class KYCVerificationCreate(KYCVerificationBase):
    user_id: int
    
    class Config:
        from_attributes = True


class KYCVerificationUpdate(BaseModel):
    status: Optional[KYCStatus] = None
    external_verification_id: Optional[str] = None
    verification_url: Optional[str] = None
    residential_address_locked_at: Optional[datetime] = None
    verified_first_name: Optional[str] = None
    verified_last_name: Optional[str] = None
    verified_date_of_birth: Optional[datetime] = None
    verified_nationality: Optional[str] = None
    verified_address: Optional[str] = None
    identity_verified: Optional[bool] = None
    address_verified: Optional[bool] = None
    document_verified: Optional[bool] = None
    face_verified: Optional[bool] = None
    identity_confidence_score: Optional[int] = Field(None, ge=0, le=100)
    document_confidence_score: Optional[int] = Field(None, ge=0, le=100)
    face_match_score: Optional[int] = Field(None, ge=0, le=100)
    rejection_reason: Optional[str] = None
    rejection_details: Optional[str] = None
    processed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    provider_response: Optional[str] = None
    webhook_data: Optional[str] = None
    
    class Config:
        from_attributes = True


class KYCVerification(KYCVerificationBase):
    id: int
    user_id: int
    external_verification_id: Optional[str] = None
    residential_address_locked_at: Optional[datetime] = None
    identity_verified: bool = False
    address_verified: bool = False
    document_verified: bool = False
    face_verified: bool = False
    identity_confidence_score: Optional[int] = None
    document_confidence_score: Optional[int] = None
    face_match_score: Optional[int] = None
    rejection_reason: Optional[str] = None
    rejection_details: Optional[str] = None
    submitted_at: datetime
    processed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Schémas pour les documents
class KYCDocumentBase(BaseModel):
    document_type: DocumentType
    document_number: Optional[str] = None
    issuing_country: Optional[str] = None
    front_image_url: Optional[str] = None
    back_image_url: Optional[str] = None
    selfie_image_url: Optional[str] = None


class KYCDocumentCreate(KYCDocumentBase):
    verification_id: int
    
    class Config:
        from_attributes = True


class KYCDocumentUpdate(BaseModel):
    document_number: Optional[str] = None
    issuing_country: Optional[str] = None
    front_image_url: Optional[str] = None
    back_image_url: Optional[str] = None
    selfie_image_url: Optional[str] = None
    is_verified: Optional[bool] = None
    verification_notes: Optional[str] = None
    verified_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class KYCDocument(KYCDocumentBase):
    id: int
    verification_id: int
    is_verified: bool = False
    verification_notes: Optional[str] = None
    uploaded_at: datetime
    verified_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class KYCDocumentWithPublicUrls(KYCDocument):
    """Same as KYCDocument plus absolute URLs for admin viewers (local /media/ → BACKEND_PUBLIC_URL)."""

    front_public_url: Optional[str] = None
    back_public_url: Optional[str] = None

    class Config:
        from_attributes = True


class KYCVerificationAdminDetail(KYCVerification):
    """Verification row + all documents with resolvable file URLs + user hints for admin UI."""

    documents: List[KYCDocumentWithPublicUrls] = Field(default_factory=list)
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None

    class Config:
        from_attributes = True


# Schémas pour l'audit
class KYCAuditLogBase(BaseModel):
    action: str
    details: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    performed_by_admin: bool = False
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class KYCAuditLogCreate(KYCAuditLogBase):
    verification_id: int
    performed_by_user_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class KYCAuditLog(KYCAuditLogBase):
    id: int
    verification_id: int
    performed_by_user_id: Optional[int] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Schémas composés
class KYCVerificationWithDocuments(KYCVerification):
    documents: List[KYCDocument] = []
    
    class Config:
        from_attributes = True


class KYCVerificationWithAudit(KYCVerification):
    audit_logs: List[KYCAuditLog] = []
    
    class Config:
        from_attributes = True


class KYCVerificationComplete(KYCVerification):
    documents: List[KYCDocument] = []
    audit_logs: List[KYCAuditLog] = []
    
    class Config:
        from_attributes = True


class KYCInitiateRequest(BaseModel):
    """Body for POST /kyc/initiate — residential address required for new sessions; omit to reuse locked address while in progress."""

    model_config = ConfigDict(extra="ignore")

    residential_address: Optional[str] = Field(
        None,
        max_length=500,
        description="Declared residential address; locked when Shufti verification starts.",
    )


# Schémas pour les requêtes
class KYCSubmissionRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100, alias='firstName')
    last_name: str = Field(..., min_length=1, max_length=100, alias='lastName')
    date_of_birth: datetime = Field(..., alias='dateOfBirth')
    nationality: str = Field(..., min_length=2, max_length=100)
    address: str = Field(..., min_length=2, max_length=500)
    document_type: DocumentType = Field(..., alias='documentType')
    document_number: Optional[str] = Field(None, max_length=100, alias='documentNumber')
    issuing_country: str = Field(..., min_length=2, max_length=100, alias='issuingCountry')
    document_front: Optional[str] = Field(None, alias='documentFront')
    document_back: Optional[str] = Field(None, alias='documentBack')
    selfie: Optional[str] = None
    
    model_config = ConfigDict(
        populate_by_name=True,  # Accepte à la fois snake_case et camelCase
        from_attributes=True
    )
    
    @validator('date_of_birth', pre=True)
    def validate_date_of_birth(cls, v):
        if isinstance(v, str):
            # Convertir string en datetime si nécessaire
            from datetime import datetime as dt
            try:
                return dt.fromisoformat(v.replace('Z', '+00:00'))
            except:
                return dt.strptime(v, '%Y-%m-%d')
        return v
    
    @validator('date_of_birth')
    def validate_age(cls, v):
        if v and (datetime.now() - v).days < 18 * 365:
            raise ValueError('L\'utilisateur doit être majeur (18 ans minimum)')
        return v


class KYCStatusResponse(BaseModel):
    verification_id: int
    status: KYCStatus
    identity_verified: bool
    address_verified: bool
    document_verified: bool
    face_verified: bool
    submitted_at: datetime
    processed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class KYCStatistics(BaseModel):
    total_verifications: int
    pending_verifications: int
    approved_verifications: int
    rejected_verifications: int
    approval_rate: float
    average_processing_time_hours: Optional[float] = None
    
    class Config:
        from_attributes = True


# Schémas pour les webhooks
class ShuftiProWebhookData(BaseModel):
    reference: str
    event: str
    verification_result: Optional[dict] = None
    verification_data: Optional[dict] = None
    declined_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class KYCWebhookResponse(BaseModel):
    success: bool
    message: str
    verification_id: Optional[int] = None
    
    class Config:
        from_attributes = True
