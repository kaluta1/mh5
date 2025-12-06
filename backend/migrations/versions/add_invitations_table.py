"""Add invitations table

Revision ID: add_invitations_table
Revises: 
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_invitations_table'
down_revision = 'merge_all_heads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vérifier si la table existe déjà
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'invitations' not in inspector.get_table_names():
        op.create_table(
            'invitations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('inviter_id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('message', sa.Text(), nullable=True),
            sa.Column('referral_code', sa.String(length=20), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('invited_user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['inviter_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['invited_user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_invitations_email', 'invitations', ['email'], unique=False)
        op.create_index('ix_invitations_inviter_id', 'invitations', ['inviter_id'], unique=False)
        op.create_index('ix_invitations_referral_code', 'invitations', ['referral_code'], unique=False)
        op.create_index('ix_invitations_status', 'invitations', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_invitations_status', table_name='invitations')
    op.drop_index('ix_invitations_referral_code', table_name='invitations')
    op.drop_index('ix_invitations_inviter_id', table_name='invitations')
    op.drop_index('ix_invitations_email', table_name='invitations')
    op.drop_table('invitations')
