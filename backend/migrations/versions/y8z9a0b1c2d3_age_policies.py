"""Versioned jurisdiction age policies (Child/Teen Safety Phase 2).

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-09-25

Additive only: one new table, age_policies. No existing table, column or row is
touched, and no policy data is seeded (jurisdiction legal rules must come from
an approved source and be entered by administrators).
Downgrade drops only the new table.
"""
from alembic import op


revision = "y8z9a0b1c2d3"
down_revision = "x7y8z9a0b1c2"
branch_labels = None
depends_on = None

_AGE_COLUMNS = (
    "minimum_account_age",
    "minimum_independent_participation_age",
    "parental_consent_age",
    "adult_age",
    "voting_minimum_age",
    "nomination_minimum_age",
    "personal_submission_minimum_age",
    "livestream_minimum_age",
    "prize_contract_age",
    "payment_minimum_age",
)


def upgrade() -> None:
    age_cols = ",\n            ".join(
        f"{c} INTEGER NOT NULL CONSTRAINT ck_age_policies_{c}_range CHECK ({c} BETWEEN 0 AND 120)"
        for c in _AGE_COLUMNS
    )
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS age_policies (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            jurisdiction VARCHAR(10) NOT NULL,
            policy_version INTEGER NOT NULL CONSTRAINT ck_age_policies_version_positive CHECK (policy_version >= 1),
            status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                CONSTRAINT ck_age_policies_status CHECK (status IN ('DRAFT', 'ACTIVE', 'WITHDRAWN')),
            effective_date DATE NOT NULL,
            {age_cols},
            kyc_requirement JSONB NOT NULL,
            age_assurance_level JSONB NOT NULL,
            parental_consent_requirement JSONB NOT NULL,
            permitted_content_ratings JSONB NOT NULL,
            advertising_restrictions JSONB NOT NULL,
            profile_visibility_rules JSONB NOT NULL,
            notes TEXT,
            created_by_user_id INTEGER REFERENCES users(id),
            status_changed_at TIMESTAMP,
            status_changed_by_user_id INTEGER REFERENCES users(id),
            status_reason TEXT,
            CONSTRAINT uq_age_policies_jurisdiction_version UNIQUE (jurisdiction, policy_version)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_policies_id ON age_policies (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_age_policies_jurisdiction ON age_policies (jurisdiction)")
    # At most one ACTIVE policy per jurisdiction and effective date: resolution is deterministic.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_age_policies_active_jurisdiction_effective "
        "ON age_policies (jurisdiction, effective_date) WHERE status = 'ACTIVE'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS age_policies")
