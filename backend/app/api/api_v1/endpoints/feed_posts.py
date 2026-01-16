"""
Posts API Endpoints for Feed System
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import uuid

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.post import Post, PostMedia, PostComment, PostReaction, PostType, PostVisibility, ReactionType
from app.models.social_group import SocialGroup, GroupMember
from app.schemas.feed_post import PostCreate, PostResponse, PostCommentCreate, PostCommentResponse
from app.services.feed_aws_s3 import s3_service

router = APIRouter()


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    post_data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new post"""
    author_id = current_user.id
    
    # Verify group membership if post is in a group
    if post_data.group_id:
        member = db.query(GroupMember).filter(
            GroupMember.group_id == post_data.group_id,
            GroupMember.user_id == author_id
        ).first()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this group"
            )
    
    # Create post
    post = Post(
        author_id=author_id,
        content=post_data.content,
        post_type=post_data.post_type,
        visibility=post_data.visibility,
        group_id=post_data.group_id,
        location=post_data.location,
        tags=post_data.tags
    )
    
    db.add(post)
    
    # Update group post count if in group (before commit for atomicity)
    if post_data.group_id:
        group = db.query(SocialGroup).filter(SocialGroup.id == post_data.group_id).first()
        if group:
            group.post_count += 1
    
    # Single commit for atomicity
    db.commit()
    db.refresh(post)
    
    return PostResponse.model_validate(post)


@router.post("/{post_id}/media", status_code=status.HTTP_201_CREATED)
async def upload_post_media(
    post_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload media for a post"""
    user_id = current_user.id
    
    # Verify post ownership
    post = db.query(Post).filter(
        Post.id == post_id,
        Post.author_id == user_id,
        Post.is_deleted == False
    ).first()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Upload to S3
    file_key = f"posts/{post_id}/{uuid.uuid4()}_{file.filename}"
    
    try:
        media_url = s3_service.upload_file(
            file_obj=file.file,
            key=file_key,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload media: {str(e)}"
        )
    
    # Create post media record
    # Count existing media to determine order
    existing_count = db.query(PostMedia).filter(PostMedia.post_id == post_id).count()
    
    post_media = PostMedia(
        post_id=post_id,
        media_url=media_url,
        media_type=file.content_type or "image",
        order=existing_count
    )
    
    db.add(post_media)
    db.commit()
    db.refresh(post_media)
    
    return {
        "id": post_media.id,
        "media_url": media_url,
        "media_type": post_media.media_type,
        "order": post_media.order
    }


@router.get("", response_model=List[PostResponse])
def list_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    group_id: Optional[int] = Query(None),
    author_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List posts"""
    query = db.query(Post).filter(Post.is_deleted == False)
    
    if group_id:
        query = query.filter(Post.group_id == group_id)
    
    if author_id:
        query = query.filter(Post.author_id == author_id)
    
    posts = query.order_by(Post.created_at.desc()).offset(skip).limit(limit).all()
    return [PostResponse.model_validate(p) for p in posts]


@router.get("/{post_id}", response_model=PostResponse)
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get post details"""
    post = db.query(Post).filter(
        Post.id == post_id,
        Post.is_deleted == False
    ).first()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Increment view count
    post.view_count += 1
    db.commit()
    
    return PostResponse.model_validate(post)


@router.post("/{post_id}/comments", response_model=PostCommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    post_id: int,
    comment_data: PostCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a comment on a post"""
    author_id = current_user.id
    
    # Verify post exists
    post = db.query(Post).filter(
        Post.id == post_id,
        Post.is_deleted == False
    ).first()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    # Create comment
    comment = PostComment(
        post_id=post_id,
        author_id=author_id,
        content=comment_data.content,
        parent_id=comment_data.parent_id
    )
    
    db.add(comment)
    
    # Update post comment count
    post.comment_count += 1
    
    # Update parent comment reply count if exists
    if comment_data.parent_id:
        parent = db.query(PostComment).filter(PostComment.id == comment_data.parent_id).first()
        if parent:
            parent.reply_count += 1
    
    db.commit()
    db.refresh(comment)
    
    return PostCommentResponse.model_validate(comment)


@router.post("/{post_id}/reactions", status_code=status.HTTP_200_OK)
def toggle_reaction(
    post_id: int,
    reaction_type: ReactionType = Query(ReactionType.LIKE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Toggle reaction on a post"""
    user_id = current_user.id
    
    # Check if reaction exists
    existing = db.query(PostReaction).filter(
        PostReaction.post_id == post_id,
        PostReaction.user_id == user_id
    ).first()
    
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    if existing:
        # Remove reaction
        if existing.reaction_type == reaction_type:
            db.delete(existing)
            post.like_count = max(0, post.like_count - 1)
        else:
            # Update reaction type
            existing.reaction_type = reaction_type
    else:
        # Add reaction
        reaction = PostReaction(
            post_id=post_id,
            user_id=user_id,
            reaction_type=reaction_type
        )
        db.add(reaction)
        post.like_count += 1
    
    db.commit()
    
    return {"message": "Reaction updated"}
