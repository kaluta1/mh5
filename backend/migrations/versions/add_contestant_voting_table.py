"""add contestant_voting table

Revision ID: add_contestant_voting
Revises: add_reactions_shares
Create Date: 2025-01-27 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_contestant_voting'
down_revision = 'add_reactions_shares'
branch_labels = None
depends_on = None


def upgrade():
    # Créer la table contestant_voting
    op.create_table(
        'contestant_voting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('contestant_id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('vote_date', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
        sa.ForeignKeyConstraint(['contest_id'], ['contest.id'], ),
        sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'contestant_id', 'contest_id', name='uq_contestant_voting')
    )
    op.create_index(op.f('ix_contestant_voting_user_id'), 'contestant_voting', ['user_id'], unique=False)
    op.create_index(op.f('ix_contestant_voting_contestant_id'), 'contestant_voting', ['contestant_id'], unique=False)
    op.create_index(op.f('ix_contestant_voting_contest_id'), 'contestant_voting', ['contest_id'], unique=False)
    op.create_index(op.f('ix_contestant_voting_season_id'), 'contestant_voting', ['season_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_contestant_voting_season_id'), table_name='contestant_voting')
    op.drop_index(op.f('ix_contestant_voting_contest_id'), table_name='contestant_voting')
    op.drop_index(op.f('ix_contestant_voting_contestant_id'), table_name='contestant_voting')
    op.drop_index(op.f('ix_contestant_voting_user_id'), table_name='contestant_voting')
    op.drop_table('contestant_voting')

