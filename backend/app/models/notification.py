from typing import Optional
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class NotificationType(str, enum.Enum):
    SYSTEM = "system"
    CONTEST = "contest"
    COMPTE = "compte"


class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(SQLEnum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Relations optionnelles pour lier la notification à une entité spécifique
    related_contestant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=True)
    related_comment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comment.id"), nullable=True)
    related_contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id"), nullable=True)
    
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="notifications")
    related_contestant: Mapped[Optional["Contestant"]] = relationship("Contestant")
    related_comment: Mapped[Optional["Comment"]] = relationship("Comment")
    related_contest: Mapped[Optional["Contest"]] = relationship("Contest")

