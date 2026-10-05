"""Account security state (EMAIL-2).

AuthToken       one-time credentials sent by email (email verification,
                password reset). Only a SHA-256 digest of the credential is
                stored; the credential itself exists in the email and nowhere
                else. NOT related to `user_verifications` (contest media).
AuthRateLimit   durable fixed-window counters for the public auth endpoints
                (per client address, per account, global). Keys are keyed
                hashes: no address or email is stored.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

PURPOSE_EMAIL_VERIFICATION = "email_verification"
PURPOSE_PASSWORD_RESET = "password_reset"
TOKEN_PURPOSES = (PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('email_verification', 'password_reset')", name="ck_auth_tokens_purpose"),
        Index("ix_auth_tokens_user_purpose", "user_id", "purpose"),
        Index("ix_auth_tokens_expires_at", "expires_at"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Keyed hash of the address the credential was sent to: it stops working
    # if the account's address is no longer that one.
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # users.security_version when issued (checked for password reset).
    security_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        UniqueConstraint("scope", "key_hash", "window_start", name="uq_auth_rate_limits_window"),
        Index("ix_auth_rate_limits_window_start", "window_start"),
    )

    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
