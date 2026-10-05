from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional

from app.core.security_validators import validate_password_strength


class PasswordResetRequest(BaseModel):
    """Schéma pour demander une réinitialisation de mot de passe"""
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    """Ask for a new email verification link."""
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """The one-time credential from the verification email (request body)."""
    token: str = Field(min_length=1, max_length=512)


class RegistrationAccepted(BaseModel):
    """Public answer to a registration. Identical whether or not the address
    already had an account; `email` only echoes what the caller sent."""
    message: str
    detail: str
    code: str = "REGISTRATION_ACCEPTED"
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schéma pour confirmer la réinitialisation avec le token"""
    token: str = Field(min_length=1, max_length=512)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_strength(v)
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "<one-time credential from the email>",
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


class PasswordChangeResponse(BaseModel):
    """A password change ends every earlier session; this is the new one for
    the device that made the change."""
    message: str
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    """Schéma pour changer le mot de passe (utilisateur connecté)"""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return validate_password_strength(v)
    
    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "mot_de_passe_actuel",
                "new_password": "nouveau_mot_de_passe_securise"
            }
        }
