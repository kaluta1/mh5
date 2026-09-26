"""Content moderation state (Child/Teen Safety Phase 6).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-26

Additive only: one new table, content_moderation (one row per governed
entry). Nothing is backfilled: no historical entry is classified, rated,
approved or hidden, and no existing table, column or row is changed. The
action history uses the existing audit_trail table.

Downgrade drops only this table (locally created Phase 6 rows go with it).
"""
from alembic import op


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

_RATINGS = "('GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', 'ADULT_18_PLUS', 'PROHIBITED')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS content_moderation (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            contestant_id INTEGER NOT NULL UNIQUE REFERENCES contestants(id) ON DELETE CASCADE,
            state VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                CONSTRAINT ck_content_moderation_state CHECK (state IN
                ('PENDING', 'APPROVED', 'REVIEW_REQUIRED', 'PROHIBITED', 'CHILD_SAFETY_ESCALATED')),
            rating VARCHAR(20)
                CONSTRAINT ck_content_moderation_rating CHECK (rating IS NULL OR rating IN {_RATINGS}),
            proposed_rating VARCHAR(20)
                CONSTRAINT ck_content_moderation_proposed_rating CHECK (proposed_rating IS NULL OR
                proposed_rating IN {_RATINGS}),
            findings JSONB,
            resolved_findings JSONB,
            classifier_status VARCHAR(20) NOT NULL DEFAULT 'NOT_RUN'
                CONSTRAINT ck_content_moderation_classifier CHECK (classifier_status IN
                ('COMPLETED', 'PARTIAL', 'UNAVAILABLE', 'FAILED', 'NOT_RUN')),
            classifier_version VARCHAR(40) NOT NULL,
            coverage JSONB,
            human_review_required BOOLEAN NOT NULL DEFAULT TRUE,
            update_required BOOLEAN NOT NULL DEFAULT FALSE,
            subject_possibly_minor BOOLEAN NOT NULL DEFAULT TRUE,
            child_safety_escalated BOOLEAN NOT NULL DEFAULT FALSE,
            child_safety_escalated_at TIMESTAMP,
            child_safety_resolution VARCHAR(30)
                CONSTRAINT ck_content_moderation_cs_resolution CHECK (child_safety_resolution IS NULL OR
                child_safety_resolution IN ('CONFIRMED', 'NO_CHILD_SAFETY_CONCERN')),
            child_safety_resolved_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            child_safety_resolved_at TIMESTAMP,
            evaluated_at TIMESTAMP NOT NULL,
            decided_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMP,
            automated_decision BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT ck_content_moderation_approved_rating CHECK
                (state <> 'APPROVED' OR (rating IS NOT NULL AND rating <> 'PROHIBITED')))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_moderation_id ON content_moderation (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_moderation_state ON content_moderation (state)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_content_moderation_child_safety "
               "ON content_moderation (child_safety_escalated)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_moderation")
