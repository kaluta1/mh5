from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum

from app.models.contests import SeasonStatus, StageLevel, StageStatus
from app.models.user import Gender


# Contest Type schemas
class ContestTypeBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool = True


class ContestTypeCreate(ContestTypeBase):
    pass


class ContestTypeUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ContestType(ContestTypeBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Contest Category schemas
class ContestCategoryBase(BaseModel):
    contest_type_id: int
    name: str
    description: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    gender_restriction: Optional[Gender] = None
    is_active: bool = True


class ContestCategoryCreate(ContestCategoryBase):
    pass


class ContestCategoryUpdate(BaseModel):
    contest_type_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    gender_restriction: Optional[Gender] = None
    is_active: Optional[bool] = None


class ContestCategory(ContestCategoryBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int


# Contest Season schemas
class ContestSeasonBase(BaseModel):
    contest_type_id: int
    name: str
    year: int
    start_date: datetime
    end_date: datetime
    registration_start: datetime
    registration_end: datetime
    status: SeasonStatus = SeasonStatus.UPCOMING


class ContestSeasonCreate(ContestSeasonBase):
    pass


class ContestSeasonUpdate(BaseModel):
    contest_type_id: Optional[int] = None
    name: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    registration_start: Optional[datetime] = None
    registration_end: Optional[datetime] = None
    status: Optional[SeasonStatus] = None


class ContestSeason(ContestSeasonBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    contest_type: Optional[ContestType] = None


# Contest Stage schemas
class ContestStageBase(BaseModel):
    season_id: int
    stage_type: StageLevel
    geographic_entity_id: int
    name: str
    start_date: datetime
    end_date: datetime
    voting_start: datetime
    voting_end: datetime
    max_participants: Optional[int] = None
    status: StageStatus = StageStatus.UPCOMING


class ContestStageCreate(ContestStageBase):
    pass


class ContestStageUpdate(BaseModel):
    season_id: Optional[int] = None
    stage_type: Optional[StageLevel] = None
    geographic_entity_id: Optional[int] = None
    name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    voting_start: Optional[datetime] = None
    voting_end: Optional[datetime] = None
    max_participants: Optional[int] = None
    status: Optional[StageStatus] = None


class ContestStage(ContestStageBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    season: Optional[ContestSeason] = None


# Contestant schemas
class ContestantBase(BaseModel):
    user_id: int
    season_id: int
    category_id: int
    stage_id: int
    contestant_number: Optional[str] = None
    bio: Optional[str] = None
    is_active: bool = True


class ContestantCreate(ContestantBase):
    pass


class ContestantUpdate(BaseModel):
    contestant_number: Optional[str] = None
    bio: Optional[str] = None
    is_active: Optional[bool] = None


class Contestant(ContestantBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    registration_date: Optional[datetime] = None
    current_ranking: Optional[int] = None
    total_votes: int = 0
    total_points: int = 0


class ContestantProfile(Contestant):
    """Profil complet d'un participant avec informations utilisateur"""
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    profile_picture_url: Optional[str] = None
    stage_name: Optional[str] = None
    category_name: Optional[str] = None


# Contest Submission schemas
class ContestSubmissionBase(BaseModel):
    contestant_id: int
    submission_type: str  # video, image, external_link
    title: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    external_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_primary: bool = False


class ContestSubmissionCreate(ContestSubmissionBase):
    pass


class ContestSubmissionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    external_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_primary: Optional[bool] = None


class ContestSubmission(ContestSubmissionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    submission_date: Optional[datetime] = None
    is_approved: bool = False
    moderation_notes: Optional[str] = None


# Contestant Ranking schemas
class ContestantRankingBase(BaseModel):
    contestant_id: int
    stage_id: int
    current_position: int
    total_votes: int = 0
    total_points: int = 0
    points_breakdown: Optional[dict] = None


class ContestantRankingCreate(ContestantRankingBase):
    pass


class ContestantRankingUpdate(BaseModel):
    current_position: Optional[int] = None
    total_votes: Optional[int] = None
    total_points: Optional[int] = None
    points_breakdown: Optional[dict] = None


class ContestantRanking(ContestantRankingBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    last_updated: Optional[datetime] = None


# Response schemas with nested data
class ContestTypeWithCategories(ContestType):
    categories: List[ContestCategory] = []


class ContestSeasonWithStages(ContestSeason):
    stages: List[ContestStage] = []


class ContestStageWithContestants(ContestStage):
    contestants: List[ContestantProfile] = []
    total_contestants: int = 0


class ContestantWithSubmissions(Contestant):
    submissions: List[ContestSubmission] = []
    ranking: Optional[ContestantRanking] = None
