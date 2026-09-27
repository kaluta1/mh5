"""Interaction safety: user blocks + reported private messages (Child/Teen Safety Phase 9).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-27

Additive only:
- new table user_blocks (one row per blocker -> blocked pair);
- new nullable column report.private_message_id (reports of a private message).

Nothing is backfilled. No existing row, comment, message, conversation, vote,
ranking or financial record is read-and-rewritten.

Downgrade drops only the new table and column (locally created Phase 9 rows go
with them).
"""
from alembic import op


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_blocks (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT uq_user_blocks_blocker_blocked UNIQUE (blocker_id, blocked_id),
            CONSTRAINT ck_user_blocks_not_self CHECK (blocker_id <> blocked_id))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_blocks_id ON user_blocks (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_blocks_blocked ON user_blocks (blocked_id)")
    op.execute("ALTER TABLE report ADD COLUMN IF NOT EXISTS private_message_id INTEGER "
               "REFERENCES private_messages(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE report DROP COLUMN IF EXISTS private_message_id")
    op.execute("DROP TABLE IF EXISTS user_blocks")
