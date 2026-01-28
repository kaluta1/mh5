from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.round import Round


class ContestStageLevel(str, enum.Enum):
    UPLOAD = "upload"
    CITY = "city"
    COUNTRY = "country"
    REGIONAL = "regional"
    CONTINENTAL = "continental"
    GLOBAL = "global"
    FINALE = "finale"


class SeasonLevel(str, enum.Enum):
    CITY = "city"
    COUNTRY = "country"
    REGIONAL = "regional"
    CONTINENT = "continent"
    GLOBAL = "global"


class ContestStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    UPLOAD_PHASE = "upload_phase"
    VOTING_ACTIVE = "voting_active"
    VOTING_ENDED = "voting_ended"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VotingRestriction(str, enum.Enum):
    NONE = "none"
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"
    GEOGRAPHIC = "geographic"
    AGE_RESTRICTED = "age_restricted"


class ContestType(Base):
    __tablename__ = "contest_types"
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voting_restriction: Mapped[VotingRestriction] = mapped_column(SQLEnum(VotingRestriction), default=VotingRestriction.NONE)
    max_submissions_per_user: Mapped[int] = mapped_column(Integer, default=1)
    upload_duration_days: Mapped[int] = mapped_column(Integer, default=60)
    voting_duration_days: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    categories: Mapped[List["ContestCategory"]] = relationship("ContestCategory", back_populates="contest_type")


class ContestCategory(Base):
    __tablename__ = "contest_categories"
    contest_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_types.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    contest_type: Mapped["ContestType"] = relationship("ContestType", back_populates="categories")


    GLOBAL = "global"

    
class ContestSeason(Base):
    __tablename__ = "contest_seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    round_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[SeasonLevel] = mapped_column(SQLEnum(SeasonLevel, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    round: Mapped[Optional["Round"]] = relationship("Round", back_populates="seasons")
    stages: Mapped[List["ContestStage"]] = relationship("ContestStage", back_populates="season")
    contestants: Mapped[List["ContestantSeason"]] = relationship("ContestantSeason", back_populates="season")
    contests: Mapped[List["ContestSeasonLink"]] = relationship("ContestSeasonLink", back_populates="season")


class ContestStage(Base):
    __tablename__ = "contest_stages"
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_seasons.id"), nullable=False)
    stage_level: Mapped[ContestStageLevel] = mapped_column(SQLEnum(ContestStageLevel), nullable=False)
    
    # Geographic scope (null for global stages)
    continent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("continents.id"), nullable=True)
    region_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("regions.id"), nullable=True)
    country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("countries.id"), nullable=True)
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    
    status: Mapped[ContestStatus] = mapped_column(SQLEnum(ContestStatus), default=ContestStatus.UPCOMING)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    max_qualifiers: Mapped[int] = mapped_column(Integer, default=5)
    min_participants: Mapped[int] = mapped_column(Integer, default=2)
    
    # Relations
    season: Mapped["ContestSeason"] = relationship("ContestSeason", back_populates="stages")
    continent: Mapped[Optional["Continent"]] = relationship("Continent")
    region: Mapped[Optional["Region"]] = relationship("Region")
    country: Mapped[Optional["Country"]] = relationship("Country")
    city: Mapped[Optional["City"]] = relationship("City")
    rankings: Mapped[List["ContestantRanking"]] = relationship("ContestantRanking", back_populates="stage")


class Contestant(Base):
    __tablename__ = "contestants"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=True)  # Optional if linked via round
    round_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=True)
    season_id: Mapped[int] = mapped_column(Integer, nullable=True)  # Legacy/Transition: Can be Contest ID or ContestSeason ID
    
    # Submission details
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_media_ids: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # JSON array of up to 10 image media IDs
    video_media_ids: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # JSON array of video media IDs
    
    # Geographic data (copied from user at creation time)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    continent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Author gender (copied from user at creation time)
    author_gender: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Nominator location (for nomination contests)
    nominator_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nominator_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    registration_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    verification_status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, verified, rejected
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_qualified: Mapped[bool] = mapped_column(Boolean, default=True)  # Par défaut, tous les contestants sont qualifiés
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    submissions: Mapped[List["ContestSubmission"]] = relationship("ContestSubmission", back_populates="contestant")
    rankings: Mapped[List["ContestantRanking"]] = relationship("ContestantRanking", back_populates="contestant")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="contestant")
    seasons: Mapped[List["ContestantSeason"]] = relationship("ContestantSeason", back_populates="contestant")
    seasons: Mapped[List["ContestantSeason"]] = relationship("ContestantSeason", back_populates="contestant")
    verifications: Mapped[List["ContestantVerification"]] = relationship("ContestantVerification", back_populates="contestant")
    round: Mapped[Optional["Round"]] = relationship("Round", back_populates="contestants")


class ContestSubmission(Base):
    __tablename__ = "contest_submissions"
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, video, youtube, vimeo
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    upload_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    moderation_status: Mapped[str] = mapped_column(String(50), default="pending")
    
    # Relations
    contestant: Mapped["Contestant"] = relationship("Contestant", back_populates="submissions")


class ContestantRanking(Base):
    __tablename__ = "contestant_rankings"
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    stage_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_stages.id"), nullable=False)
    
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    total_votes: Mapped[int] = mapped_column(Integer, default=0)
    page_views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    final_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    contestant: Mapped["Contestant"] = relationship("Contestant", back_populates="rankings")
    stage: Mapped["ContestStage"] = relationship("ContestStage", back_populates="rankings")


class ContestantSeason(Base):
    """
    Modèle de liaison entre les contestants et les seasons.
    Permet une relation many-to-many entre contestants et seasons.
    """
    __tablename__ = "contestant_seasons"
    
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_seasons.id"), nullable=False)
    
    # Métadonnées de la liaison
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relations
    contestant: Mapped["Contestant"] = relationship("Contestant", back_populates="seasons")
    season: Mapped["ContestSeason"] = relationship("ContestSeason", back_populates="contestants")
    
    # Contrainte d'unicité : un contestant ne peut être lié qu'une seule fois à une saison
    __table_args__ = (
        UniqueConstraint('contestant_id', 'season_id', name='uq_contestant_season'),
        {"comment": "Liaison entre contestants et seasons"}
    )


class ContestSeasonLink(Base):
    """
    Modèle de liaison entre les contests et les seasons.
    Permet une relation many-to-many entre contests et seasons.
    """
    __tablename__ = "contest_season_links"
    
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_seasons.id"), nullable=False)
    
    # Métadonnées de la liaison
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relations
    contest: Mapped["Contest"] = relationship("Contest", back_populates="seasons")
    season: Mapped["ContestSeason"] = relationship("ContestSeason", back_populates="contests")
    
    # Contrainte d'unicité : un contest ne peut être lié qu'une seule fois à une saison
    __table_args__ = (
        UniqueConstraint('contest_id', 'season_id', name='uq_contest_season'),
        {"comment": "Liaison entre contests et seasons"}
    )
