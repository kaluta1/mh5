from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.media import Media
    from app.models.contests import Contestant

class Comment(Base):
    __tablename__ = "comment"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Le commentaire peut être sur un média ou une participation de concours
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    contestant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=True)
    
    # Commentaire parent pour les réponses
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comment.id"), nullable=True)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Modération
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Statistiques
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="comments")
    media: Mapped[Optional["Media"]] = relationship("Media", back_populates="comments")
    contestant: Mapped[Optional["Contestant"]] = relationship("Contestant", back_populates="comments")
    
    # Commentaires imbriqués
    parent: Mapped[Optional["Comment"]] = relationship("Comment", remote_side="Comment.id", back_populates="replies")
    replies: Mapped[List["Comment"]] = relationship("Comment", back_populates="parent")

class Like(Base):
    __tablename__ = "like"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Un like peut être sur un média ou un commentaire
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    comment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comment.id"), nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="likes")
    media: Mapped[Optional["Media"]] = relationship("Media", back_populates="likes")
    comment: Mapped[Optional["Comment"]] = relationship("Comment")

class Report(Base):
    __tablename__ = "report"
    
    reporter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Un signalement peut concerner différents types de contenu
    media_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("media.id"), nullable=True)
    contest_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest_entry.id"), nullable=True)
    comment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comment.id"), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    reason: Mapped[str] = mapped_column(String(100), nullable=False)  # spam, inappropriate, harassment, etc.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Statut du signalement
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, reviewed, resolved
    
    # Modération
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    moderator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    reporter: Mapped["User"] = relationship("User", foreign_keys=[reporter_id])
    reported_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    moderator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])
