"""Add all MyHigh5 models

Revision ID: 002_add_myfav_models
Revises: 001_initial_migration
Create Date: 2025-08-27 16:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '002_add_myfav_models'
down_revision = '001'
branch_labels = None
depends_on = None


def table_exists(table_name, insp):
    return table_name in insp.get_table_names()


def column_exists(table_name, column_name, insp):
    if not table_exists(table_name, insp):
        return False
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    
    # Create all ENUM types first (PostgreSQL doesn't support IF NOT EXISTS for CREATE TYPE)
    op.execute("DO $$ BEGIN CREATE TYPE gender AS ENUM ('MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY', 'ANY'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE seasonstatus AS ENUM ('UPCOMING', 'REGISTRATION_OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE stagelevel AS ENUM ('CITY', 'COUNTRY', 'REGION', 'CONTINENT', 'GLOBAL'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE stagestatus AS ENUM ('UPCOMING', 'REGISTRATION_OPEN', 'IN_PROGRESS', 'VOTING', 'COMPLETED'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE clubstatus AS ENUM ('ACTIVE', 'SUSPENDED', 'CLOSED'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE accounttype AS ENUM ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE userstatus AS ENUM ('ACTIVE', 'SUSPENDED', 'BANNED', 'PENDING_VERIFICATION'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # Geography tables
    if not table_exists('continents', insp):
        op.create_table('continents',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=2), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code'),
            sa.UniqueConstraint('name')
        )
    
    if not table_exists('regions', insp):
        op.create_table('regions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('continent_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=10), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['continent_id'], ['continents.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code')
        )
    
    if not table_exists('countries', insp):
        op.create_table('countries',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('region_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('code', sa.String(length=3), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code')
        )
    
    if not table_exists('cities', insp):
        op.create_table('cities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('country_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('state_province', sa.String(length=100), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['country_id'], ['countries.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Contest tables
    if not table_exists('contest_types', insp):
        op.create_table('contest_types',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('slug', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('slug')
        )
    
    if not table_exists('contest_categories', insp):
        op.create_table('contest_categories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contest_type_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('min_age', sa.Integer(), nullable=True),
            sa.Column('max_age', sa.Integer(), nullable=True),
            sa.Column('gender_restriction', postgresql.ENUM('MALE', 'FEMALE', 'OTHER', 'ANY', name='gender', create_type=False), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.ForeignKeyConstraint(['contest_type_id'], ['contest_types.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not table_exists('contest_seasons', insp):
        op.create_table('contest_seasons',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contest_type_id', sa.Integer(), nullable=True),  # Made nullable for future migrations
            sa.Column('name', sa.String(length=100), nullable=True),
            sa.Column('title', sa.String(length=200), nullable=True),  # Added for future use
            sa.Column('year', sa.Integer(), nullable=True),
            sa.Column('start_date', sa.DateTime(), nullable=True),
            sa.Column('end_date', sa.DateTime(), nullable=True),
            sa.Column('registration_start', sa.DateTime(), nullable=True),
            sa.Column('registration_end', sa.DateTime(), nullable=True),
            sa.Column('status', postgresql.ENUM('UPCOMING', 'REGISTRATION_OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='seasonstatus', create_type=False), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not table_exists('contest_stages', insp):
        op.create_table('contest_stages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('stage_type', postgresql.ENUM('CITY', 'COUNTRY', 'REGION', 'CONTINENT', 'GLOBAL', name='stagelevel', create_type=False), nullable=True),
            sa.Column('stage_level', postgresql.ENUM('upload', 'city', 'country', 'regional', 'continental', 'global', 'finale', name='conteststagelevel', create_type=True), nullable=True),
            sa.Column('geographic_entity_id', sa.Integer(), nullable=True),
            sa.Column('name', sa.String(length=200), nullable=True),
            sa.Column('start_date', sa.DateTime(), nullable=True),
            sa.Column('end_date', sa.DateTime(), nullable=True),
            sa.Column('voting_start', sa.DateTime(), nullable=True),
            sa.Column('voting_end', sa.DateTime(), nullable=True),
            sa.Column('max_participants', sa.Integer(), nullable=True),
            sa.Column('max_qualifiers', sa.Integer(), nullable=True),
            sa.Column('min_participants', sa.Integer(), nullable=True),
            sa.Column('status', postgresql.ENUM('UPCOMING', 'REGISTRATION_OPEN', 'IN_PROGRESS', 'VOTING', 'COMPLETED', name='stagestatus', create_type=False), nullable=True),
            sa.Column('continent_id', sa.Integer(), nullable=True),
            sa.Column('region_id', sa.Integer(), nullable=True),
            sa.Column('country_id', sa.Integer(), nullable=True),
            sa.Column('city_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id'], ),
            sa.ForeignKeyConstraint(['continent_id'], ['continents.id'], ),
            sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
            sa.ForeignKeyConstraint(['country_id'], ['countries.id'], ),
            sa.ForeignKeyConstraint(['city_id'], ['cities.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # DSP tables
    if not table_exists('dsp_wallets', insp):
        op.create_table('dsp_wallets',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('balance_dsp', sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column('frozen_balance', sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column('total_earned', sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column('total_spent', sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('last_updated', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id')
        )
    
    # Affiliate tables
    if not table_exists('affiliate_trees', insp):
        op.create_table('affiliate_trees',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('sponsor_id', sa.Integer(), nullable=True),
            sa.Column('level', sa.Integer(), nullable=False),
            sa.Column('referral_code', sa.String(length=20), nullable=False),
            sa.Column('joined_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('referral_code'),
            sa.UniqueConstraint('user_id')
        )
    
    # Fan clubs
    if not table_exists('fan_clubs', insp):
        op.create_table('fan_clubs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('slug', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('membership_fee', sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column('premium_fee', sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column('annual_discount_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column('requires_approval', sa.Boolean(), nullable=True),
            sa.Column('is_public', sa.Boolean(), nullable=True),
            sa.Column('max_members', sa.Integer(), nullable=True),
            sa.Column('multisig_threshold', sa.Integer(), nullable=True),
            sa.Column('status', postgresql.ENUM('ACTIVE', 'SUSPENDED', 'CLOSED', name='clubstatus', create_type=False), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('slug')
        )
    
    # Accounting tables
    if not table_exists('chart_of_accounts', insp):
        op.create_table('chart_of_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('account_code', sa.String(length=20), nullable=False),
            sa.Column('account_name', sa.String(length=200), nullable=False),
            sa.Column('account_type', postgresql.ENUM('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE', name='accounttype', create_type=False), nullable=False),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.Column('balance', sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['parent_id'], ['chart_of_accounts.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('account_code')
        )
    
    # contestants table
    if not table_exists('contestants', insp):
        op.create_table('contestants',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('image_media_ids', sa.String(length=1000), nullable=True),
            sa.Column('video_media_ids', sa.String(length=1000), nullable=True),
            sa.Column('registration_date', sa.DateTime(), nullable=True),
            sa.Column('verification_status', sa.String(length=50), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
            sa.Column('is_qualified', sa.Boolean(), nullable=True, default=True),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, default=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # my_favorites table
    if not table_exists('my_favorites', insp):
        op.create_table('my_favorites',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False, default=0),
            sa.Column('added_date', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # votes table
    if not table_exists('votes', insp):
        op.create_table('votes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('voter_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('stage_id', sa.Integer(), nullable=False),
            sa.Column('rank_position', sa.Integer(), nullable=False),
            sa.Column('points', sa.Integer(), nullable=False),
            sa.Column('vote_date', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True, default='active'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['voter_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.ForeignKeyConstraint(['stage_id'], ['contest_stages.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # vote_sessions table
    if not table_exists('vote_sessions', insp):
        op.create_table('vote_sessions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('voter_id', sa.Integer(), nullable=False),
            sa.Column('contest_type_id', sa.Integer(), nullable=False),
            sa.Column('stage_id', sa.Integer(), nullable=False),
            sa.Column('votes_count', sa.Integer(), nullable=False, default=0),
            sa.Column('max_votes_reached', sa.Boolean(), nullable=False, default=False),
            sa.Column('last_vote_date', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['voter_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contest_type_id'], ['contest_types.id'], ),
            sa.ForeignKeyConstraint(['stage_id'], ['contest_stages.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # contest_comments table
    if not table_exists('contest_comments', insp):
        op.create_table('contest_comments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('is_approved', sa.Boolean(), nullable=True, default=True),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.ForeignKeyConstraint(['parent_id'], ['contest_comments.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # contest_likes table
    if not table_exists('contest_likes', insp):
        op.create_table('contest_likes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # page_views table
    if not table_exists('page_views', insp):
        op.create_table('page_views',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.Column('viewed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # contest_submissions table
    if not table_exists('contest_submissions', insp):
        op.create_table('contest_submissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('media_type', sa.String(length=50), nullable=False),
            sa.Column('file_url', sa.String(length=500), nullable=True),
            sa.Column('external_url', sa.String(length=500), nullable=True),
            sa.Column('title', sa.String(length=200), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('upload_date', sa.DateTime(), nullable=True),
            sa.Column('is_approved', sa.Boolean(), nullable=True, default=False),
            sa.Column('moderation_status', sa.String(length=50), nullable=True, default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # contestant_rankings table
    if not table_exists('contestant_rankings', insp):
        op.create_table('contestant_rankings',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('stage_id', sa.Integer(), nullable=False),
            sa.Column('total_points', sa.Integer(), nullable=False, default=0),
            sa.Column('total_votes', sa.Integer(), nullable=False, default=0),
            sa.Column('page_views', sa.Integer(), nullable=False, default=0),
            sa.Column('likes', sa.Integer(), nullable=False, default=0),
            sa.Column('final_rank', sa.Integer(), nullable=True),
            sa.Column('last_updated', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.ForeignKeyConstraint(['stage_id'], ['contest_stages.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Update user table with new fields - check if columns exist first
    # Note: The table might be called 'user' or 'users'
    user_table = 'users' if table_exists('users', insp) else 'user'
    
    columns_to_add = [
        ('continent_id', sa.Column('continent_id', sa.Integer(), nullable=True)),
        ('region_id', sa.Column('region_id', sa.Integer(), nullable=True)),
        ('country_id', sa.Column('country_id', sa.Integer(), nullable=True)),
        ('city_id', sa.Column('city_id', sa.Integer(), nullable=True)),
        ('gender', sa.Column('gender', postgresql.ENUM('MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY', name='gender', create_type=False), nullable=True)),
        ('date_of_birth', sa.Column('date_of_birth', sa.Date(), nullable=True)),
        ('phone_number', sa.Column('phone_number', sa.String(length=20), nullable=True)),
        ('address_line1', sa.Column('address_line1', sa.String(length=200), nullable=True)),
        ('address_line2', sa.Column('address_line2', sa.String(length=200), nullable=True)),
        ('postal_code', sa.Column('postal_code', sa.String(length=20), nullable=True)),
        ('identity_verified', sa.Column('identity_verified', sa.Boolean(), nullable=True)),
        ('identity_verification_date', sa.Column('identity_verification_date', sa.DateTime(), nullable=True)),
        ('referral_code', sa.Column('referral_code', sa.String(length=20), nullable=True)),
        ('profile_picture_url', sa.Column('profile_picture_url', sa.String(length=500), nullable=True)),
        ('website_url', sa.Column('website_url', sa.String(length=500), nullable=True)),
        ('social_media_links', sa.Column('social_media_links', sa.JSON(), nullable=True)),
        ('status', sa.Column('status', postgresql.ENUM('ACTIVE', 'SUSPENDED', 'BANNED', 'PENDING_VERIFICATION', name='userstatus', create_type=False), nullable=True)),
    ]
    
    for col_name, col_def in columns_to_add:
        if not column_exists(user_table, col_name, insp):
            op.add_column(user_table, col_def)


def downgrade():
    # Drop tables (in reverse order of dependencies)
    tables_to_drop = [
        'contestant_rankings', 'contest_submissions', 'page_views',
        'contest_likes', 'contest_comments', 'vote_sessions', 'votes',
        'my_favorites', 'contestants', 'chart_of_accounts', 'fan_clubs',
        'affiliate_trees', 'dsp_wallets', 'contest_stages', 'contest_seasons',
        'contest_categories', 'contest_types', 'cities', 'countries',
        'regions', 'continents'
    ]
    
    for table in tables_to_drop:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS userstatus')
    op.execute('DROP TYPE IF EXISTS accounttype')
    op.execute('DROP TYPE IF EXISTS clubstatus')
    op.execute('DROP TYPE IF EXISTS stagestatus')
    op.execute('DROP TYPE IF EXISTS stagelevel')
    op.execute('DROP TYPE IF EXISTS seasonstatus')
    op.execute('DROP TYPE IF EXISTS gender')
    op.execute('DROP TYPE IF EXISTS conteststagelevel')
