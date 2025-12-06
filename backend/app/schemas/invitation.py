"""
Schemas pour les invitations de parrainage
"""
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# Création d'invitation
class InvitationCreate(BaseModel):
    email: EmailStr = Field(..., description="Email du destinataire")
    message: Optional[str] = Field(None, max_length=500, description="Message personnalisé")


class InvitationBulkCreate(BaseModel):
    emails: List[EmailStr] = Field(..., min_length=1, max_length=10, description="Liste d'emails")
    message: Optional[str] = Field(None, max_length=500, description="Message personnalisé")


# Réponse invitation
class InvitationResponse(BaseModel):
    id: int
    email: str
    message: Optional[str]
    referral_code: str
    status: InvitationStatus
    sent_at: datetime
    accepted_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class InvitationWithInviter(InvitationResponse):
    inviter_name: Optional[str] = None
    inviter_avatar: Optional[str] = None


# Statistiques invitations
class InvitationStats(BaseModel):
    total_sent: int = 0
    pending: int = 0
    accepted: int = 0
    expired: int = 0
    conversion_rate: float = 0.0


# Résultat envoi
class InvitationSendResult(BaseModel):
    success: bool
    email: str
    message: Optional[str] = None
    invitation_id: Optional[int] = None
