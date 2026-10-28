"""Account retirements: a member account can be retired so its email address and username can be
registered again, without deleting the account row or anything that points at it.

Revision ID: b8d0f2a4c6e9
Revises: a7c9e1b3d5f7
Create Date: 2026-10-29

Additive: one new table, no row rewritten. Downgrade refuses while a retirement exists (the retired
accounts' original addresses live only here).
"""
from alembic import op


revision = "b8d0f2a4c6e9"
down_revision = "a7c9e1b3d5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_retirements (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            original_email VARCHAR(255) NOT NULL,
            original_email_norm VARCHAR(255) NOT NULL,
            original_username VARCHAR(255),
            reason VARCHAR(300) NOT NULL,
            retired_by INTEGER REFERENCES users(id),
            retired_at TIMESTAMP NOT NULL,
            successor_user_id INTEGER UNIQUE REFERENCES users(id),
            successor_linked_at TIMESTAMP,
            CONSTRAINT ck_account_retirements_not_own_successor CHECK (successor_user_id IS NULL OR successor_user_id <> user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_account_retirements_email_norm ON account_retirements (original_email_norm)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_account_retirements_id ON account_retirements (id)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM account_retirements) THEN
                RAISE EXCEPTION 'account_retirements holds retired accounts; refusing to drop it';
            END IF;
        END $$
    """)
    op.execute("DROP TABLE IF EXISTS account_retirements")
