"""
Group Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.group import GroupType


class GroupCreate(BaseModel):
    """Schema for creating a group"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    group_type: GroupType = GroupType.PRIVATE
    max_members: Optional[int] = Field(None, gt=0)
    requires_approval: bool = False


class GroupResponse(BaseModel):
    """Schema for group response"""
    id: int
    name: str
    description: Optional[str]
    group_type: GroupType
    creator_id: int
    avatar_url: Optional[str]
    cover_url: Optional[str]
    max_members: Optional[int]
    invite_code: Optional[str]
    requires_approval: bool
    member_count: int
    post_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class GroupMemberResponse(BaseModel):
    """Schema for group member response"""
    id: int
    group_id: int
    user_id: int
    role: str
    joined_at: datetime
    is_muted: bool
    is_banned: bool
    
    class Config:
        from_attributes = True
