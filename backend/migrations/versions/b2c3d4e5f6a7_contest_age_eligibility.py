"""Contest age eligibility, category age policies, contest entry safety workflow
(incl. nominee claim), media metadata flag and AgePolicy nomination scope
(Child/Teen Safety Phase 5).

Revision ID: b2c3d4e5f6a7
Revises: a0b1c2d3e4f5
Create Date: 2026-09-26

Additive only:
- three new tables (contest_age_eligibility, category_age_policies,
  contest_entry_safety);
- one new NULLABLE column media.metadata_sanitized_at (no default, no backfill);
- one new NULLABLE column age_policies.nomination_age_applies_to (which
  nomination actor nomination_minimum_age applies to; NULL = not stated, never
  assumed). Existing policies are not changed.
No existing row is changed. No age rule, entry safety record or sanitization
flag is created for existing contests, categories, contestants or media, so
historical entries keep exactly their current behaviour. Foreign keys point
only at real primary keys (contest.id, categories.id, contestants.id, users.id,
guardian_relationships.id, age_policies.id); none targets a legacy semantic
column such as contestants.season_id.

Downgrade drops only these tables and these two columns (and their constraint).
"""
from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"

_RULE_COLUMNS = """
    jurisdiction VARCHAR(10) NOT NULL DEFAULT '*',
    rule_version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CONSTRAINT ck_{t}_status CHECK (status IN ('DRAFT', 'ACTIVE', 'WITHDRAWN')),
    minimum_age INTEGER,
    maximum_age INTEGER,
    eligible_age_tiers JSONB,
    minor_participation_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    adult_only BOOLEAN NOT NULL DEFAULT FALSE,
    parental_consent_required BOOLEAN NOT NULL DEFAULT FALSE,
    publicity_consent_required BOOLEAN NOT NULL DEFAULT FALSE,
    content_age_rating VARCHAR(20)
        CONSTRAINT ck_{t}_rating CHECK (content_age_rating IS NULL OR content_age_rating IN
        ('GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', 'ADULT_18_PLUS')),
    prize_restrictions JSONB,
    financial_restrictions JSONB,
    notes TEXT,
    activated_at TIMESTAMP,
    withdrawn_at TIMESTAMP,
    changed_by_user_id INTEGER REFERENCES users(id),
    change_reason TEXT,
    CONSTRAINT ck_{t}_ages CHECK (
        (minimum_age IS NULL OR (minimum_age >= 0 AND minimum_age <= 120)) AND
        (maximum_age IS NULL OR (maximum_age >= 0 AND maximum_age <= 120)) AND
        (minimum_age IS NULL OR maximum_age IS NULL OR minimum_age <= maximum_age))
"""


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS contest_age_eligibility ({_BASE},
            contest_id INTEGER NOT NULL REFERENCES contest(id) ON DELETE CASCADE,
            {_RULE_COLUMNS.format(t="contest_age_eligibility")})""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_age_eligibility_id ON contest_age_eligibility (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_age_eligibility_contest ON contest_age_eligibility (contest_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_contest_age_eligibility_active "
               "ON contest_age_eligibility (contest_id, jurisdiction) WHERE status = 'ACTIVE'")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS category_age_policies ({_BASE},
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            {_RULE_COLUMNS.format(t="category_age_policies")})""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_category_age_policies_id ON category_age_policies (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_category_age_policies_category ON category_age_policies (category_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_category_age_policies_active "
               "ON category_age_policies (category_id, jurisdiction) WHERE status = 'ACTIVE'")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS contest_entry_safety ({_BASE},
            contestant_id INTEGER NOT NULL UNIQUE REFERENCES contestants(id) ON DELETE CASCADE,
            contest_id INTEGER REFERENCES contest(id) ON DELETE SET NULL,
            entry_kind VARCHAR(30) NOT NULL
                CONSTRAINT ck_contest_entry_safety_kind CHECK (entry_kind IN ('PERSONAL_SUBMISSION', 'NOMINATION')),
            submitted_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            account_holder_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            nominee_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            creative_owner_type VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'
                CONSTRAINT ck_contest_entry_safety_owner CHECK (creative_owner_type IN
                ('SELF', 'NOMINEE', 'THIRD_PARTY', 'UNKNOWN')),
            creative_owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            guardian_relationship_id INTEGER REFERENCES guardian_relationships(id) ON DELETE SET NULL,
            nominee_age_declaration VARCHAR(10)
                CONSTRAINT ck_contest_entry_safety_declaration CHECK (nominee_age_declaration IS NULL OR
                nominee_age_declaration IN ('ADULT', 'MINOR', 'UNKNOWN')),
            claim_token_hash VARCHAR(64),
            claim_token_issued_at TIMESTAMP,
            claim_token_expires_at TIMESTAMP,
            claimed_at TIMESTAMP,
            claim_declined_at TIMESTAMP,
            exposure_status VARCHAR(30) NOT NULL DEFAULT 'HELD'
                CONSTRAINT ck_contest_entry_safety_exposure CHECK (exposure_status IN
                ('PUBLIC', 'HELD', 'BLOCKED', 'CHILD_SAFETY_ESCALATED')),
            workflow_step VARCHAR(30),
            rights_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUIRED'
                CONSTRAINT ck_contest_entry_safety_rights CHECK (rights_status IN
                ('NOT_REQUIRED', 'PENDING', 'CONFIRMED', 'DISPUTED')),
            safety_status VARCHAR(30) NOT NULL DEFAULT 'CLEAR'
                CONSTRAINT ck_contest_entry_safety_safety CHECK (safety_status IN
                ('CLEAR', 'REVIEW_REQUIRED', 'REVIEWED_CLEAR', 'BLOCKED', 'CHILD_SAFETY_ESCALATED')),
            safety_concerns JSONB,
            metadata_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUIRED'
                CONSTRAINT ck_contest_entry_safety_metadata CHECK (metadata_status IN
                ('NOT_REQUIRED', 'SANITIZED', 'UNRESOLVED')),
            age_window_ok_at_entry BOOLEAN NOT NULL DEFAULT TRUE,
            outcome VARCHAR(20) NOT NULL,
            reason_codes JSONB,
            missing_consent_scopes JSONB,
            decision_basis VARCHAR(40),
            enforced BOOLEAN NOT NULL DEFAULT FALSE,
            subject_age_tier VARCHAR(20),
            jurisdiction_code VARCHAR(10),
            policy_id INTEGER REFERENCES age_policies(id),
            policy_version INTEGER,
            last_evaluated_at TIMESTAMP NOT NULL,
            activated_at TIMESTAMP,
            suspended_at TIMESTAMP,
            reviewed_by_user_id INTEGER REFERENCES users(id),
            reviewed_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_entry_safety_id ON contest_entry_safety (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_entry_safety_exposure ON contest_entry_safety (exposure_status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_entry_safety_submitted_by "
               "ON contest_entry_safety (submitted_by_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contest_entry_safety_nominee ON contest_entry_safety (nominee_user_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_contest_entry_safety_claim_token "
               "ON contest_entry_safety (claim_token_hash)")

    op.execute("ALTER TABLE media ADD COLUMN IF NOT EXISTS metadata_sanitized_at TIMESTAMP")
    op.execute("ALTER TABLE age_policies ADD COLUMN IF NOT EXISTS nomination_age_applies_to VARCHAR(20)")
    op.execute("ALTER TABLE age_policies ADD CONSTRAINT ck_age_policies_nomination_scope CHECK "
               "(nomination_age_applies_to IS NULL OR nomination_age_applies_to IN ('NOMINATOR', 'NOMINEE', 'BOTH'))")


def downgrade() -> None:
    op.execute("ALTER TABLE age_policies DROP CONSTRAINT IF EXISTS ck_age_policies_nomination_scope")
    op.execute("ALTER TABLE age_policies DROP COLUMN IF EXISTS nomination_age_applies_to")
    op.execute("ALTER TABLE media DROP COLUMN IF EXISTS metadata_sanitized_at")
    for table in ("contest_entry_safety", "category_age_policies", "contest_age_eligibility"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
