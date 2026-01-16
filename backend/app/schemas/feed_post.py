"""
Post Schemas for Feed System
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.post import PostType, PostVisibility


class PostCreate(BaseModel):
    """Schema for creating a post"""
    content: Optional[str] = None
    post_type: PostType = PostType.TEXT
    visibility: PostVisibility = PostVisibility.PUBLIC
    group_id: Optional[int] = None
    location: Optional[str] = None
    tags: Optional[str] = None


class PostMediaResponse(BaseModel):
    """Schema for post media"""
    id: int
    media_url: str
    media_type: str
    order: int
    
    class Config:
        from_attributes = True


class PostResponse(BaseModel):
    """Schema for post response"""
    id: int
    author_id: int
    content: Optional[str]
    post_type: PostType
    visibility: PostVisibility
    group_id: Optional[int]
    location: Optional[str]
    tags: Optional[str]
    like_count: int
    comment_count: int
    share_count: int
    view_count: int
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    media: List[PostMediaResponse] = []
    
    class Config:
        from_attributes = True


class PostCommentCreate(BaseModel):
    """Schema for creating a comment"""
    content: str = Field(..., min_length=1)
    parent_id: Optional[int] = None


class PostCommentResponse(BaseModel):
    """Schema for comment response"""
    id: int
    post_id: int
    author_id: int
    content: str
    parent_id: Optional[int]
    like_count: int
    reply_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
