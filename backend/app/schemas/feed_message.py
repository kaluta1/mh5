"""
Message Schemas for Feed System
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.social_group import MessageType
from app.models.private_message import PrivateMessageStatus as MessageStatus


class SendMessageRequest(BaseModel):
    """Schema for sending a message"""
    recipient_id: int = Field(..., gt=0)
    content: str = Field(..., min_length=1)
    message_type: MessageType = MessageType.TEXT
    media_url: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageCreate(BaseModel):
    """Schema for creating a message"""
    conversation_id: int
    content: str
    message_type: MessageType = MessageType.TEXT
    media_url: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageResponse(BaseModel):
    """Schema for message response (encrypted)"""
    id: int
    conversation_id: int
    sender_id: int
    encrypted_content: str  # Encrypted content
    message_type: MessageType
    media_url: Optional[str]
    reply_to_id: Optional[int]
    status: MessageStatus
    is_edited: bool
    is_deleted: bool
    created_at: datetime
    edited_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DecryptedMessageResponse(BaseModel):
    """Schema for decrypted message response"""
    id: int
    conversation_id: int
    sender_id: int
    content: str  # Decrypted content
    message_type: MessageType
    media_url: Optional[str]
    reply_to_id: Optional[int]
    status: MessageStatus
    is_edited: bool
    created_at: datetime
    edited_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """Schema for conversation response"""
    id: int
    conversation_type: str
    user1_id: Optional[int]
    user2_id: Optional[int]
    group_id: Optional[int]
    last_message_id: Optional[int]
    last_message_at: Optional[datetime]
    message_count: int
    unread_count_user1: int
    unread_count_user2: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
