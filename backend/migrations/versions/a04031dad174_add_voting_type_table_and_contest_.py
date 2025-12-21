"""add_voting_type_table_and_contest_relation

Revision ID: a04031dad174
Revises: e66e1251cb0d
Create Date: 2025-12-21 23:15:58.663282

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a04031dad174'
down_revision = 'e66e1251cb0d'
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


def upgrade():
    # Créer les types ENUM si ils n'existent pas
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
    
    # Créer la table voting_type si elle n'existe pas
    if not table_exists('voting_type'):
        # Utiliser les types ENUM existants au lieu de les créer à nouveau
        voting_level_enum = postgresql.ENUM('city', 'country', 'regional', 'continent', 'global', name='votinglevel', create_type=False)
        commission_source_enum = postgresql.ENUM('advert', 'affiliate', 'kyc', 'MFM', name='commissionsource', create_type=False)
        
        op.create_table(
            'voting_type',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('voting_level', voting_level_enum, nullable=False),
            sa.Column('commission_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('commission_source', commission_source_enum, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Ajouter la colonne voting_type_id à la table contest si elle n'existe pas
    if not column_exists('contest', 'voting_type_id'):
        op.add_column(
            'contest',
            sa.Column('voting_type_id', sa.Integer(), nullable=True)
        )
        
        # Créer la clé étrangère
        op.create_foreign_key(
            'fk_contest_voting_type',
            'contest',
            'voting_type',
            ['voting_type_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    # Supprimer la clé étrangère
    op.drop_constraint('fk_contest_voting_type', 'contest', type_='foreignkey')
    
    # Supprimer la colonne voting_type_id de contest
    if column_exists('contest', 'voting_type_id'):
        op.drop_column('contest', 'voting_type_id')
    
    # Supprimer la table voting_type
    if table_exists('voting_type'):
        op.drop_table('voting_type')
    
    # Supprimer les types ENUM
    op.execute("DROP TYPE IF EXISTS commissionsource")
    op.execute("DROP TYPE IF EXISTS votinglevel")
