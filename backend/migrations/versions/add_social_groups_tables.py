"""Add social groups tables

Revision ID: add_social_groups
Revises: 
Create Date: 2025-01-30 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_social_groups'
down_revision = 'add_invitations_table'  # Update this if needed to point to latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Create enum types (only if they don't exist)
    conn = op.get_bind()
    
    # Check and create grouptype
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'grouptype'"))
    if result.fetchone() is None:
        op.execute(sa.text("CREATE TYPE grouptype AS ENUM ('public', 'private', 'secret')"))
    
    # Check and create groupmemberrole
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'groupmemberrole'"))
    if result.fetchone() is None:
        op.execute(sa.text("CREATE TYPE groupmemberrole AS ENUM ('member', 'admin', 'moderator', 'owner')"))
    
    # Check and create messagetype
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'messagetype'"))
    if result.fetchone() is None:
        op.execute(sa.text("CREATE TYPE messagetype AS ENUM ('text', 'image', 'video', 'file', 'audio', 'system')"))
    
    # Check and create messagestatus
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'messagestatus'"))
    if result.fetchone() is None:
        op.execute(sa.text("CREATE TYPE messagestatus AS ENUM ('sent', 'delivered', 'read', 'deleted')"))
    
    # Create social_groups table (only if it doesn't exist)
    inspector = sa.inspect(conn)
    if 'social_groups' not in inspector.get_table_names():
        op.create_table(
            'social_groups',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('group_type', postgresql.ENUM('public', 'private', 'secret', name='grouptype', create_type=False), nullable=False),
            sa.Column('creator_id', sa.Integer(), nullable=False),
            sa.Column('avatar_url', sa.String(length=512), nullable=True),
            sa.Column('cover_url', sa.String(length=512), nullable=True),
            sa.Column('max_members', sa.Integer(), nullable=True),
            sa.Column('invite_code', sa.String(length=50), nullable=True),
            sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('member_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('post_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
            sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_social_groups_name'), 'social_groups', ['name'], unique=False)
        op.create_index(op.f('ix_social_groups_creator_id'), 'social_groups', ['creator_id'], unique=False)
        op.create_index(op.f('ix_social_groups_invite_code'), 'social_groups', ['invite_code'], unique=True)
    
    # Create group_members table (only if it doesn't exist)
    if 'group_members' not in inspector.get_table_names():
        op.create_table(
        'group_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('role', postgresql.ENUM('member', 'admin', 'moderator', 'owner', name='groupmemberrole', create_type=False), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.Column('is_muted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['group_id'], ['social_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'user_id', name='uq_group_member')
    )
        op.create_index(op.f('ix_group_members_group_id'), 'group_members', ['group_id'], unique=False)
        op.create_index(op.f('ix_group_members_user_id'), 'group_members', ['user_id'], unique=False)
    
    # Create group_join_requests table (only if it doesn't exist)
    if 'group_join_requests' not in inspector.get_table_names():
        op.create_table(
        'group_join_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['social_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
        op.create_index(op.f('ix_group_join_requests_group_id'), 'group_join_requests', ['group_id'], unique=False)
        op.create_index(op.f('ix_group_join_requests_user_id'), 'group_join_requests', ['user_id'], unique=False)
    
    # Create group_messages table (only if it doesn't exist)
    if 'group_messages' not in inspector.get_table_names():
        op.create_table(
        'group_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
            sa.Column('message_type', postgresql.ENUM('text', 'image', 'video', 'file', 'audio', 'system', name='messagetype', create_type=False), nullable=False),
        sa.Column('media_id', sa.Integer(), nullable=True),
        sa.Column('reply_to_id', sa.Integer(), nullable=True),
            sa.Column('status', postgresql.ENUM('sent', 'delivered', 'read', 'deleted', name='messagestatus', create_type=False), nullable=False),
        sa.Column('is_edited', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('edited_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['social_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
        sa.ForeignKeyConstraint(['reply_to_id'], ['group_messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
        op.create_index(op.f('ix_group_messages_group_id'), 'group_messages', ['group_id'], unique=False)
        op.create_index(op.f('ix_group_messages_sender_id'), 'group_messages', ['sender_id'], unique=False)
    
    # Create message_read_receipts table (only if it doesn't exist)
    if 'message_read_receipts' not in inspector.get_table_names():
        op.create_table(
        'message_read_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['group_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
        op.create_index(op.f('ix_message_read_receipts_message_id'), 'message_read_receipts', ['message_id'], unique=False)
        op.create_index(op.f('ix_message_read_receipts_user_id'), 'message_read_receipts', ['user_id'], unique=False)


def downgrade():
    # Drop tables in reverse order
    op.drop_table('message_read_receipts')
    op.drop_table('group_messages')
    op.drop_table('group_join_requests')
    op.drop_table('group_members')
    op.drop_table('social_groups')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS messagestatus')
    op.execute('DROP TYPE IF EXISTS messagetype')
    op.execute('DROP TYPE IF EXISTS groupmemberrole')
    op.execute('DROP TYPE IF EXISTS grouptype')
