from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime


# Vote schemas
class VoteBase(BaseModel):
    voter_id: int
    contestant_id: int
    stage_id: int
    points: int  # 1-5 points selon le système MyFav
    vote_type: str = "regular"  # regular, premium, sponsor


class VoteCreate(VoteBase):
    pass


class VoteUpdate(BaseModel):
    points: Optional[int] = None


class Vote(VoteBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    vote_date: Optional[datetime] = None
    is_valid: bool = True
    ip_address: Optional[str] = None


class VoteWithDetails(Vote):
    """Vote avec détails du votant et participant"""
    voter_name: Optional[str] = None
    contestant_name: Optional[str] = None
    stage_name: Optional[str] = None


# Vote Validation schemas
class VoteValidationBase(BaseModel):
    vote_id: int
    validation_type: str  # ip_check, user_verification, duplicate_check
    is_valid: bool
    validation_notes: Optional[str] = None


class VoteValidationCreate(VoteValidationBase):
    pass


class VoteValidation(VoteValidationBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    validated_at: Optional[datetime] = None


# Voting Statistics schemas
class VotingStatsBase(BaseModel):
    contestant_id: int
    stage_id: int
    total_votes: int = 0
    total_points: int = 0
    points_5: int = 0
    points_4: int = 0
    points_3: int = 0
    points_2: int = 0
    points_1: int = 0
    average_rating: float = 0.0
    current_rank: int = 0


class VotingStatsCreate(VotingStatsBase):
    pass


class VotingStatsUpdate(BaseModel):
    total_votes: Optional[int] = None
    total_points: Optional[int] = None
    points_5: Optional[int] = None
    points_4: Optional[int] = None
    points_3: Optional[int] = None
    points_2: Optional[int] = None
    points_1: Optional[int] = None
    average_rating: Optional[float] = None
    current_rank: Optional[int] = None


class VotingStats(VotingStatsBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    last_updated: Optional[datetime] = None


class VotingStatsWithContestant(VotingStats):
    """Statistiques avec informations participant"""
    contestant_name: Optional[str] = None
    contestant_number: Optional[str] = None
    user_profile_picture: Optional[str] = None


# Vote Ranking schemas
class VoteRankingBase(BaseModel):
    stage_id: int
    contestant_id: int
    current_position: int
    previous_position: Optional[int] = None
    total_points: int = 0
    total_votes: int = 0
    points_change: int = 0
    rank_change: int = 0


class VoteRankingCreate(VoteRankingBase):
    pass


class VoteRankingUpdate(BaseModel):
    current_position: Optional[int] = None
    previous_position: Optional[int] = None
    total_points: Optional[int] = None
    total_votes: Optional[int] = None
    points_change: Optional[int] = None
    rank_change: Optional[int] = None


class VoteRanking(VoteRankingBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    last_updated: Optional[datetime] = None


class VoteRankingWithContestant(VoteRanking):
    """Classement avec informations participant"""
    contestant_name: Optional[str] = None
    contestant_number: Optional[str] = None
    user_profile_picture: Optional[str] = None
    bio: Optional[str] = None


# Voting Session schemas
class VotingSessionBase(BaseModel):
    user_id: int
    stage_id: int
    session_start: datetime
    session_end: Optional[datetime] = None
    total_votes_cast: int = 0
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class VotingSessionCreate(VotingSessionBase):
    pass


class VotingSessionUpdate(BaseModel):
    session_end: Optional[datetime] = None
    total_votes_cast: Optional[int] = None


class VotingSession(VotingSessionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int


# Response schemas complexes
class StageLeaderboard(BaseModel):
    """Classement d'une étape de concours"""
    stage_id: int
    stage_name: str
    total_contestants: int = 0
    total_votes: int = 0
    rankings: List[VoteRankingWithContestant] = []
    voting_period_active: bool = False
    voting_ends_at: Optional[datetime] = None


class ContestantVotingProfile(BaseModel):
    """Profil de vote d'un participant"""
    contestant_id: int
    contestant_name: str
    contestant_number: Optional[str] = None
    profile_picture_url: Optional[str] = None
    bio: Optional[str] = None
    current_rank: int = 0
    total_votes: int = 0
    total_points: int = 0
    average_rating: float = 0.0
    vote_breakdown: dict = {}  # {"5": count, "4": count, ...}
    recent_votes: List[Vote] = []


class VotingAnalytics(BaseModel):
    """Analytiques de vote pour une étape"""
    stage_id: int
    total_votes: int = 0
    unique_voters: int = 0
    average_votes_per_contestant: float = 0.0
    most_active_voting_hour: Optional[int] = None
    vote_distribution: dict = {}  # {"5": count, "4": count, ...}
    geographic_distribution: dict = {}
    daily_vote_counts: List[dict] = []


class UserVotingHistory(BaseModel):
    """Historique de vote d'un utilisateur"""
    user_id: int
    total_votes_cast: int = 0
    favorite_contestants: List[dict] = []
    voting_patterns: dict = {}
    recent_votes: List[VoteWithDetails] = []
    voting_sessions: List[VotingSession] = []


class VotingSystemStats(BaseModel):
    """Statistiques globales du système de vote"""
    total_votes_all_time: int = 0
    total_active_voters: int = 0
    average_votes_per_user: float = 0.0
    most_voted_contestant: Optional[dict] = None
    most_active_stage: Optional[dict] = None
    vote_validation_rate: float = 0.0
    fraud_detection_alerts: int = 0


# Reaction schemas
class ReactionBase(BaseModel):
    contestant_id: int
    reaction_type: str  # like, love, wow, dislike
    
    @field_validator('reaction_type', mode='before')
    @classmethod
    def normalize_reaction_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class ReactionCreate(ReactionBase):
    pass


class Reaction(ReactionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    created_at: Optional[datetime] = None


class ReactionStats(BaseModel):
    """Statistiques de réactions pour un contestant"""
    contestant_id: int
    total_reactions: int = 0
    like_count: int = 0
    love_count: int = 0
    wow_count: int = 0
    dislike_count: int = 0
    user_reaction: Optional[str] = None  # La réaction de l'utilisateur actuel


class ReactionUserDetail(BaseModel):
    """Détails d'un utilisateur qui a réagi"""
    id: Optional[int] = None  # ID de la réaction
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    reaction_type: str


class ReactionDetails(BaseModel):
    """Détails des réactions groupées par type"""
    contestant_id: int
    reactions_by_type: dict[str, List[ReactionUserDetail]] = {}  # Clé: reaction_type, Valeur: liste d'utilisateurs


class VoteUserDetail(BaseModel):
    """Détails d'un utilisateur qui a voté"""
    id: Optional[int] = None  # ID du vote dans contestant_voting
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    points: int
    vote_date: datetime
    contest_id: Optional[int] = None  # ID du contest
    season_id: Optional[int] = None  # ID de la saison


class VoteDetails(BaseModel):
    """Détails des votes pour un contestant"""
    contestant_id: int
    voters: List[VoteUserDetail] = []


class FavoriteUserDetail(BaseModel):
    """Détails d'un utilisateur qui a ajouté en favoris"""
    id: Optional[int] = None  # ID du favori
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    position: Optional[int] = None
    added_date: datetime


class FavoriteDetails(BaseModel):
    """Détails des favoris pour un contestant"""
    contestant_id: int
    users: List[FavoriteUserDetail] = []


# Share schemas
class ShareBase(BaseModel):
    contestant_id: int
    share_link: str
    platform: Optional[str] = None  # facebook, twitter, whatsapp, etc.
    referral_code: Optional[str] = None  # Code de parrainage de celui qui partage


class ShareCreate(ShareBase):
    shared_by_user_id: Optional[int] = None


class Share(ShareBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    author_id: Optional[int] = None
    user_id: Optional[int] = None  # Déprécié, utiliser author_id
    shared_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None  # Utilise created_at de Base au lieu de shared_at


class ShareStats(BaseModel):
    """Statistiques de partage pour un contestant"""
    contestant_id: int
    total_shares: int = 0
    shares_by_platform: dict = {}  # {"facebook": count, "twitter": count, ...}
    # Informations du contestant
    contestant_title: Optional[str] = None
    contestant_description: Optional[str] = None
    contestant_registration_date: Optional[datetime] = None
    # Informations de l'auteur
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    author_username: Optional[str] = None
    author_country: Optional[str] = None
    author_city: Optional[str] = None
    author_avatar_url: Optional[str] = None
