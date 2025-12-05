"""Add sponsor_id to users table

Revision ID: add_sponsor_id
Revises: 
Create Date: 2024-12-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sponsor_id'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Vérifier si la colonne existe déjà
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'sponsor_id' not in columns:
        # Ajouter la colonne sponsor_id à la table users
        op.add_column('users', sa.Column('sponsor_id', sa.Integer(), nullable=True))
        
        # Créer la contrainte de clé étrangère
        op.create_foreign_key(
            'fk_users_sponsor_id',
            'users', 'users',
            ['sponsor_id'], ['id'],
            ondelete='SET NULL'
        )
        
        # Créer un index pour améliorer les performances des requêtes sur sponsor_id
        op.create_index('ix_users_sponsor_id', 'users', ['sponsor_id'])


def downgrade():
    # Supprimer l'index
    op.drop_index('ix_users_sponsor_id', table_name='users')
    
    # Supprimer la contrainte de clé étrangère
    op.drop_constraint('fk_users_sponsor_id', 'users', type_='foreignkey')
    
    # Supprimer la colonne
    op.drop_column('users', 'sponsor_id')
