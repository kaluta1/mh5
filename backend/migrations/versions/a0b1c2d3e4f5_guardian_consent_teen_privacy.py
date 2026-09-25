"""Guardian consent, pending registrations and teen privacy preferences
(Child/Teen Safety Phase 4).

Revision ID: a0b1c2d3e4f5
Revises: z9a0b1c2d3e4
Create Date: 2026-09-26

Additive only: five new tables. No existing table, column or row is changed and
nothing is backfilled (no guardian or consent is created for any existing user).
Downgrade drops only these tables.
"""
from alembic import op


revision = "a0b1c2d3e4f5"
down_revision = "z9a0b1c2d3e4"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS guardians ({_BASE},
            email VARCHAR(255) NOT NULL,
            email_hash VARCHAR(64) NOT NULL UNIQUE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardians_id ON guardians (id)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS pending_registrations ({_BASE},
            status VARCHAR(20) NOT NULL DEFAULT 'AWAITING_GUARDIAN'
                CONSTRAINT ck_pending_registrations_status CHECK (status IN
                ('AWAITING_GUARDIAN', 'APPROVED', 'COMPLETED', 'DECLINED', 'EXPIRED', 'CANCELLED')),
            email VARCHAR(255),
            email_hash VARCHAR(64) NOT NULL,
            username VARCHAR(255),
            date_of_birth DATE,
            country VARCHAR(100),
            region VARCHAR(100),
            continent VARCHAR(100),
            sponsor_code VARCHAR(50),
            terms_accepted_at TIMESTAMP NOT NULL,
            jurisdiction_code VARCHAR(10),
            policy_id INTEGER REFERENCES age_policies(id),
            policy_version INTEGER,
            expires_at TIMESTAMP NOT NULL,
            guardian_token_hash VARCHAR(64),
            guardian_token_expires_at TIMESTAMP,
            guardian_token_used_at TIMESTAMP,
            completion_token_hash VARCHAR(64),
            completion_token_expires_at TIMESTAMP,
            completion_token_used_at TIMESTAMP,
            completed_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            completed_at TIMESTAMP,
            data_purged_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pending_registrations_id ON pending_registrations (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_registrations_open_email ON pending_registrations "
               "(email_hash) WHERE status IN ('AWAITING_GUARDIAN', 'APPROVED')")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_pending_registrations_guardian_token_hash "
               "ON pending_registrations (guardian_token_hash)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_pending_registrations_completion_token_hash "
               "ON pending_registrations (completion_token_hash)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS guardian_relationships ({_BASE},
            guardian_id INTEGER NOT NULL REFERENCES guardians(id),
            minor_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            pending_registration_id INTEGER REFERENCES pending_registrations(id),
            relationship_type VARCHAR(20)
                CONSTRAINT ck_guardian_relationships_type
                CHECK (relationship_type IS NULL OR relationship_type IN ('PARENT', 'LEGAL_GUARDIAN')),
            verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                CONSTRAINT ck_guardian_relationships_status CHECK (verification_status IN
                ('PENDING', 'VERIFICATION_REQUIRED', 'VERIFIED', 'REJECTED', 'REVOKED', 'EXPIRED')),
            verification_method VARCHAR(40),
            requested_at TIMESTAMP NOT NULL,
            responded_at TIMESTAMP,
            verified_at TIMESTAMP,
            verified_by_user_id INTEGER REFERENCES users(id),
            revoked_at TIMESTAMP,
            revoked_by_user_id INTEGER REFERENCES users(id),
            status_reason VARCHAR(120),
            jurisdiction_code VARCHAR(10),
            policy_id INTEGER REFERENCES age_policies(id),
            policy_version INTEGER,
            CONSTRAINT ck_guardian_relationships_subject
                CHECK (minor_user_id IS NOT NULL OR pending_registration_id IS NOT NULL))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_relationships_id ON guardian_relationships (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_relationships_guardian_id ON guardian_relationships (guardian_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_relationships_minor ON guardian_relationships (minor_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_relationships_pending ON guardian_relationships (pending_registration_id)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS guardian_consents ({_BASE},
            relationship_id INTEGER NOT NULL REFERENCES guardian_relationships(id),
            guardian_reference INTEGER NOT NULL REFERENCES guardians(id),
            minor_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            pending_registration_id INTEGER REFERENCES pending_registrations(id),
            jurisdiction VARCHAR(10),
            consent_scope VARCHAR(40) NOT NULL,
            verification_method VARCHAR(40),
            consent_timestamp TIMESTAMP NOT NULL,
            policy_id INTEGER REFERENCES age_policies(id),
            policy_version INTEGER,
            withdrawal_status VARCHAR(20) NOT NULL DEFAULT 'GRANTED'
                CONSTRAINT ck_guardian_consents_status CHECK (withdrawal_status IN ('GRANTED', 'WITHDRAWN')),
            withdrawn_at TIMESTAMP,
            withdrawn_by_user_id INTEGER REFERENCES users(id),
            withdrawal_reason TEXT,
            expires_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_consents_id ON guardian_consents (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_guardian_consents_minor_scope ON guardian_consents (minor_user_id, consent_scope)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_guardian_consents_active_scope ON guardian_consents "
               "(relationship_id, consent_scope) WHERE withdrawal_status = 'GRANTED'")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS user_privacy_preferences ({_BASE},
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            preferences JSONB NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_privacy_preferences_id ON user_privacy_preferences (id)")


def downgrade() -> None:
    for table in ("user_privacy_preferences", "guardian_consents", "guardian_relationships",
                  "pending_registrations", "guardians"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
