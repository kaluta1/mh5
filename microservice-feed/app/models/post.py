"""
Posts Models
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SQLEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
import enum

from app.core.database import Base


class PostType(str, enum.Enum):
    """Post content types"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    POLL = "poll"


class PostVisibility(str, enum.Enum):
    """Post visibility"""
    PUBLIC = "public"
    FOLLOWERS = "followers"
    PRIVATE = "private"
    GROUP = "group"


class ReactionType(str, enum.Enum):
    """Reaction types"""
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class Post(Base):
    """Post model"""
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    author_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Content
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_type: Mapped[PostType] = mapped_column(SQLEnum(PostType), default=PostType.TEXT, nullable=False)
    visibility: Mapped[PostVisibility] = mapped_column(SQLEnum(PostVisibility), default=PostVisibility.PUBLIC, nullable=False)
    
    # Group reference
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("social_groups.id"), nullable=True, index=True)
    
    # Metadata
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Statistics
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Moderation
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    group: Mapped[Optional["SocialGroup"]] = relationship("SocialGroup", back_populates="posts")
    media: Mapped[list["PostMedia"]] = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[list["PostComment"]] = relationship("PostComment", back_populates="post", cascade="all, delete-orphan")
    reactions: Mapped[list["PostReaction"]] = relationship("PostReaction", back_populates="post", cascade="all, delete-orphan")


class PostMedia(Base):
    """Post media model"""
    __tablename__ = "post_media"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # S3 URL
    media_url: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, video, etc.
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="media")


class PostComment(Base):
    """Post comment model"""
    __tablename__ = "post_comments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Parent comment for replies
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=True)
    
    # Statistics
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Moderation
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    parent: Mapped[Optional["PostComment"]] = relationship("PostComment", remote_side="PostComment.id")


class PostReaction(Base):
    """Post reaction model"""
    __tablename__ = "post_reactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    reaction_type: Mapped[ReactionType] = mapped_column(SQLEnum(ReactionType), default=ReactionType.LIKE, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="reactions")
    
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_reaction_user"),
    )
