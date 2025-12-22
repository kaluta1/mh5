"""add_suggested_contest_table

Revision ID: b1c2d3e4f5a6
Revises: a04031dad174
Create Date: 2025-12-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a04031dad174'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade():
    # Créer le type ENUM pour le statut si il n'existe pas
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE suggestedconteststatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Créer la table suggested_contest si elle n'existe pas
    if not table_exists('suggested_contest'):
        # Utiliser le type ENUM existant
        status_enum = postgresql.ENUM('pending', 'approved', 'rejected', name='suggestedconteststatus', create_type=False)
        
        op.create_table(
            'suggested_contest',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('category', sa.String(length=100), nullable=False),
            sa.Column('status', status_enum, nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    # Supprimer la table suggested_contest
    if table_exists('suggested_contest'):
        op.drop_table('suggested_contest')
    
    # Supprimer le type ENUM
    op.execute("DROP TYPE IF EXISTS suggestedconteststatus")

