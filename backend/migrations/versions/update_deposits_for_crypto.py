"""Update deposits table for crypto payments

Revision ID: update_deposits_crypto
Revises: add_payment_tables
Create Date: 2024-12-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'update_deposits_crypto'
down_revision = 'add_payment_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Add new crypto payment columns to deposits
    op.add_column('deposits', sa.Column('crypto_currency', sa.String(20), nullable=True))
    op.add_column('deposits', sa.Column('crypto_amount', sa.Numeric(18, 8), nullable=True))
    op.add_column('deposits', sa.Column('payment_address', sa.String(255), nullable=True))
    op.add_column('deposits', sa.Column('order_id', sa.String(100), nullable=True))
    op.add_column('deposits', sa.Column('external_payment_id', sa.String(255), nullable=True))
    
    # Make payment_method_id nullable
    op.alter_column('deposits', 'payment_method_id', nullable=True)
    
    # Make reference nullable (we use order_id now)
    op.alter_column('deposits', 'reference', nullable=True)
    
    # Create unique index on order_id
    op.create_index('ix_deposits_order_id', 'deposits', ['order_id'], unique=True)
    
    # Add new status values to enum
    op.execute("ALTER TYPE depositstatus ADD VALUE IF NOT EXISTS 'partially_paid'")
    op.execute("ALTER TYPE depositstatus ADD VALUE IF NOT EXISTS 'failed'")


def downgrade():
    op.drop_index('ix_deposits_order_id', table_name='deposits')
    op.drop_column('deposits', 'external_payment_id')
    op.drop_column('deposits', 'order_id')
    op.drop_column('deposits', 'payment_address')
    op.drop_column('deposits', 'crypto_amount')
    op.drop_column('deposits', 'crypto_currency')
    op.alter_column('deposits', 'payment_method_id', nullable=False)
    op.alter_column('deposits', 'reference', nullable=False)
