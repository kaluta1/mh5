from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
import asyncio

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.private_message import ConversationParticipant
from app.schemas.social import (
    PrivateMessageCreate, PrivateMessageUpdate, PrivateMessageResponse, PrivateMessageListResponse,
    PrivateConversationResponse, ConversationListResponse,
    GroupInvitationCreate, GroupInvitationResponse, GroupInvitationListResponse
)
from app.crud.crud_private_message import (
    crud_private_conversation, crud_private_message, crud_group_invitation
)
from app.crud.crud_social import crud_social_group
from app.services.social_socket import social_socket_service

router = APIRouter()


# ============ CONVERSATIONS ============

@router.get("/conversations", response_model=ConversationListResponse)
def get_conversations(
    *,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer toutes les conversations de l'utilisateur"""
    conversations = crud_private_conversation.get_user_conversations(
        db, 
        user_id=current_user.id, 
        skip=skip, 
        limit=limit
    )
    
    result = []
    for conv in conversations:
        conv_dict = {
            "id": conv.id,
            "conversation_type": conv.conversation_type,
            "user1_id": conv.user1_id,
            "user2_id": conv.user2_id,
            "group_id": conv.group_id,
            "last_message_id": conv.last_message_id,
            "last_message_at": conv.last_message_at,
            "message_count": conv.message_count,
            "unread_count": 0,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "user1": {
                "id": conv.user1.id,
                "username": conv.user1.username,
                "avatar_url": conv.user1.avatar_url
            } if conv.user1 else None,
            "user2": {
                "id": conv.user2.id,
                "username": conv.user2.username,
                "avatar_url": conv.user2.avatar_url
            } if conv.user2 else None,
            "group": {
                "id": conv.group.id,
                "name": conv.group.name,
                "avatar_url": conv.group.avatar_url
            } if conv.group else None,
            "last_message": None,
            "participants": [],
            "other_user": None
        }
        
        # Calculer le nombre de non lus
        if conv.conversation_type.value == "direct":
            if conv.user1_id == current_user.id:
                conv_dict["unread_count"] = conv.unread_count_user1
                conv_dict["other_user"] = conv_dict["user2"]
            else:
                conv_dict["unread_count"] = conv.unread_count_user2
                conv_dict["other_user"] = conv_dict["user1"]
        else:
            # Pour les groupes
            participant = db.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.user_id == current_user.id
            ).first()
            if participant:
                conv_dict["unread_count"] = participant.unread_count
        
        # Ajouter le dernier message
        if conv.last_message:
            conv_dict["last_message"] = {
                "id": conv.last_message.id,
                "content": conv.last_message.content,
                "sender_id": conv.last_message.sender_id,
                "created_at": conv.last_message.created_at
            }
        
        # Ajouter les participants pour les groupes
        if conv.conversation_type.value == "group":
            for part in conv.participants:
                if part.is_active:
                    conv_dict["participants"].append({
                        "id": part.id,
                        "user_id": part.user_id,
                        "user": {
                            "id": part.user.id,
                            "username": part.user.username,
                            "avatar_url": part.user.avatar_url
                        } if part.user else None
                    })
        
        result.append(conv_dict)
    
    return {
        "conversations": result,
        "total": len(result),
        "page": skip // limit + 1,
        "page_size": limit,
        "has_next": len(result) == limit
    }


@router.get("/conversations/{conversation_id}", response_model=PrivateConversationResponse)
def get_conversation(
    *,
    db: Session = Depends(get_db),
    conversation_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer une conversation par son ID"""
    conversation = crud_private_conversation.get(db, conversation_id=conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation introuvable"
        )
    
    # Vérifier que l'utilisateur a accès à cette conversation
    has_access = False
    if conversation.conversation_type.value == "direct":
        has_access = (conversation.user1_id == current_user.id or 
                     conversation.user2_id == current_user.id)
    else:
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_active == True
        ).first()
        has_access = participant is not None
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé à cette conversation"
        )
    
    # Construire la réponse
    conv_dict = {
        "id": conversation.id,
        "conversation_type": conversation.conversation_type,
        "user1_id": conversation.user1_id,
        "user2_id": conversation.user2_id,
        "group_id": conversation.group_id,
        "last_message_id": conversation.last_message_id,
        "last_message_at": conversation.last_message_at,
        "message_count": conversation.message_count,
        "unread_count": 0,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "user1": {
            "id": conversation.user1.id,
            "username": conversation.user1.username,
            "avatar_url": conversation.user1.avatar_url
        } if conversation.user1 else None,
        "user2": {
            "id": conversation.user2.id,
            "username": conversation.user2.username,
            "avatar_url": conversation.user2.avatar_url
        } if conversation.user2 else None,
        "group": {
            "id": conversation.group.id,
            "name": conversation.group.name,
            "avatar_url": conversation.group.avatar_url
        } if conversation.group else None,
        "last_message": None,
        "participants": [],
        "other_user": None
    }
    
    if conversation.conversation_type.value == "direct":
        if conversation.user1_id == current_user.id:
            conv_dict["unread_count"] = conversation.unread_count_user1
            conv_dict["other_user"] = conv_dict["user2"]
        else:
            conv_dict["unread_count"] = conversation.unread_count_user2
            conv_dict["other_user"] = conv_dict["user1"]
    else:
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id
        ).first()
        if participant:
            conv_dict["unread_count"] = participant.unread_count
    
    if conversation.last_message:
        conv_dict["last_message"] = {
            "id": conversation.last_message.id,
            "content": conversation.last_message.content,
            "sender_id": conversation.last_message.sender_id,
            "created_at": conversation.last_message.created_at
        }
    
    return conv_dict


@router.post("/conversations/direct/{user_id}", response_model=PrivateConversationResponse, status_code=status.HTTP_201_CREATED)
def create_or_get_direct_conversation(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Créer ou récupérer une conversation directe avec un utilisateur"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas créer une conversation avec vous-même"
        )
    
    conversation = crud_private_conversation.get_or_create_direct(
        db,
        user1_id=current_user.id,
        user2_id=user_id
    )
    
    return conversation


# ============ MESSAGES PRIVÉS ============

@router.get("/conversations/{conversation_id}/messages", response_model=PrivateMessageListResponse)
def get_conversation_messages(
    *,
    db: Session = Depends(get_db),
    conversation_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=10),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer les messages d'une conversation"""
    conversation = crud_private_conversation.get(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation introuvable"
        )
    
    # Vérifier l'accès
    has_access = False
    if conversation.conversation_type.value == "direct":
        has_access = (conversation.user1_id == current_user.id or 
                     conversation.user2_id == current_user.id)
    else:
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_active == True
        ).first()
        has_access = participant is not None
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
    
    messages = crud_private_message.get_by_conversation(
        db,
        conversation_id=conversation_id,
        skip=skip,
        limit=limit
    )
    
    result = []
    for msg in messages:
        msg_dict = {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "content": msg.content,
            "message_type": msg.message_type,
            "media_id": msg.media_id,
            "reply_to_id": msg.reply_to_id,
            "status": msg.status,
            "is_edited": msg.is_edited,
            "is_deleted": msg.is_deleted,
            "edited_at": msg.edited_at,
            "deleted_at": msg.deleted_at,
            "created_at": msg.created_at,
            "updated_at": msg.updated_at,
            "sender": {
                "id": msg.sender.id,
                "username": msg.sender.username,
                "avatar_url": msg.sender.avatar_url
            } if msg.sender else None,
            "reply_to": None,
            "read_by": [r.user_id for r in msg.read_receipts]
        }
        
        if msg.reply_to:
            msg_dict["reply_to"] = {
                "id": msg.reply_to.id,
                "content": msg.reply_to.content,
                "sender_id": msg.reply_to.sender_id
            }
        
        result.append(msg_dict)
    
    return {
        "messages": result,
        "total": len(result),
        "page": skip // limit + 1,
        "page_size": limit,
        "has_next": len(result) == limit
    }


@router.post("/conversations/{conversation_id}/messages", response_model=PrivateMessageResponse, status_code=status.HTTP_201_CREATED)
def send_private_message(
    *,
    db: Session = Depends(get_db),
    conversation_id: int,
    message_in: PrivateMessageCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """Envoyer un message dans une conversation"""
    conversation = crud_private_conversation.get(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation introuvable"
        )
    
    # Vérifier l'accès
    has_access = False
    recipient_ids = []
    
    if conversation.conversation_type.value == "direct":
        has_access = (conversation.user1_id == current_user.id or 
                     conversation.user2_id == current_user.id)
        if has_access:
            if conversation.user1_id == current_user.id:
                recipient_ids = [conversation.user2_id] if conversation.user2_id else []
            else:
                recipient_ids = [conversation.user1_id] if conversation.user1_id else []
    else:
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_active == True
        ).first()
        has_access = participant is not None
        if has_access:
            # Récupérer tous les participants sauf l'expéditeur
            participants = db.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id != current_user.id,
                ConversationParticipant.is_active == True
            ).all()
            recipient_ids = [p.user_id for p in participants]
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
    
    message = crud_private_message.create(
        db,
        obj_in=message_in.dict(),
        conversation_id=conversation_id,
        sender_id=current_user.id
    )
    
    # Notifier tous les destinataires via Socket.IO
    def notify_message():
        try:
            for recipient_id in recipient_ids:
                asyncio.run(social_socket_service.emit_to_user(
                    recipient_id,
                    "new_private_message",
                    {
                        "conversation_id": conversation_id,
                        "message_id": message.id,
                        "sender_id": current_user.id,
                        "sender_name": current_user.username or "Utilisateur",
                        "content_preview": (message.content[:100] + "...") if message.content and len(message.content) > 100 else message.content
                    }
                ))
        except Exception as e:
            print(f"Erreur notification Socket.IO: {e}")
    
    background_tasks.add_task(notify_message)
    
    return message


@router.post("/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_message_read(
    *,
    db: Session = Depends(get_db),
    message_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Marquer un message comme lu"""
    success = crud_private_message.mark_as_read(db, message_id=message_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message introuvable"
        )


@router.post("/conversations/{conversation_id}/read", status_code=status.HTTP_200_OK)
def mark_conversation_read(
    *,
    db: Session = Depends(get_db),
    conversation_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Marquer tous les messages d'une conversation comme lus"""
    count = crud_private_message.mark_conversation_as_read(
        db,
        conversation_id=conversation_id,
        user_id=current_user.id
    )
    
    return {"marked_count": count}


# ============ INVITATIONS DE GROUPE ============

@router.post("/groups/{group_id}/invite", response_model=GroupInvitationResponse, status_code=status.HTTP_201_CREATED)
def invite_user_to_group(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    invitation_in: GroupInvitationCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """Inviter un utilisateur à rejoindre un groupe"""
    if not crud_social_group.is_member(db, group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être membre du groupe pour inviter des utilisateurs"
        )
    
    try:
        invitation = crud_group_invitation.create(
            db,
            obj_in=invitation_in.dict(),
            group_id=group_id,
            inviter_id=current_user.id,
            invitee_id=invitation_in.invitee_id
        )
        
        # Notifier l'invité via Socket.IO
        def notify_invitation():
            try:
                asyncio.run(social_socket_service.emit_to_user(
                    invitation_in.invitee_id,
                    "new_group_invitation",
                    {
                        "group_id": group_id,
                        "invitation_id": invitation.id,
                        "inviter_id": current_user.id,
                        "inviter_name": current_user.username or "Utilisateur"
                    }
                ))
            except Exception as e:
                print(f"Erreur notification Socket.IO: {e}")
        
        background_tasks.add_task(notify_invitation)
        
        return invitation
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/invitations", response_model=GroupInvitationListResponse)
def get_invitations(
    *,
    db: Session = Depends(get_db),
    status: Optional[str] = Query("pending", description="Statut des invitations"),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer les invitations de l'utilisateur"""
    invitations = crud_group_invitation.get_user_invitations(
        db,
        user_id=current_user.id,
        status=status
    )
    
    result = []
    for inv in invitations:
        inv_dict = {
            "id": inv.id,
            "group_id": inv.group_id,
            "inviter_id": inv.inviter_id,
            "invitee_id": inv.invitee_id,
            "message": inv.message,
            "status": inv.status,
            "responded_at": inv.responded_at,
            "created_at": inv.created_at,
            "group": {
                "id": inv.group.id,
                "name": inv.group.name,
                "avatar_url": inv.group.avatar_url
            } if inv.group else None,
            "inviter": {
                "id": inv.inviter.id,
                "username": inv.inviter.username,
                "avatar_url": inv.inviter.avatar_url
            } if inv.inviter else None,
            "invitee": {
                "id": inv.invitee.id,
                "username": inv.invitee.username,
                "avatar_url": inv.invitee.avatar_url
            } if inv.invitee else None
        }
        result.append(inv_dict)
    
    return {
        "invitations": result,
        "total": len(result)
    }


@router.post("/invitations/{invitation_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept_invitation(
    *,
    db: Session = Depends(get_db),
    invitation_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Accepter une invitation"""
    success = crud_group_invitation.accept(db, invitation_id=invitation_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation introuvable ou déjà traitée"
        )


@router.post("/invitations/{invitation_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_invitation(
    *,
    db: Session = Depends(get_db),
    invitation_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Rejeter une invitation"""
    success = crud_group_invitation.reject(db, invitation_id=invitation_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation introuvable ou déjà traitée"
        )

