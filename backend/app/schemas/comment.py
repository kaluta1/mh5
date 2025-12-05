from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CommentBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class CommentCreate(CommentBase):
    text: Optional[str] = None  # Alias pour content (frontend utilise "text")
    target_type: str = Field(..., description="contest, photo, or video")
    target_id: Optional[str] = None
    parent_id: Optional[int] = None
    
    def __init__(self, **data):
        # Si "text" est fourni, l'utiliser comme "content"
        if "text" in data and "content" not in data:
            data["content"] = data.pop("text")
        super().__init__(**data)


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class CommentResponse(CommentBase):
    id: int
    user_id: int
    author_name: str
    author_avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    like_count: int = 0
    reply_count: int = 0
    parent_id: Optional[int] = None
    media_id: Optional[int] = None
    contestant_id: Optional[int] = None
    is_flagged: bool = False
    is_hidden: bool = False
    is_liked: Optional[bool] = False

    class Config:
        from_attributes = True


class CommentWithReplies(CommentResponse):
    replies: List["CommentResponse"] = []


# Update forward reference
CommentWithReplies.model_rebuild()


class CommentListResponse(BaseModel):
    comments: List[CommentWithReplies]
    total: int
    page: int
    page_size: int


class LikeResponse(BaseModel):
    id: int
    user_id: int
    comment_id: int
    created_at: datetime

    class Config:
        from_attributes = True
