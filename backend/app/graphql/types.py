"""
GraphQL Types for MyHigh5 Platform
Defines all GraphQL types: Contest, Round, Contestant, Vote, User, Season
"""

import strawberry
from typing import List, Optional, Annotated, TYPE_CHECKING
from datetime import datetime

# Forward reference for circular dependency
if TYPE_CHECKING:
    from .types import ContestType


@strawberry.type
class UserType:
    """Représente un utilisateur"""
    id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None


@strawberry.type
class VoteType:
    """Représente un vote avec position et points"""
    id: int
    user_id: int
    round_id: int
    contestant_id: int
    position: int  # 1-5
    points: int    # 5,4,3,2,1
    created_at: datetime
    user: Optional[UserType] = None


@strawberry.type
class SeasonType:
    """Représente une saison (city, country, regional, continental, global)"""
    id: int
    title: str
    level: str  # city, country, regional, continental, global
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@strawberry.type
class ContestantType:
    """Représente un contestant dans un round"""
    id: int
    user_id: int
    round_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    
    # Statistiques
    votes_count: int = 0
    rank: Optional[int] = None
    
    # Relations
    author: Optional[UserType] = None
    votes: List[VoteType] = strawberry.field(default_factory=list)


@strawberry.type
class RoundType:
    """Représente un round d'un contest"""
    id: int
    name: str
    status: str  # upcoming, active, completed, cancelled
    is_submission_open: bool = False
    is_voting_open: bool = False
    current_season_level: Optional[str] = None
    
    # Dates
    submission_start_date: Optional[datetime] = None
    submission_end_date: Optional[datetime] = None
    voting_start_date: Optional[datetime] = None
    voting_end_date: Optional[datetime] = None
    
    # Statistiques
    participants_count: int = 0
    votes_count: int = 0
    top_contestants: List[ContestantType] = strawberry.field(default_factory=list)
    current_user_participated: bool = False
    
    # Relations
    contestants: List[ContestantType] = strawberry.field(default_factory=list)
    seasons: List[SeasonType] = strawberry.field(default_factory=list)
    
    # New hierarchical structure
    contests: List[Annotated["ContestInRoundType", strawberry.lazy(".types")]] = strawberry.field(default_factory=list)
    
    # Deprecated singular contest relation
    # contest: Optional[Annotated["ContestType", strawberry.lazy(".types")]] = None


@strawberry.type 
class VotingTypeType:
    """Type de vote associé à un contest"""
    id: int
    name: str
    voting_level: str
    commission_source: Optional[str] = None


@strawberry.type
class ContestInRoundType:
    """Représente un contest dans le contexte d'un round specifique"""
    id: int
    name: str
    description: Optional[str] = None
    contest_type: str
    cover_image_url: Optional[str] = None
    level: str
    
    # Context specific data (loaded via resolvers)
    participants_count: int = 0
    votes_count: int = 0 # Added
    participants: List[ContestantType] = strawberry.field(default_factory=list)


@strawberry.type
class ContestType:
    """Représente un contest"""
    id: int
    name: str
    description: Optional[str] = None
    contest_type: str
    cover_image_url: Optional[str] = None
    is_active: bool = True
    level: str  # city, country, region, continent, global
    
    # Submission Status & Dates
    is_submission_open: bool = True
    submission_start_date: Optional[datetime] = None
    submission_end_date: Optional[datetime] = None
    
    # Verification Requirements
    requires_kyc: bool = True
    requires_visual_verification: bool = False
    requires_voice_verification: bool = False
    requires_brand_verification: bool = False
    requires_content_verification: bool = False
    participant_type: str = "individual"
    
    # Media Requirements
    requires_video: bool = False
    max_videos: int = 1
    video_max_duration: int = 3000
    video_max_size_mb: int = 500
    min_images: int = 0
    max_images: int = 10
    
    # Verification Media Limits
    verification_video_max_duration: int = 30
    verification_max_size_mb: int = 50
    
    # Statistiques
    entries_count: int = 0
    total_votes: int = 0
    
    # Relations
    rounds: List[RoundType] = strawberry.field(default_factory=list)
    voting_type: Optional[VotingTypeType] = None
    contestants: List[ContestantType] = strawberry.field(default_factory=list)
    current_user_participation: Optional[ContestantType] = None


# Update RoundType to use ContestInRoundType
# We need to redefine it or inject it. Since types.py is simple, we just update class definition.
# However, RoundType content is earlier in file. I need to update it there.


