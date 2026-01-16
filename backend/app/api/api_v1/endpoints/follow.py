from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.follow import Follow
from app.models.user import User
from app.schemas.follow import FollowRequest

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
def follow_user(
    payload: FollowRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Follow a user"""
    if payload.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself"
        )

    target = db.query(User).filter(User.id == payload.user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    existing = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == payload.user_id
    ).first()

    if existing:
        return {"message": "Already following"}

    follow = Follow(
        follower_id=current_user.id,
        following_id=payload.user_id
    )
    db.add(follow)
    db.commit()

    return {"message": "Followed"}


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def unfollow_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Unfollow a user"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unfollow yourself"
        )

    follow = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user_id
    ).first()

    if not follow:
        return {"message": "Not following"}

    db.delete(follow)
    db.commit()
    return {"message": "Unfollowed"}
