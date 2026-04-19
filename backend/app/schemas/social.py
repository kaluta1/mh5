from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum


# Enums
class PostType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    POLL = "poll"


class PostVisibility(str, Enum):
    PUBLIC = "public"
    FOLLOWERS = "followers"
    PRIVATE = "private"
    GROUP = "group"


class ReactionType(str, Enum):
    LIKE = "like"
    LOVE = "love"
    HAHA = "haha"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class GroupType(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SECRET = "secret"


class GroupMemberRole(str, Enum):
    MEMBER = "member"
    ADMIN = "admin"
    MODERATOR = "moderator"
    OWNER = "owner"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"
    AUDIO = "audio"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"


# Schémas pour les Posts
class PostBase(BaseModel):
    content: Optional[str] = None
    post_type: PostType = PostType.TEXT
    visibility: PostVisibility = PostVisibility.PUBLIC
    location: Optional[str] = None
    tags: Optional[str] = None


class PostCreate(PostBase):
    group_id: Optional[int] = None
    media_ids: Optional[List[int]] = Field(default_factory=list)


class PostUpdate(BaseModel):
    content: Optional[str] = None
    visibility: Optional[PostVisibility] = None
    location: Optional[str] = None
    tags: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None


class PostMediaResponse(BaseModel):
    id: int
    media_id: int
    order: int
    url: Optional[str] = None

    class Config:
        from_attributes = True


class PostResponse(PostBase):
    id: int
    author_id: int
    group_id: Optional[int] = None
    like_count: int
    comment_count: int
    share_count: int
    view_count: int
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    author: Optional[dict] = None  # User info
    media: List[PostMediaResponse] = Field(default_factory=list)
    user_reaction: Optional[ReactionType] = None

    class Config:
        from_attributes = True


# Schémas pour les Commentaires de Posts
class PostCommentBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class PostCommentCreate(PostCommentBase):
    parent_id: Optional[int] = None


class PostCommentResponse(PostCommentBase):
    id: int
    post_id: int
    author_id: int
    parent_id: Optional[int] = None
    like_count: int
    reply_count: int
    created_at: datetime
    updated_at: datetime
    author: Optional[dict] = None
    user_reaction: Optional[ReactionType] = None
    replies: List["PostCommentResponse"] = Field(default_factory=list)

    class Config:
        from_attributes = True


# Schémas pour les Réactions
class PostReactionCreate(BaseModel):
    reaction_type: ReactionType = ReactionType.LIKE


class PostReactionResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    reaction_type: ReactionType
    created_at: datetime
    user: Optional[dict] = None

    class Config:
        from_attributes = True


class PostCommentReactionCreate(BaseModel):
    reaction_type: ReactionType = ReactionType.LIKE


# Schémas pour les Partages
class PostShareCreate(BaseModel):
    comment: Optional[str] = None


class PostShareResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    comment: Optional[str] = None
    created_at: datetime
    user: Optional[dict] = None

    class Config:
        from_attributes = True


# Schémas pour les Groupes Sociaux
class SocialGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    group_type: GroupType = GroupType.PRIVATE
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    max_members: Optional[int] = None
    requires_approval: bool = False


class SocialGroupCreate(SocialGroupBase):
    pass


class SocialGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    group_type: Optional[GroupType] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    max_members: Optional[int] = None
    requires_approval: Optional[bool] = None


class GroupMemberResponse(BaseModel):
    id: int
    group_id: int
    user_id: int
    role: GroupMemberRole
    joined_at: datetime
    is_muted: bool
    is_banned: bool
    user: Optional[dict] = None

    class Config:
        from_attributes = True


class SocialGroupResponse(SocialGroupBase):
    id: int
    creator_id: int
    invite_code: Optional[str] = None
    member_count: int
    post_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    creator: Optional[dict] = None
    user_role: Optional[GroupMemberRole] = None
    is_member: bool = False

    class Config:
        from_attributes = True


# Schémas pour les Demandes d'Adhésion
class GroupJoinRequestCreate(BaseModel):
    message: Optional[str] = None


class GroupJoinRequestResponse(BaseModel):
    id: int
    group_id: int
    user_id: int
    message: Optional[str] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    user: Optional[dict] = None

    class Config:
        from_attributes = True


# Schémas pour les Messages de Groupe
class GroupMessageBase(BaseModel):
    content: Optional[str] = None
    message_type: MessageType = MessageType.TEXT
    media_id: Optional[int] = None
    reply_to_id: Optional[int] = None


class GroupMessageCreate(GroupMessageBase):
    pass


class GroupMessageUpdate(BaseModel):
    content: Optional[str] = None


class MessageSenderBrief(BaseModel):
    """User row exposed on group messages — must not use dict (breaks ORM validation)."""

    id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GroupMessageResponse(GroupMessageBase):
    id: int
    group_id: int
    sender_id: int
    status: MessageStatus
    is_edited: bool
    is_deleted: bool
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    sender: Optional[MessageSenderBrief] = None
    reply_to: Optional["GroupMessageResponse"] = None
    read_by: List[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# Schémas pour le Feed
class FeedResponse(BaseModel):
    id: int
    user_id: int
    post_id: int
    relevance_score: float
    is_seen: bool
    added_at: datetime
    post: Optional[PostResponse] = None

    class Config:
        from_attributes = True


# Schémas pour les listes et pagination
class PostListResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class GroupListResponse(BaseModel):
    groups: List[SocialGroupResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class MessageListResponse(BaseModel):
    messages: List[GroupMessageResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# Schémas Socket.IO
class SocketMessage(BaseModel):
    """Schéma pour les messages Socket.IO"""
    event: str
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PostNotificationData(BaseModel):
    """Données pour les notifications de posts via Socket.IO"""
    post_id: int
    author_id: int
    author_name: str
    content_preview: Optional[str] = None
    post_type: PostType


class ReactionNotificationData(BaseModel):
    """Données pour les notifications de réactions via Socket.IO"""
    post_id: Optional[int] = None
    comment_id: Optional[int] = None
    user_id: int
    user_name: str
    reaction_type: ReactionType


class MessageNotificationData(BaseModel):
    """Données pour les notifications de messages via Socket.IO"""
    group_id: int
    group_name: str
    message_id: int
    sender_id: int
    sender_name: str
    content_preview: Optional[str] = None
    message_type: MessageType


# ============ MESSAGERIE PRIVÉE ============

class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"


class PrivateMessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DELETED = "deleted"


class PrivateMessageBase(BaseModel):
    content: Optional[str] = None
    message_type: str = "text"
    media_id: Optional[int] = None
    reply_to_id: Optional[int] = None


class PrivateMessageCreate(PrivateMessageBase):
    pass


class PrivateMessageUpdate(BaseModel):
    content: Optional[str] = None


class PrivateMessageResponse(PrivateMessageBase):
    id: int
    conversation_id: int
    sender_id: int
    status: PrivateMessageStatus
    is_edited: bool
    is_deleted: bool
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    sender: Optional[dict] = None
    reply_to: Optional["PrivateMessageResponse"] = None
    read_by: List[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ConversationParticipantResponse(BaseModel):
    id: int
    conversation_id: int
    user_id: int
    joined_at: datetime
    is_active: bool
    is_muted: bool
    unread_count: int
    last_read_at: Optional[datetime] = None
    user: Optional[dict] = None

    class Config:
        from_attributes = True


class PrivateConversationResponse(BaseModel):
    id: int
    conversation_type: ConversationType
    user1_id: Optional[int] = None
    user2_id: Optional[int] = None
    group_id: Optional[int] = None
    last_message_id: Optional[int] = None
    last_message_at: Optional[datetime] = None
    message_count: int
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime
    user1: Optional[dict] = None
    user2: Optional[dict] = None
    group: Optional[dict] = None
    last_message: Optional[PrivateMessageResponse] = None
    participants: List[ConversationParticipantResponse] = Field(default_factory=list)
    other_user: Optional[dict] = None  # Pour les conversations directes

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    conversations: List[PrivateConversationResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class PrivateMessageListResponse(BaseModel):
    messages: List[PrivateMessageResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class GroupInvitationCreate(BaseModel):
    invitee_id: int
    message: Optional[str] = None


class GroupInvitationResponse(BaseModel):
    id: int
    group_id: int
    inviter_id: int
    invitee_id: int
    message: Optional[str] = None
    status: str
    responded_at: Optional[datetime] = None
    created_at: datetime
    group: Optional[dict] = None
    inviter: Optional[dict] = None
    invitee: Optional[dict] = None

    class Config:
        from_attributes = True


class GroupInvitationListResponse(BaseModel):
    invitations: List[GroupInvitationResponse]
    total: int

