"""Registration age gate, DOB provenance/change protection and enforcement switch
(Child/Teen Safety Phase 3).

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-09-25

Additive only: four new tables. No existing table, column or row is changed, and
nothing is backfilled. A user without a user_age_profiles row is a legacy user
(DOB, if any, counts as LEGACY_PROFILE / self-declared). No enforcement row is
created, so registration enforcement starts OFF everywhere.
Downgrade drops only the four new tables.
"""
from alembic import op


revision = "z9a0b1c2d3e4"
down_revision = "y8z9a0b1c2d3"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS user_age_profiles ({_BASE},
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            dob_source VARCHAR(40),
            assurance_level VARCHAR(40),
            jurisdiction_code VARCHAR(10),
            jurisdiction_status VARCHAR(20),
            registration_decision VARCHAR(40),
            registration_policy_outcome VARCHAR(40),
            registration_enforced BOOLEAN NOT NULL DEFAULT false,
            registration_policy_id INTEGER REFERENCES age_policies(id),
            registration_policy_version INTEGER,
            review_status VARCHAR(40) NOT NULL DEFAULT 'NONE'
                CONSTRAINT ck_user_age_profiles_review_status
                CHECK (review_status IN ('NONE', 'AGE_VERIFICATION_REQUIRED', 'AGE_REVIEW_REQUIRED')),
            review_reason VARCHAR(80),
            review_updated_at TIMESTAMP,
            terms_accepted_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_age_profiles_id ON user_age_profiles (id)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS dob_change_records ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            previous_dob DATE,
            requested_dob DATE NOT NULL,
            status VARCHAR(20) NOT NULL
                CONSTRAINT ck_dob_change_records_status
                CHECK (status IN ('AUTO_APPLIED', 'PENDING', 'APPROVED', 'REJECTED', 'ADMIN_APPLIED')),
            reason_code VARCHAR(60) NOT NULL,
            requested_by_user_id INTEGER REFERENCES users(id),
            reviewed_by_user_id INTEGER REFERENCES users(id),
            reviewed_at TIMESTAMP,
            review_note TEXT)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dob_change_records_id ON dob_change_records (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dob_change_records_user_created ON dob_change_records (user_id, created_at)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_dob_change_records_one_pending "
        "ON dob_change_records (user_id) WHERE status = 'PENDING'"
    )

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS age_safety_events ({_BASE},
            event_type VARCHAR(40) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            email_hash VARCHAR(64),
            ip_hash VARCHAR(64),
            jurisdiction_code VARCHAR(10),
            age_tier VARCHAR(20),
            decision VARCHAR(40),
            enforced BOOLEAN,
            policy_id INTEGER,
            policy_version INTEGER,
            risk_flag BOOLEAN NOT NULL DEFAULT false,
            details JSONB)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_safety_events_id ON age_safety_events (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_safety_events_email_hash_created ON age_safety_events (email_hash, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_safety_events_ip_hash_created ON age_safety_events (ip_hash, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_safety_events_user_created ON age_safety_events (user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_safety_events_type_created ON age_safety_events (event_type, created_at)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS child_safety_enforcement ({_BASE},
            operation VARCHAR(40) NOT NULL,
            jurisdiction VARCHAR(10) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT false,
            reason TEXT,
            changed_by_user_id INTEGER REFERENCES users(id),
            changed_at TIMESTAMP,
            CONSTRAINT uq_child_safety_enforcement_operation_jurisdiction UNIQUE (operation, jurisdiction))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_child_safety_enforcement_id ON child_safety_enforcement (id)")


def downgrade() -> None:
    for table in ("child_safety_enforcement", "age_safety_events", "dob_change_records", "user_age_profiles"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
