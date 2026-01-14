"""
Social Groups Models
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SQLEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from app.core.database import Base


class GroupType(str, enum.Enum):
    """Group visibility types"""
    PUBLIC = "public"
    PRIVATE = "private"
    SECRET = "secret"


class GroupMemberRole(str, enum.Enum):
    """Member roles in a group"""
    MEMBER = "member"
    ADMIN = "admin"
    MODERATOR = "moderator"
    OWNER = "owner"


class SocialGroup(Base):
    """Social group model"""
    __tablename__ = "social_groups"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    group_type: Mapped[GroupType] = mapped_column(SQLEnum(GroupType), default=GroupType.PRIVATE, nullable=False)
    
    # Creator from main platform
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Media URLs (stored in S3)
    avatar_url: Mapped[str] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[str] = mapped_column(String(512), nullable=True)
    
    # Configuration
    max_members: Mapped[int] = mapped_column(Integer, nullable=True)
    invite_code: Mapped[str] = mapped_column(String(50), nullable=True, unique=True, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Statistics
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    members: Mapped[list["GroupMember"]] = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="group")
    conversations: Mapped[list["PrivateConversation"]] = relationship("PrivateConversation", back_populates="group")


class GroupMember(Base):
    """Group member model"""
    __tablename__ = "group_members"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("social_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    role: Mapped[GroupMemberRole] = mapped_column(SQLEnum(GroupMemberRole), default=GroupMemberRole.MEMBER, nullable=False)
    
    # Metadata
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    group: Mapped["SocialGroup"] = relationship("SocialGroup", back_populates="members")
    
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )
