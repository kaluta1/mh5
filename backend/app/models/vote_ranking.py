"""
UserVoteRanking model for ranked voting system
Max 5 votes per user per round, position-based points (1st=5pts, 5th=1pt)
"""

from typing import Optional
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base_class import Base


class UserVoteRanking(Base):
    """
    Table pour le système de vote par classement.
    
    Règles:
    - Max 5 votes par utilisateur par round
    - Position 1 = 5 points, Position 2 = 4 points, ..., Position 5 = 1 point
    - Contrainte unique: (user_id, round_id, contestant_id)
    - Le 6e vote remplace le 5e et décale les positions
    """
    __tablename__ = "user_vote_rankings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id", ondelete="CASCADE"), nullable=False)
    
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    points: Mapped[int] = mapped_column(Integer, nullable=False)    # 5,4,3,2,1
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Contrainte unique: un utilisateur ne peut voter qu'une fois pour un contestant dans un round
    __table_args__ = (
        UniqueConstraint('user_id', 'round_id', 'contestant_id', name='unique_user_round_contestant_vote'),
    )
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    round: Mapped["Round"] = relationship("Round", foreign_keys=[round_id])
    contestant: Mapped["Contestant"] = relationship("Contestant", foreign_keys=[contestant_id])
    
    @staticmethod
    def calculate_points(position: int) -> int:
        """Calcule les points en fonction de la position (1-5)"""
        points_map = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
        return points_map.get(position, 0)
