"""Fix voting_type table and contest columns

Revision ID: fix_voting_type_contest
Revises: 5a9dda393841
Create Date: 2025-12-28 02:00:00.000000

This migration ensures all missing tables and columns exist.
It is fully idempotent and safe to run multiple times.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'fix_voting_type_contest'
down_revision = '5a9dda393841'
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
    
    # ============== ENUM TYPES ==============
    # Create required ENUM types if they don't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE votinglevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE commissionsource AS ENUM ('advert', 'affiliate', 'kyc', 'MFM');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE verificationtype AS ENUM ('none', 'visual', 'voice', 'brand', 'content');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE participanttype AS ENUM ('individual', 'pet', 'club', 'content');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE contestantverificationstatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE contestantverificationtype AS ENUM ('selfie', 'selfie_with_pet', 'selfie_with_doc', 'voice_recording', 'video_verification', 'brand_proof');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE suggestedconteststatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # ============== VOTING_TYPE TABLE ==============
    if not table_exists('voting_type', insp):
        op.create_table(
            'voting_type',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('voting_level', postgresql.ENUM('city', 'country', 'regional', 'continent', 'global', name='votinglevel', create_type=False), nullable=False),
            sa.Column('commission_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('commission_source', postgresql.ENUM('advert', 'affiliate', 'kyc', 'MFM', name='commissionsource', create_type=False), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        print("Created voting_type table")
    
    # ============== CONTEST TABLE - Convert ENUM to VARCHAR and add columns ==============
    if table_exists('contest', insp):
        # Check if level is ENUM and convert to VARCHAR
        result = bind.execute(sa.text("""
            SELECT data_type, udt_name FROM information_schema.columns 
            WHERE table_name = 'contest' AND column_name = 'level'
        """))
        row = result.fetchone()
        if row and row[0] == 'USER-DEFINED':
            op.execute("""
                ALTER TABLE contest ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
            """)
            print("Converted contest.level to VARCHAR(20)")
        
        # Add missing columns to contest table
        contest_columns = [
            ('cover_image_url', 'VARCHAR(500)'),
            ('voting_type_id', 'INTEGER'),
            ('city_season_start_date', 'DATE'),
            ('city_season_end_date', 'DATE'),
            ('country_season_start_date', 'DATE'),
            ('country_season_end_date', 'DATE'),
            ('regional_start_date', 'DATE'),
            ('regional_end_date', 'DATE'),
            ('continental_start_date', 'DATE'),
            ('continental_end_date', 'DATE'),
            ('global_start_date', 'DATE'),
            ('global_end_date', 'DATE'),
            ('image_url', 'VARCHAR(500)'),
            ('participant_count', 'INTEGER DEFAULT 0 NOT NULL'),
            ('requires_kyc', 'BOOLEAN DEFAULT true NOT NULL'),
            ('verification_type', "VARCHAR(20) DEFAULT 'none' NOT NULL"),
            ('participant_type', "VARCHAR(20) DEFAULT 'individual' NOT NULL"),
            ('requires_visual_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('requires_voice_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('requires_brand_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('requires_content_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('min_age', 'INTEGER'),
            ('max_age', 'INTEGER'),
            ('requires_video', 'BOOLEAN DEFAULT false NOT NULL'),
            ('max_videos', 'INTEGER DEFAULT 1 NOT NULL'),
            ('video_max_duration', 'INTEGER DEFAULT 3000 NOT NULL'),
            ('video_max_size_mb', 'INTEGER DEFAULT 500 NOT NULL'),
            ('min_images', 'INTEGER DEFAULT 0 NOT NULL'),
            ('max_images', 'INTEGER DEFAULT 10 NOT NULL'),
            ('verification_video_max_duration', 'INTEGER DEFAULT 30 NOT NULL'),
            ('verification_max_size_mb', 'INTEGER DEFAULT 50 NOT NULL'),
            ('is_deleted', 'BOOLEAN DEFAULT false NOT NULL'),
        ]
        
        for col_name, col_type in contest_columns:
            if not column_exists('contest', col_name, insp):
                op.execute(f"ALTER TABLE contest ADD COLUMN {col_name} {col_type};")
                print(f"Added column contest.{col_name}")
        
        # Add foreign key constraint for voting_type_id
        op.execute("""
            DO $$ BEGIN
                ALTER TABLE contest ADD CONSTRAINT fk_contest_voting_type 
                FOREIGN KEY (voting_type_id) REFERENCES voting_type(id) ON DELETE SET NULL;
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
    
    # ============== LOCATION TABLE - Convert ENUM to VARCHAR ==============
    if table_exists('location', insp):
        result = bind.execute(sa.text("""
            SELECT data_type, udt_name FROM information_schema.columns 
            WHERE table_name = 'location' AND column_name = 'level'
        """))
        row = result.fetchone()
        if row and row[0] == 'USER-DEFINED':
            op.execute("""
                ALTER TABLE location ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
            """)
            print("Converted location.level to VARCHAR(20)")
    
    # ============== CONTEST_TEMPLATE TABLE ==============
    if table_exists('contest_template', insp):
        template_columns = [
            ('default_requires_kyc', 'BOOLEAN DEFAULT true NOT NULL'),
            ('default_verification_type', "VARCHAR(20) DEFAULT 'none' NOT NULL"),
            ('default_participant_type', "VARCHAR(20) DEFAULT 'individual' NOT NULL"),
            ('default_visual_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_voice_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_brand_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_content_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_min_age', 'INTEGER'),
            ('default_max_age', 'INTEGER'),
        ]
        
        for col_name, col_type in template_columns:
            if not column_exists('contest_template', col_name, insp):
                op.execute(f"ALTER TABLE contest_template ADD COLUMN {col_name} {col_type};")
                print(f"Added column contest_template.{col_name}")
    
    # ============== CONTESTANT_VERIFICATIONS TABLE ==============
    if not table_exists('contestant_verifications', insp):
        op.create_table(
            'contestant_verifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('verification_type', postgresql.ENUM('selfie', 'selfie_with_pet', 'selfie_with_doc', 'voice_recording', 'video_verification', 'brand_proof', name='contestantverificationtype', create_type=False), nullable=False),
            sa.Column('media_url', sa.String(500), nullable=False),
            sa.Column('media_type', sa.String(20), nullable=False),
            sa.Column('duration_seconds', sa.Integer(), nullable=True),
            sa.Column('file_size_bytes', sa.Integer(), nullable=True),
            sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='contestantverificationstatus', create_type=False), default='pending', nullable=False),
            sa.Column('rejection_reason', sa.Text(), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
        print("Created contestant_verifications table")
    
    # ============== CONTEST_SEASON_LINKS TABLE ==============
    if not table_exists('contest_season_links', insp):
        op.create_table(
            'contest_season_links',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contest_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('linked_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contest_id'], ['contest.id']),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('contest_id', 'season_id', name='uq_contest_season')
        )
        print("Created contest_season_links table")
    
    # ============== CONTESTANT_SEASONS TABLE ==============
    if not table_exists('contestant_seasons', insp):
        op.create_table(
            'contestant_seasons',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('joined_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('contestant_id', 'season_id', name='uq_contestant_season')
        )
        print("Created contestant_seasons table")
    
    # ============== SUGGESTED_CONTEST TABLE ==============
    if not table_exists('suggested_contest', insp):
        op.create_table(
            'suggested_contest',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='suggestedconteststatus', create_type=False), default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        print("Created suggested_contest table")
    
    # ============== ROLES TABLE ==============
    if not table_exists('roles', insp):
        op.create_table(
            'roles',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(64), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('is_system', sa.Boolean(), default=False, nullable=False),
            sa.Column('inherit_from_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['inherit_from_id'], ['roles.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )
        print("Created roles table")
    
    # ============== PERMISSIONS TABLE ==============
    if not table_exists('permissions', insp):
        op.create_table(
            'permissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('category', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )
        print("Created permissions table")
    
    # ============== ROLE_PERMISSIONS TABLE ==============
    if not table_exists('role_permissions', insp):
        op.create_table(
            'role_permissions',
            sa.Column('role_id', sa.Integer(), nullable=False),
            sa.Column('permission_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('role_id', 'permission_id')
        )
        print("Created role_permissions table")
    
    # ============== USERS TABLE COLUMNS ==============
    if table_exists('users', insp):
        user_columns = [
            ('first_name', 'VARCHAR(100)'),
            ('last_name', 'VARCHAR(100)'),
            ('continent', 'VARCHAR(100)'),
            ('region', 'VARCHAR(100)'),
            ('country', 'VARCHAR(100)'),
            ('city', 'VARCHAR(100)'),
            ('is_deleted', 'BOOLEAN DEFAULT false NOT NULL'),
            ('email_verified', 'BOOLEAN DEFAULT false NOT NULL'),
            ('personal_referral_code', 'VARCHAR(50)'),
            ('preferred_language', "VARCHAR(5) DEFAULT 'fr' NOT NULL"),
            ('sponsor_id', 'INTEGER'),
            ('role_id', 'INTEGER'),
        ]
        
        for col_name, col_type in user_columns:
            if not column_exists('users', col_name, insp):
                op.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
                print(f"Added column users.{col_name}")
        
        # Add foreign key for role_id if roles table exists
        if table_exists('roles', insp) and column_exists('users', 'role_id', insp):
            op.execute("""
                DO $$ BEGIN
                    ALTER TABLE users ADD CONSTRAINT fk_users_role_id 
                    FOREIGN KEY (role_id) REFERENCES roles(id);
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """)
    
    # ============== CONTEST_SEASONS TABLE COLUMNS ==============
    if table_exists('contest_seasons', insp):
        if not column_exists('contest_seasons', 'is_deleted', insp):
            op.execute("ALTER TABLE contest_seasons ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;")
            print("Added column contest_seasons.is_deleted")
        if not column_exists('contest_seasons', 'title', insp):
            op.execute("ALTER TABLE contest_seasons ADD COLUMN title VARCHAR(200) DEFAULT '' NOT NULL;")
            print("Added column contest_seasons.title")
    
    # ============== CONTESTANTS TABLE COLUMNS ==============
    if table_exists('contestants', insp):
        contestant_columns = [
            ('title', 'VARCHAR(200)'),
            ('description', 'TEXT'),
            ('image_media_ids', 'VARCHAR(1000)'),
            ('video_media_ids', 'VARCHAR(1000)'),
            ('is_deleted', 'BOOLEAN DEFAULT false NOT NULL'),
        ]
        
        for col_name, col_type in contestant_columns:
            if not column_exists('contestants', col_name, insp):
                op.execute(f"ALTER TABLE contestants ADD COLUMN {col_name} {col_type};")
                print(f"Added column contestants.{col_name}")
    
    # ============== MY_FAVORITES TABLE COLUMNS ==============
    if table_exists('my_favorites', insp):
        if not column_exists('my_favorites', 'position', insp):
            op.execute("ALTER TABLE my_favorites ADD COLUMN position INTEGER DEFAULT 0 NOT NULL;")
            print("Added column my_favorites.position")
    
    print("Migration fix_voting_type_contest completed successfully!")


def downgrade() -> None:
    # Downgrade not implemented - this is a fix migration
    pass

