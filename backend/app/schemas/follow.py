from typing import Optional
from pydantic import BaseModel


class FollowRequest(BaseModel):
    user_id: int


class FollowUserResponse(BaseModel):
    id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_following: bool = False
    is_followed_by: bool = False
    followers_count: int = 0
    following_count: int = 0
    posts_count: int = 0

    class Config:
        from_attributes = True
