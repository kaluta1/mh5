"""add reactions and shares tables

Revision ID: add_reactions_shares
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_reactions_shares'
down_revision = '1f78dfe04588'  # Dernière migration appliquée
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    insp = inspect(bind)
    
    def table_exists(table_name):
        return table_name in insp.get_table_names()
    
    # Créer l'enum ReactionType s'il n'existe pas déjà
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE reactiontype AS ENUM ('like', 'love', 'wow', 'dislike');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Créer la table contestant_reactions si elle n'existe pas
    if not table_exists('contestant_reactions'):
        op.create_table(
            'contestant_reactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('reaction_type', sa.String(length=20), nullable=False),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'contestant_id', name='uq_user_contestant_reaction')
        )
        op.create_index(op.f('ix_contestant_reactions_contestant_id'), 'contestant_reactions', ['contestant_id'], unique=False)
        op.create_index(op.f('ix_contestant_reactions_user_id'), 'contestant_reactions', ['user_id'], unique=False)
    
    # Créer la table contestant_shares si elle n'existe pas
    if not table_exists('contestant_shares'):
        op.create_table(
            'contestant_shares',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('contestant_id', sa.Integer(), nullable=False),
            sa.Column('shared_by_user_id', sa.Integer(), nullable=True),
            sa.Column('share_link', sa.String(length=500), nullable=False),
            sa.Column('platform', sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
            sa.ForeignKeyConstraint(['shared_by_user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_contestant_shares_contestant_id'), 'contestant_shares', ['contestant_id'], unique=False)
        op.create_index(op.f('ix_contestant_shares_user_id'), 'contestant_shares', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_contestant_shares_user_id'), table_name='contestant_shares')
    op.drop_index(op.f('ix_contestant_shares_contestant_id'), table_name='contestant_shares')
    op.drop_table('contestant_shares')
    op.drop_index(op.f('ix_contestant_reactions_user_id'), table_name='contestant_reactions')
    op.drop_index(op.f('ix_contestant_reactions_contestant_id'), table_name='contestant_reactions')
    op.drop_table('contestant_reactions')
    op.execute("DROP TYPE reactiontype")

