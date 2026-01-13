"""
User Encryption Keys Model
Stores public/private key pairs for E2E encryption
Private keys are encrypted at rest
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.core.database import Base


class UserEncryptionKeys(Base):
    """User encryption keys for E2E messaging"""
    __tablename__ = "user_encryption_keys"
    
    # User ID from main platform
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Public key (stored in plain text - safe to share)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Private key (encrypted at rest)
    # In production, use additional encryption layer
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Key metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
