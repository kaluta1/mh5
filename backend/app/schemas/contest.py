from typing import List, Optional, Any
from datetime import date
from pydantic import BaseModel, Field

from app.schemas.media import Media


# Schéma de base pour les concours
class ContestBase(BaseModel):
    name: str
    description: Optional[str] = None
    contest_type: str
    cover_image_url: Optional[str] = None
    submission_start_date: date
    submission_end_date: date
    voting_start_date: date
    voting_end_date: date
    is_active: bool = True
    is_submission_open: bool = True
    is_voting_open: bool = False
    level: str  # city, country, region, continent, global
    location_id: Optional[int] = None
    gender_restriction: Optional[str] = None
    voting_restriction: Optional[str] = None  # Ajout du champ voting_restriction
    max_entries_per_user: int = 1
    template_id: Optional[int] = None


# Schéma pour créer un concours
class ContestCreate(ContestBase):
    pass


# Schéma pour mettre à jour un concours
class ContestUpdate(ContestBase):
    name: Optional[str] = None
    contest_type: Optional[str] = None
    submission_start_date: Optional[date] = None
    submission_end_date: Optional[date] = None
    voting_start_date: Optional[date] = None
    voting_end_date: Optional[date] = None
    level: Optional[str] = None


# Schéma pour une participation à un concours
class ContestEntryBase(BaseModel):
    contest_id: int
    user_id: int
    media_id: int
    total_score: float = 0
    rank: Optional[int] = None


# Schéma pour créer une participation
class ContestEntryCreate(ContestEntryBase):
    pass


# Schéma pour afficher une participation
class ContestEntry(ContestEntryBase):
    id: int
    media: Media
    
    class Config:
        from_attributes = True


# Schéma pour afficher un concours
class Contest(ContestBase):
    id: int
    created_at: Any
    updated_at: Any
    entries_count: int = 0  # Nombre de participants
    total_votes: int = 0  # Nombre total de votes
    season_level: Optional[str] = None  # Niveau depuis la season
    image_url: Optional[str] = None  # URL de l'image principale
    
    class Config:
        from_attributes = True
        # Inclure les champs None dans la sérialisation
        exclude_none = False


# Schéma pour afficher un concours avec ses participations
class ContestWithEntries(Contest):
    entries: List[ContestEntry] = []


# Schéma pour un vote de concours
class ContestVoteBase(BaseModel):
    entry_id: int
    user_id: int
    score: int  # 1-5 pour MyFav


# Schéma pour créer un vote de concours
class ContestVoteCreate(ContestVoteBase):
    pass


# Schéma pour afficher un vote de concours
class ContestVote(ContestVoteBase):
    id: int
    
    class Config:
        from_attributes = True

# Alias pour compatibilité
VoteBase = ContestVoteBase
VoteCreate = ContestVoteCreate
Vote = ContestVote


# Schéma pour un template de concours
class ContestTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    contest_type: str
    has_geo_restrictions: bool = False
    has_gender_restrictions: bool = False
    default_submission_days: int = 60
    default_voting_days: int = 60


# Schéma pour créer un template de concours
class ContestTemplateCreate(ContestTemplateBase):
    pass


# Schéma pour afficher un template de concours
class ContestTemplate(ContestTemplateBase):
    id: int
    
    class Config:
        from_attributes = True


# Schéma pour une localisation
class LocationBase(BaseModel):
    name: str
    level: str  # city, country, region, continent, global
    parent_id: Optional[int] = None


# Schéma pour créer une localisation
class LocationCreate(LocationBase):
    pass


# Schéma pour afficher une localisation
class Location(LocationBase):
    id: int
    
    class Config:
        from_attributes = True
