from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, DateTime, Enum as SQLEnum, Table, Column, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.post import Post
    from app.models.media import Media


class GroupType(str, enum.Enum):
    """Types de groupes sociaux"""
    PUBLIC = "public"
    PRIVATE = "private"
    SECRET = "secret"


class GroupMemberRole(str, enum.Enum):
    """Rôles des membres dans un groupe"""
    MEMBER = "member"
    ADMIN = "admin"
    MODERATOR = "moderator"
    OWNER = "owner"


class SocialGroup(Base):
    """Modèle pour les groupes sociaux"""
    __tablename__ = "social_groups"
    
    # Informations du groupe
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_type: Mapped[GroupType] = mapped_column(SQLEnum(GroupType), default=GroupType.PRIVATE, nullable=False)
    
    # Créateur du groupe
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Métadonnées
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Configuration
    max_members: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = illimité
    invite_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Statistiques
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id], back_populates="created_groups")
    members: Mapped[List["GroupMember"]] = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="group")
    messages: Mapped[List["GroupMessage"]] = relationship("GroupMessage", back_populates="group", cascade="all, delete-orphan")
    join_requests: Mapped[List["GroupJoinRequest"]] = relationship("GroupJoinRequest", back_populates="group", cascade="all, delete-orphan")
    conversation: Mapped[Optional["PrivateConversation"]] = relationship("PrivateConversation", back_populates="group")
    invitations: Mapped[List["GroupInvitation"]] = relationship("GroupInvitation", foreign_keys="GroupInvitation.group_id", back_populates="group")


class GroupMember(Base):
    """Membres d'un groupe social"""
    __tablename__ = "group_members"
    
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("social_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Rôle dans le groupe
    role: Mapped[GroupMemberRole] = mapped_column(SQLEnum(GroupMemberRole), default=GroupMemberRole.MEMBER, nullable=False)
    
    # Métadonnées
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Contrainte unique pour éviter les doublons
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )
    
    # Relations
    group: Mapped["SocialGroup"] = relationship("SocialGroup", back_populates="members")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="group_memberships")


class GroupJoinRequest(Base):
    """Demandes d'adhésion à un groupe"""
    __tablename__ = "group_join_requests"
    
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("social_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Message de la demande
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Statut
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    
    # Révision
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    group: Mapped["SocialGroup"] = relationship("SocialGroup", back_populates="join_requests")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])


class MessageType(str, enum.Enum):
    """Types de messages"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"
    AUDIO = "audio"
    SYSTEM = "system"  # Messages système (membre ajouté, etc.)


class MessageStatus(str, enum.Enum):
    """Statut des messages"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"


class GroupMessage(Base):
    """Messages dans un groupe"""
    __tablename__ = "group_messages"
    
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("social_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenu
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType), default=MessageType.TEXT, nullable=False)
    
    # Média associé (si message_type est image, video, etc.)
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    
    # Référence à un message parent (pour les réponses)
    reply_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("group_messages.id", ondelete="SET NULL"), nullable=True)
    
    # Statut
    status: Mapped[MessageStatus] = mapped_column(SQLEnum(MessageStatus), default=MessageStatus.SENT, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Métadonnées
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    group: Mapped["SocialGroup"] = relationship("SocialGroup", back_populates="messages")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id], back_populates="group_messages")
    media: Mapped[Optional["Media"]] = relationship("Media")
    reply_to: Mapped[Optional["GroupMessage"]] = relationship("GroupMessage", remote_side="GroupMessage.id", back_populates="replies")
    replies: Mapped[List["GroupMessage"]] = relationship("GroupMessage", back_populates="reply_to")
    read_receipts: Mapped[List["MessageReadReceipt"]] = relationship("MessageReadReceipt", back_populates="message", cascade="all, delete-orphan")


class MessageReadReceipt(Base):
    """Reçus de lecture des messages"""
    __tablename__ = "message_read_receipts"
    
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("group_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    read_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relations
    message: Mapped["GroupMessage"] = relationship("GroupMessage", back_populates="read_receipts")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

