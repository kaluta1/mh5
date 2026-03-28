from typing import Optional, List, Union, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
import json


class ContestantCreate(BaseModel):
    """Schéma pour créer une candidature"""
    title: str
    description: str
    image_media_ids: Optional[str] = None  # JSON array of up to 10 image media IDs
    video_media_ids: Optional[str] = None  # JSON array of video media IDs
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None
    entry_type: Optional[str] = "participation"  # 'nomination' ou 'participation'

    @field_validator('image_media_ids', 'video_media_ids', mode='before')
    @classmethod
    def normalize_media_ids(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, list):
            return json.dumps(v)
        return v


class ContestantResponse(BaseModel):
    """Réponse pour une candidature"""
    id: int
    user_id: int
    season_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None
    entry_type: Optional[str] = "participation"
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
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None
    entry_type: Optional[str] = "participation"
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
    round_id: Optional[int] = None
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
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None
    entry_type: Optional[str] = "participation"
    contestant_image_url: Optional[str] = None
    registration_date: Optional[datetime] = None
    is_qualified: bool = False
    
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
    shares_count: int = 0
    
    # Infos du contest
    contest_title: Optional[str] = None
    contest_category: Optional[str] = None
    contest_level: Optional[str] = None
    contest_image_url: Optional[str] = None
    contest_id: Optional[int] = None
    total_participants: int = 0
    
    # Position dans les favoris
    position: Optional[int] = None
    
    # État du vote pour l'utilisateur courant
    has_voted: bool = False
    can_vote: bool = False

    model_config = ConfigDict(from_attributes=True)
