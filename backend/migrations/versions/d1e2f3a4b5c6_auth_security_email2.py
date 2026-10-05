"""EMAIL-2: account security state (session version, one-time email
credentials, durable auth rate limits).

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-10-05

Additive only. Four things, all new:

  users.email_verification_required   BOOLEAN NOT NULL DEFAULT false
      Login policy marker. TRUE = the account was created by public
      registration under the verify-before-login rule and cannot sign in
      until its address is verified. EVERY EXISTING ROW GETS FALSE: accounts
      that predate the rule are grandfathered and keep signing in, verified
      or not. Nothing is marked verified, no verification date is invented;
      users.email_verified is not touched.

  users.security_version   INTEGER NOT NULL DEFAULT 0
      Session generation. Access tokens carry the value they were issued
      under; a password change / reset increments it, which invalidates every
      earlier access token. Existing rows get 0, and a token issued before
      this release (no claim) counts as 0: nobody is signed out by the
      migration or the deployment.

  auth_tokens
      One-time credentials sent by email (email verification, password
      reset). Stores a SHA-256 digest, never the credential. Starts EMPTY.
      Unrelated to user_verifications (contest entry media verification).

  auth_rate_limits
      Durable fixed-window counters for the public auth endpoints. Keyed
      hashes only (no address, email or account id). Starts EMPTY.

No existing row of any table is updated, no existing column or constraint is
changed, nothing is deleted. On PostgreSQL 11+ adding a NOT NULL column with a
constant default does not rewrite the table.

Downgrade drops exactly what this revision added. The two tables hold only
short-lived security state (outstanding links, rate counters); dropping them
loses no business data. Dropping email_verification_required forgets which
accounts were created under the verify-before-login rule: after a downgrade
and a later re-upgrade they would all count as grandfathered. Do not downgrade
a database that has taken registrations under the rule; roll the code back
and leave the schema in place instead.
"""
from alembic import op


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS security_version INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_required BOOLEAN NOT NULL "
               "DEFAULT false")

    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose VARCHAR(30) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            email_hash VARCHAR(64) NOT NULL,
            security_version INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP,
            revoked_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_auth_tokens_token_hash UNIQUE (token_hash),
            CONSTRAINT ck_auth_tokens_purpose CHECK (purpose IN ('email_verification', 'password_reset')))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_tokens_id ON auth_tokens (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_tokens_user_purpose ON auth_tokens (user_id, purpose)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_tokens_expires_at ON auth_tokens (expires_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_rate_limits (
            id SERIAL PRIMARY KEY,
            scope VARCHAR(40) NOT NULL,
            key_hash VARCHAR(64) NOT NULL,
            window_start TIMESTAMP NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_auth_rate_limits_window UNIQUE (scope, key_hash, window_start))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_rate_limits_id ON auth_rate_limits (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_rate_limits_window_start ON auth_rate_limits (window_start)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_rate_limits")
    op.execute("DROP TABLE IF EXISTS auth_tokens")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verification_required")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS security_version")
