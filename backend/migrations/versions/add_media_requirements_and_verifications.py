"""Add media requirements to contests and contestant verifications table

Revision ID: add_media_reqs_001
Revises: 
Create Date: 2024-12-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_media_reqs_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add media requirements columns to contest table
    op.add_column('contest', sa.Column('requires_video', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest', sa.Column('max_videos', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('contest', sa.Column('video_max_duration', sa.Integer(), nullable=False, server_default='3000'))
    op.add_column('contest', sa.Column('video_max_size_mb', sa.Integer(), nullable=False, server_default='500'))
    op.add_column('contest', sa.Column('min_images', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('contest', sa.Column('max_images', sa.Integer(), nullable=False, server_default='10'))
    op.add_column('contest', sa.Column('verification_video_max_duration', sa.Integer(), nullable=False, server_default='30'))
    op.add_column('contest', sa.Column('verification_max_size_mb', sa.Integer(), nullable=False, server_default='50'))
    
    # Create contestant_verifications table
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
