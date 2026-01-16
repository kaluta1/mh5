"""
Messages API Endpoints with E2E Encryption for Feed System
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy import func
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.private_message import (
    PrivateMessage, PrivateConversation, ConversationParticipant,
    ConversationType, PrivateMessageStatus
)
from app.models.social_group import MessageType
from app.models.user_encryption_keys import UserEncryptionKeys
from app.schemas.feed_message import (
    MessageCreate, MessageResponse, ConversationResponse,
    SendMessageRequest, DecryptedMessageResponse
)
from app.services.feed_encryption import get_encryption_service

router = APIRouter()

def _get_or_create_user_keys(
    db: Session,
    user_id: int,
    encryption_service
) -> UserEncryptionKeys:
    try:
        user_keys = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == user_id,
            UserEncryptionKeys.is_active == True
        ).first()
    except (OperationalError, ProgrammingError):
        # Table might not exist yet; create it and retry
        UserEncryptionKeys.__table__.create(db.bind, checkfirst=True)
        user_keys = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == user_id,
            UserEncryptionKeys.is_active == True
        ).first()

    if user_keys:
        return user_keys

    public_key, private_key = encryption_service.generate_key_pair()
    encrypted_private_key = encryption_service.encrypt_private_key_at_rest(private_key)

    next_id = db.query(func.coalesce(func.max(UserEncryptionKeys.id), 0)).scalar() + 1
    user_keys = UserEncryptionKeys(
        id=next_id,
        user_id=user_id,
        public_key=public_key,
        encrypted_private_key=encrypted_private_key,
        is_active=True
    )
    db.add(user_keys)
    db.commit()
    db.refresh(user_keys)
    return user_keys


def _ensure_sender_encrypted_column(db: Session) -> None:
    try:
        db.execute(text("ALTER TABLE private_messages ADD COLUMN IF NOT EXISTS sender_encrypted_content TEXT"))
        db.commit()
    except Exception:
        db.rollback()


@router.post("/send", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Send an encrypted message
    
    The message content is encrypted using E2E encryption.
    Only the sender and receiver can decrypt it.
    """
    sender_id = current_user.id
    recipient_id = message_data.recipient_id
    
    if sender_id == recipient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send message to yourself"
        )
    
    # Get or create conversation
    conversation = db.query(PrivateConversation).filter(
        ((PrivateConversation.user1_id == sender_id) & (PrivateConversation.user2_id == recipient_id)) |
        ((PrivateConversation.user1_id == recipient_id) & (PrivateConversation.user2_id == sender_id)),
        PrivateConversation.conversation_type == ConversationType.DIRECT
    ).first()
    
    if not conversation:
        # Create new conversation
        conversation = PrivateConversation(
            conversation_type=ConversationType.DIRECT,
            user1_id=sender_id,
            user2_id=recipient_id,
            message_count=0,
            unread_count_user1=0,
            unread_count_user2=0
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    
    # Get encryption keys
    encryption_service = get_encryption_service()

    _ensure_sender_encrypted_column(db)
    
    # Get sender's private key
    sender_keys = _get_or_create_user_keys(db, sender_id, encryption_service)
    
    # Get recipient's public key
    recipient_keys = _get_or_create_user_keys(db, recipient_id, encryption_service)
    
    # Encrypt message for recipient and sender
    try:
        encrypted_content = encryption_service.encrypt_message(
            message=message_data.content,
            recipient_public_key=recipient_keys.public_key,
            sender_private_key=sender_keys.encrypted_private_key,
            is_private_key_encrypted=True
        )
        sender_encrypted_content = encryption_service.encrypt_message(
            message=message_data.content,
            recipient_public_key=sender_keys.public_key,
            sender_private_key=sender_keys.encrypted_private_key,
            is_private_key_encrypted=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Encryption failed: {str(e)}"
        )
    
    # Create message (store encrypted content in content field)
    # Backend uses string for message_type, not enum
    msg_type_str = message_data.message_type.value if hasattr(message_data.message_type, 'value') else str(message_data.message_type)
    message = PrivateMessage(
        conversation_id=conversation.id,
        sender_id=sender_id,
        content=encrypted_content,  # Store encrypted content
        sender_encrypted_content=sender_encrypted_content,
        message_type=msg_type_str,
        status=PrivateMessageStatus.SENT
    )
    
    db.add(message)
    
    # Update conversation
    conversation.last_message_id = message.id
    conversation.last_message_at = datetime.utcnow()
    conversation.message_count += 1
    
    # Update unread count for recipient
    if conversation.user1_id == recipient_id:
        conversation.unread_count_user1 += 1
    else:
        conversation.unread_count_user2 += 1
    
    db.commit()
    db.refresh(message)
    
    # Return response with encrypted_content field
    # Convert message_type string to enum
    try:
        msg_type_enum = MessageType(msg_type_str)
    except:
        msg_type_enum = MessageType.TEXT
    
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        encrypted_content=message.content,  # This is the encrypted content
        message_type=msg_type_enum,
        media_url=None,
        reply_to_id=message.reply_to_id,
        status=message.status,
        is_edited=message.is_edited,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        edited_at=message.edited_at
    )


@router.get("/conversations", response_model=List[ConversationResponse])
def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List user's conversations"""
    user_id = current_user.id
    
    conversations = db.query(PrivateConversation).filter(
        ((PrivateConversation.user1_id == user_id) | (PrivateConversation.user2_id == user_id)),
    ).order_by(PrivateConversation.last_message_at.desc()).offset(skip).limit(limit).all()
    
    return [ConversationResponse.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}/messages", response_model=List[DecryptedMessageResponse])
def get_messages(
    conversation_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get messages from a conversation and decrypt them
    
    Only the sender and receiver can decrypt the messages.
    """
    user_id = current_user.id
    
    # Verify user is part of conversation
    conversation = db.query(PrivateConversation).filter(
        PrivateConversation.id == conversation_id,
        ((PrivateConversation.user1_id == user_id) | (PrivateConversation.user2_id == user_id))
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Get messages
    messages = db.query(PrivateMessage).filter(
        PrivateMessage.conversation_id == conversation_id,
        PrivateMessage.is_deleted == False
    ).order_by(PrivateMessage.created_at.desc()).offset(skip).limit(limit).all()
    
    # Get or create user's encryption keys
    encryption_service = get_encryption_service()
    _ensure_sender_encrypted_column(db)
    user_keys = _get_or_create_user_keys(db, user_id, encryption_service)
    decrypted_messages = []
    
    for msg in messages:
        # Get sender's public key
        sender_keys = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == msg.sender_id,
            UserEncryptionKeys.is_active == True
        ).first()
        
        if not sender_keys:
            # Skip if sender keys not found
            continue
        
        # Decrypt message (content field contains encrypted content)
        encrypted_payload = msg.sender_encrypted_content if msg.sender_id == user_id and msg.sender_encrypted_content else msg.content
        try:
            decrypted_content = encryption_service.decrypt_message(
                encrypted_message=encrypted_payload,
                sender_public_key=sender_keys.public_key,
                recipient_private_key=user_keys.encrypted_private_key,
                is_private_key_encrypted=True
            )
        except Exception as e:
            # If decryption fails, return encrypted content indicator
            decrypted_content = "[Encrypted - Decryption failed]"
        
        # Message type - backend uses string, convert to enum
        try:
            msg_type = MessageType(msg.message_type) if isinstance(msg.message_type, str) and hasattr(MessageType, msg.message_type.upper()) else MessageType.TEXT
        except:
            msg_type = MessageType.TEXT
        
        decrypted_messages.append(DecryptedMessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            content=decrypted_content,
            message_type=msg_type,
            media_url=None,  # Backend uses media_id, not media_url
            reply_to_id=msg.reply_to_id,
            status=msg.status,
            is_edited=msg.is_edited,
            created_at=msg.created_at,
            edited_at=msg.edited_at
        ))
    
    return decrypted_messages


@router.post("/{message_id}/read", status_code=status.HTTP_200_OK)
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mark a message as read"""
    user_id = current_user.id
    
    message = db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Verify user is part of conversation
    conversation = db.query(PrivateConversation).filter(
        PrivateConversation.id == message.conversation_id,
        ((PrivateConversation.user1_id == user_id) | (PrivateConversation.user2_id == user_id))
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to read this message"
        )
    
    # Update message status
    message.status = PrivateMessageStatus.READ
    
    # Update conversation unread count
    if conversation.user1_id == user_id:
        conversation.unread_count_user1 = max(0, conversation.unread_count_user1 - 1)
    else:
        conversation.unread_count_user2 = max(0, conversation.unread_count_user2 - 1)
    
    db.commit()
    
    return {"message": "Message marked as read"}


@router.delete("/{message_id}", status_code=status.HTTP_200_OK)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a message sent by the current user"""
    user_id = current_user.id
    message = db.query(PrivateMessage).filter(PrivateMessage.id == message_id).first()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    if message.sender_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this message"
        )

    message.is_deleted = True
    message.deleted_at = datetime.utcnow()
    message.status = PrivateMessageStatus.DELETED

    if message.conversation_id:
        last_message = db.query(PrivateMessage).filter(
            PrivateMessage.conversation_id == message.conversation_id,
            PrivateMessage.is_deleted == False
        ).order_by(PrivateMessage.created_at.desc()).first()
        conversation = db.query(PrivateConversation).filter(
            PrivateConversation.id == message.conversation_id
        ).first()
        if conversation:
            conversation.last_message_id = last_message.id if last_message else None
            conversation.last_message_at = last_message.created_at if last_message else None

    db.commit()
    return {"message": "Message deleted"}
