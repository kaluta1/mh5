"""Add is_deleted column to contestants table

Revision ID: add_is_deleted_contestants
Revises: add_is_deleted_users
Create Date: 2025-11-22 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_deleted_contestants'
down_revision = 'add_is_deleted_users'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c['name'] for c in insp.get_columns('contestants')]
    if 'is_deleted' not in columns:
        op.add_column('contestants', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c['name'] for c in insp.get_columns('contestants')]
    if 'is_deleted' in columns:
        op.drop_column('contestants', 'is_deleted')
