from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Enum, Text, Date, Float
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, date
import enum

from app.db.base_class import Base

class VotingRestriction(str, enum.Enum):
    NONE = "none"
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"
    GEOGRAPHIC = "geographic"
    AGE_RESTRICTED = "age_restricted"

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.media import Media
    from app.models.comment import Comment, Like
    from app.models.transaction import UserTransaction
    from app.models.prize import Prize

class Contest(Base):
    __tablename__ = "contest"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contest_type: Mapped[str] = mapped_column(String(50), nullable=False)  # beauty, handsome, latest_hits, etc.
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # URL de l'image de couverture
    
    # Template de référence
    template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest_template.id"), nullable=True)
    
    # Dates
    submission_start_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    submission_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    voting_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    voting_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # État
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_submission_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_voting_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Structure géographique
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # 'city', 'country', 'region', 'continent', 'global'
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    
    # Relations
    template: Mapped[Optional["ContestTemplate"]] = relationship("ContestTemplate", back_populates="contests")
    location: Mapped[Optional["Location"]] = relationship("Location", back_populates="contests")
    entries: Mapped[List["ContestEntry"]] = relationship("ContestEntry", back_populates="contest")
    transactions: Mapped[List["UserTransaction"]] = relationship("UserTransaction", back_populates="contest")
    prizes: Mapped[List["Prize"]] = relationship("Prize", back_populates="contest")
    seasons: Mapped[List["ContestSeasonLink"]] = relationship("ContestSeasonLink", back_populates="contest")
    
    # Règles du concours
    gender_restriction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # male, female, ou null si pas de restriction
    max_entries_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Restriction de vote (pour l'admin)
    voting_restriction: Mapped[VotingRestriction] = mapped_column(Enum(VotingRestriction), default=VotingRestriction.NONE, nullable=False)
    
    # Image du concours
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Nombre de participants
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ContestTemplate(Base):
    __tablename__ = "contest_template"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contest_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Configuration du template
    has_geo_restrictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_gender_restrictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_submission_days: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    default_voting_days: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    
    # Relations
    contests: Mapped[List["Contest"]] = relationship("Contest", back_populates="template")


class Location(Base):
    __tablename__ = "location"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # 'city', 'country', 'region', 'continent', 'global'
    
    # Relations hiérarchiques
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    parent: Mapped[Optional["Location"]] = relationship("Location", remote_side="Location.id", back_populates="children")
    children: Mapped[List["Location"]] = relationship("Location", back_populates="parent")
    
    # Relations avec les concours
    contests: Mapped[List["Contest"]] = relationship("Contest", back_populates="location")


class ContestEntry(Base):
    __tablename__ = "contest_entry"
    
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id"), nullable=False)
    
    # Score et classement
    total_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="contest_entries")
    contest: Mapped["Contest"] = relationship("Contest", back_populates="entries")
    media: Mapped["Media"] = relationship("Media", back_populates="contest_entries")
    votes: Mapped[List["ContestVote"]] = relationship("ContestVote", back_populates="entry")


class ContestVote(Base):
    __tablename__ = "contest_votes"
    
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_entry.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 pour MyFav
    
    # Relations
    entry: Mapped["ContestEntry"] = relationship("ContestEntry", back_populates="votes")
    user: Mapped["User"] = relationship("User")


class ContestFavorite(Base):
    __tablename__ = "contest_favorites"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    added_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contest: Mapped["Contest"] = relationship("Contest")
