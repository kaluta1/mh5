from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SearchHistoryBase(BaseModel):
    term: str


class SearchHistoryCreate(SearchHistoryBase):
    pass


class SearchHistoryRead(SearchHistoryBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
