from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import user as crud_user
from app.db.session import get_db
from app.models.follow import Follow
from app.models.post import Post
from app.models.user import User as UserModel
from app.schemas.follow import FollowUserResponse
from app.schemas.user import User, UserUpdate

router = APIRouter()

@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer les détails de l'utilisateur courant.
    """
    return current_user

@router.put("/me", response_model=User)
def update_user_me(
    *,
    db: Session = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour les informations de l'utilisateur courant.
    """
    user = crud_user.update(db, db_obj=current_user, obj_in=user_in)
    return user


def _build_follow_users(
    db: Session,
    users: List[UserModel],
    current_user_id: int
) -> List[FollowUserResponse]:
    if not users:
        return []

    user_ids = [u.id for u in users]

    followers_counts = dict(
        db.query(Follow.following_id, func.count(Follow.follower_id))
        .filter(Follow.following_id.in_(user_ids))
        .group_by(Follow.following_id)
        .all()
    )
    following_counts = dict(
        db.query(Follow.follower_id, func.count(Follow.following_id))
        .filter(Follow.follower_id.in_(user_ids))
        .group_by(Follow.follower_id)
        .all()
    )
    posts_counts = dict(
        db.query(Post.author_id, func.count(Post.id))
        .filter(Post.author_id.in_(user_ids))
        .group_by(Post.author_id)
        .all()
    )

    is_following_set = set(
        x[0] for x in db.query(Follow.following_id)
        .filter(
            Follow.follower_id == current_user_id,
            Follow.following_id.in_(user_ids)
        )
        .all()
    )
    is_followed_by_set = set(
        x[0] for x in db.query(Follow.follower_id)
        .filter(
            Follow.following_id == current_user_id,
            Follow.follower_id.in_(user_ids)
        )
        .all()
    )

    result = []
    for u in users:
        result.append(FollowUserResponse(
            id=u.id,
            username=u.username,
            full_name=u.full_name,
            avatar_url=u.avatar_url,
            bio=u.bio,
            is_following=u.id in is_following_set,
            is_followed_by=u.id in is_followed_by_set,
            followers_count=int(followers_counts.get(u.id, 0)),
            following_count=int(following_counts.get(u.id, 0)),
            posts_count=int(posts_counts.get(u.id, 0)),
        ))
    return result


@router.get("/suggested", response_model=List[FollowUserResponse])
def get_suggested_users(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Suggested users to follow"""
    following_ids = db.query(Follow.following_id).filter(
        Follow.follower_id == current_user.id
    )

    users = db.query(UserModel).filter(
        UserModel.id != current_user.id,
        ~UserModel.id.in_(following_ids)
    ).offset(skip).limit(limit).all()

    return _build_follow_users(db, users, current_user.id)


@router.get("/search", response_model=List[FollowUserResponse])
def search_users(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Search users by username or full name for mentions."""
    search_term = f"%{q.strip()}%"

    users = db.query(UserModel).filter(
        UserModel.id != current_user.id,
        or_(
            UserModel.username.ilike(search_term),
            UserModel.full_name.ilike(search_term),
            UserModel.first_name.ilike(search_term),
            UserModel.last_name.ilike(search_term),
        )
    ).limit(limit).all()

    return _build_follow_users(db, users, current_user.id)


@router.get("/by-username/{username}", response_model=User)
def read_user_by_username(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Retrieve a user by username."""
    user = crud_user.get_by_username(db=db, username=username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    return user


@router.get("/{user_id}/followers", response_model=List[FollowUserResponse])
def get_followers(
    user_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get users who follow the given user"""
    users = db.query(UserModel).join(
        Follow, Follow.follower_id == UserModel.id
    ).filter(
        Follow.following_id == user_id
    ).offset(skip).limit(limit).all()

    return _build_follow_users(db, users, current_user.id)


@router.get("/{user_id}/following", response_model=List[FollowUserResponse])
def get_following(
    user_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get users that the given user follows"""
    users = db.query(UserModel).join(
        Follow, Follow.following_id == UserModel.id
    ).filter(
        Follow.follower_id == user_id
    ).offset(skip).limit(limit).all()

    return _build_follow_users(db, users, current_user.id)

@router.get("/{user_id}", response_model=User)
def read_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer un utilisateur par ID.
    """
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    return user

@router.get("/", response_model=List[User])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer tous les utilisateurs.
    Accessible uniquement par les administrateurs.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users
