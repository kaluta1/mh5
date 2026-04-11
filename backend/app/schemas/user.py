from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


# Schémas de base
class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    is_verified: bool = False
    is_admin: bool = False
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


class UserCreate(UserBase):
    email: EmailStr
    password: str
    continent: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserUpdate(UserBase):
    password: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    continent: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    # Anciens champs (dépréciés)
    city_id: Optional[int] = None
    country_id: Optional[int] = None
    region_id: Optional[int] = None
    continent_id: Optional[int] = None


# Schéma pour afficher un rôle
class RoleBase(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


# Schéma pour afficher un utilisateur
class User(UserBase):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    continent: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    phone_number: Optional[str] = None
    personal_referral_code: Optional[str] = None
    sponsor_id: Optional[int] = None
    role_id: Optional[int] = None
    role: Optional[RoleBase] = None
    identity_verified: Optional[bool] = False
    address_verified: Optional[bool] = False
    affiliate_agreement_accepted: Optional[bool] = False
    affiliate_agreement_accepted_at: Optional[datetime] = None
    # Anciens champs (dépréciés)
    city_id: Optional[int] = None
    country_id: Optional[int] = None
    region_id: Optional[int] = None
    continent_id: Optional[int] = None
    
    class Config:
        from_attributes = True


# Schéma simple pour les informations de parrain
class UserSponsorInfo(BaseModel):
    id: int
    email: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    personal_referral_code: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Schéma pour afficher un utilisateur avec ses permissions
class UserWithPermissions(User):
    permissions: List[str] = []


# Schéma pour afficher un utilisateur avec son parrain
class UserWithSponsor(User):
    sponsor: Optional[UserSponsorInfo] = None
