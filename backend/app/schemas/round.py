from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.models.round import RoundStatus

# Shared properties
class RoundBase(BaseModel):
    name: str
    status: Optional[RoundStatus] = RoundStatus.UPCOMING
    
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
    contest_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Additional properties to return via API
class Round(RoundInDBBase):
    pass
