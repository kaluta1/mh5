from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ContestantCreate(BaseModel):
    """Schéma pour créer une candidature"""
    title: str
    description: str
    image_media_ids: Optional[str] = None  # JSON array of up to 10 image media IDs
    video_media_ids: Optional[str] = None  # JSON array of video media IDs


class ContestantResponse(BaseModel):
    """Réponse pour une candidature"""
    id: int
    user_id: int
    season_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    registration_date: datetime
    verification_status: str
    is_active: bool
    is_qualified: bool

    model_config = ConfigDict(from_attributes=True)


class ContestantListResponse(BaseModel):
    """Réponse pour la liste des candidatures"""
    id: int
    user_id: int
    season_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    is_qualified: bool
    registration_date: datetime

    model_config = ConfigDict(from_attributes=True)


class ContestantSubmissionResponse(BaseModel):
    """Réponse après création d'une candidature"""
    id: int
    season_id: int
    user_id: int
    title: str
    description: str
    registration_date: datetime
    message: str

    model_config = ConfigDict(from_attributes=True)


class ContestantWithAuthorAndStats(BaseModel):
    """Réponse enrichie pour une candidature avec infos auteur et stats"""
    id: int
    user_id: int
    season_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    registration_date: datetime
    is_qualified: bool
    
    # Infos auteur
    author_name: Optional[str] = None
    author_country: Optional[str] = None
    author_city: Optional[str] = None
    author_continent: Optional[str] = None
    author_avatar_url: Optional[str] = None
    
    # Stats
    rank: Optional[int] = None
    votes_count: int = 0
    images_count: int = 0
    videos_count: int = 0
    favorites_count: int = 0
    reactions_count: int = 0
    comments_count: int = 0
    
    # Infos du contest
    contest_title: Optional[str] = None
    contest_id: Optional[int] = None
    total_participants: int = 0
    
    # Position dans les favoris
    position: Optional[int] = None
    
    # État du vote pour l'utilisateur courant
    has_voted: bool = False
    can_vote: bool = False

    model_config = ConfigDict(from_attributes=True)
