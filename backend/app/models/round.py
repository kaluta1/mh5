from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Date, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base

class RoundStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Round(Base):
    """
    Modèle pour les rounds d'un concours.
    Un round représente une cohorte temporelle de participants (ex: Round Janvier, Round Février).
    Les dates de soumission et de vote sont spécifiques à chaque round.
    """
    __tablename__ = "rounds"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RoundStatus] = mapped_column(SQLEnum(RoundStatus), default=RoundStatus.UPCOMING)
    
    # Dates (migrées depuis Contest)
    submission_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    submission_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    voting_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    voting_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Dates des saisons spécifiques à ce round
    city_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    city_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    country_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    country_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    regional_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    regional_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    continental_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    continental_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    global_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    global_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    contest: Mapped["Contest"] = relationship("Contest", back_populates="rounds")
    contestants: Mapped[List["Contestant"]] = relationship("Contestant", back_populates="round")
    seasons: Mapped[List["ContestSeason"]] = relationship("ContestSeason", back_populates="round")
