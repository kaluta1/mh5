from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class VoteStatus(str, enum.Enum):
    ACTIVE = "active"
    REPLACED = "replaced"
    CANCELLED = "cancelled"


class Vote(Base):
    __tablename__ = "votes"
    voter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    stage_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_stages.id"), nullable=False)
    
    # Position dans le classement personnel (1-5)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # 5,4,3,2,1 selon position
    
    vote_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[VoteStatus] = mapped_column(SQLEnum(VoteStatus), default=VoteStatus.ACTIVE)
    
    # Relations
    voter: Mapped["User"] = relationship("User", foreign_keys=[voter_id])
    contestant: Mapped["Contestant"] = relationship("Contestant")
    stage: Mapped["ContestStage"] = relationship("ContestStage")


class VoteSession(Base):
    __tablename__ = "vote_sessions"
    voter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contest_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_types.id"), nullable=False)
    stage_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_stages.id"), nullable=False)
    
    votes_count: Mapped[int] = mapped_column(Integer, default=0)
    max_votes_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    last_vote_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    voter: Mapped["User"] = relationship("User")
    contest_type: Mapped["ContestType"] = relationship("ContestType")
    stage: Mapped["ContestStage"] = relationship("ContestStage")


class MyFavorites(Base):
    __tablename__ = "my_favorites"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    position: Mapped[int] = mapped_column(Integer, default=0)  # Ordre d'affichage (0 = pas d'ordre défini)
    added_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contestant: Mapped["Contestant"] = relationship("Contestant")


class ContestComment(Base):
    __tablename__ = "contest_comments"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest_comments.id"), nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contestant: Mapped["Contestant"] = relationship("Contestant")
    parent: Mapped[Optional["ContestComment"]] = relationship("ContestComment", remote_side="ContestComment.id")
    replies: Mapped[List["ContestComment"]] = relationship("ContestComment", back_populates="parent")


class ContestLike(Base):
    __tablename__ = "contest_likes"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contestant: Mapped["Contestant"] = relationship("Contestant")


class PageView(Base):
    __tablename__ = "page_views"
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped[Optional["User"]] = relationship("User")
    contestant: Mapped["Contestant"] = relationship("Contestant")


class ReactionType(str, enum.Enum):
    LIKE = "like"
    LOVE = "love"
    WOW = "wow"
    DISLIKE = "dislike"


class ContestantReaction(Base):
    __tablename__ = "contestant_reactions"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    # Utiliser String directement et valider avec l'enum dans le code
    reaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contestant: Mapped["Contestant"] = relationship("Contestant")
    
    # Contrainte unique pour éviter les doublons
    __table_args__ = (
        {'extend_existing': True},
    )


class ContestantShare(Base):
    """
    Table pour enregistrer les partages de contestants.
    - author_id: L'auteur du contestant (celui qui a créé le contestant)
    - shared_by_user_id: L'utilisateur qui partage le contestant
    - contestant_id: Le contestant partagé
    - referral_code: Le code de parrainage de celui qui partage
    """
    __tablename__ = "contestant_shares"
    
    # ID de l'auteur du contestant (celui qui a créé le contestant)
    author_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # ID de celui qui partage
    shared_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # ID du contestant partagé
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    # Code de parrainage de celui qui partage
    referral_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Lien de partage
    share_link: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Plateforme de partage (facebook, twitter, whatsapp, etc.)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Date de création
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relations
    author: Mapped[Optional["User"]] = relationship("User", foreign_keys=[author_id])
    shared_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[shared_by_user_id])
    contestant: Mapped["Contestant"] = relationship("Contestant")
    
    # Conserver user_id pour compatibilité (déprécié, utiliser author_id)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id], overlaps="author")


class ContestantVoting(Base):
    """
    Table pour enregistrer les votes des utilisateurs pour les contestants.
    Stocke l'utilisateur qui vote, le contestant, le contest et la saison active.
    """
    __tablename__ = "contestant_voting"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_seasons.id"), nullable=False)

    # MyHigh5 bucket at vote time: "cat:{category_id}" or "ty:{contest_type}:{contest_mode}".
    # Source of truth for per-category 5-slot cap; independent of ambiguous contest_id joins.
    vote_bucket_key: Mapped[str] = mapped_column(String(128), nullable=False)
    
    vote_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Position dans le classement MyHigh5 de l'utilisateur (1-5)
    # Le 1er reçoit 5 points, le 2ème 4 points, etc.
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    
    # Points attribués selon la position (5, 4, 3, 2, 1)
    # Calculé automatiquement lors du vote ou du réordonnancement
    points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    contestant: Mapped["Contestant"] = relationship("Contestant")
    contest: Mapped["Contest"] = relationship("Contest")
    season: Mapped["ContestSeason"] = relationship("ContestSeason")
    
    # Contrainte unique pour éviter les doublons : un utilisateur ne peut voter qu'une seule fois 
    # pour un contestant donné dans une saison donnée
    # Mais il peut voter pour plusieurs contestants différents dans la même saison
    __table_args__ = (
        UniqueConstraint('user_id', 'contestant_id', 'season_id', name='uq_contestant_voting'),
        {'extend_existing': True},
    )
