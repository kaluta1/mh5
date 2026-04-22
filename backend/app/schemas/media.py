from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


# Schémas de base
class MediaBase(BaseModel):
    title: str
    description: Optional[str] = None
    media_type: str  # "image" ou "video"
    

# Schéma pour créer un média
class MediaCreate(MediaBase):
    path: str
    url: str
    user_id: int
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None


# Schéma pour mettre à jour un média
class MediaUpdate(MediaBase):
    pass


# Schéma pour afficher un média
class Media(MediaBase):
    id: int
    path: str
    url: str
    user_id: int
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
