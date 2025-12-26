"""
Modèle pour les messages de contact
"""
from typing import Optional
from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base


class ContactMessage(Base):
    """Message de contact depuis le formulaire"""
    __tablename__ = "contact_messages"
    
    # Informations de contact
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # general, billing, account, technical, partnership, other
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Statut
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Date de lecture (created_at vient de Base)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ContactMessage {self.id}: {self.email} - {self.subject}>"

