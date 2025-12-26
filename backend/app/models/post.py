from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, DateTime, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.media import Media


class PostType(str, enum.Enum):
    """Types de posts sociaux"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    POLL = "poll"


class PostVisibility(str, enum.Enum):
    """Visibilité des posts"""
    PUBLIC = "public"
    FOLLOWERS = "followers"
    PRIVATE = "private"
    GROUP = "group"


class Post(Base):
    """Modèle pour les posts sociaux"""
    __tablename__ = "posts"
    
    # Auteur du post
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenu du post
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_type: Mapped[PostType] = mapped_column(SQLEnum(PostType), default=PostType.TEXT, nullable=False)
    visibility: Mapped[PostVisibility] = mapped_column(SQLEnum(PostVisibility), default=PostVisibility.PUBLIC, nullable=False)
    
    # Référence à un groupe si le post est dans un groupe
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("social_groups.id"), nullable=True, index=True)
    
    # Métadonnées
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Tags séparés par des virgules
    
    # Statistiques (mis à jour via triggers ou application)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Modération
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id], back_populates="posts")
    group: Mapped[Optional["SocialGroup"]] = relationship("SocialGroup", back_populates="posts")
    media: Mapped[List["PostMedia"]] = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[List["PostComment"]] = relationship("PostComment", back_populates="post", cascade="all, delete-orphan")
    reactions: Mapped[List["PostReaction"]] = relationship("PostReaction", back_populates="post", cascade="all, delete-orphan")
    shares: Mapped[List["PostShare"]] = relationship("PostShare", back_populates="post", cascade="all, delete-orphan")


class PostMedia(Base):
    """Médias associés à un post"""
    __tablename__ = "post_media"
    
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Ordre d'affichage
    
    # Relations
    post: Mapped["Post"] = relationship("Post", back_populates="media")
    media: Mapped["Media"] = relationship("Media")


class PostComment(Base):
    """Commentaires sur les posts"""
    __tablename__ = "post_comments"
    
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenu
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Commentaire parent pour les réponses
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=True)
    
    # Statistiques
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Modération
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id], back_populates="post_comments")
    parent: Mapped[Optional["PostComment"]] = relationship("PostComment", remote_side="PostComment.id", back_populates="replies")
    replies: Mapped[List["PostComment"]] = relationship("PostComment", back_populates="parent", cascade="all, delete-orphan")
    reactions: Mapped[List["PostCommentReaction"]] = relationship("PostCommentReaction", back_populates="comment", cascade="all, delete-orphan")


class ReactionType(str, enum.Enum):
    """Types de réactions"""
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class PostReaction(Base):
    """Réactions sur les posts"""
    __tablename__ = "post_reactions"
    
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction_type: Mapped[ReactionType] = mapped_column(SQLEnum(ReactionType), default=ReactionType.LIKE, nullable=False)
    
    # Contrainte unique pour éviter les doublons
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_reaction_user"),
    )
    
    # Relations
    post: Mapped["Post"] = relationship("Post", back_populates="reactions")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="post_reactions")


class PostCommentReaction(Base):
    """Réactions sur les commentaires de posts"""
    __tablename__ = "post_comment_reactions"
    
    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reaction_type: Mapped[ReactionType] = mapped_column(SQLEnum(ReactionType), default=ReactionType.LIKE, nullable=False)
    
    # Contrainte unique pour éviter les doublons
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_post_comment_reaction_user"),
    )
    
    # Relations
    comment: Mapped["PostComment"] = relationship("PostComment", back_populates="reactions")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class PostShare(Base):
    """Partages de posts"""
    __tablename__ = "post_shares"
    
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Commentaire optionnel lors du partage
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Contrainte unique pour éviter les doublons
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_share_user"),
    )
    
    # Relations
    post: Mapped["Post"] = relationship("Post", back_populates="shares")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="post_shares")

