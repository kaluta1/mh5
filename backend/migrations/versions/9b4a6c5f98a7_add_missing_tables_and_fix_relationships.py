"""Add missing tables and fix relationships - Idempotent version

Revision ID: 9b4a6c5f98a7
Revises: 002_add_myfav_models
Create Date: 2025-08-28 10:16:45.851209

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '9b4a6c5f98a7'
down_revision = '002_add_myfav_models'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    if not table_exists(table_name):
        return False
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def index_exists(index_name):
    """Check if an index exists"""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade():
    conn = op.get_bind()
    
    # ============== ENUM TYPES ==============
    # Create ENUM types if they don't exist
    enums_to_create = [
        ("votinglevel", "'city', 'country', 'regional', 'continent', 'global'"),
        ("commissionsource", "'advert', 'affiliate', 'kyc', 'MFM'"),
        ("votingrestriction", "'NONE', 'MALE_ONLY', 'FEMALE_ONLY', 'GEOGRAPHIC', 'AGE_RESTRICTED'"),
        ("verificationtype", "'none', 'visual', 'voice', 'brand', 'content'"),
        ("participanttype", "'individual', 'pet', 'club', 'content'"),
        ("commissiontype", "'AD_REVENUE', 'CLUB_MEMBERSHIP', 'SHOP_PURCHASE', 'CONTEST_PARTICIPATION'"),
        ("contestantverificationstatus", "'pending', 'approved', 'rejected'"),
        ("contestantverificationtype", "'selfie', 'selfie_with_pet', 'selfie_with_doc', 'voice_recording', 'video_verification', 'brand_proof'"),
        ("suggestedconteststatus", "'pending', 'approved', 'rejected'"),
    ]
    
    for enum_name, enum_values in enums_to_create:
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE {enum_name} AS ENUM ({enum_values});
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
    
    # ============== VOTING_TYPE TABLE ==============
    if not table_exists('voting_type'):
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
    
    # ============== CONTEST TABLE COLUMNS ==============
    # Convert contest.level from ENUM to VARCHAR if it's an ENUM
    result = conn.execute(sa.text("""
        SELECT data_type, udt_name FROM information_schema.columns 
        WHERE table_name = 'contest' AND column_name = 'level'
    """))
    row = result.fetchone()
    if row and row[0] == 'USER-DEFINED' and row[1] in ('contest_level', 'location_level'):
        op.execute("""
            ALTER TABLE contest ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
        """)
        op.execute("DROP TYPE IF EXISTS contest_level;")
    
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
        ('verification_type', "verificationtype DEFAULT 'none' NOT NULL"),
        ('participant_type', "participanttype DEFAULT 'individual' NOT NULL"),
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
        if not column_exists('contest', col_name):
            op.execute(f"ALTER TABLE contest ADD COLUMN {col_name} {col_type};")
    
    # Add voting_type_id foreign key if not exists
    if column_exists('contest', 'voting_type_id') and table_exists('voting_type'):
        op.execute("""
            DO $$ BEGIN
                ALTER TABLE contest ADD CONSTRAINT fk_contest_voting_type 
                FOREIGN KEY (voting_type_id) REFERENCES voting_type(id) ON DELETE SET NULL;
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
    
    # ============== LOCATION TABLE ==============
    # Convert location.level from ENUM to VARCHAR if needed
    if table_exists('location'):
        result = conn.execute(sa.text("""
            SELECT data_type, udt_name FROM information_schema.columns 
            WHERE table_name = 'location' AND column_name = 'level'
        """))
        row = result.fetchone()
        if row and row[0] == 'USER-DEFINED' and row[1] == 'location_level':
            op.execute("""
                ALTER TABLE location ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
            """)
            op.execute("DROP TYPE IF EXISTS location_level;")
    
    # ============== CONTEST_TEMPLATE TABLE COLUMNS ==============
    if table_exists('contest_template'):
        template_columns = [
            ('default_requires_kyc', 'BOOLEAN DEFAULT true NOT NULL'),
            ('default_verification_type', "verificationtype DEFAULT 'none' NOT NULL"),
            ('default_participant_type', "participanttype DEFAULT 'individual' NOT NULL"),
            ('default_visual_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_voice_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_brand_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_content_verification', 'BOOLEAN DEFAULT false NOT NULL'),
            ('default_min_age', 'INTEGER'),
            ('default_max_age', 'INTEGER'),
        ]
        
        for col_name, col_type in template_columns:
            if not column_exists('contest_template', col_name):
                op.execute(f"ALTER TABLE contest_template ADD COLUMN {col_name} {col_type};")
    
    # ============== USERS TABLE COLUMNS ==============
    if table_exists('users'):
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
        ]
        
        for col_name, col_type in user_columns:
            if not column_exists('users', col_name):
                op.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
        
        # Add unique constraint on personal_referral_code
        op.execute("""
            DO $$ BEGIN
                ALTER TABLE users ADD CONSTRAINT uq_users_personal_referral_code UNIQUE (personal_referral_code);
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
    
    # ============== CONTEST_SEASONS TABLE ==============
    if table_exists('contest_seasons'):
        if not column_exists('contest_seasons', 'is_deleted'):
            op.execute("ALTER TABLE contest_seasons ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;")
        if not column_exists('contest_seasons', 'title'):
            op.execute("ALTER TABLE contest_seasons ADD COLUMN title VARCHAR(200) DEFAULT '' NOT NULL;")
    
    # ============== CONTESTANTS TABLE ==============
    if table_exists('contestants'):
        contestant_columns = [
            ('title', 'VARCHAR(200)'),
            ('description', 'TEXT'),
            ('image_media_ids', 'VARCHAR(1000)'),
            ('video_media_ids', 'VARCHAR(1000)'),
            ('is_deleted', 'BOOLEAN DEFAULT false NOT NULL'),
        ]
        
        for col_name, col_type in contestant_columns:
            if not column_exists('contestants', col_name):
                op.execute(f"ALTER TABLE contestants ADD COLUMN {col_name} {col_type};")
    
    # ============== CONTESTANT_VERIFICATIONS TABLE ==============
    if not table_exists('contestant_verifications'):
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
    
    # ============== CONTEST_SEASON_LINKS TABLE ==============
    if not table_exists('contest_season_links'):
        op.create_table(
            'contest_season_links',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contest_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('linked_at', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contest_id'], ['contest.id']),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('contest_id', 'season_id', name='uq_contest_season')
        )
    
    # ============== CONTESTANT_SEASONS TABLE ==============
    if not table_exists('contestant_seasons'):
        op.create_table(
            'contestant_seasons',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('joined_at', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('contestant_id', 'season_id', name='uq_contestant_season')
        )
    
    # ============== SUGGESTED_CONTEST TABLE ==============
    if not table_exists('suggested_contest'):
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
    
    # ============== MY_FAVORITES TABLE ==============
    if table_exists('my_favorites'):
        if not column_exists('my_favorites', 'position'):
            op.execute("ALTER TABLE my_favorites ADD COLUMN position INTEGER DEFAULT 0 NOT NULL;")
    
    # ============== CONTEST_VOTES TABLE ==============
    if not table_exists('contest_votes'):
        op.create_table(
            'contest_votes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('entry_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('score', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['entry_id'], ['contest_entry.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== CONTEST_FAVORITES TABLE ==============
    if not table_exists('contest_favorites'):
        op.create_table(
            'contest_favorites',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contest_id', sa.Integer(), nullable=False),
            sa.Column('added_date', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['contest_id'], ['contest.id']),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== CONTESTANT_REACTIONS TABLE ==============
    if not table_exists('contestant_reactions'):
        op.create_table(
            'contestant_reactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('reaction_type', sa.String(20), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== CONTESTANT_SHARES TABLE ==============
    if not table_exists('contestant_shares'):
        op.create_table(
            'contestant_shares',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('author_id', sa.Integer(), nullable=True),
            sa.Column('shared_by_user_id', sa.Integer(), nullable=True),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('referral_code', sa.String(50), nullable=True),
            sa.Column('share_link', sa.String(500), nullable=False),
            sa.Column('platform', sa.String(50), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['author_id'], ['users.id']),
            sa.ForeignKeyConstraint(['shared_by_user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== CONTESTANT_VOTING TABLE ==============
    if not table_exists('contestant_voting'):
        op.create_table(
            'contestant_voting',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('contest_id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('vote_date', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id']),
            sa.ForeignKeyConstraint(['contest_id'], ['contest.id']),
            sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'contestant_id', 'season_id', name='uq_contestant_voting')
        )
    
    # ============== NOTIFICATIONS TABLE ==============
    if not table_exists('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('type', sa.String(50), nullable=False),
            sa.Column('is_read', sa.Boolean(), default=False),
            sa.Column('data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
        if not index_exists('ix_notifications_user_id'):
            op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    
    # ============== ROLES TABLE ==============
    if not table_exists('roles'):
        op.create_table(
            'roles',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(64), nullable=False, unique=True),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('is_system', sa.Boolean(), default=False, nullable=False),
            sa.Column('inherit_from_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['inherit_from_id'], ['roles.id']),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== PERMISSIONS TABLE ==============
    if not table_exists('permissions'):
        op.create_table(
            'permissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('category', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    
    # ============== ROLE_PERMISSIONS TABLE ==============
    if not table_exists('role_permissions'):
        op.create_table(
            'role_permissions',
            sa.Column('role_id', sa.Integer(), nullable=False),
            sa.Column('permission_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('role_id', 'permission_id')
        )
    
    # Add role_id to users if not exists
    if table_exists('users') and not column_exists('users', 'role_id'):
        op.execute("ALTER TABLE users ADD COLUMN role_id INTEGER;")
        op.execute("""
            DO $$ BEGIN
                ALTER TABLE users ADD CONSTRAINT fk_users_role_id 
                FOREIGN KEY (role_id) REFERENCES roles(id);
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)


def downgrade():
    # Downgrade is complex for this migration
    # In production, would typically not use downgrade for such a comprehensive migration
    pass
