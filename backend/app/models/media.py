from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Enum, Boolean, DateTime
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.contest import ContestEntry
    from app.models.comment import Comment, Like

class Media(Base):
    __tablename__ = "media"
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'image', 'video'
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # Chemin du fichier ou URL S3
    url: Mapped[str] = mapped_column(String(512), nullable=False)   # URL accessible publiquement
    
    # Métadonnées pour les médias (taille, dimensions, etc.)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Pour les vidéos, en secondes
    # Child/Teen Safety s.10 (Phase 5): set when EXIF/GPS/XMP/IPTC metadata was
    # stripped from an uploaded image. NULL = not sanitized (legacy upload or video).
    metadata_sanitized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="medias")
    contest_entries: Mapped[List["ContestEntry"]] = relationship("ContestEntry", back_populates="media")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="media")
    likes: Mapped[List["Like"]] = relationship("Like", back_populates="media")
