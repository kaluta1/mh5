from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, DateTime, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.media import Media
    from app.models.social_group import SocialGroup


class ConversationType(str, enum.Enum):
    """Types de conversations"""
    DIRECT = "direct"  # Conversation 1-1
    GROUP = "group"   # Conversation de groupe


class PrivateMessageStatus(str, enum.Enum):
    """Statut des messages privés"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"


class PrivateConversation(Base):
    """Conversation privée entre utilisateurs"""
    __tablename__ = "private_conversations"
    
    # Type de conversation
    conversation_type: Mapped[ConversationType] = mapped_column(
        SQLEnum(ConversationType), 
        default=ConversationType.DIRECT, 
        nullable=False
    )
    
    # Pour les conversations directes (1-1)
    user1_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    user2_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Pour les conversations de groupe
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("social_groups.id"), nullable=True, index=True)
    
    # Métadonnées
    last_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id"), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Statistiques
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unread_count_user1: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unread_count_user2: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relations
    user1: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user1_id], back_populates="conversations_as_user1")
    user2: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user2_id], back_populates="conversations_as_user2")
    group: Mapped[Optional["SocialGroup"]] = relationship("SocialGroup", back_populates="conversation")
    messages: Mapped[List["PrivateMessage"]] = relationship(
        "PrivateMessage", 
        foreign_keys="PrivateMessage.conversation_id",
        back_populates="conversation", 
        cascade="all, delete-orphan"
    )
    last_message: Mapped[Optional["PrivateMessage"]] = relationship(
        "PrivateMessage", 
        foreign_keys=[last_message_id], 
        post_update=True,
        viewonly=True
    )
    participants: Mapped[List["ConversationParticipant"]] = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")


class ConversationParticipant(Base):
    """Participants d'une conversation (pour les groupes)"""
    __tablename__ = "conversation_participants"
    
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Métadonnées
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Notifications
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_read_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id"), nullable=True)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Contrainte unique
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
    )
    
    # Relations
    conversation: Mapped["PrivateConversation"] = relationship("PrivateConversation", back_populates="participants")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="conversation_participations")
    last_read_message: Mapped[Optional["PrivateMessage"]] = relationship("PrivateMessage", foreign_keys=[last_read_message_id])


class PrivateMessage(Base):
    """Message privé dans une conversation"""
    __tablename__ = "private_messages"
    
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenu
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender_encrypted_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text, image, video, file, audio
    
    # Média associé
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    
    # Référence à un message parent (pour les réponses)
    reply_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id", ondelete="SET NULL"), nullable=True)
    
    # Statut
    status: Mapped[PrivateMessageStatus] = mapped_column(SQLEnum(PrivateMessageStatus), default=PrivateMessageStatus.SENT, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Métadonnées
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    conversation: Mapped["PrivateConversation"] = relationship(
        "PrivateConversation", 
        foreign_keys=[conversation_id],
        back_populates="messages",
        overlaps="last_message"
    )
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id], back_populates="sent_private_messages")
    media: Mapped[Optional["Media"]] = relationship("Media")
    reply_to: Mapped[Optional["PrivateMessage"]] = relationship("PrivateMessage", remote_side="PrivateMessage.id", foreign_keys=[reply_to_id], back_populates="replies")
    replies: Mapped[List["PrivateMessage"]] = relationship("PrivateMessage", foreign_keys="PrivateMessage.reply_to_id", back_populates="reply_to")
    read_receipts: Mapped[List["PrivateMessageReadReceipt"]] = relationship("PrivateMessageReadReceipt", back_populates="message", cascade="all, delete-orphan")


class PrivateMessageReadReceipt(Base):
    """Reçus de lecture des messages privés"""
    __tablename__ = "private_message_read_receipts"
    
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    read_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Contrainte unique
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_private_message_read_receipt"),
    )
    
    # Relations
    message: Mapped["PrivateMessage"] = relationship("PrivateMessage", back_populates="read_receipts")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class GroupInvitation(Base):
    """Invitations à rejoindre un groupe"""
    __tablename__ = "group_invitations"
    
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("social_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    inviter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    invitee_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Message d'invitation
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Statut
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, accepted, rejected, cancelled
    
    # Dates
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    group: Mapped["SocialGroup"] = relationship("SocialGroup", foreign_keys=[group_id], back_populates="invitations")
    inviter: Mapped["User"] = relationship("User", foreign_keys=[inviter_id], back_populates="sent_group_invitations")
    invitee: Mapped["User"] = relationship("User", foreign_keys=[invitee_id], back_populates="received_group_invitations")

