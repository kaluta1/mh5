"""Add user_verifications table

Revision ID: add_user_verifications
Revises: df16106251a5
Create Date: 2025-12-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = 'add_user_verifications'
down_revision = 'df16106251a5'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def index_exists(index_name):
    """Check if an index exists"""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname = :name)"
    ), {"name": index_name})
    return result.scalar()


def upgrade():
    # Créer les types ENUM si nécessaire
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_verification_type AS ENUM (
                'selfie', 'selfie_with_pet', 'selfie_with_document', 
                'voice', 'video', 'brand', 'content'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE verification_media_type AS ENUM ('image', 'audio', 'video', 'document');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_verification_status AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Créer la table user_verifications si elle n'existe pas
    if not table_exists('user_verifications'):
        op.create_table(
            'user_verifications',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('verification_type', sa.String(50), nullable=False),
            sa.Column('media_url', sa.String(500), nullable=False),
            sa.Column('media_type', sa.String(20), nullable=False),
            sa.Column('media_key', sa.String(255), nullable=True),
            sa.Column('duration_seconds', sa.Integer(), nullable=True),
            sa.Column('file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('contest_id', sa.Integer(), sa.ForeignKey('contest.id', ondelete='SET NULL'), nullable=True),
            sa.Column('contestant_id', sa.Integer(), sa.ForeignKey('contestants.id', ondelete='SET NULL'), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    
    # Créer les index si ils n'existent pas
    if not index_exists('ix_user_verifications_user_type'):
        op.create_index('ix_user_verifications_user_type', 'user_verifications', ['user_id', 'verification_type'])
    if not index_exists('ix_user_verifications_status'):
        op.create_index('ix_user_verifications_status', 'user_verifications', ['status'])
    if not index_exists('ix_user_verifications_user_id'):
        op.create_index('ix_user_verifications_user_id', 'user_verifications', ['user_id'])


def downgrade():
    op.drop_index('ix_user_verifications_status', 'user_verifications')
    op.drop_index('ix_user_verifications_user_type', 'user_verifications')
    op.drop_table('user_verifications')
    
    op.execute("DROP TYPE IF EXISTS user_verification_status")
    op.execute("DROP TYPE IF EXISTS verification_media_type")
    op.execute("DROP TYPE IF EXISTS user_verification_type")
