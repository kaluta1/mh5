"""Add media requirements to contests and contestant verifications table

Revision ID: add_media_reqs_001
Revises: 
Create Date: 2024-12-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'add_media_reqs_001'
down_revision = None
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    # Add media requirements columns to contest table (only if they don't exist)
    columns_to_add = [
        ('requires_video', sa.Boolean(), 'false'),
        ('max_videos', sa.Integer(), '1'),
        ('video_max_duration', sa.Integer(), '3000'),
        ('video_max_size_mb', sa.Integer(), '500'),
        ('min_images', sa.Integer(), '0'),
        ('max_images', sa.Integer(), '10'),
        ('verification_video_max_duration', sa.Integer(), '30'),
        ('verification_max_size_mb', sa.Integer(), '50'),
    ]
    
    for col_name, col_type, default_val in columns_to_add:
        if not column_exists('contest', col_name):
            op.add_column('contest', sa.Column(col_name, col_type, nullable=False, server_default=default_val))
    
    # Create contestant_verifications table (only if it doesn't exist)
    if not table_exists('contestant_verifications'):
        op.create_table(
            'contestant_verifications',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('contestant_id', sa.Integer(), sa.ForeignKey('contestants.id'), nullable=False),
            sa.Column('verification_type', sa.String(50), nullable=False),
            sa.Column('media_url', sa.String(500), nullable=False),
            sa.Column('media_type', sa.String(20), nullable=False),
            sa.Column('duration_seconds', sa.Integer(), nullable=True),
            sa.Column('file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )
        
        # Create indexes
        op.create_index('ix_contestant_verifications_contestant_id', 'contestant_verifications', ['contestant_id'])
        op.create_index('ix_contestant_verifications_status', 'contestant_verifications', ['status'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_contestant_verifications_status', 'contestant_verifications')
    op.drop_index('ix_contestant_verifications_contestant_id', 'contestant_verifications')
    
    # Drop contestant_verifications table
    op.drop_table('contestant_verifications')
    
    # Remove media requirements columns from contest table
    op.drop_column('contest', 'verification_max_size_mb')
    op.drop_column('contest', 'verification_video_max_duration')
    op.drop_column('contest', 'max_images')
    op.drop_column('contest', 'min_images')
    op.drop_column('contest', 'video_max_size_mb')
    op.drop_column('contest', 'video_max_duration')
    op.drop_column('contest', 'max_videos')
    op.drop_column('contest', 'requires_video')
