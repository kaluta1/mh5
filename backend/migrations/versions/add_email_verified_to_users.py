"""Add email_verified field to users table

Revision ID: add_email_verified
Revises: 
Create Date: 2025-12-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_email_verified'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add email_verified column to users table
    op.add_column(
        'users',
        sa.Column(
            'email_verified',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    # Remove email_verified column from users table
    op.drop_column('users', 'email_verified')
