"""add author_id and referral_code to contestant_shares

Revision ID: add_author_ref_to_shares
Revises: merge_contestant_voting_email
Create Date: 2025-01-27 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_author_ref_to_shares'
down_revision = 'merge_contestant_voting_email'
branch_labels = None
depends_on = None


def upgrade():
    # Ajouter la colonne author_id
    op.add_column('contestant_shares', sa.Column('author_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_contestant_shares_author_id',
        'contestant_shares',
        'users',
        ['author_id'],
        ['id']
    )
    op.create_index(op.f('ix_contestant_shares_author_id'), 'contestant_shares', ['author_id'], unique=False)
    
    # Ajouter la colonne referral_code
    op.add_column('contestant_shares', sa.Column('referral_code', sa.String(length=50), nullable=True))
    
    # Migrer les données : copier user_id vers author_id si user_id existe
    op.execute("""
        UPDATE contestant_shares
        SET author_id = user_id
        WHERE user_id IS NOT NULL AND author_id IS NULL
    """)


def downgrade():
    # Supprimer l'index et la contrainte de clé étrangère
    op.drop_index(op.f('ix_contestant_shares_author_id'), table_name='contestant_shares')
    op.drop_constraint('fk_contestant_shares_author_id', 'contestant_shares', type_='foreignkey')
    
    # Supprimer les colonnes
    op.drop_column('contestant_shares', 'referral_code')
    op.drop_column('contestant_shares', 'author_id')

