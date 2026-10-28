"""A member account retired so its email address and username can be registered again.

The account row stays (every financial, audit, DSM and sponsor record keeps pointing at it); only its
address and username are replaced by placeholders. The original values are kept here, and a later
registration with the same address is linked to it explicitly (successor_user_id): that link carries
the historical DSM classification and nothing else (no sponsor, wallet, KYC or money).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AccountRetirement(Base):
    __tablename__ = "account_retirements"
    __table_args__ = (Index("ix_account_retirements_email_norm", "original_email_norm"),)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    original_email: Mapped[str] = mapped_column(String(255), nullable=False)
    original_email_norm: Mapped[str] = mapped_column(String(255), nullable=False)
    original_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    retired_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    retired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    successor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True,
                                                            unique=True)
    successor_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
