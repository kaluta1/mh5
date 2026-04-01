from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.models.round import RoundStatus

# Shared properties
class RoundBase(BaseModel):
    name: str
    status: Optional[RoundStatus] = RoundStatus.UPCOMING
    
    # État du round
    is_submission_open: Optional[bool] = True
    is_voting_open: Optional[bool] = False
    current_season_level: Optional[str] = None  # city, country, regional, continental, global
    
    # Dates
    submission_start_date: Optional[date] = None
    submission_end_date: Optional[date] = None
    voting_start_date: Optional[date] = None
    voting_end_date: Optional[date] = None
    
    city_season_start_date: Optional[date] = None
    city_season_end_date: Optional[date] = None
    country_season_start_date: Optional[date] = None
    country_season_end_date: Optional[date] = None
    regional_start_date: Optional[date] = None
    regional_end_date: Optional[date] = None
    continental_start_date: Optional[date] = None
    continental_end_date: Optional[date] = None
    global_start_date: Optional[date] = None
    global_end_date: Optional[date] = None


# Properties to receive via API on creation
class RoundCreate(RoundBase):
    contest_id: int
    name: str  # e.g. "Round January 2026"
    # Dates can be passed explicitly, or if missing, will be calculated by the backend


# Properties to receive via API on update
class RoundUpdate(RoundBase):
    name: Optional[str] = None
    status: Optional[RoundStatus] = None


class RoundInDBBase(RoundBase):
    id: int
    contest_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Additional properties to return via API
class Round(RoundInDBBase):
    pass



# Forward reference to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.schemas.contest import Contest, TopContestantPreview

# Round with statistics for frontend display
class RoundWithStats(Round):
    participants_count: int = 0
    contests_count: int = 0
    votes_count: int = 0  # Added votes_count
    current_user_participated: bool = False
    is_completed: bool = False  # True if global_end_date passed
    # Set when MYHIGH5_NOMINATION_EXTENSION_UNTIL is active for this round (voting calendar)
    nomination_extension_until: Optional[datetime] = None

    # Nested data
    top_contestants: List["TopContestantPreview"] = []
    contests: List["Contest"] = []

# Update forward refs
from app.schemas.contest import Contest, TopContestantPreview
RoundWithStats.model_rebuild()


