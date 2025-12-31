"""
Modèle pour les logs de connexion des utilisateurs
"""
from typing import Optional
from sqlalchemy import String, Boolean, JSON, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.db.base_class import Base


class LoginLog(Base):
    """Log de connexion d'un utilisateur"""
    __tablename__ = "login_logs"
    
    # Référence à l'utilisateur
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Adresse IP
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)  # IPv6 peut faire jusqu'à 45 caractères
    
    # User Agent
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Informations de l'appareil (stockées en JSON)
    device_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # platform, browser, screen_size, etc.
    
    # Informations de localisation (stockées en JSON)
    location_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # country, city, continent, timezone, etc.
    
    # Date et heure de connexion (created_at vient de Base, mais on peut ajouter login_at pour plus de clarté)
    login_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, index=True)
    
    # Statut de la connexion
    is_successful: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # Raison d'échec (si is_successful = False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="login_logs")
    
    def __repr__(self):
        return f"<LoginLog {self.id}: User {self.user_id} - {self.login_at} - Success: {self.is_successful}>"

