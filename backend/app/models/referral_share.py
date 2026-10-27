from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReferralShareLink(Base):
    """A member's short link (/s/{short_code}). Destination, owner and invitation choice are fixed at
    creation (the database refuses to change them); a link is only ever disabled."""
    __tablename__ = "referral_share_links"
    __table_args__ = (
        # One ACTIVE link per member, destination and invitation choice; a disabled one frees the slot.
        Index("uq_referral_share_active_user_url", "user_id", "normalized_url", "invitation_enabled", unique=True,
              postgresql_where=text("disabled_at IS NULL"), sqlite_where=text("disabled_at IS NULL")),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    short_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Opening the link applies the creator's personal invitation (server-side identity only).
    invitation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                                     server_default=text("true"))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class ReferralShareClick(Base):
    __tablename__ = "referral_share_clicks"

    share_link_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("referral_share_links.id"), nullable=False, index=True
    )
    referrer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    referer: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    landing_url: Mapped[str] = mapped_column(Text, nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReferralShareConversion(Base):
    __tablename__ = "referral_share_conversions"

    referrer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    converted_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    conversion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    conversion_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    share_link_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("referral_share_links.id"), nullable=True
    )
    converted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
