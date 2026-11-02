"""Administrator-approved restoration of a DSM sponsor link (Prompt 6). One row per member, never updated."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class DsmSponsorRestoration(Base):
    __tablename__ = "dsm_sponsor_restorations"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_dsm_sponsor_restoration_user"),
        CheckConstraint("status IN ('APPLIED', 'REFUSED')", name="ck_dsm_restoration_status"),
        CheckConstraint("user_id <> restored_sponsor_id", name="ck_dsm_restoration_not_self"),
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    dsm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_sponsor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    restored_sponsor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    approved_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
