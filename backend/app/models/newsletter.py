"""
Modèle pour les abonnements à la newsletter
"""
from typing import Optional
from sqlalchemy import String, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base


class NewsletterSubscription(Base):
    """Abonnement à la newsletter"""
    __tablename__ = "newsletter_subscriptions"
    
    # Email (unique)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Informations de l'appareil et localisation (stockées en JSON)
    device_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # user_agent, platform, etc.
    location_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # country, city, continent, ip, etc.
    
    # Date de vérification
    verified_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Date de désinscription
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    def __repr__(self):
        return f"<NewsletterSubscription {self.id}: {self.email} - Active: {self.is_active}>"

