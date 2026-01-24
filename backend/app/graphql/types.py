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
    # Relation parent vers Contest (lazy load pour éviter circular import)
    contest: Optional[Annotated["ContestType", strawberry.lazy(".types")]] = None


@strawberry.type 
class VotingTypeType:
    """Type de vote associé à un contest"""
    id: int
    name: str
    voting_level: str
    commission_source: Optional[str] = None


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
    
    # Statistiques
    entries_count: int = 0
    total_votes: int = 0
    
    # Relations
    rounds: List[RoundType] = strawberry.field(default_factory=list)
    voting_type: Optional[VotingTypeType] = None

