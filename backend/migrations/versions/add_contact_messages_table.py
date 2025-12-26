"""Add contact messages table

Revision ID: add_contact_messages_table
Revises: add_invitations_table
Create Date: 2025-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_contact_messages_table'
down_revision = 'add_invitations_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vérifier si la table existe déjà
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'contact_messages' not in inspector.get_table_names():
        op.create_table(
            'contact_messages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('subject', sa.String(length=500), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_contact_messages_email', 'contact_messages', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_contact_messages_email', table_name='contact_messages')
    op.drop_table('contact_messages')

