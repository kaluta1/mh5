from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models.comment import Comment, Like
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentUpdate
from typing import Optional, List
from datetime import datetime


class CommentCRUD:
    
    @staticmethod
    def create_comment(
        db: Session,
        user_id: int,
        content: str,
        media_id: Optional[int] = None,
        contestant_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ) -> Comment:
        """Créer un nouveau commentaire"""
        comment = Comment(
            user_id=user_id,
            content=content,
            media_id=media_id,
            contestant_id=contestant_id,
            parent_id=parent_id
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return comment

    @staticmethod
    def get_comment(db: Session, comment_id: int) -> Optional[Comment]:
        """Récupérer un commentaire par ID"""
        return db.query(Comment).filter(Comment.id == comment_id).first()

    @staticmethod
    def get_comments_by_media(
        db: Session,
        media_id: int,
        skip: int = 0,
        limit: int = 50,
        parent_id: Optional[int] = None
    ) -> tuple[List[Comment], int]:
        """Récupérer les commentaires d'un média"""
        query = db.query(Comment).filter(
            and_(
                Comment.media_id == media_id,
                Comment.is_hidden == False,
                Comment.parent_id == parent_id
            )
        ).order_by(Comment.created_at.desc())
        
        total = query.count()
        comments = query.offset(skip).limit(limit).all()
        return comments, total

    @staticmethod
    def get_comments_by_contestant(
        db: Session,
        contestant_id: int,
        skip: int = 0,
        limit: int = 50,
        parent_id: Optional[int] = None
    ) -> tuple[List[Comment], int]:
        """Récupérer les commentaires d'un contestant"""
        query = db.query(Comment).filter(
            and_(
                Comment.contestant_id == contestant_id,
                Comment.is_hidden == False,
                Comment.parent_id == parent_id
            )
        ).order_by(Comment.created_at.desc())
        
        total = query.count()
        comments = query.offset(skip).limit(limit).all()
        return comments, total

    @staticmethod
    def get_replies(
        db: Session,
        parent_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[Comment], int]:
        """Récupérer les réponses à un commentaire"""
        query = db.query(Comment).filter(
            and_(
                Comment.parent_id == parent_id,
                Comment.is_hidden == False
            )
        ).order_by(Comment.created_at.asc())
        
        total = query.count()
        replies = query.offset(skip).limit(limit).all()
        return replies, total

    @staticmethod
    def update_comment(
        db: Session,
        comment_id: int,
        content: str
    ) -> Optional[Comment]:
        """Mettre à jour un commentaire"""
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if comment:
            comment.content = content
            comment.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(comment)
        return comment

    @staticmethod
    def delete_comment(db: Session, comment_id: int) -> bool:
        """Supprimer un commentaire (soft delete)"""
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if comment:
            comment.is_hidden = True
            db.commit()
            return True
        return False

    @staticmethod
    def like_comment(db: Session, user_id: int, comment_id: int) -> Like:
        """Liker un commentaire"""
        # Vérifier si le like existe déjà
        existing_like = db.query(Like).filter(
            and_(
                Like.user_id == user_id,
                Like.comment_id == comment_id
            )
        ).first()
        
        if existing_like:
            return existing_like
        
        # Créer le like
        like = Like(user_id=user_id, comment_id=comment_id)
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if comment:
            comment.like_count += 1
        
        db.add(like)
        db.commit()
        db.refresh(like)
        return like

    @staticmethod
    def unlike_comment(db: Session, user_id: int, comment_id: int) -> bool:
        """Retirer le like d'un commentaire"""
        like = db.query(Like).filter(
            and_(
                Like.user_id == user_id,
                Like.comment_id == comment_id
            )
        ).first()
        
        if like:
            comment = db.query(Comment).filter(Comment.id == comment_id).first()
            if comment and comment.like_count > 0:
                comment.like_count -= 1
            
            db.delete(like)
            db.commit()
            return True
        return False

    @staticmethod
    def is_comment_liked(db: Session, user_id: int, comment_id: int) -> bool:
        """Vérifier si un utilisateur a liké un commentaire"""
        like = db.query(Like).filter(
            and_(
                Like.user_id == user_id,
                Like.comment_id == comment_id
            )
        ).first()
        return like is not None

    @staticmethod
    def flag_comment(db: Session, comment_id: int) -> Optional[Comment]:
        """Signaler un commentaire"""
        comment = db.query(Comment).filter(Comment.id == comment_id).first()
        if comment:
            comment.is_flagged = True
            db.commit()
            db.refresh(comment)
        return comment

    @staticmethod
    def get_user_comments(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[Comment], int]:
        """Récupérer tous les commentaires d'un utilisateur"""
        query = db.query(Comment).filter(
            Comment.user_id == user_id
        ).order_by(Comment.created_at.desc())
        
        total = query.count()
        comments = query.offset(skip).limit(limit).all()
        return comments, total


comment_crud = CommentCRUD()
