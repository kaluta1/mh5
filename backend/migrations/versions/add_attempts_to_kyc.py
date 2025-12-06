"""add attempts_count and max_attempts to kyc_verifications

Revision ID: add_attempts_to_kyc
Revises: add_verification_url
Create Date: 2024-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_attempts_to_kyc'
down_revision = 'add_verification_url'
branch_labels = None
depends_on = None


def upgrade():
    # Add attempts tracking columns
    op.add_column('kyc_verifications', sa.Column('attempts_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('kyc_verifications', sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'))


def downgrade():
    op.drop_column('kyc_verifications', 'max_attempts')
    op.drop_column('kyc_verifications', 'attempts_count')
