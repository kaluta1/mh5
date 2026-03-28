from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import asyncio

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.social import (
    PostCreate, PostUpdate, PostResponse, PostListResponse,
    PostCommentCreate, PostCommentResponse,
    PostReactionCreate, PostReactionResponse,
    PostShareCreate, PostShareResponse,
    SocialGroupCreate, SocialGroupUpdate, SocialGroupResponse, GroupListResponse,
    GroupMemberResponse, GroupJoinRequestCreate, GroupJoinRequestResponse,
    GroupMessageCreate, GroupMessageUpdate, GroupMessageResponse, MessageListResponse,
    FeedResponse, ReactionType,
    PrivateMessageCreate, PrivateMessageUpdate, PrivateMessageResponse, PrivateMessageListResponse,
    PrivateConversationResponse, ConversationListResponse,
    GroupInvitationCreate, GroupInvitationResponse, GroupInvitationListResponse
)
from app.crud.crud_social import (
    crud_post, crud_post_comment, crud_post_reaction,
    crud_post_share, crud_social_group, crud_group_message, crud_feed
)
from app.crud.crud_private_message import (
    crud_private_conversation, crud_private_message, crud_group_invitation
)
from app.models.post import Post, PostReaction
from app.models.social_group import GroupMember, GroupMemberRole
from app.models.private_message import ConversationParticipant
from app.services.social_socket import social_socket_service

router = APIRouter()


# ============ POSTS ============

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    *,
    db: Session = Depends(get_db),
    post_in: PostCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """Créer un nouveau post"""
    post = crud_post.create(db, obj_in=post_in, author_id=current_user.id)
    
    # Notifier via Socket.IO en arrière-plan
    def notify_post():
        try:
            asyncio.run(social_socket_service.emit_to_user(
                current_user.id,
                "new_post",
                {"post_id": post.id}
            ))
        except Exception as e:
            print(f"Erreur notification Socket.IO: {e}")
    
    background_tasks.add_task(notify_post)

    return {
        "id": post.id,
        "author_id": post.author_id,
        "content": post.content,
        "post_type": post.post_type,
        "visibility": post.visibility,
        "group_id": post.group_id,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "share_count": post.share_count,
        "view_count": post.view_count,
        "is_pinned": post.is_pinned,
        "is_archived": post.is_archived,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "author": {
            "id": post.author.id,
            "username": post.author.username,
            "avatar_url": post.author.avatar_url
        } if post.author else None,
        "media": [
            {
                "id": pm.id,
                "media_id": pm.media_id,
                "order": pm.order,
                "url": pm.media.url if pm.media else None
            } for pm in post.media
        ],
        "user_reaction": None
    }


@router.get("/posts", response_model=PostListResponse)
def get_posts(
    *,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    author_id: Optional[int] = None,
    group_id: Optional[int] = None,
    current_user: Optional[User] = Depends(get_current_active_user)
) -> Any:
    """Récupérer les posts"""
    user_id = current_user.id if current_user else None
    posts = crud_post.get_multi(
        db, 
        user_id=user_id,
        author_id=author_id,
        group_id=group_id,
        skip=skip, 
        limit=limit
    )
    
    # Enrichir avec les données utilisateur
    result_posts = []
    for post in posts:
        post_dict = {
            "id": post.id,
            "author_id": post.author_id,
            "content": post.content,
            "post_type": post.post_type,
            "visibility": post.visibility,
            "group_id": post.group_id,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "share_count": post.share_count,
            "view_count": post.view_count,
            "is_pinned": post.is_pinned,
            "is_archived": post.is_archived,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
            "author": {
                "id": post.author.id,
                "username": post.author.username,
                "avatar_url": post.author.avatar_url
            } if post.author else None,
            "media": [
                {
                    "id": pm.id,
                    "media_id": pm.media_id,
                    "order": pm.order,
                    "url": pm.media.url if pm.media else None
                } for pm in post.media
            ],
            "user_reaction": None
        }
        
        # Ajouter la réaction de l'utilisateur si connecté
        if user_id:
            reaction = crud_post_reaction.get(db, post.id, user_id)
            if reaction:
                post_dict["user_reaction"] = reaction.reaction_type
        
        result_posts.append(post_dict)
    
    return {
        "posts": result_posts,
        "total": len(result_posts),
        "page": skip // limit + 1,
        "page_size": limit,
        "has_next": len(result_posts) == limit
    }


@router.get("/posts/{post_id}", response_model=PostResponse)
def get_post(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    current_user: Optional[User] = Depends(get_current_active_user)
) -> Any:
    """Récupérer un post par son ID"""
    user_id = current_user.id if current_user else None
    post = crud_post.get(db, post_id=post_id, user_id=user_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post introuvable"
        )
    
    # Incrémenter le compteur de vues
    crud_post.increment_view_count(db, post_id)
    
    post_dict = {
        "id": post.id,
        "author_id": post.author_id,
        "content": post.content,
        "post_type": post.post_type,
        "visibility": post.visibility,
        "group_id": post.group_id,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "share_count": post.share_count,
        "view_count": post.view_count + 1,
        "is_pinned": post.is_pinned,
        "is_archived": post.is_archived,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "author": {
            "id": post.author.id,
            "username": post.author.username,
            "avatar_url": post.author.avatar_url
        } if post.author else None,
        "media": [
            {
                "id": pm.id,
                "media_id": pm.media_id,
                "order": pm.order,
                "url": pm.media.url if pm.media else None
            } for pm in post.media
        ],
        "user_reaction": None
    }
    
    if user_id:
        reaction = crud_post_reaction.get(db, post.id, user_id)
        if reaction:
            post_dict["user_reaction"] = reaction.reaction_type
    
    return post_dict


@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    post_in: PostUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Mettre à jour un post"""
    post = crud_post.get(db, post_id=post_id, user_id=current_user.id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post introuvable"
        )
    
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à modifier ce post"
        )
    
    return crud_post.update(db, db_obj=post, obj_in=post_in)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Supprimer un post"""
    success = crud_post.delete(db, post_id=post_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post introuvable ou non autorisé"
        )


# ============ COMMENTS ============

@router.post("/posts/{post_id}/comments", response_model=PostCommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    comment_in: PostCommentCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks = None
) -> Any:
    """Créer un commentaire sur un post"""
    # Vérifier que le post existe
    post = crud_post.get(db, post_id=post_id, user_id=current_user.id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post introuvable"
        )
    
    comment = crud_post_comment.create(
        db, 
        obj_in=comment_in, 
        post_id=post_id, 
        author_id=current_user.id
    )
    
    # Notifier via Socket.IO en arrière-plan
    def notify_comment():
        try:
            asyncio.run(social_socket_service.emit_to_user(
                post.author_id,
                "new_comment",
                {"post_id": post_id, "comment_id": comment.id}
            ))
        except Exception as e:
            print(f"Erreur notification Socket.IO: {e}")
    
    if background_tasks:
        background_tasks.add_task(notify_comment)
    
    return comment


@router.get("/posts/{post_id}/comments", response_model=List[PostCommentResponse])
def get_comments(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_active_user)
) -> Any:
    """Récupérer les commentaires d'un post"""
    comments = crud_post_comment.get_by_post(db, post_id=post_id, skip=skip, limit=limit)
    
    user_id = current_user.id if current_user else None
    
    result = []
    for comment in comments:
        comment_dict = {
            "id": comment.id,
            "post_id": comment.post_id,
            "author_id": comment.author_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "like_count": comment.like_count,
            "reply_count": comment.reply_count,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "author": {
                "id": comment.author.id,
                "username": comment.author.username,
                "avatar_url": comment.author.avatar_url
            } if comment.author else None,
            "user_reaction": None,
            "replies": []
        }
        
        if user_id:
            from app.models.post import PostCommentReaction
            reaction = db.query(PostCommentReaction).filter(
                PostCommentReaction.comment_id == comment.id,
                PostCommentReaction.user_id == user_id
            ).first()
            if reaction:
                comment_dict["user_reaction"] = reaction.reaction_type
        
        result.append(comment_dict)
    
    return result


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    *,
    db: Session = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Supprimer un commentaire"""
    success = crud_post_comment.delete(db, comment_id=comment_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire introuvable ou non autorisé"
        )


# ============ REACTIONS ============

@router.post("/posts/{post_id}/reactions", response_model=Optional[PostReactionResponse])
def create_or_toggle_reaction(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    reaction_in: PostReactionCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """Créer ou supprimer une réaction sur un post"""
    reaction = crud_post_reaction.create_or_update(
        db,
        post_id=post_id,
        user_id=current_user.id,
        obj_in=reaction_in
    )
    
    if reaction:
        # Notifier via Socket.IO en arrière-plan
        post = crud_post.get(db, post_id=post_id)
        if post:
            def notify_reaction():
                try:
                    asyncio.run(social_socket_service.emit_to_user(
                        post.author_id,
                        "new_reaction",
                        {
                            "post_id": post_id,
                            "user_id": current_user.id,
                            "reaction_type": reaction.reaction_type.value
                        }
                    ))
                except Exception as e:
                    print(f"Erreur notification Socket.IO: {e}")
            
            background_tasks.add_task(notify_reaction)
    
    return reaction


@router.delete("/posts/{post_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
def delete_reaction(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Supprimer une réaction sur un post"""
    success = crud_post_reaction.delete(db, post_id=post_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Réaction introuvable"
        )


# ============ SHARES ============

@router.post("/posts/{post_id}/shares", response_model=PostShareResponse, status_code=status.HTTP_201_CREATED)
def share_post(
    *,
    db: Session = Depends(get_db),
    post_id: int,
    share_in: PostShareCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Partager un post"""
    # Vérifier que le post existe
    post = crud_post.get(db, post_id=post_id, user_id=current_user.id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post introuvable"
        )
    
    share = crud_post_share.create(
        db,
        post_id=post_id,
        user_id=current_user.id,
        obj_in=share_in
    )
    
    return share


# ============ GROUPS ============

@router.post("/groups", response_model=SocialGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    *,
    db: Session = Depends(get_db),
    group_in: SocialGroupCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Créer un nouveau groupe social (privé par défaut, comme WhatsApp).
    Le créateur devient automatiquement admin du groupe.
    """
    # FIXED: Force private by default if not specified
    if not group_in.group_type:
        group_in.group_type = GroupType.PRIVATE
    
    group = crud_social_group.create(db, obj_in=group_in, creator_id=current_user.id)
    
    # Build response with invitation link
    group_dict = {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "group_type": group.group_type,
        "creator_id": group.creator_id,
        "avatar_url": group.avatar_url,
        "cover_url": group.cover_url,
        "max_members": group.max_members,
        "requires_approval": group.requires_approval,
        "invite_code": group.invite_code,
        "invitation_link": f"/groups/join/{group.invite_code}" if group.invite_code else None,  # Frontend will build full URL
        "member_count": group.member_count,
        "post_count": group.post_count,
        "is_active": group.is_active,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "creator": {
            "id": group.creator.id,
            "username": group.creator.username,
            "avatar_url": group.creator.avatar_url
        } if group.creator else None,
        "user_role": GroupMemberRole.ADMIN,  # Creator is admin
        "is_member": True  # Creator is always a member
    }
    
    return group_dict


@router.get("/groups", response_model=GroupListResponse)
def get_groups(
    *,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_active_user)
) -> Any:
    """
    Récupérer les groupes.
    FIXED: Private groups are only shown to members (like WhatsApp).
    Public groups are visible to everyone.
    """
    user_id = current_user.id if current_user else None
    groups = crud_social_group.get_multi(db, user_id=user_id, skip=skip, limit=limit)
    
    result = []
    for group in groups:
        group_dict = {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "group_type": group.group_type,
            "creator_id": group.creator_id,
            "avatar_url": group.avatar_url,
            "cover_url": group.cover_url,
            "max_members": group.max_members,
            "requires_approval": group.requires_approval,
            "invite_code": group.invite_code,
            "invitation_link": f"/groups/join/{group.invite_code}" if group.invite_code else None,
            "member_count": group.member_count,
            "post_count": group.post_count,
            "is_active": group.is_active,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "creator": {
                "id": group.creator.id,
                "username": group.creator.username,
                "avatar_url": group.creator.avatar_url
            } if group.creator else None,
            "user_role": None,
            "is_member": False
        }
        
        if user_id:
            is_member = crud_social_group.is_member(db, group.id, user_id)
            group_dict["is_member"] = is_member
            if is_member:
                group_dict["user_role"] = crud_social_group.get_member_role(db, group.id, user_id)
        
        result.append(group_dict)
    
    return {
        "groups": result,
        "total": len(result),
        "page": skip // limit + 1,
        "page_size": limit,
        "has_next": len(result) == limit
    }


@router.get("/groups/{group_id}", response_model=SocialGroupResponse)
def get_group(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    current_user: Optional[User] = Depends(get_current_active_user)
) -> Any:
    """
    Récupérer un groupe par son ID.
    FIXED: Private groups are only visible to members (like WhatsApp).
    """
    group = crud_social_group.get(db, group_id=group_id)
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe introuvable"
        )
    
    user_id = current_user.id if current_user else None
    
    # FIXED: Private groups are only visible to members
    if group.group_type == GroupType.PRIVATE:
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ce groupe est privé. Vous devez être connecté et membre pour y accéder."
            )
        
        is_member = crud_social_group.is_member(db, group.id, user_id)
        is_creator = group.creator_id == user_id
        
        if not is_member and not is_creator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ce groupe est privé. Vous devez être membre pour y accéder."
            )
    
    group_dict = {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "group_type": group.group_type,
        "creator_id": group.creator_id,
        "avatar_url": group.avatar_url,
        "cover_url": group.cover_url,
        "max_members": group.max_members,
        "requires_approval": group.requires_approval,
        "invite_code": group.invite_code,
        "invitation_link": f"/groups/join/{group.invite_code}" if group.invite_code else None,
        "member_count": group.member_count,
        "post_count": group.post_count,
        "is_active": group.is_active,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "creator": {
            "id": group.creator.id,
            "username": group.creator.username,
            "avatar_url": group.creator.avatar_url
        } if group.creator else None,
        "user_role": None,
        "is_member": False
    }
    
    if user_id:
        is_member = crud_social_group.is_member(db, group.id, user_id)
        group_dict["is_member"] = is_member
        if is_member:
            group_dict["user_role"] = crud_social_group.get_member_role(db, group.id, user_id)
    
    return group_dict


@router.post("/groups/{group_id}/join", response_model=GroupMemberResponse)
def join_group(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Rejoindre un groupe"""
    try:
        member = crud_social_group.add_member(
            db,
            group_id=group_id,
            user_id=current_user.id
        )
        return member
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/groups/{group_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_group(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Quitter un groupe"""
    success = crud_social_group.remove_member(db, group_id=group_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vous n'êtes pas membre de ce groupe"
        )


# ============ MESSAGES ============

@router.post("/groups/{group_id}/messages", response_model=GroupMessageResponse, status_code=status.HTTP_201_CREATED)
def create_message(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    message_in: GroupMessageCreate,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """Envoyer un message dans un groupe"""
    # Vérifier que l'utilisateur est membre du groupe
    if not crud_social_group.is_member(db, group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être membre du groupe pour envoyer des messages"
        )
    
    message = crud_group_message.create(
        db,
        obj_in=message_in,
        group_id=group_id,
        sender_id=current_user.id
    )
    
    # Notifier via Socket.IO en arrière-plan
    def notify_message():
        try:
            asyncio.run(social_socket_service.emit_to_group(
                group_id,
                "new_message",
                {"message_id": message.id, "group_id": group_id}
            ))
        except Exception as e:
            print(f"Erreur notification Socket.IO: {e}")
    
    background_tasks.add_task(notify_message)
    
    return message


@router.get("/groups/{group_id}/messages", response_model=MessageListResponse)
def get_messages(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer les messages d'un groupe"""
    # Vérifier que l'utilisateur est membre du groupe
    if not crud_social_group.is_member(db, group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être membre du groupe pour voir les messages"
        )
    
    messages = crud_group_message.get_by_group(
        db,
        group_id=group_id,
        skip=skip,
        limit=limit
    )
    
    result = []
    for message in messages:
        message_dict = {
            "id": message.id,
            "group_id": message.group_id,
            "sender_id": message.sender_id,
            "content": message.content,
            "message_type": message.message_type,
            "media_id": message.media_id,
            "reply_to_id": message.reply_to_id,
            "status": message.status,
            "is_edited": message.is_edited,
            "is_deleted": message.is_deleted,
            "edited_at": message.edited_at,
            "deleted_at": message.deleted_at,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "sender": {
                "id": message.sender.id,
                "username": message.sender.username,
                "avatar_url": message.sender.avatar_url
            } if message.sender else None,
            "reply_to": None,
            "read_by": [r.user_id for r in message.read_receipts]
        }
        
        result.append(message_dict)
    
    return {
        "messages": result,
        "total": len(result),
        "page": skip // limit + 1,
        "page_size": limit,
        "has_next": len(result) == limit
    }


@router.post("/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_message_read(
    *,
    db: Session = Depends(get_db),
    message_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Marquer un message comme lu"""
    success = crud_group_message.mark_as_read(db, message_id=message_id, user_id=current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message introuvable"
        )


# ============ FEED ============

@router.get("/feed", response_model=List[PostResponse])
def get_feed(
    *,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Récupérer le fil d'actualité de l'utilisateur"""
    posts = crud_feed.generate_feed(db, user_id=current_user.id, limit=limit)
    
    result = []
    for post in posts:
        post_dict = {
            "id": post.id,
            "author_id": post.author_id,
            "content": post.content,
            "post_type": post.post_type,
            "visibility": post.visibility,
            "group_id": post.group_id,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "share_count": post.share_count,
            "view_count": post.view_count,
            "is_pinned": post.is_pinned,
            "is_archived": post.is_archived,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
            "author": {
                "id": post.author.id,
                "username": post.author.username,
                "avatar_url": post.author.avatar_url
            } if post.author else None,
            "media": [
                {
                    "id": pm.id,
                    "media_id": pm.media_id,
                    "order": pm.order,
                    "url": pm.media.url if pm.media else None
                } for pm in post.media
            ],
            "user_reaction": None
        }
        
        reaction = crud_post_reaction.get(db, post.id, current_user.id)
        if reaction:
            post_dict["user_reaction"] = reaction.reaction_type
        
        result.append(post_dict)
    
    return result

