"""Add round_contests join table for N:N relationship

Revision ID: add_round_contests
Revises: 4443c46923b6
Create Date: 2026-01-23 23:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_round_contests'
down_revision = '4443c46923b6'  # Points to the merge migration
branch_labels = None
depends_on = None


def upgrade():
    # Check if table already exists (idempotent migration)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    if 'round_contests' not in tables:
        # 1. Create round_contests association table
        op.create_table(
            'round_contests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('round_id', sa.Integer(), sa.ForeignKey('rounds.id', ondelete='CASCADE'), nullable=False),
            sa.Column('contest_id', sa.Integer(), sa.ForeignKey('contest.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('round_id', 'contest_id', name='unique_round_contest'),
        )
        
        # 2. Create indexes for performance
        op.create_index('idx_round_contests_round_id', 'round_contests', ['round_id'])
        op.create_index('idx_round_contests_contest_id', 'round_contests', ['contest_id'])
        
        # 3. Migrate existing data from rounds.contest_id to round_contests
        # This is done with raw SQL to handle the data migration
        op.execute("""
            INSERT INTO round_contests (round_id, contest_id)
            SELECT id, contest_id FROM rounds WHERE contest_id IS NOT NULL
            ON CONFLICT (round_id, contest_id) DO NOTHING
        """)
    else:
        # Table already exists, just ensure indexes exist
        indexes = [idx['name'] for idx in inspector.get_indexes('round_contests')]
        if 'idx_round_contests_round_id' not in indexes:
            op.create_index('idx_round_contests_round_id', 'round_contests', ['round_id'])
        if 'idx_round_contests_contest_id' not in indexes:
            op.create_index('idx_round_contests_contest_id', 'round_contests', ['contest_id'])
    
    # 4. Make contest_id nullable on rounds table (keeping for backward compatibility)
    # Check if column exists and is not already nullable
    try:
        op.alter_column('rounds', 'contest_id', nullable=True)
    except Exception:
        pass  # Column may already be nullable or doesn't exist


def downgrade():
    # 1. Restore contest_id NOT NULL constraint (if data allows)
    # op.alter_column('rounds', 'contest_id', nullable=False)
    
    # 2. Drop indexes
    op.drop_index('idx_round_contests_contest_id', 'round_contests')
    op.drop_index('idx_round_contests_round_id', 'round_contests')
    
    # 3. Drop round_contests table
    op.drop_table('round_contests')
