"""Add user_vote_rankings table for ranked voting system

Revision ID: add_vote_rankings
Revises: add_round_contests
Create Date: 2026-01-23 23:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_vote_rankings'
down_revision = 'add_round_contests'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create user_vote_rankings table for the ranked voting system
    # Max 5 votes per user per round, position-based points
    op.create_table(
        'user_vote_rankings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_id', sa.Integer(), sa.ForeignKey('rounds.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contestant_id', sa.Integer(), sa.ForeignKey('contestants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),  # 1-5
        sa.Column('points', sa.Integer(), nullable=False),    # 5,4,3,2,1
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        # Ensure unique vote per user per contestant per round
        sa.UniqueConstraint('user_id', 'round_id', 'contestant_id', name='unique_user_round_contestant_vote'),
    )
    
    # 2. Create indexes for performance
    op.create_index('idx_vote_rankings_user_round', 'user_vote_rankings', ['user_id', 'round_id'])
    op.create_index('idx_vote_rankings_contestant', 'user_vote_rankings', ['contestant_id'])
    op.create_index('idx_vote_rankings_round', 'user_vote_rankings', ['round_id'])
    
    # 3. Add round_id to contest_votes if not exists (for existing votes)
    # Note: This should already exist but we ensure it's there
    try:
        op.add_column('contest_votes', sa.Column('round_id', sa.Integer(), sa.ForeignKey('rounds.id'), nullable=True))
    except Exception:
        pass  # Column may already exist


def downgrade():
    # 1. Drop indexes
    op.drop_index('idx_vote_rankings_round', 'user_vote_rankings')
    op.drop_index('idx_vote_rankings_contestant', 'user_vote_rankings')
    op.drop_index('idx_vote_rankings_user_round', 'user_vote_rankings')
    
    # 2. Drop user_vote_rankings table
    op.drop_table('user_vote_rankings')
