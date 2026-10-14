"""Fingerprints of exposed password hashes.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-15

Additive only. Nothing that exists is changed, moved or deleted.

  * exposed_password_fingerprints (NEW, created EMPTY): the SHA-256 of stored
    password hashes known to have been exposed (app.services.password_exposure).
    No hash, password, account id or email is stored. It is filled on purpose by
    app/scripts/load_exposed_password_fingerprints.py; until then it is empty
    and the Super Admin bootstrap refuses to run.

No user, role, permission, payment, deposit, ledger or commission row is read
or changed. Re-running the upgrade is a no-op. Downgrade drops the table.
"""
from alembic import op


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS exposed_password_fingerprints (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            fingerprint VARCHAR(64) NOT NULL,
            source VARCHAR(100) NULL,
            CONSTRAINT uq_exposed_password_fingerprints_fingerprint UNIQUE (fingerprint),
            CONSTRAINT ck_exposed_password_fingerprints_hex CHECK (fingerprint ~ '^[0-9a-f]{64}$')
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_exposed_password_fingerprints_id ON exposed_password_fingerprints (id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS exposed_password_fingerprints")
