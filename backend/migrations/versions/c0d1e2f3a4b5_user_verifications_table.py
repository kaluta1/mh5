"""Ensure the user_verifications table exists (contest entry media verification).

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-05

Root cause: user_verifications is created by the old revision
'add_user_verifications' (2025-12-08). Databases that were bootstrapped from
the model registry and then stamped past that revision never ran it, and the
UserVerification model was not part of app.models (it was imported only by its
endpoint module), so the bootstrap did not create the table either. On such a
database every request touching the table fails with "relation
user_verifications does not exist" (GET /api/v1/verifications/me -> 503, and
participation in a contest that requires a selfie / voice / brand / content
verification).

This migration converges every database on the SAME table the old revision
creates: identical columns (plain VARCHAR for type / media type / status),
foreign keys and indexes. It is additive and idempotent:

  * table present (the old revision did run)  -> nothing is changed;
  * table absent                              -> it is created, EMPTY.

No row is inserted, no verification state is fabricated, and no other table,
column or row is touched. The PostgreSQL enum types the old revision also
creates were never used by the table and are not needed.

Downgrade is a deliberate no-op: this revision cannot know whether the table
came from here or from 'add_user_verifications' (possibly with members' rows),
so it never drops it.
"""
from alembic import op


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_verifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            verification_type VARCHAR(50) NOT NULL,
            media_url VARCHAR(500) NOT NULL,
            media_type VARCHAR(20) NOT NULL,
            media_key VARCHAR(255),
            duration_seconds INTEGER,
            file_size_bytes INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            rejection_reason TEXT,
            contest_id INTEGER REFERENCES contest(id) ON DELETE SET NULL,
            contestant_id INTEGER REFERENCES contestants(id) ON DELETE SET NULL,
            reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_verifications_user_type "
               "ON user_verifications (user_id, verification_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_verifications_status ON user_verifications (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_verifications_user_id ON user_verifications (user_id)")


def downgrade() -> None:
    # Never drops the table: see the module docstring.
    pass
