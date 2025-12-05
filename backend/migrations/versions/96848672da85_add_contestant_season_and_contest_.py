"""add_contestant_season_and_contest_season_link_models

Revision ID: 96848672da85
Revises: bae8bd7b411d
Create Date: 2025-01-27 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '96848672da85'
down_revision = 'bae8bd7b411d'
branch_labels = None
depends_on = None


def upgrade():
    # Create contestant_seasons table
    op.create_table(
        'contestant_seasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contestant_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contestant_id'], ['contestants.id'], ),
        sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contestant_id', 'season_id', name='uq_contestant_season'),
        comment='Liaison entre contestants et seasons'
    )
    op.create_index(op.f('ix_contestant_seasons_contestant_id'), 'contestant_seasons', ['contestant_id'], unique=False)
    op.create_index(op.f('ix_contestant_seasons_season_id'), 'contestant_seasons', ['season_id'], unique=False)

    # Create contest_season_links table
    op.create_table(
        'contest_season_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('linked_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contest_id'], ['contest.id'], ),
        sa.ForeignKeyConstraint(['season_id'], ['contest_seasons.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contest_id', 'season_id', name='uq_contest_season'),
        comment='Liaison entre contests et seasons'
    )
    op.create_index(op.f('ix_contest_season_links_contest_id'), 'contest_season_links', ['contest_id'], unique=False)
    op.create_index(op.f('ix_contest_season_links_season_id'), 'contest_season_links', ['season_id'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_contest_season_links_season_id'), table_name='contest_season_links')
    op.drop_index(op.f('ix_contest_season_links_contest_id'), table_name='contest_season_links')
    op.drop_index(op.f('ix_contestant_seasons_season_id'), table_name='contestant_seasons')
    op.drop_index(op.f('ix_contestant_seasons_contestant_id'), table_name='contestant_seasons')
    
    # Drop tables
    op.drop_table('contest_season_links')
    op.drop_table('contestant_seasons')
