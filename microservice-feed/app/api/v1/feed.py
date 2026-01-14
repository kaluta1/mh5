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
from app.models.group import GroupMember
from app.schemas.post import PostResponse
from app.services.main_platform import main_platform_service

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
    token = current_user.get("token", "")
    
    # Get following list from main platform
    following_ids = []
    try:
        following_ids = await main_platform_service.get_following(user_id, token)
    except Exception as e:
        # If main platform is unavailable, continue without following filter
        pass
    
    # Get groups user is member of
    user_groups = db.query(GroupMember.group_id).filter(
        GroupMember.user_id == user_id
    ).subquery()
    
    # Build query
    query = db.query(Post).filter(
        Post.is_deleted == False
    )
    
    # Build conditions
    conditions = [
        Post.author_id == user_id,  # User's own posts
        Post.visibility == PostVisibility.PUBLIC,  # Public posts
    ]
    
    # Add posts from followed users
    if following_ids:
        conditions.append(
            and_(
                Post.author_id.in_(following_ids),
                Post.visibility.in_([PostVisibility.PUBLIC, PostVisibility.FOLLOWERS])
            )
        )
    
    # Add posts from groups user is member of
    conditions.append(
        and_(
            Post.group_id.in_(user_groups),
            Post.visibility == PostVisibility.GROUP
        )
    )
    
    # Apply conditions
    query = query.filter(or_(*conditions))
    
    # Order by creation date (newest first)
    posts = query.order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    
    return [PostResponse.from_orm(p) for p in posts]
