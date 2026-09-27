"""Progression safety holds (Child/Teen Safety Phase 8).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-27

Additive only: one new table, progression_safety_holds (one row per contestant
whose lifecycle advancement to a destination season was held by the Phase 8
participation-safety gate). Nothing is backfilled: no historical vote, ranking,
contestant, membership or TopHigh5 row is read-and-rewritten, and no existing
table, column or row is changed.

Downgrade drops only this table (locally created Phase 8 rows go with it).
"""
from alembic import op


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS progression_safety_holds (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            contestant_id INTEGER NOT NULL REFERENCES contestants(id) ON DELETE CASCADE,
            contest_id INTEGER REFERENCES contest(id) ON DELETE SET NULL,
            round_id INTEGER,
            from_season_id INTEGER REFERENCES contest_seasons(id) ON DELETE SET NULL,
            to_season_id INTEGER NOT NULL REFERENCES contest_seasons(id) ON DELETE CASCADE,
            from_level VARCHAR(20),
            to_level VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'HELD'
                CONSTRAINT ck_progression_safety_holds_status CHECK
                (status IN ('HELD', 'RELEASED', 'REVIEW_REQUIRED')),
            reason_codes JSONB,
            held_at TIMESTAMP NOT NULL,
            last_checked_at TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            resolution VARCHAR(40),
            CONSTRAINT uq_progression_safety_holds_contestant_to_season UNIQUE (contestant_id, to_season_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_progression_safety_holds_id ON progression_safety_holds (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_progression_safety_holds_status ON progression_safety_holds (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_progression_safety_holds_contestant "
               "ON progression_safety_holds (contestant_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS progression_safety_holds")
