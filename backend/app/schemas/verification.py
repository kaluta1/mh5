from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class VerificationType(str, Enum):
    SELFIE = "selfie"
    SELFIE_WITH_PET = "selfie_with_pet"
    SELFIE_WITH_DOCUMENT = "selfie_with_document"
    VOICE = "voice"
    VIDEO = "video"
    BRAND = "brand"
    CONTENT = "content"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MediaType(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


# ============== Request Schemas ==============

class VerificationCreate(BaseModel):
    """Schéma pour créer une nouvelle vérification"""
    verification_type: VerificationType
    media_url: str = Field(..., description="URL du média uploadé (Uploadthing)")
    media_type: MediaType
    duration_seconds: Optional[int] = Field(None, description="Durée pour audio/vidéo")
    file_size_bytes: Optional[int] = Field(None, description="Taille du fichier")
    contest_id: Optional[int] = Field(None, description="ID du concours (optionnel)")
    contestant_id: Optional[int] = Field(None, description="ID du contestant (optionnel)")
    metadata: Optional[dict] = Field(None, description="Métadonnées additionnelles")


class VerificationUpdate(BaseModel):
    """Schéma pour mettre à jour une vérification (admin)"""
    status: VerificationStatus
    rejection_reason: Optional[str] = None


# ============== Response Schemas ==============

class VerificationResponse(BaseModel):
    """Schéma de réponse pour une vérification"""
    id: int
    user_id: int
    verification_type: str
    media_url: str
    media_type: str
    duration_seconds: Optional[int]
    file_size_bytes: Optional[int]
    status: str
    rejection_reason: Optional[str]
    contest_id: Optional[int]
    contestant_id: Optional[int]
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VerificationListResponse(BaseModel):
    """Schéma pour liste de vérifications"""
    verifications: List[VerificationResponse]
    total: int
    page: int
    per_page: int


class UserVerificationsResponse(BaseModel):
    """Statut des vérifications d'un utilisateur"""
    has_selfie: bool = False
    has_voice: bool = False
    has_video: bool = False
    has_brand: bool = False
    has_content: bool = False
    selfie_status: Optional[str] = None
    voice_status: Optional[str] = None
    video_status: Optional[str] = None
    brand_status: Optional[str] = None
    content_status: Optional[str] = None
    selfie_url: Optional[str] = None
    voice_url: Optional[str] = None
    video_url: Optional[str] = None
    brand_url: Optional[str] = None
    content_url: Optional[str] = None
