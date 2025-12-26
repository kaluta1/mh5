from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, ForeignKey, DateTime, Index, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.post import Post


class Feed(Base):
    """
    Modèle pour le fil d'actualité (feed).
    Ce modèle permet de stocker les posts qui apparaissent dans le feed d'un utilisateur.
    Il peut être utilisé pour un système de cache ou de personnalisation.
    """
    __tablename__ = "feeds"
    
    # Utilisateur propriétaire du feed
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Post à afficher dans le feed
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Score de pertinence (pour l'ordre d'affichage)
    relevance_score: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    
    # Indicateur si le post a été vu
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Date d'ajout au feed
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="feed_entries")
    post: Mapped["Post"] = relationship("Post", foreign_keys=[post_id])
    
    # Index composite pour les requêtes fréquentes
    __table_args__ = (
        Index("idx_feed_user_seen", "user_id", "is_seen"),
        Index("idx_feed_user_score", "user_id", "relevance_score"),
    )

