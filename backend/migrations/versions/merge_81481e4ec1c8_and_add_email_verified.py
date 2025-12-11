"""Merge heads 81481e4ec1c8 and add_email_verified.

Revision ID: merge_8148_add_email_verified
Revises: 81481e4ec1c8, add_email_verified
Create Date: 2025-12-11
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "merge_8148_add_email_verified"
down_revision = ("81481e4ec1c8", "add_email_verified")
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration; no schema changes.
    pass


def downgrade():
    # Merge migration; no schema rollback.
    pass

