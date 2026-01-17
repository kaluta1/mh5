"""
Feed API Endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import or_

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.post import Post, PostVisibility
from app.schemas.feed_post import PostResponse

router = APIRouter()


@router.get("", response_model=List[PostResponse])
def get_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get personalized feed for the user
    
    Shows:
    - Posts from users they follow
    - Public posts
    - Posts from groups they're members of
    - Their own posts
    """
    user_id = current_user.id
    
    # TODO: Get following list from main platform API
    # For now, show public posts and user's own posts
    
    # Get posts
    posts = db.query(Post).filter(
        Post.is_deleted == False,
        or_(
            Post.visibility == PostVisibility.PUBLIC,
            Post.author_id == user_id
        )
    ).order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    
    return [PostResponse.model_validate(p) for p in posts]
