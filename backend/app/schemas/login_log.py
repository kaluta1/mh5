"""
Schémas Pydantic pour les logs de connexion
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class LoginLogCreate(BaseModel):
    """Schéma pour créer un log de connexion"""
    user_id: int = Field(..., description="ID de l'utilisateur")
    ip_address: Optional[str] = Field(None, description="Adresse IP")
    user_agent: Optional[str] = Field(None, max_length=500, description="User Agent")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Informations de l'appareil")
    location_info: Optional[Dict[str, Any]] = Field(None, description="Informations de localisation")
    is_successful: bool = Field(True, description="Indique si la connexion a réussi")
    failure_reason: Optional[str] = Field(None, max_length=255, description="Raison de l'échec si applicable")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0...",
                "device_info": {
                    "platform": "Windows",
                    "browser": "Chrome",
                    "screen_width": 1920,
                    "screen_height": 1080
                },
                "location_info": {
                    "ip": "192.168.1.1",
                    "city": "Montreal",
                    "timezone": "America/Montreal",
                    "continent": "NA",
                    "country": "Canada"
                },
                "is_successful": True,
                "failure_reason": None
            }
        }


class LoginLogResponse(BaseModel):
    """Schéma de réponse pour un log de connexion"""
    id: int
    user_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    location_info: Optional[Dict[str, Any]] = None
    login_at: datetime
    is_successful: bool
    failure_reason: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class LoginLogListResponse(BaseModel):
    """Schéma pour une liste de logs de connexion"""
    logs: list[LoginLogResponse]
    total: int
    skip: int
    limit: int

