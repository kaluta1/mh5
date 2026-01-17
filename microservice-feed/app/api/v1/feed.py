"""
Feed API Endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import or_, and_

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.post import Post, PostVisibility
from app.schemas.post import PostResponse

router = APIRouter()


@router.get("", response_model=List[PostResponse])
async def get_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get personalized feed for the user
    
    Shows:
    - Posts from users they follow
    - Public posts
    - Posts from groups they're members of
    - Their own posts
    """
    user_id = current_user["user_id"]
    
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
    
    return [PostResponse.from_orm(p) for p in posts]
