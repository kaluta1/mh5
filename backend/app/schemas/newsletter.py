"""
Schémas Pydantic pour les abonnements à la newsletter
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class NewsletterSubscriptionCreate(BaseModel):
    """Schéma pour créer un abonnement à la newsletter"""
    email: EmailStr = Field(..., description="Adresse email")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Informations de l'appareil (user_agent, platform, etc.)")
    location_info: Optional[Dict[str, Any]] = Field(None, description="Informations de localisation (country, city, continent, ip, etc.)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "device_info": {
                    "user_agent": "Mozilla/5.0...",
                    "platform": "Windows",
                    "browser": "Chrome"
                },
                "location_info": {
                    "country": "Canada",
                    "city": "Montreal",
                    "continent": "North America",
                    "ip": "192.168.1.1"
                }
            }
        }


class NewsletterSubscriptionResponse(BaseModel):
    """Schéma de réponse pour un abonnement à la newsletter"""
    id: int
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    verified_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

