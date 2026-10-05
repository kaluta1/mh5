"""
Service Socket.IO pour le service social
Gère les événements en temps réel : messages, posts, réactions, notifications
"""
from typing import Dict, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

try:
    from socketio import AsyncServer, ASGIApp
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    AsyncServer = None
    ASGIApp = None

from fastapi import Depends
import json

from app.db.session import SessionLocal
from app.models.post import Post, PostReaction, PostComment
from app.models.social_group import GroupMessage, SocialGroup, GroupMember
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.crud.crud_social import (
    crud_post, crud_post_reaction, crud_post_comment,
    crud_group_message, crud_social_group
)


class SocialSocketService:
    """Service Socket.IO pour les fonctionnalités sociales"""
    
    def __init__(self):
        self.sio: Optional[AsyncServer] = None
        self.app: Optional[ASGIApp] = None
        self.user_sessions: Dict[str, int] = {}  # socket_id -> user_id
        self.user_rooms: Dict[int, List[str]] = {}  # user_id -> [socket_ids]
    
    def initialize(self, sio):
        """Initialise le service avec une instance Socket.IO"""
        if not SOCKETIO_AVAILABLE:
            print("⚠️  Socket.IO n'est pas disponible")
            return
        self.sio = sio
        self._register_handlers()
    
    def _register_handlers(self):
        """Enregistre tous les gestionnaires d'événements"""
        
        @self.sio.event
        async def connect(sid, environ, auth):
            """Gestionnaire de connexion"""
            try:
                # Récupérer l'utilisateur depuis le token d'authentification
                user_id = await self._authenticate_user(auth)
                if not user_id:
                    return False
                
                self.user_sessions[sid] = user_id
                if user_id not in self.user_rooms:
                    self.user_rooms[user_id] = []
                self.user_rooms[user_id].append(sid)
                
                # Rejoindre la room personnelle de l'utilisateur
                await self.sio.enter_room(sid, f"user_{user_id}")
                
                # Notifier les autres sockets de l'utilisateur
                await self.sio.emit("user_online", {"user_id": user_id}, room=f"user_{user_id}")
                
                print(f"✅ Utilisateur {user_id} connecté (socket: {sid})")
                return True
            except Exception as e:
                print(f"❌ Erreur de connexion: {e}")
                return False
        
        @self.sio.event
        async def disconnect(sid):
            """Gestionnaire de déconnexion"""
            user_id = self.user_sessions.get(sid)
            if user_id:
                if user_id in self.user_rooms:
                    self.user_rooms[user_id].remove(sid)
                    if not self.user_rooms[user_id]:
                        del self.user_rooms[user_id]
                
                del self.user_sessions[sid]
                await self.sio.leave_room(sid, f"user_{user_id}")
                
                # Notifier que l'utilisateur est hors ligne
                await self.sio.emit("user_offline", {"user_id": user_id}, room=f"user_{user_id}")
                print(f"👋 Utilisateur {user_id} déconnecté (socket: {sid})")
        
        @self.sio.event
        async def join_group(sid, data):
            """Rejoindre une room de groupe"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            group_id = data.get("group_id")
            if not group_id:
                return {"error": "group_id requis"}
            
            # Vérifier que l'utilisateur est membre du groupe
            db = SessionLocal()
            try:
                is_member = crud_social_group.is_member(db, group_id, user_id)
                if not is_member:
                    return {"error": "Non membre du groupe"}
                
                room_name = f"group_{group_id}"
                await self.sio.enter_room(sid, room_name)
                return {"success": True, "group_id": group_id}
            finally:
                db.close()
        
        @self.sio.event
        async def leave_group(sid, data):
            """Quitter une room de groupe"""
            group_id = data.get("group_id")
            if group_id:
                room_name = f"group_{group_id}"
                await self.sio.leave_room(sid, room_name)
                return {"success": True}
        
        @self.sio.event
        async def new_post(sid, data):
            """Nouveau post créé"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            post_id = data.get("post_id")
            if not post_id:
                return {"error": "post_id requis"}
            
            db = SessionLocal()
            try:
                post = crud_post.get(db, post_id, user_id)
                if not post:
                    return {"error": "Post introuvable"}
                
                # Récupérer les followers de l'auteur
                from app.models.follow import Follow
                followers = db.query(Follow.follower_id).filter(
                    Follow.following_id == post.author_id
                ).all()
                
                # Envoyer la notification aux followers
                notification_data = {
                    "post_id": post.id,
                    "author_id": post.author_id,
                    "author_name": post.author.username if post.author else "Utilisateur",
                    "content_preview": (post.content[:100] + "...") if post.content and len(post.content) > 100 else post.content,
                    "post_type": post.post_type.value
                }
                
                for follower_id, in followers:
                    await self.sio.emit("new_post", notification_data, room=f"user_{follower_id}")
                
                # Si le post est dans un groupe, notifier les membres
                if post.group_id:
                    await self.emit_group_safe(post.group_id, [post.author_id, user_id], "new_post", notification_data)  # Phase 9
                
                return {"success": True}
            finally:
                db.close()
        
        @self.sio.event
        async def new_reaction(sid, data):
            """Nouvelle réaction sur un post ou commentaire"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            post_id = data.get("post_id")
            comment_id = data.get("comment_id")
            reaction_type = data.get("reaction_type")
            
            if not reaction_type:
                return {"error": "reaction_type requis"}
            
            db = SessionLocal()
            try:
                if post_id:
                    post = crud_post.get(db, post_id)
                    if not post:
                        return {"error": "Post introuvable"}
                    
                    # Récupérer l'utilisateur qui a réagi
                    user = db.query(User).filter(User.id == user_id).first()
                    
                    notification_data = {
                        "post_id": post_id,
                        "user_id": user_id,
                        "user_name": user.username if user else "Utilisateur",
                        "reaction_type": reaction_type
                    }
                    
                    # Notifier l'auteur du post
                    await self.sio.emit("new_reaction", notification_data, room=f"user_{post.author_id}")
                    
                    # Notifier dans la room du groupe si applicable
                    if post.group_id:
                        await self.emit_group_safe(post.group_id, [post.author_id, user_id], "new_reaction", notification_data)  # Phase 9
                
                elif comment_id:
                    comment = crud_post_comment.get(db, comment_id)
                    if not comment:
                        return {"error": "Commentaire introuvable"}
                    
                    user = db.query(User).filter(User.id == user_id).first()
                    
                    notification_data = {
                        "comment_id": comment_id,
                        "post_id": comment.post_id,
                        "user_id": user_id,
                        "user_name": user.username if user else "Utilisateur",
                        "reaction_type": reaction_type
                    }
                    
                    # Notifier l'auteur du commentaire
                    await self.sio.emit("new_reaction", notification_data, room=f"user_{comment.author_id}")
                
                return {"success": True}
            finally:
                db.close()
        
        @self.sio.event
        async def new_comment(sid, data):
            """Nouveau commentaire sur un post"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            post_id = data.get("post_id")
            comment_id = data.get("comment_id")
            
            if not post_id or not comment_id:
                return {"error": "post_id et comment_id requis"}
            
            db = SessionLocal()
            try:
                post = crud_post.get(db, post_id)
                comment = crud_post_comment.get(db, comment_id)
                
                if not post or not comment:
                    return {"error": "Post ou commentaire introuvable"}
                
                user = db.query(User).filter(User.id == user_id).first()
                
                notification_data = {
                    "post_id": post_id,
                    "comment_id": comment_id,
                    "author_id": user_id,
                    "author_name": user.username if user else "Utilisateur",
                    "content_preview": (comment.content[:100] + "...") if comment.content and len(comment.content) > 100 else comment.content
                }
                
                # Notifier l'auteur du post
                if post.author_id != user_id:
                    await self.sio.emit("new_comment", notification_data, room=f"user_{post.author_id}")
                
                # Notifier dans la room du groupe si applicable
                if post.group_id:
                    await self.emit_group_safe(post.group_id, [post.author_id, user_id], "new_comment", notification_data)  # Phase 9
                
                return {"success": True}
            finally:
                db.close()
        
        @self.sio.event
        async def send_message(sid, data):
            """Envoyer un message dans un groupe"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            group_id = data.get("group_id")
            message_id = data.get("message_id")
            
            if not group_id or not message_id:
                return {"error": "group_id et message_id requis"}
            
            db = SessionLocal()
            try:
                message = crud_group_message.get(db, message_id)
                # Phase 9: relay only the caller's own live message of THIS group.
                if (not message or str(message.group_id) != str(group_id) or message.sender_id != user_id
                        or getattr(message, "is_deleted", False)):
                    return {"error": "Message introuvable"}
                
                # Vérifier que l'utilisateur est membre du groupe
                is_member = crud_social_group.is_member(db, group_id, user_id)
                if not is_member:
                    return {"error": "Non membre du groupe"}
                
                # Récupérer les informations du message
                sender = db.query(User).filter(User.id == user_id).first()
                
                message_data = {
                    "message_id": message.id,
                    "group_id": group_id,
                    "sender_id": user_id,
                    "sender_name": sender.username if sender else "Utilisateur",
                    "content": message.content,
                    "message_type": message.message_type.value,
                    "created_at": message.created_at.isoformat()
                }
                
                # Phase 9: only to members the sender may reach (same decision as REST).
                await self.emit_group_safe(message.group_id, [user_id], "new_message", message_data)
                
                return {"success": True}
            finally:
                db.close()
        
        @self.sio.event
        async def message_read(sid, data):
            """Marquer un message comme lu"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            message_id = data.get("message_id")
            if not message_id:
                return {"error": "message_id requis"}
            
            db = SessionLocal()
            try:
                # Phase 9: only a message this member CURRENTLY may see; the
                # receipt reaches only members who may see both the message's
                # sender and the reader.
                from app.services import interaction_safety as isafe

                message = isafe.visible_group_message(db, db.query(User).filter(User.id == user_id).first(),
                                                      message_id)
                success = message is not None and crud_group_message.mark_as_read(db, message_id, user_id)
                group_id, sender_id = (message.group_id, message.sender_id) if message is not None else (None, None)
            finally:
                db.close()
            if success:
                await self.emit_group_safe(group_id, [sender_id, user_id], "message_read",
                                           {"message_id": message_id, "user_id": user_id})
            return {"success": bool(success)}
        
        @self.sio.event
        async def join_conversation(sid, data):
            """Rejoindre une room de conversation"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            conversation_id = data.get("conversation_id")
            if not conversation_id:
                return {"error": "conversation_id requis"}
            
            db = SessionLocal()
            try:
                from app.crud.crud_private_message import crud_private_conversation
                from app.models.private_message import ConversationParticipant
                
                conversation = crud_private_conversation.get(db, conversation_id)
                if not conversation:
                    return {"error": "Conversation introuvable"}
                
                # Vérifier l'accès
                has_access = False
                if conversation.conversation_type.value == "direct":
                    has_access = (conversation.user1_id == user_id or 
                                 conversation.user2_id == user_id)
                else:
                    participant = db.query(ConversationParticipant).filter(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id == user_id,
                        ConversationParticipant.is_active == True
                    ).first()
                    has_access = participant is not None
                
                if not has_access:
                    return {"error": "Accès non autorisé"}
                
                room_name = f"conversation_{conversation_id}"
                await self.sio.enter_room(sid, room_name)
                return {"success": True, "conversation_id": conversation_id}
            finally:
                db.close()
        
        @self.sio.event
        async def leave_conversation(sid, data):
            """Quitter une room de conversation"""
            conversation_id = data.get("conversation_id")
            if conversation_id:
                room_name = f"conversation_{conversation_id}"
                await self.sio.leave_room(sid, room_name)
                return {"success": True}
        
        @self.sio.event
        async def send_private_message(sid, data):
            """Envoyer un message privé (via Socket.IO)"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            conversation_id = data.get("conversation_id")
            message_id = data.get("message_id")
            
            if not conversation_id or not message_id:
                return {"error": "conversation_id et message_id requis"}
            
            db = SessionLocal()
            try:
                from app.crud.crud_private_message import crud_private_message, crud_private_conversation
                from app.models.private_message import ConversationParticipant
                
                message = crud_private_message.get(db, message_id)
                if not message:
                    return {"error": "Message introuvable"}
                
                conversation = crud_private_conversation.get(db, conversation_id)
                if not conversation:
                    return {"error": "Conversation introuvable"}
                
                # Vérifier que l'utilisateur est l'expéditeur
                if message.sender_id != user_id:
                    return {"error": "Vous n'êtes pas l'expéditeur de ce message"}
                # Phase 9: the message must belong to THIS conversation (no
                # re-routing an allowed message into someone else's conversation).
                if str(message.conversation_id) != str(conversation_id):
                    return {"error": "Message introuvable"}
                
                # Récupérer les destinataires
                recipient_ids = []
                if conversation.conversation_type.value == "direct":
                    if conversation.user1_id == user_id:
                        recipient_ids = [conversation.user2_id] if conversation.user2_id else []
                    else:
                        recipient_ids = [conversation.user1_id] if conversation.user1_id else []
                else:
                    participants = db.query(ConversationParticipant).filter(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id != user_id,
                        ConversationParticipant.is_active == True
                    ).all()
                    recipient_ids = [p.user_id for p in participants]
                
                sender = db.query(User).filter(User.id == user_id).first()
                # Phase 9: a re-emit is checked against CURRENT state (blocks,
                # minor protection) like a new REST message.
                from app.services import interaction_safety as isafe

                recipient_ids = [rid for rid in recipient_ids if isafe.can_contact(
                    db, sender, db.query(User).filter(User.id == rid).first()).allowed]
                if not recipient_ids:
                    return {"error": "Accès non autorisé"}

                message_data = {
                    "message_id": message.id,
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "sender_name": sender.username if sender else "Utilisateur",
                    "content": message.content,
                    "message_type": message.message_type,
                    "created_at": message.created_at.isoformat()
                }
                
                # Envoyer aux destinataires autorisés (Phase 9: never the shared
                # conversation-room broadcast, which would reach filtered participants)
                for recipient_id in recipient_ids:
                    await self.sio.emit("new_private_message", message_data, room=f"user_{recipient_id}")
                await self._emit_room_filtered(f"conversation_{conversation_id}", set(recipient_ids) | {user_id},
                                               "new_private_message", message_data)
                
                return {"success": True}
            finally:
                db.close()
        
        @self.sio.event
        async def private_message_read(sid, data):
            """Marquer un message privé comme lu"""
            user_id = self.user_sessions.get(sid)
            if not user_id:
                return {"error": "Non authentifié"}
            
            message_id = data.get("message_id")
            if not message_id:
                return {"error": "message_id requis"}
            
            db = SessionLocal()
            try:
                from app.crud.crud_private_message import crud_private_message
                
                success = crud_private_message.mark_as_read(db, message_id, user_id)
                if success:
                    message = crud_private_message.get(db, message_id)
                    if message:
                        await self.sio.emit("private_message_read", {
                            "message_id": message_id,
                            "user_id": user_id
                        }, room=f"conversation_{message.conversation_id}")
                
                return {"success": success}
            finally:
                db.close()
    
    async def _authenticate_user(self, auth: Optional[Dict]) -> Optional[int]:
        """Authentifie un utilisateur depuis le token"""
        if not auth:
            return None
        
        token = auth.get("token")
        if not token:
            return None
        
        # Valider le token JWT
        try:
            from app.services.auth_security import access_token_user_id

            # Same rule as the API: a token issued before the account's last
            # password change / reset is not an identity.
            user_id = access_token_user_id(token)
            if user_id:
                return user_id
        except Exception as e:
            print(f"Erreur d'authentification Socket.IO: {e}")
        
        # Phase 9: never trust a client-supplied user id (no token = no identity).
        return None
    
    async def emit_to_user(self, user_id: int, event: str, data: dict):
        """Émet un événement à un utilisateur spécifique"""
        if self.sio and SOCKETIO_AVAILABLE:
            await self.sio.emit(event, data, room=f"user_{user_id}")
    
    async def emit_group_safe(self, group_id: int, actor_ids, event: str, data: dict):
        """Phase 9: the ONLY group-room emitter. Sends to each socket in the
        group room whose user is a CURRENT member reachable by every actor
        (interaction_safety.group_recipient_ids); anything unresolvable is
        skipped (fail closed). The shared room broadcast is never used."""
        if not (self.sio and SOCKETIO_AVAILABLE) or not group_id:
            return
        from app.services import interaction_safety as isafe

        db = SessionLocal()
        try:
            allowed = isafe.group_recipient_ids(db, group_id, actor_ids)
        finally:
            db.close()
        await self._emit_room_filtered(f"group_{group_id}", allowed, event, data)

    async def _emit_room_filtered(self, room: str, allowed_user_ids, event: str, data: dict):
        try:
            sids = [sid for sid, _ in self.sio.manager.get_participants("/", room)]
        except Exception:  # noqa: BLE001 - no room info: deliver nothing (clients fetch over HTTP)
            return
        for sid in sids:
            if self.user_sessions.get(sid) in allowed_user_ids:
                await self.sio.emit(event, data, to=sid)
    
    async def emit_to_conversation(self, conversation_id: int, event: str, data: dict):
        """Émet un événement à tous les participants d'une conversation"""
        if self.sio and SOCKETIO_AVAILABLE:
            await self.sio.emit(event, data, room=f"conversation_{conversation_id}")


# Instance globale du service
social_socket_service = SocialSocketService()

