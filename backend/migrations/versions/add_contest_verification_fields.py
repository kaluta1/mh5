"""Add verification requirements to Contest and ContestTemplate

Revision ID: add_contest_verification
Revises: add_rbac_permissions
Create Date: 2025-12-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_contest_verification'
down_revision = 'add_rbac_permissions'
branch_labels = None
depends_on = None


def upgrade():
    # Créer les enums
    verification_type = postgresql.ENUM(
        'none', 'visual', 'voice', 'brand', 'content',
        name='verificationtype',
        create_type=False
    )
    
    participant_type = postgresql.ENUM(
        'individual', 'pet', 'club', 'content',
        name='participanttype',
        create_type=False
    )
    
    # Créer les types ENUM si ils n'existent pas
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
    
    # ============== Ajouter les colonnes à la table contest ==============
    
    # KYC obligatoire (défaut: true)
    op.add_column('contest', sa.Column('requires_kyc', sa.Boolean(), nullable=False, server_default='true'))
    
    # Type de vérification
    op.add_column('contest', sa.Column(
        'verification_type',
        sa.Enum('none', 'visual', 'voice', 'brand', 'content', name='verificationtype'),
        nullable=False,
        server_default='none'
    ))
    
    # Type de participant
    op.add_column('contest', sa.Column(
        'participant_type',
        sa.Enum('individual', 'pet', 'club', 'content', name='participanttype'),
        nullable=False,
        server_default='individual'
    ))
    
    # Vérifications spécifiques
    op.add_column('contest', sa.Column('requires_visual_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest', sa.Column('requires_voice_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest', sa.Column('requires_brand_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest', sa.Column('requires_content_verification', sa.Boolean(), nullable=False, server_default='false'))
    
    # Restrictions d'âge
    op.add_column('contest', sa.Column('min_age', sa.Integer(), nullable=True))
    op.add_column('contest', sa.Column('max_age', sa.Integer(), nullable=True))
    
    # ============== Ajouter les colonnes à la table contest_template ==============
    
    # KYC obligatoire par défaut
    op.add_column('contest_template', sa.Column('default_requires_kyc', sa.Boolean(), nullable=False, server_default='true'))
    
    # Type de vérification par défaut
    op.add_column('contest_template', sa.Column(
        'default_verification_type',
        sa.Enum('none', 'visual', 'voice', 'brand', 'content', name='verificationtype'),
        nullable=False,
        server_default='none'
    ))
    
    # Type de participant par défaut
    op.add_column('contest_template', sa.Column(
        'default_participant_type',
        sa.Enum('individual', 'pet', 'club', 'content', name='participanttype'),
        nullable=False,
        server_default='individual'
    ))
    
    # Vérifications par défaut
    op.add_column('contest_template', sa.Column('default_visual_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest_template', sa.Column('default_voice_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest_template', sa.Column('default_brand_verification', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('contest_template', sa.Column('default_content_verification', sa.Boolean(), nullable=False, server_default='false'))
    
    # Restrictions d'âge par défaut
    op.add_column('contest_template', sa.Column('default_min_age', sa.Integer(), nullable=True))
    op.add_column('contest_template', sa.Column('default_max_age', sa.Integer(), nullable=True))
    
    # ============== Mettre à jour les templates existants avec des valeurs par défaut ==============
    # Beauty contest - nécessite vérification visuelle
    op.execute("""
        UPDATE contest_template 
        SET default_visual_verification = true,
            default_verification_type = 'visual'
        WHERE contest_type IN ('beauty', 'handsome')
    """)
    
    # Pet contests - participant type = pet
    op.execute("""
        UPDATE contest_template 
        SET default_participant_type = 'pet',
            default_visual_verification = true
        WHERE contest_type LIKE '%pet%'
    """)
    
    # Music/Singer contests - vérification vocale
    op.execute("""
        UPDATE contest_template 
        SET default_voice_verification = true,
            default_verification_type = 'voice'
        WHERE contest_type IN ('singer', 'music', 'latest_hits')
    """)
    
    # Club contests - participant type = club, vérification brand
    op.execute("""
        UPDATE contest_template 
        SET default_participant_type = 'club',
            default_brand_verification = true,
            default_verification_type = 'brand'
        WHERE contest_type LIKE '%club%' OR contest_type LIKE '%football%'
    """)


def downgrade():
    # Supprimer les colonnes de contest
    op.drop_column('contest', 'max_age')
    op.drop_column('contest', 'min_age')
    op.drop_column('contest', 'requires_content_verification')
    op.drop_column('contest', 'requires_brand_verification')
    op.drop_column('contest', 'requires_voice_verification')
    op.drop_column('contest', 'requires_visual_verification')
    op.drop_column('contest', 'participant_type')
    op.drop_column('contest', 'verification_type')
    op.drop_column('contest', 'requires_kyc')
    
    # Supprimer les colonnes de contest_template
    op.drop_column('contest_template', 'default_max_age')
    op.drop_column('contest_template', 'default_min_age')
    op.drop_column('contest_template', 'default_content_verification')
    op.drop_column('contest_template', 'default_brand_verification')
    op.drop_column('contest_template', 'default_voice_verification')
    op.drop_column('contest_template', 'default_visual_verification')
    op.drop_column('contest_template', 'default_participant_type')
    op.drop_column('contest_template', 'default_verification_type')
    op.drop_column('contest_template', 'default_requires_kyc')
    
    # Supprimer les types ENUM
    op.execute("DROP TYPE IF EXISTS verificationtype")
    op.execute("DROP TYPE IF EXISTS participanttype")
