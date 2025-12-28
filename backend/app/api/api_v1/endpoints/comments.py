import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from app.api import deps
from app.api.deps import is_owner_or_has_permission, check_user_permission
from app.models.comment import Comment, Like
from app.models.user import User
from app.models.contests import Contestant
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
from app.services.content_moderation import content_moderation_service

router = APIRouter()


def serialize_comment_with_replies(
    comment, 
    all_replies_map: dict, 
    liked_comment_ids: set,
    current_user_id: Optional[int] = None
) -> CommentWithReplies:
    """Sérialiser un commentaire avec ses réponses (version optimisée)"""
    user = comment.user
    replies = all_replies_map.get(comment.id, [])
    
    # Vérifier si l'utilisateur actuel a liké ce commentaire
    is_liked = comment.id in liked_comment_ids if current_user_id else False
    
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
        contestant_id=comment.contestant_id,
        is_flagged=comment.is_flagged,
        is_hidden=comment.is_hidden,
        is_liked=is_liked,
        replies=[serialize_comment_with_replies(r, all_replies_map, liked_comment_ids, current_user_id) for r in replies]
    )


# Endpoints pour les commentaires de contestant
@router.get("/{contestant_id}/comments")
def get_contestant_comments(
    contestant_id: int,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Récupérer les commentaires d'un contestant (version optimisée)"""
    
    # Vérifier que le contestant existe
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Récupérer les commentaires principaux avec eager loading des utilisateurs
    comments, total = comment_crud.get_comments_by_contestant(
        db, contestant_id, skip, limit, parent_id=None
    )
    
    if not comments:
        return CommentListResponse(
            comments=[],
            total=total,
            page=skip // limit + 1 if limit > 0 else 1,
            page_size=limit
        )
    
    # Récupérer tous les commentaires du contestant (y compris les réponses) en une seule requête
    comment_ids = [c.id for c in comments]
    all_comments = db.query(Comment).options(
        joinedload(Comment.user)
    ).filter(
        Comment.contestant_id == contestant_id,
        Comment.is_hidden == False
    ).all()
    
    # Créer un dictionnaire de toutes les réponses groupées par parent_id
    all_replies_map = {}
    for comment in all_comments:
        if comment.parent_id is not None:
            if comment.parent_id not in all_replies_map:
                all_replies_map[comment.parent_id] = []
            all_replies_map[comment.parent_id].append(comment)
    
    # Trier les réponses par date de création
    for parent_id in all_replies_map:
        all_replies_map[parent_id].sort(key=lambda x: x.created_at)
    
    # Récupérer tous les likes de l'utilisateur actuel en une seule requête
    current_user_id = current_user.id if current_user else None
    liked_comment_ids = set()
    if current_user_id:
        likes = db.query(Like.comment_id).filter(
            Like.user_id == current_user_id,
            Like.comment_id.in_([c.id for c in all_comments])
        ).all()
        liked_comment_ids = {like[0] for like in likes}
    
    # Sérialiser les commentaires principaux
    serialized_comments = [
        serialize_comment_with_replies(c, all_replies_map, liked_comment_ids, current_user_id)
        for c in comments
    ]
    
    return CommentListResponse(
        comments=serialized_comments,
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.post("/{contestant_id}/comments")
def create_contestant_comment(
    contestant_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """Créer un commentaire sur un contestant"""
    # Vérifier que le contestant existe
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # ============================================
    # MODÉRATION DU CONTENU AVANT CRÉATION
    # ============================================
    logger = logging.getLogger(__name__)
    logger.info(f"Moderating comment text: '{comment_data.content[:50]}...'")
    
    text_moderation = content_moderation_service.moderate_text(comment_data.content)
    logger.info(f"Comment moderation result: approved={text_moderation.is_approved}, flags={len(text_moderation.flags)}")
    
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        logger.warning(f"Comment rejected: {flags_desc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Commentaire rejeté: {flags_desc}"
        )
    
    comment = comment_crud.create_comment(
        db,
        user_id=current_user.id,
        content=comment_data.content,
        contestant_id=contestant_id,
        parent_id=comment_data.parent_id
    )
    
    # Recharger le commentaire avec les relations
    db.refresh(comment)
    comment = db.query(Comment).options(joinedload(Comment.user)).filter(Comment.id == comment.id).first()
    
    # Créer une notification
    from app.crud.crud_notification import crud_notification
    from app.models.notification import NotificationType
    
    commenter_name = current_user.full_name or current_user.username or "Someone"
    
    # Si c'est une réponse (parent_id existe), notifier le propriétaire du commentaire parent
    if comment_data.parent_id:
        parent_comment = db.query(Comment).filter(Comment.id == comment_data.parent_id).first()
        if parent_comment and parent_comment.user_id != current_user.id:
            crud_notification.create(
                db,
                user_id=parent_comment.user_id,
                type=NotificationType.CONTEST,
                title="New reply",
                message=f"{commenter_name} replied to your comment",
                related_contestant_id=contestant_id,
                related_comment_id=comment_data.parent_id
            )
    # Sinon, notifier le propriétaire du contestant
    elif contestant.user_id != current_user.id:
        crud_notification.create(
            db,
            user_id=contestant.user_id,
            type=NotificationType.CONTEST,
            title="New comment",
            message=f"{commenter_name} commented on your application",
            related_contestant_id=contestant_id,
            related_comment_id=comment.id
        )
    
    db.commit()
    
    # Pour un nouveau commentaire, pas de réponses
    all_replies_map = {}
    liked_comment_ids = set()
    
    return serialize_comment_with_replies(comment, all_replies_map, liked_comment_ids, current_user.id)


# Endpoints pour les commentaires de média
@router.get("/{contestant_id}/media/{media_type}/{media_id}/comments")
def get_media_comments(
    contestant_id: int,
    media_type: str,
    media_id: str,
    db: Session = Depends(deps.get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Récupérer les commentaires d'un média"""
    # Vérifier que le contestant existe
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Pour maintenant, on accepte juste l'ID de média comme string
    # Les commentaires seront stockés avec media_id = None et target_id = media_id
    # On va traiter cela après
    
    return CommentListResponse(
        comments=[],
        total=0,
        page=1,
        page_size=limit
    )


@router.post("/{contestant_id}/media/{media_type}/{media_id}/comments")
def create_media_comment(
    contestant_id: int,
    media_type: str,
    media_id: str,
    comment_data: CommentCreate,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """Créer un commentaire sur un média"""
    # Vérifier que le contestant existe
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Modérer le contenu avant création
    text_moderation = content_moderation_service.moderate_text(comment_data.content)
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Commentaire rejeté: {flags_desc}"
        )
    
    # Pour maintenant, on stocke le commentaire au niveau du contestant
    # avec target_id = media_id (string)
    comment = comment_crud.create_comment(
        db,
        user_id=current_user.id,
        content=comment_data.content,
        contestant_id=contestant_id,
        parent_id=comment_data.parent_id
    )
    
    return serialize_comment_with_replies(comment, db)


# Endpoints généraux pour les commentaires
@router.get("/comment/{comment_id}")
def get_comment(
    comment_id: int,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
):
    """Récupérer un commentaire par ID"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    current_user_id = current_user.id if current_user else None
    return serialize_comment_with_replies(comment, db, current_user_id)


@router.put("/comment/{comment_id}")
def update_comment(
    comment_id: int,
    comment_data: CommentUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """Mettre à jour un commentaire. Seul l'auteur peut modifier son commentaire."""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Vérifier que l'utilisateur est l'auteur (permission: edit_own_comment)
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment"
        )
    
    # Vérifier la permission
    if not check_user_permission(current_user, 'edit_own_comment'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission 'edit_own_comment' required"
        )
    
    # Modérer le nouveau contenu
    text_moderation = content_moderation_service.moderate_text(comment_data.content)
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Commentaire rejeté: {flags_desc}"
        )
    
    updated_comment = comment_crud.update_comment(db, comment_id, comment_data.content)
    return serialize_comment_with_replies(updated_comment, db, current_user.id)


@router.delete("/comment/{comment_id}")
def delete_comment(
    comment_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """
    Supprimer un commentaire.
    - L'auteur peut supprimer son propre commentaire (permission: delete_own_comment)
    - Les modérateurs peuvent supprimer n'importe quel commentaire (permission: delete_comment)
    """
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Vérifier les permissions
    is_owner = comment.user_id == current_user.id
    can_delete_own = is_owner and check_user_permission(current_user, 'delete_own_comment')
    can_delete_any = check_user_permission(current_user, 'delete_comment')
    
    if not (can_delete_own or can_delete_any):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )
    
    comment_crud.delete_comment(db, comment_id)
    return {"message": "Comment deleted successfully"}


@router.post("/comment/{comment_id}/like")
def like_comment(
    comment_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
):
    """Liker un commentaire"""
    comment = comment_crud.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    comment_crud.like_comment(db, current_user.id, comment_id)
    
    # Créer une notification pour le propriétaire du commentaire
    from app.crud.crud_notification import crud_notification
    from app.models.notification import NotificationType
    
    if comment.user_id != current_user.id:
        liker_name = current_user.full_name or current_user.username or "Someone"
        crud_notification.create(
            db,
            user_id=comment.user_id,
            type=NotificationType.CONTEST,
            title="New like",
            message=f"{liker_name} liked your comment",
            related_contestant_id=comment.contestant_id,
            related_comment_id=comment_id
        )
        db.commit()
    
    updated_comment = comment_crud.get_comment(db, comment_id)
    # Pour un seul commentaire, on crée un dict vide pour les réponses
    liked_ids = {comment_id}  # L'utilisateur vient de liker ce commentaire
    return serialize_comment_with_replies(updated_comment, {}, liked_ids, current_user.id)


@router.post("/comment/{comment_id}/unlike")
def unlike_comment(
    comment_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
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
    # Pour un seul commentaire, on crée un dict vide pour les réponses
    liked_ids = set()  # L'utilisateur vient de retirer son like
    return serialize_comment_with_replies(updated_comment, {}, liked_ids, current_user.id)


@router.get("/comment/{comment_id}/replies")
def get_comment_replies(
    comment_id: int,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
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
    
    current_user_id = current_user.id if current_user else None
    
    # Récupérer tous les commentaires du contestant pour construire all_replies_map
    all_comments = db.query(Comment).options(
        joinedload(Comment.user)
    ).filter(
        Comment.contestant_id == comment.contestant_id,
        Comment.is_hidden == False
    ).all()
    
    # Créer un dictionnaire de toutes les réponses groupées par parent_id
    all_replies_map = {}
    for c in all_comments:
        if c.parent_id:
            if c.parent_id not in all_replies_map:
                all_replies_map[c.parent_id] = []
            all_replies_map[c.parent_id].append(c)
    
    # Récupérer les IDs des commentaires likés par l'utilisateur actuel
    liked_comment_ids = set()
    if current_user_id:
        liked_comments = db.query(Like.comment_id).filter(
            Like.user_id == current_user_id,
            Like.comment_id.in_([c.id for c in all_comments])
        ).all()
        liked_comment_ids = {like[0] for like in liked_comments}
    
    return CommentListResponse(
        comments=[serialize_comment_with_replies(r, all_replies_map, liked_comment_ids, current_user_id) for r in replies],
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.get("/{contestant_id}/commenters")
def get_contestant_commenters(
    contestant_id: int,
    db: Session = Depends(deps.get_db)
):
    """Récupérer la liste des utilisateurs ayant commenté sur un contestant"""
    from app.models.comment import Comment
    from app.models.user import User
    from sqlalchemy import distinct
    
    # Récupérer les IDs uniques des utilisateurs ayant commenté
    user_ids = db.query(distinct(Comment.user_id)).filter(
        Comment.contestant_id == contestant_id,
        Comment.is_deleted == False
    ).all()
    
    # Récupérer les informations des utilisateurs
    users = db.query(User).filter(
        User.id.in_([uid[0] for uid in user_ids])
    ).all()
    
    return [
        {
            "id": user.id,
            "username": user.username or user.email.split("@")[0],
            "name": user.full_name or user.username or user.email.split("@")[0],
            "avatar_url": user.avatar_url
        }
        for user in users
    ]