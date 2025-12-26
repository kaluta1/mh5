from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime

from app.models.private_message import (
    PrivateConversation, ConversationParticipant, PrivateMessage,
    PrivateMessageReadReceipt, GroupInvitation,
    ConversationType, PrivateMessageStatus
)
from app.models.user import User
# Les schémas sont utilisés dans les endpoints, pas dans le CRUD
# from app.schemas.social import (
#     PrivateMessageCreate, PrivateMessageUpdate,
#     GroupInvitationCreate
# )


class CRUDPrivateConversation:
    """CRUD pour les conversations privées"""
    
    def get_or_create_direct(
        self, 
        db: Session, 
        user1_id: int, 
        user2_id: int
    ) -> PrivateConversation:
        """Récupère ou crée une conversation directe entre deux utilisateurs"""
        # S'assurer que user1_id < user2_id pour éviter les doublons
        if user1_id > user2_id:
            user1_id, user2_id = user2_id, user1_id
        
        conversation = db.query(PrivateConversation).filter(
            PrivateConversation.conversation_type == ConversationType.DIRECT,
            PrivateConversation.user1_id == user1_id,
            PrivateConversation.user2_id == user2_id
        ).first()
        
        if not conversation:
            conversation = PrivateConversation(
                conversation_type=ConversationType.DIRECT,
                user1_id=user1_id,
                user2_id=user2_id
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        
        return conversation
    
    def get(self, db: Session, conversation_id: int) -> Optional[PrivateConversation]:
        """Récupère une conversation par son ID"""
        return db.query(PrivateConversation).filter(
            PrivateConversation.id == conversation_id
        ).first()
    
    def get_by_group(self, db: Session, group_id: int) -> Optional[PrivateConversation]:
        """Récupère la conversation d'un groupe"""
        return db.query(PrivateConversation).filter(
            PrivateConversation.group_id == group_id,
            PrivateConversation.conversation_type == ConversationType.GROUP
        ).first()
    
    def get_or_create_group(self, db: Session, group_id: int) -> PrivateConversation:
        """Récupère ou crée une conversation de groupe"""
        conversation = self.get_by_group(db, group_id)
        
        if not conversation:
            conversation = PrivateConversation(
                conversation_type=ConversationType.GROUP,
                group_id=group_id
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            
            # Ajouter tous les membres du groupe comme participants
            from app.models.social_group import GroupMember
            members = db.query(GroupMember).filter(
                GroupMember.group_id == group_id
            ).all()
            
            for member in members:
                participant = ConversationParticipant(
                    conversation_id=conversation.id,
                    user_id=member.user_id
                )
                db.add(participant)
            
            db.commit()
            db.refresh(conversation)
        
        return conversation
    
    def get_user_conversations(
        self, 
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[PrivateConversation]:
        """Récupère toutes les conversations d'un utilisateur"""
        # Conversations directes où l'utilisateur est user1 ou user2
        direct_conversations = db.query(PrivateConversation).filter(
            PrivateConversation.conversation_type == ConversationType.DIRECT,
            or_(
                PrivateConversation.user1_id == user_id,
                PrivateConversation.user2_id == user_id
            )
        )
        
        # Conversations de groupe où l'utilisateur est participant
        group_conversations = db.query(PrivateConversation).join(
            ConversationParticipant
        ).filter(
            PrivateConversation.conversation_type == ConversationType.GROUP,
            ConversationParticipant.user_id == user_id,
            ConversationParticipant.is_active == True
        )
        
        # Combiner et trier par dernière activité
        all_conversations = direct_conversations.union(group_conversations).order_by(
            desc(PrivateConversation.last_message_at)
        ).offset(skip).limit(limit).all()
        
        return all_conversations
    
    def add_participant(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int
    ) -> ConversationParticipant:
        """Ajoute un participant à une conversation de groupe"""
        # Vérifier si déjà participant
        existing = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id
        ).first()
        
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.left_at = None
                db.commit()
                db.refresh(existing)
            return existing
        
        participant = ConversationParticipant(
            conversation_id=conversation_id,
            user_id=user_id
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
        return participant
    
    def remove_participant(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int
    ) -> bool:
        """Retire un participant d'une conversation"""
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id
        ).first()
        
        if not participant:
            return False
        
        participant.is_active = False
        participant.left_at = datetime.utcnow()
        db.commit()
        return True
    
    def update_unread_count(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int, 
        increment: bool = True
    ):
        """Met à jour le compteur de messages non lus"""
        conversation = self.get(db, conversation_id)
        if not conversation:
            return
        
        if conversation.conversation_type == ConversationType.DIRECT:
            if conversation.user1_id == user_id:
                if increment:
                    conversation.unread_count_user1 += 1
                else:
                    conversation.unread_count_user1 = 0
            elif conversation.user2_id == user_id:
                if increment:
                    conversation.unread_count_user2 += 1
                else:
                    conversation.unread_count_user2 = 0
        else:
            # Pour les groupes, utiliser ConversationParticipant
            participant = db.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id
            ).first()
            
            if participant:
                if increment:
                    participant.unread_count += 1
                else:
                    participant.unread_count = 0
        
        db.commit()


class CRUDPrivateMessage:
    """CRUD pour les messages privés"""
    
    def get(self, db: Session, message_id: int) -> Optional[PrivateMessage]:
        """Récupère un message par son ID"""
        return db.query(PrivateMessage).filter(
            PrivateMessage.id == message_id,
            PrivateMessage.is_deleted == False
        ).first()
    
    def get_by_conversation(
        self, 
        db: Session, 
        conversation_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[PrivateMessage]:
        """Récupère les messages d'une conversation"""
        return db.query(PrivateMessage).filter(
            PrivateMessage.conversation_id == conversation_id,
            PrivateMessage.is_deleted == False
        ).order_by(desc(PrivateMessage.created_at)).offset(skip).limit(limit).all()
    
    def create(
        self, 
        db: Session, 
        obj_in: dict, 
        conversation_id: int, 
        sender_id: int
    ) -> PrivateMessage:
        """Crée un nouveau message privé"""
        db_obj = PrivateMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=obj_in.get("content"),
            message_type=obj_in.get("message_type", "text"),
            media_id=obj_in.get("media_id"),
            reply_to_id=obj_in.get("reply_to_id"),
            status=PrivateMessageStatus.SENT
        )
        db.add(db_obj)
        db.flush()
        
        # Mettre à jour la conversation
        conversation = db.query(PrivateConversation).filter(
            PrivateConversation.id == conversation_id
        ).first()
        
        if conversation:
            conversation.last_message_id = db_obj.id
            conversation.last_message_at = datetime.utcnow()
            conversation.message_count += 1
            
            # Incrémenter les compteurs de non lus pour les autres participants
            if conversation.conversation_type == ConversationType.DIRECT:
                if conversation.user1_id != sender_id:
                    conversation.unread_count_user1 += 1
                if conversation.user2_id != sender_id:
                    conversation.unread_count_user2 += 1
            else:
                # Pour les groupes
                participants = db.query(ConversationParticipant).filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id != sender_id,
                    ConversationParticipant.is_active == True
                ).all()
                
                for participant in participants:
                    participant.unread_count += 1
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, 
        db: Session, 
        db_obj: PrivateMessage, 
        obj_in: dict
    ) -> PrivateMessage:
        """Met à jour un message"""
        db_obj.content = obj_in.get("content", db_obj.content)
        db_obj.is_edited = True
        db_obj.edited_at = datetime.utcnow()
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, message_id: int, user_id: int) -> bool:
        """Supprime un message (soft delete)"""
        message = self.get(db, message_id)
        if not message or message.sender_id != user_id:
            return False
        
        message.is_deleted = True
        message.deleted_at = datetime.utcnow()
        message.status = PrivateMessageStatus.DELETED
        
        # Décrémenter le compteur de messages
        conversation = db.query(PrivateConversation).filter(
            PrivateConversation.id == message.conversation_id
        ).first()
        if conversation:
            conversation.message_count = max(0, conversation.message_count - 1)
        
        db.commit()
        return True
    
    def mark_as_read(
        self, 
        db: Session, 
        message_id: int, 
        user_id: int
    ) -> bool:
        """Marque un message comme lu"""
        message = self.get(db, message_id)
        if not message:
            return False
        
        # Vérifier si déjà lu
        existing = db.query(PrivateMessageReadReceipt).filter(
            PrivateMessageReadReceipt.message_id == message_id,
            PrivateMessageReadReceipt.user_id == user_id
        ).first()
        
        if not existing:
            receipt = PrivateMessageReadReceipt(
                message_id=message_id,
                user_id=user_id
            )
            db.add(receipt)
            message.status = PrivateMessageStatus.READ
            
            # Mettre à jour le compteur de non lus
            conversation = db.query(PrivateConversation).filter(
                PrivateConversation.id == message.conversation_id
            ).first()
            
            if conversation:
                if conversation.conversation_type == ConversationType.DIRECT:
                    if conversation.user1_id == user_id:
                        conversation.unread_count_user1 = max(0, conversation.unread_count_user1 - 1)
                    elif conversation.user2_id == user_id:
                        conversation.unread_count_user2 = max(0, conversation.unread_count_user2 - 1)
                else:
                    participant = db.query(ConversationParticipant).filter(
                        ConversationParticipant.conversation_id == message.conversation_id,
                        ConversationParticipant.user_id == user_id
                    ).first()
                    if participant:
                        participant.unread_count = max(0, participant.unread_count - 1)
        
        db.commit()
        return True
    
    def mark_conversation_as_read(
        self, 
        db: Session, 
        conversation_id: int, 
        user_id: int
    ) -> int:
        """Marque tous les messages d'une conversation comme lus"""
        # Récupérer tous les messages non lus
        messages = db.query(PrivateMessage).filter(
            PrivateMessage.conversation_id == conversation_id,
            PrivateMessage.sender_id != user_id,
            PrivateMessage.is_deleted == False
        ).all()
        
        count = 0
        for message in messages:
            # Vérifier si déjà lu
            existing = db.query(PrivateMessageReadReceipt).filter(
                PrivateMessageReadReceipt.message_id == message.id,
                PrivateMessageReadReceipt.user_id == user_id
            ).first()
            
            if not existing:
                receipt = PrivateMessageReadReceipt(
                    message_id=message.id,
                    user_id=user_id
                )
                db.add(receipt)
                message.status = PrivateMessageStatus.READ
                count += 1
        
        # Réinitialiser le compteur de non lus
        conversation = db.query(PrivateConversation).filter(
            PrivateConversation.id == conversation_id
        ).first()
        
        if conversation:
            # Utiliser la méthode directement
            if conversation.conversation_type == ConversationType.DIRECT:
                if conversation.user1_id == user_id:
                    conversation.unread_count_user1 = 0
                elif conversation.user2_id == user_id:
                    conversation.unread_count_user2 = 0
            else:
                participant = db.query(ConversationParticipant).filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == user_id
                ).first()
                if participant:
                    participant.unread_count = 0
        
        db.commit()
        return count


class CRUDGroupInvitation:
    """CRUD pour les invitations de groupe"""
    
    def create(
        self, 
        db: Session, 
        obj_in: dict, 
        group_id: int, 
        inviter_id: int, 
        invitee_id: int
    ) -> GroupInvitation:
        """Crée une invitation à rejoindre un groupe"""
        # Vérifier si déjà membre
        from app.crud.crud_social import crud_social_group
        if crud_social_group.is_member(db, group_id, invitee_id):
            raise ValueError("L'utilisateur est déjà membre du groupe")
        
        # Vérifier si invitation en attente
        existing = db.query(GroupInvitation).filter(
            GroupInvitation.group_id == group_id,
            GroupInvitation.invitee_id == invitee_id,
            GroupInvitation.status == "pending"
        ).first()
        
        if existing:
            raise ValueError("Une invitation est déjà en attente")
        
        db_obj = GroupInvitation(
            group_id=group_id,
            inviter_id=inviter_id,
            invitee_id=invitee_id,
            message=obj_in.get("message")
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get(self, db: Session, invitation_id: int) -> Optional[GroupInvitation]:
        """Récupère une invitation par son ID"""
        return db.query(GroupInvitation).filter(
            GroupInvitation.id == invitation_id
        ).first()
    
    def get_user_invitations(
        self, 
        db: Session, 
        user_id: int, 
        status: Optional[str] = "pending"
    ) -> List[GroupInvitation]:
        """Récupère les invitations d'un utilisateur"""
        query = db.query(GroupInvitation).filter(
            GroupInvitation.invitee_id == user_id
        )
        
        if status:
            query = query.filter(GroupInvitation.status == status)
        
        return query.order_by(desc(GroupInvitation.created_at)).all()
    
    def accept(self, db: Session, invitation_id: int, user_id: int) -> bool:
        """Accepte une invitation"""
        invitation = self.get(db, invitation_id)
        if not invitation or invitation.invitee_id != user_id:
            return False
        
        if invitation.status != "pending":
            return False
        
        # Ajouter l'utilisateur au groupe
        from app.crud.crud_social import crud_social_group
        try:
            crud_social_group.add_member(db, invitation.group_id, user_id)
            
            invitation.status = "accepted"
            invitation.responded_at = datetime.utcnow()
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
    
    def reject(self, db: Session, invitation_id: int, user_id: int) -> bool:
        """Rejette une invitation"""
        invitation = self.get(db, invitation_id)
        if not invitation or invitation.invitee_id != user_id:
            return False
        
        if invitation.status != "pending":
            return False
        
        invitation.status = "rejected"
        invitation.responded_at = datetime.utcnow()
        db.commit()
        return True
    
    def cancel(self, db: Session, invitation_id: int, inviter_id: int) -> bool:
        """Annule une invitation (par l'inviteur)"""
        invitation = self.get(db, invitation_id)
        if not invitation or invitation.inviter_id != inviter_id:
            return False
        
        if invitation.status != "pending":
            return False
        
        invitation.status = "cancelled"
        db.commit()
        return True


# Instances des CRUD
crud_private_conversation = CRUDPrivateConversation()
crud_private_message = CRUDPrivateMessage()
crud_group_invitation = CRUDGroupInvitation()

