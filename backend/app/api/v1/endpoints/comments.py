from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.contest import ContestEntry
from app.models.media import Media
from app.crud.comment import comment_crud
from app.schemas.comment import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentWithReplies,
    CommentListResponse
)
from typing import Optional

router = APIRouter(prefix="/comments", tags=["comments"])


def serialize_comment_with_replies(comment, db: Session) -> CommentWithReplies:
    """Sérialiser un commentaire avec ses réponses"""
    user = comment.user
    replies, _ = comment_crud.get_replies(db, comment.id)
    
    return CommentWithReplies(
        id=comment.id,
        content=comment.content,
        user_id=comment.user_id,
        author_name=user.full_name or user.username,
        author_avatar=user.avatar_url,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        like_count=comment.like_count,
        reply_count=len(replies),
        parent_id=comment.parent_id,
        media_id=comment.media_id,
        contest_entry_id=comment.contest_entry_id,
        is_flagged=comment.is_flagged,
        is_hidden=comment.is_hidden,
        replies=[serialize_comment_with_replies(r, db) for r in replies]
    )


# Endpoints pour les commentaires de contestant
@router.get("/contestants/{contestant_id}/comments")
def get_contestant_comments(
    contestant_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Récupérer les commentaires d'un contestant"""
    # Vérifier que le contestant existe
    contestant = db.query(ContestEntry).filter(ContestEntry.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    comments, total = comment_crud.get_comments_by_contest_entry(
        db, contestant_id, skip, limit, parent_id=None
    )
    
    return CommentListResponse(
        comments=[serialize_comment_with_replies(c, db) for c in comments],
        total=total,
        page=skip // limit + 1,
        page_size=limit
    )


@router.post("/contestants/{contestant_id}/comments")
def create_contestant_comment(
    contestant_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Créer un commentaire sur un contestant"""
    # Vérifier que le contestant existe
    contestant = db.query(ContestEntry).filter(ContestEntry.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    comment = comment_crud.create_comment(
        db,
        user_id=current_user.id,
        content=comment_data.content,
        contest_entry_id=contestant_id,
        parent_id=comment_data.parent_id
    )
    
    return serialize_comment_with_replies(comment, db)


# Endpoints pour les commentaires de média
@router.get("/contestants/{contestant_id}/media/{media_type}/{media_id}/comments")
def get_media_comments(
    contestant_id: int,
    media_type: str,
    media_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Récupérer les commentaires d'un média"""
    # Vérifier que le média existe
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )
    
    comments, total = comment_crud.get_comments_by_media(
        db, media_id, skip, limit, parent_id=None
    )
    
    return CommentListResponse(
        comments=[serialize_comment_with_replies(c, db) for c in comments],
        total=total,
        page=skip // limit + 1,
        page_size=limit
    )


@router.post("/contestants/{contestant_id}/media/{media_type}/{media_id}/comments")
def create_media_comment(
    contestant_id: int,
    media_type: str,
    media_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Créer un commentaire sur un média"""
    # Vérifier que le média existe
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )
    
    comment = comment_crud.create_comment(
        db,
        user_id=current_user.id,
        content=comment_data.content,
        media_id=media_id,
        parent_id=comment_data.parent_id
    )
    
    return serialize_comment_with_replies(comment, db)


# Endpoints généraux pour les commentaires
@router.get("/{comment_id}")
def get_comment(
    comment_id: int,
    db: Session = Depends(get_db)
):
    """Récupérer un commentaire par ID"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    return serialize_comment_with_replies(comment, db)


@router.put("/{comment_id}")
def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mettre à jour un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Vérifier que l'utilisateur est l'auteur
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment"
        )
    
    updated_comment = comment_crud.update_comment(db, comment_id, comment_data.content)
    return serialize_comment_with_replies(updated_comment, db)


@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Supprimer un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Vérifier que l'utilisateur est l'auteur
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )
    
    comment_crud.delete_comment(db, comment_id)
    return {"message": "Comment deleted successfully"}


@router.post("/{comment_id}/like")
def like_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Liker un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    comment_crud.like_comment(db, current_user.id, comment_id)
    updated_comment = comment_crud.get_comment(db, comment_id)
    return serialize_comment_with_replies(updated_comment, db)


@router.post("/{comment_id}/unlike")
def unlike_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retirer le like d'un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    comment_crud.unlike_comment(db, current_user.id, comment_id)
    updated_comment = comment_crud.get_comment(db, comment_id)
    return serialize_comment_with_replies(updated_comment, db)


@router.get("/{comment_id}/replies")
def get_comment_replies(
    comment_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Récupérer les réponses à un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    replies, total = comment_crud.get_replies(db, comment_id, skip, limit)
    
    return CommentListResponse(
        comments=[serialize_comment_with_replies(r, db) for r in replies],
        total=total,
        page=skip // limit + 1,
        page_size=limit
    )
