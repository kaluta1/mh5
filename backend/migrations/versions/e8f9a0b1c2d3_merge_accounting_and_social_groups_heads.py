"""merge accounting head and social groups head

Revision ID: e8f9a0b1c2d3
Revises: a7f3e2d1c4b8, add_social_groups
Create Date: 2026-04-06

"""
from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = ("a7f3e2d1c4b8", "add_social_groups")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
