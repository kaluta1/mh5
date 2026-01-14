"""
Private Messages Models with E2E Encryption
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SQLEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
import enum

from app.core.database import Base


class MessageType(str, enum.Enum):
    """Message content types"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"
    AUDIO = "audio"
    SYSTEM = "system"


class MessageStatus(str, enum.Enum):
    """Message delivery status"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"


class ConversationType(str, enum.Enum):
    """Conversation types"""
    DIRECT = "direct"  # 1-on-1
    GROUP = "group"    # Group chat


class PrivateConversation(Base):
    """Private conversation model"""
    __tablename__ = "private_conversations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_type: Mapped[ConversationType] = mapped_column(SQLEnum(ConversationType), default=ConversationType.DIRECT, nullable=False)
    
    # For direct conversations (1-on-1)
    user1_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    user2_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    # For group conversations
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("social_groups.id"), nullable=True, index=True)
    
    # Last message info
    last_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id"), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Statistics
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unread_count_user1: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unread_count_user2: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    group: Mapped[Optional["SocialGroup"]] = relationship("SocialGroup", back_populates="conversations")
    messages: Mapped[list["PrivateMessage"]] = relationship("PrivateMessage", back_populates="conversation", cascade="all, delete-orphan")
    participants: Mapped[list["ConversationParticipant"]] = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")


class ConversationParticipant(Base):
    """Conversation participants (for group chats)"""
    __tablename__ = "conversation_participants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Metadata
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Notifications
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_read_message_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id"), nullable=True)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    conversation: Mapped["PrivateConversation"] = relationship("PrivateConversation", back_populates="participants")
    
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
    )


class PrivateMessage(Base):
    """Private message model with E2E encryption"""
    __tablename__ = "private_messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Encrypted content (base64)
    encrypted_content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Message metadata (not encrypted)
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType), default=MessageType.TEXT, nullable=False)
    
    # Media file URL (stored in S3, encrypted)
    media_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Reply to message
    reply_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("private_messages.id", ondelete="SET NULL"), nullable=True)
    
    # Status
    status: Mapped[MessageStatus] = mapped_column(SQLEnum(MessageStatus), default=MessageStatus.SENT, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    conversation: Mapped["PrivateConversation"] = relationship("PrivateConversation", back_populates="messages")
    reply_to: Mapped[Optional["PrivateMessage"]] = relationship("PrivateMessage", remote_side="PrivateMessage.id", foreign_keys=[reply_to_id])
    read_receipts: Mapped[list["MessageReadReceipt"]] = relationship("MessageReadReceipt", back_populates="message", cascade="all, delete-orphan")


class MessageReadReceipt(Base):
    """Message read receipts"""
    __tablename__ = "message_read_receipts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("private_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    read_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    message: Mapped["PrivateMessage"] = relationship("PrivateMessage", back_populates="read_receipts")
    
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_read_receipt"),
    )
