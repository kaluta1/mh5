from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.notification import NotificationType


class NotificationBase(BaseModel):
    type: NotificationType
    title: str = Field(..., max_length=255)
    message: str
    related_contestant_id: Optional[int] = None
    related_comment_id: Optional[int] = None
    related_contest_id: Optional[int] = None


class NotificationCreate(NotificationBase):
    user_id: int


class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None


class NotificationUnreadCount(BaseModel):
    count: int

