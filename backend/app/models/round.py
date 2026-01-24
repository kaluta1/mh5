from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime, Boolean, Enum as SQLEnum, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base

class RoundStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Association table for N:N relationship between Round and Contest
round_contests = Table(
    'round_contests',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('round_id', Integer, ForeignKey('rounds.id', ondelete='CASCADE'), nullable=False),
    Column('contest_id', Integer, ForeignKey('contest.id', ondelete='CASCADE'), nullable=False),
    Column('created_at', DateTime, default=datetime.utcnow),
)


class Round(Base):
    """
    Modèle pour les rounds.
    Un round représente une cohorte temporelle (ex: Round Janvier 2026, Round Février 2026).
    Un round peut contenir plusieurs contests (relation N:N via round_contests).
    """
    __tablename__ = "rounds"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Ancien champ - gardé pour compatibilité (nullable maintenant)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id"), nullable=True, index=True)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RoundStatus] = mapped_column(SQLEnum(RoundStatus), default=RoundStatus.UPCOMING)
    
    # État du round
    is_submission_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_voting_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_season_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # city, country, regional, continental, global
    
    # Dates de submission (1er au dernier jour du mois)
    submission_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    submission_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Dates de voting générales (peut être différent selon le contest type)
    voting_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    voting_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Dates des saisons spécifiques à ce round
    # City season (M+1) - pour contests SANS voting_type_id
    city_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    city_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Country season (M+1) - pour contests AVEC voting_type_id
    country_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    country_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Regional season (M+2)
    regional_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    regional_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Continental season (M+3)
    continental_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    continental_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Global season (M+4)
    global_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    global_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    # Ancienne relation 1:N (gardée pour compatibilité)
    contest: Mapped[Optional["Contest"]] = relationship("Contest", back_populates="legacy_rounds", foreign_keys=[contest_id])
    
    # Nouvelle relation N:N via table de liaison
    contests: Mapped[List["Contest"]] = relationship(
        "Contest", 
        secondary=round_contests, 
        back_populates="rounds"
    )
    
    contestants: Mapped[List["Contestant"]] = relationship("Contestant", back_populates="round")
    seasons: Mapped[List["ContestSeason"]] = relationship("ContestSeason", back_populates="round")
