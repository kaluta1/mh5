"""Phase 9 interaction safety state (Child/Teen Safety: comments, messaging).

UserBlock: one member blocks another. A block stops new direct interaction in
BOTH directions (messages, conversation creation, being added to a group by the
other person, replies to the other person's comments, follows). It never deletes
or rewrites history. Who blocked whom is visible only to the blocker.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_blocker_blocked"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_not_self"),
        Index("ix_user_blocks_blocked", "blocked_id"),
    )

    blocker_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
