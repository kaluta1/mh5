from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
from datetime import datetime

from app.models.post import (
    Post, PostMedia, PostComment, PostReaction, PostCommentReaction, 
    PostShare, PostType, PostVisibility, ReactionType
)
from app.models.social_group import (
    SocialGroup, GroupMember, GroupJoinRequest, GroupMessage, 
    MessageReadReceipt, GroupType, GroupMemberRole, MessageType, MessageStatus
)
from app.models.feed import Feed
from app.models.user import User
from app.models.follow import Follow
from app.schemas.social import (
    PostCreate, PostUpdate, PostCommentCreate, PostReactionCreate,
    PostCommentReactionCreate, PostShareCreate, SocialGroupCreate,
    SocialGroupUpdate, GroupJoinRequestCreate, GroupMessageCreate,
    GroupMessageUpdate
)


class CRUDPost:
    """CRUD pour les posts sociaux"""
    
    def get(self, db: Session, post_id: int, user_id: Optional[int] = None) -> Optional[Post]:
        """Récupère un post par son ID"""
        post = db.query(Post).filter(
            Post.id == post_id,
            Post.is_deleted == False
        ).first()
        
        if post and user_id:
            # Vérifier la visibilité
            if not self._can_view_post(db, post, user_id):
                return None
        
        return post
    
    def get_multi(
        self, 
        db: Session, 
        user_id: Optional[int] = None,
        author_id: Optional[int] = None,
        group_id: Optional[int] = None,
        skip: int = 0, 
        limit: int = 20
    ) -> List[Post]:
        """Récupère plusieurs posts avec filtres"""
        query = db.query(Post).filter(Post.is_deleted == False)
        
        if author_id:
            query = query.filter(Post.author_id == author_id)
        
        if group_id:
            query = query.filter(Post.group_id == group_id)
        
        if user_id:
            # Filtrer selon la visibilité
            query = query.filter(
                or_(
                    Post.visibility == PostVisibility.PUBLIC,
                    and_(
                        Post.visibility == PostVisibility.FOLLOWERS,
                        Post.author_id.in_(
                            db.query(Follow.following_id).filter(Follow.follower_id == user_id)
                        )
                    ),
                    Post.author_id == user_id
                )
            )
        
        return query.order_by(desc(Post.created_at)).offset(skip).limit(limit).all()
    
    def create(self, db: Session, obj_in: PostCreate, author_id: int) -> Post:
        """Crée un nouveau post"""
        db_obj = Post(
            author_id=author_id,
            content=obj_in.content,
            post_type=obj_in.post_type,
            visibility=obj_in.visibility,
            group_id=obj_in.group_id,
            location=obj_in.location,
            tags=obj_in.tags
        )
        db.add(db_obj)
        db.flush()
        
        # Ajouter les médias si fournis
        if obj_in.media_ids:
            for idx, media_id in enumerate(obj_in.media_ids):
                post_media = PostMedia(
                    post_id=db_obj.id,
                    media_id=media_id,
                    order=idx
                )
                db.add(post_media)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: Post, obj_in: PostUpdate) -> Post:
        """Met à jour un post"""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, post_id: int, user_id: int) -> bool:
        """Supprime un post (soft delete)"""
        post = self.get(db, post_id, user_id)
        if not post or post.author_id != user_id:
            return False
        
        post.is_deleted = True
        db.commit()
        return True
    
    def increment_view_count(self, db: Session, post_id: int):
        """Incrémente le compteur de vues"""
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.view_count += 1
            db.commit()
    
    def _can_view_post(self, db: Session, post: Post, user_id: int) -> bool:
        """Vérifie si un utilisateur peut voir un post"""
        if post.visibility == PostVisibility.PUBLIC:
            return True
        if post.author_id == user_id:
            return True
        if post.visibility == PostVisibility.FOLLOWERS:
            follow = db.query(Follow).filter(
                Follow.follower_id == user_id,
                Follow.following_id == post.author_id
            ).first()
            return follow is not None
        if post.visibility == PostVisibility.GROUP and post.group_id:
            member = db.query(GroupMember).filter(
                GroupMember.group_id == post.group_id,
                GroupMember.user_id == user_id
            ).first()
            return member is not None
        return False


class CRUDPostComment:
    """CRUD pour les commentaires de posts"""
    
    def get(self, db: Session, comment_id: int) -> Optional[PostComment]:
        """Récupère un commentaire par son ID"""
        return db.query(PostComment).filter(
            PostComment.id == comment_id,
            PostComment.is_deleted == False
        ).first()
    
    def get_by_post(
        self, 
        db: Session, 
        post_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[PostComment]:
        """Récupère les commentaires d'un post"""
        return db.query(PostComment).filter(
            PostComment.post_id == post_id,
            PostComment.parent_id == None,
            PostComment.is_deleted == False
        ).order_by(desc(PostComment.created_at)).offset(skip).limit(limit).all()
    
    def create(self, db: Session, obj_in: PostCommentCreate, post_id: int, author_id: int) -> PostComment:
        """Crée un nouveau commentaire"""
        db_obj = PostComment(
            post_id=post_id,
            author_id=author_id,
            content=obj_in.content,
            parent_id=obj_in.parent_id
        )
        db.add(db_obj)
        db.flush()
        
        # Mettre à jour les compteurs
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.comment_count += 1
            if obj_in.parent_id:
                parent = db.query(PostComment).filter(PostComment.id == obj_in.parent_id).first()
                if parent:
                    parent.reply_count += 1
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, comment_id: int, user_id: int) -> bool:
        """Supprime un commentaire (soft delete)"""
        comment = self.get(db, comment_id)
        if not comment or comment.author_id != user_id:
            return False
        
        comment.is_deleted = True
        post = db.query(Post).filter(Post.id == comment.post_id).first()
        if post:
            post.comment_count = max(0, post.comment_count - 1)
        
        db.commit()
        return True


class CRUDPostReaction:
    """CRUD pour les réactions sur les posts"""
    
    def get(self, db: Session, post_id: int, user_id: int) -> Optional[PostReaction]:
        """Récupère une réaction d'un utilisateur sur un post"""
        return db.query(PostReaction).filter(
            PostReaction.post_id == post_id,
            PostReaction.user_id == user_id
        ).first()
    
    def create_or_update(
        self, 
        db: Session, 
        post_id: int, 
        user_id: int, 
        obj_in: PostReactionCreate
    ) -> PostReaction:
        """Crée ou met à jour une réaction"""
        existing = self.get(db, post_id, user_id)
        
        if existing:
            if existing.reaction_type == obj_in.reaction_type:
                # Même réaction, on la supprime (toggle)
                db.delete(existing)
                post = db.query(Post).filter(Post.id == post_id).first()
                if post:
                    post.like_count = max(0, post.like_count - 1)
                db.commit()
                return None
            else:
                # Changement de réaction
                existing.reaction_type = obj_in.reaction_type
                db.commit()
                db.refresh(existing)
                return existing
        else:
            # Nouvelle réaction
            db_obj = PostReaction(
                post_id=post_id,
                user_id=user_id,
                reaction_type=obj_in.reaction_type
            )
            db.add(db_obj)
            post = db.query(Post).filter(Post.id == post_id).first()
            if post:
                post.like_count += 1
            db.commit()
            db.refresh(db_obj)
            return db_obj
    
    def delete(self, db: Session, post_id: int, user_id: int) -> bool:
        """Supprime une réaction"""
        reaction = self.get(db, post_id, user_id)
        if not reaction:
            return False
        
        db.delete(reaction)
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.like_count = max(0, post.like_count - 1)
        db.commit()
        return True


class CRUDPostShare:
    """CRUD pour les partages de posts"""
    
    def create(self, db: Session, post_id: int, user_id: int, obj_in: PostShareCreate) -> PostShare:
        """Crée un partage de post"""
        db_obj = PostShare(
            post_id=post_id,
            user_id=user_id,
            comment=obj_in.comment
        )
        db.add(db_obj)
        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            post.share_count += 1
        db.commit()
        db.refresh(db_obj)
        return db_obj


class CRUDSocialGroup:
    """CRUD pour les groupes sociaux"""
    
    def get(self, db: Session, group_id: int) -> Optional[SocialGroup]:
        """Récupère un groupe par son ID"""
        return db.query(SocialGroup).filter(
            SocialGroup.id == group_id,
            SocialGroup.is_deleted == False
        ).first()
    
    def get_by_invite_code(self, db: Session, invite_code: str) -> Optional[SocialGroup]:
        """Récupère un groupe par son code d'invitation"""
        return db.query(SocialGroup).filter(
            SocialGroup.invite_code == invite_code,
            SocialGroup.is_deleted == False
        ).first()
    
    def get_multi(
        self, 
        db: Session, 
        user_id: Optional[int] = None,
        skip: int = 0, 
        limit: int = 20
    ) -> List[SocialGroup]:
        """
        Récupère plusieurs groupes.
        FIXED: Private groups are only shown to members (like WhatsApp).
        """
        query = db.query(SocialGroup).filter(SocialGroup.is_deleted == False)
        
        if user_id:
            # Get groups where user is a member
            user_group_ids = db.query(GroupMember.group_id).filter(
                GroupMember.user_id == user_id
            ).subquery()
            
            # Show only:
            # 1. Public groups
            # 2. Groups where user is a member
            # 3. Groups created by user (they're automatically admin)
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    SocialGroup.group_type == GroupType.PUBLIC,
                    SocialGroup.creator_id == user_id,
                    SocialGroup.id.in_(db.query(user_group_ids.c.group_id))
                )
            )
        else:
            # If not logged in, only show public groups
            query = query.filter(SocialGroup.group_type == GroupType.PUBLIC)
        
        return query.order_by(desc(SocialGroup.created_at)).offset(skip).limit(limit).all()
    
    def create(self, db: Session, obj_in: SocialGroupCreate, creator_id: int) -> SocialGroup:
        """Crée un nouveau groupe"""
        import secrets
        import string
        
        # FIXED: Always generate invite code for private groups (default)
        # Groups are private by default like WhatsApp
        group_type = obj_in.group_type if obj_in.group_type else GroupType.PRIVATE
        
        # Générer un code d'invitation unique (always for private groups)
        invite_code = None
        if group_type == GroupType.PRIVATE:
            alphabet = string.ascii_uppercase + string.digits
            invite_code = ''.join(secrets.choice(alphabet) for _ in range(12))  # Longer code for security
            
            # Vérifier l'unicité
            while db.query(SocialGroup).filter(SocialGroup.invite_code == invite_code).first():
                invite_code = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        db_obj = SocialGroup(
            name=obj_in.name,
            description=obj_in.description,
            group_type=group_type,  # Use determined group_type
            creator_id=creator_id,
            avatar_url=obj_in.avatar_url,
            cover_url=obj_in.cover_url,
            max_members=obj_in.max_members,
            requires_approval=obj_in.requires_approval,
            invite_code=invite_code
        )
        db.add(db_obj)
        db.flush()
        
        # FIXED: Add creator as ADMIN (not just owner) - WhatsApp-like behavior
        # Owner has full control, but we also support ADMIN role
        member = GroupMember(
            group_id=db_obj.id,
            user_id=creator_id,
            role=GroupMemberRole.ADMIN  # Creator becomes admin
        )
        db.add(member)
        db_obj.member_count = 1
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: SocialGroup, obj_in: SocialGroupUpdate) -> SocialGroup:
        """Met à jour un groupe"""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def add_member(
        self, 
        db: Session, 
        group_id: int, 
        user_id: int, 
        role: GroupMemberRole = GroupMemberRole.MEMBER
    ) -> GroupMember:
        """Ajoute un membre à un groupe"""
        # Vérifier si déjà membre
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        ).first()
        
        if existing:
            return existing
        
        group = self.get(db, group_id)
        if not group:
            raise ValueError("Groupe introuvable")
        
        # Vérifier la limite de membres
        if group.max_members and group.member_count >= group.max_members:
            raise ValueError("Limite de membres atteinte")
        
        member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            role=role
        )
        db.add(member)
        group.member_count += 1
        db.commit()
        db.refresh(member)
        return member
    
    def remove_member(self, db: Session, group_id: int, user_id: int) -> bool:
        """Retire un membre d'un groupe"""
        member = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        ).first()
        
        if not member:
            return False
        
        db.delete(member)
        group = self.get(db, group_id)
        if group:
            group.member_count = max(0, group.member_count - 1)
        db.commit()
        return True
    
    def is_member(self, db: Session, group_id: int, user_id: int) -> bool:
        """Vérifie si un utilisateur est membre d'un groupe"""
        return db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        ).first() is not None
    
    def get_member_role(self, db: Session, group_id: int, user_id: int) -> Optional[GroupMemberRole]:
        """Récupère le rôle d'un membre dans un groupe"""
        member = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id
        ).first()
        return member.role if member else None


class CRUDGroupMessage:
    """CRUD pour les messages de groupe"""
    
    def get(self, db: Session, message_id: int) -> Optional[GroupMessage]:
        """Récupère un message par son ID"""
        return db.query(GroupMessage).filter(
            GroupMessage.id == message_id,
            GroupMessage.is_deleted == False
        ).first()
    
    def get_by_group(
        self, 
        db: Session, 
        group_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[GroupMessage]:
        """Récupère les messages d'un groupe"""
        return db.query(GroupMessage).filter(
            GroupMessage.group_id == group_id,
            GroupMessage.is_deleted == False
        ).order_by(desc(GroupMessage.created_at)).offset(skip).limit(limit).all()
    
    def create(self, db: Session, obj_in: GroupMessageCreate, group_id: int, sender_id: int) -> GroupMessage:
        """Crée un nouveau message"""
        db_obj = GroupMessage(
            group_id=group_id,
            sender_id=sender_id,
            content=obj_in.content,
            message_type=obj_in.message_type,
            media_id=obj_in.media_id,
            reply_to_id=obj_in.reply_to_id,
            status=MessageStatus.SENT
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: GroupMessage, obj_in: GroupMessageUpdate) -> GroupMessage:
        """Met à jour un message"""
        db_obj.content = obj_in.content
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
        message.status = MessageStatus.DELETED
        db.commit()
        return True
    
    def mark_as_read(self, db: Session, message_id: int, user_id: int) -> bool:
        """Marque un message comme lu"""
        message = self.get(db, message_id)
        if not message:
            return False
        
        # Vérifier si déjà lu
        existing = db.query(MessageReadReceipt).filter(
            MessageReadReceipt.message_id == message_id,
            MessageReadReceipt.user_id == user_id
        ).first()
        
        if not existing:
            receipt = MessageReadReceipt(
                message_id=message_id,
                user_id=user_id
            )
            db.add(receipt)
            message.status = MessageStatus.READ
            db.commit()
        
        return True


class CRUDFeed:
    """CRUD pour le fil d'actualité"""
    
    def generate_feed(self, db: Session, user_id: int, limit: int = 50) -> List[Post]:
        """Génère le fil d'actualité pour un utilisateur"""
        # Récupérer les IDs des utilisateurs suivis
        following_ids = db.query(Follow.following_id).filter(
            Follow.follower_id == user_id
        ).subquery()
        
        # Récupérer les posts des utilisateurs suivis et les posts publics
        posts = db.query(Post).filter(
            Post.is_deleted == False,
            or_(
                Post.author_id.in_(following_ids),
                Post.visibility == PostVisibility.PUBLIC,
                Post.author_id == user_id
            )
        ).order_by(desc(Post.created_at)).limit(limit).all()
        
        return posts
    
    def add_to_feed(self, db: Session, user_id: int, post_id: int, score: float = 0.0) -> Feed:
        """Ajoute un post au feed d'un utilisateur"""
        # Vérifier si déjà présent
        existing = db.query(Feed).filter(
            Feed.user_id == user_id,
            Feed.post_id == post_id
        ).first()
        
        if existing:
            return existing
        
        db_obj = Feed(
            user_id=user_id,
            post_id=post_id,
            relevance_score=score
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


# Instances des CRUD
crud_post = CRUDPost()
crud_post_comment = CRUDPostComment()
crud_post_reaction = CRUDPostReaction()
crud_post_share = CRUDPostShare()
crud_social_group = CRUDSocialGroup()
crud_group_message = CRUDGroupMessage()
crud_feed = CRUDFeed()

