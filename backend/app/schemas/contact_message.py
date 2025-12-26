"""
Schémas Pydantic pour les messages de contact
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class ContactMessageCreate(BaseModel):
    """Schéma pour créer un message de contact"""
    name: str = Field(..., min_length=1, max_length=255, description="Nom complet")
    email: EmailStr = Field(..., description="Adresse email")
    subject: str = Field(..., min_length=1, max_length=500, description="Sujet du message")
    category: str = Field(..., description="Catégorie du message")
    message: str = Field(..., min_length=1, description="Contenu du message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "subject": "Question sur le système de vote",
                "category": "general",
                "message": "Bonjour, j'aimerais savoir comment fonctionne le système de vote..."
            }
        }


class ContactMessageResponse(BaseModel):
    """Schéma de réponse pour un message de contact"""
    id: int
    name: str
    email: str
    subject: str
    category: str
    message: str
    is_read: bool
    is_archived: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ContactMessageUpdate(BaseModel):
    """Schéma pour mettre à jour un message de contact"""
    is_read: Optional[bool] = None
    is_archived: Optional[bool] = None

