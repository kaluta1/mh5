from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Text, Table, Column
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User

# Table d'association pour les membres des clubs
club_members = Table(
    "club_members",
    Base.metadata,
    Column("club_id", Integer, ForeignKey("club.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("joined_at", DateTime, default=datetime.utcnow),
    Column("is_admin", Boolean, default=False)
)

# Table d'association pour les membres des groupes privés
private_group_members = Table(
    "private_group_members",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("private_group.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("joined_at", DateTime, default=datetime.utcnow),
    Column("is_admin", Boolean, default=False)
)

class Club(Base):
    __tablename__ = "club"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Créateur du club
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Configuration du club
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Métadonnées
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Statistiques
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relations
    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id])
    members: Mapped[List["User"]] = relationship("User", secondary=club_members, back_populates="clubs")

class PrivateGroup(Base):
    __tablename__ = "private_group"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Créateur du groupe
    creator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Configuration du groupe
    max_members: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    invite_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    
    # Métadonnées
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Statistiques
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relations
    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id])
    members: Mapped[List["User"]] = relationship("User", secondary=private_group_members, back_populates="private_groups")

class ClubJoinRequest(Base):
    __tablename__ = "club_join_request"
    
    club_id: Mapped[int] = mapped_column(Integer, ForeignKey("club.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    club: Mapped["Club"] = relationship("Club")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])
