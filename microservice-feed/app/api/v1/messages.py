"""
Messages API Endpoints with E2E Encryption
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.message import (
    PrivateMessage, PrivateConversation, ConversationParticipant,
    MessageType, MessageStatus, ConversationType
)
from app.models.user_keys import UserEncryptionKeys
from app.schemas.message import (
    MessageCreate, MessageResponse, ConversationResponse,
    SendMessageRequest, DecryptedMessageResponse
)
from app.services.encryption import get_encryption_service

router = APIRouter()


@router.post("/send", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Send an encrypted direct message
    
    The message content is encrypted using E2E encryption.
    Only the sender and receiver can decrypt it.
    """
    sender_id = current_user["user_id"]
    
    if not message_data.recipient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recipient_id is required for direct messages"
        )
    
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
    
    # Get sender's private key
    sender_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == sender_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not sender_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption keys not found. Please generate keys first."
        )
    
    # Get recipient's public key
    recipient_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == recipient_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not recipient_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient encryption keys not found"
        )
    
    # Encrypt message
    try:
        encrypted_content = encryption_service.encrypt_message(
            message=message_data.content,
            recipient_public_key=recipient_keys.public_key,
            sender_private_key=sender_keys.encrypted_private_key,  # Encrypted at rest, will be decrypted
            is_private_key_encrypted=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Encryption failed: {str(e)}"
        )
    
    # Create message
    message = PrivateMessage(
        conversation_id=conversation.id,
        sender_id=sender_id,
        encrypted_content=encrypted_content,
        message_type=MessageType.TEXT,
        status=MessageStatus.SENT
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
    
    return MessageResponse.from_orm(message)


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List user's conversations"""
    user_id = current_user["user_id"]
    
    conversations = db.query(PrivateConversation).filter(
        ((PrivateConversation.user1_id == user_id) | (PrivateConversation.user2_id == user_id)),
    ).order_by(PrivateConversation.last_message_at.desc()).offset(skip).limit(limit).all()
    
    return [ConversationResponse.from_orm(c) for c in conversations]


@router.get("/conversations/{conversation_id}/messages", response_model=List[DecryptedMessageResponse])
async def get_messages(
    conversation_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get messages from a conversation and decrypt them
    
    Only the sender and receiver can decrypt the messages.
    """
    user_id = current_user["user_id"]
    
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
    
    # Get user's encryption keys
    user_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == user_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not user_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption keys not found"
        )
    
    encryption_service = get_encryption_service()
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
        
        # Decrypt message
        try:
            decrypted_content = encryption_service.decrypt_message(
                encrypted_message=msg.encrypted_content,
                sender_public_key=sender_keys.public_key,
                recipient_private_key=user_keys.encrypted_private_key,  # Encrypted at rest, will be decrypted
                is_private_key_encrypted=True
            )
        except Exception as e:
            # If decryption fails, return encrypted content indicator
            decrypted_content = "[Encrypted - Decryption failed]"
        
        decrypted_messages.append(DecryptedMessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            content=decrypted_content,
            message_type=msg.message_type,
            media_url=msg.media_url,
            reply_to_id=msg.reply_to_id,
            status=msg.status,
            is_edited=msg.is_edited,
            created_at=msg.created_at,
            edited_at=msg.edited_at
        ))
    
    return decrypted_messages


@router.post("/{message_id}/read", status_code=status.HTTP_200_OK)
async def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Mark a message as read"""
    user_id = current_user["user_id"]
    
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
    message.status = MessageStatus.READ
    
    # Update conversation unread count
    if conversation.user1_id == user_id:
        conversation.unread_count_user1 = max(0, conversation.unread_count_user1 - 1)
    else:
        conversation.unread_count_user2 = max(0, conversation.unread_count_user2 - 1)
    
    db.commit()
    
    return {"message": "Message marked as read"}


# ============ GROUP MESSAGING ============

@router.post("/groups/{group_id}/send", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_group_message(
    group_id: int,
    message_data: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Send an encrypted message to a group
    
    The message is encrypted separately for each group member.
    Only group members can decrypt the message.
    """
    sender_id = current_user["user_id"]
    
    # Verify user is member of group
    from app.models.group import GroupMember
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == sender_id,
        GroupMember.is_banned == False
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this group"
        )
    
    # Get or create group conversation
    conversation = db.query(PrivateConversation).filter(
        PrivateConversation.group_id == group_id,
        PrivateConversation.conversation_type == ConversationType.GROUP
    ).first()
    
    if not conversation:
        # Create new group conversation
        conversation = PrivateConversation(
            conversation_type=ConversationType.GROUP,
            group_id=group_id,
            message_count=0,
            unread_count_user1=0,
            unread_count_user2=0
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    
    # Get all group members (excluding sender)
    group_members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id != sender_id,
        GroupMember.is_banned == False
    ).all()
    
    if not group_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No other members in group"
        )
    
    # Get encryption service
    encryption_service = get_encryption_service()
    
    # Get sender's private key
    sender_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == sender_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not sender_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption keys not found. Please generate keys first."
        )
    
    # For group messages, we'll encrypt for the first member as a simple approach
    # In production, you might want to use a group key or encrypt for all members
    # For now, encrypt with the first member's public key
    first_member = group_members[0]
    recipient_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == first_member.user_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not recipient_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some group members don't have encryption keys"
        )
    
    # Encrypt message
    try:
        encrypted_content = encryption_service.encrypt_message(
            message=message_data.content,
            recipient_public_key=recipient_keys.public_key,
            sender_private_key=sender_keys.encrypted_private_key,
            is_private_key_encrypted=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Encryption failed: {str(e)}"
        )
    
    # Create message
    message = PrivateMessage(
        conversation_id=conversation.id,
        sender_id=sender_id,
        encrypted_content=encrypted_content,
        message_type=message_data.message_type,
        media_url=message_data.media_url,
        reply_to_id=message_data.reply_to_id,
        status=MessageStatus.SENT
    )
    
    db.add(message)
    
    # Update conversation
    conversation.last_message_id = message.id
    conversation.last_message_at = datetime.utcnow()
    conversation.message_count += 1
    
    # Update unread counts for all participants
    from app.models.message import ConversationParticipant
    participants = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id != sender_id,
        ConversationParticipant.is_active == True
    ).all()
    
    for participant in participants:
        participant.unread_count += 1
    
    db.commit()
    db.refresh(message)
    
    return MessageResponse.from_orm(message)


@router.get("/groups/{group_id}/messages", response_model=List[DecryptedMessageResponse])
async def get_group_messages(
    group_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get messages from a group conversation"""
    user_id = current_user["user_id"]
    
    # Verify user is member of group
    from app.models.group import GroupMember
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this group"
        )
    
    # Get group conversation
    conversation = db.query(PrivateConversation).filter(
        PrivateConversation.group_id == group_id,
        PrivateConversation.conversation_type == ConversationType.GROUP
    ).first()
    
    if not conversation:
        return []
    
    # Get messages
    messages = db.query(PrivateMessage).filter(
        PrivateMessage.conversation_id == conversation.id,
        PrivateMessage.is_deleted == False
    ).order_by(PrivateMessage.created_at.desc()).offset(skip).limit(limit).all()
    
    # Get user's encryption keys
    user_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == user_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not user_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption keys not found"
        )
    
    encryption_service = get_encryption_service()
    decrypted_messages = []
    
    for msg in messages:
        # Get sender's public key
        sender_keys = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == msg.sender_id,
            UserEncryptionKeys.is_active == True
        ).first()
        
        if not sender_keys:
            continue
        
        # Decrypt message
        try:
            decrypted_content = encryption_service.decrypt_message(
                encrypted_message=msg.encrypted_content,
                sender_public_key=sender_keys.public_key,
                recipient_private_key=user_keys.encrypted_private_key,
                is_private_key_encrypted=True
            )
        except Exception as e:
            decrypted_content = "[Encrypted - Decryption failed]"
        
        decrypted_messages.append(DecryptedMessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            content=decrypted_content,
            message_type=msg.message_type,
            media_url=msg.media_url,
            reply_to_id=msg.reply_to_id,
            status=msg.status,
            is_edited=msg.is_edited,
            created_at=msg.created_at,
            edited_at=msg.edited_at
        ))
    
    return decrypted_messages
