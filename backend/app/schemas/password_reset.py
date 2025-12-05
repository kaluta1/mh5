from pydantic import BaseModel, EmailStr
from typing import Optional


class PasswordResetRequest(BaseModel):
    """Schéma pour demander une réinitialisation de mot de passe"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schéma pour confirmer la réinitialisation avec le token"""
    token: str
    new_password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "new_password": "nouveau_mot_de_passe_securise"
            }
        }


class PasswordResetResponse(BaseModel):
    """Réponse après demande de réinitialisation"""
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Si cet email existe, un lien de réinitialisation a été envoyé"
            }
        }
