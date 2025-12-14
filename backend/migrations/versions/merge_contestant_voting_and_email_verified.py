"""Merge contestant_voting and email_verified heads

Revision ID: merge_contestant_voting_email
Revises: add_contestant_voting, merge_8148_add_email_verified
Create Date: 2025-01-27 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "merge_contestant_voting_email"
down_revision = ("add_contestant_voting", "merge_8148_add_email_verified")
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration; no schema changes.
    pass


def downgrade():
    # Merge migration; no schema rollback.
    pass

