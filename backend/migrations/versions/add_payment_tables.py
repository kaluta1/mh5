"""add payment_methods, product_types, deposits tables

Revision ID: add_payment_tables
Revises: add_attempts_to_kyc
Create Date: 2024-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_payment_tables'
down_revision = 'add_attempts_to_kyc'
branch_labels = None
depends_on = None


def upgrade():
    # Create payment_methods table
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('category', sa.Enum('crypto', 'bank', 'card', name='paymentmethodcategory'), nullable=False),
        sa.Column('network', sa.String(50), nullable=True),
        sa.Column('token_symbol', sa.String(20), nullable=True),
        sa.Column('wallet_address', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('min_amount', sa.Numeric(18, 8), nullable=True),
        sa.Column('max_amount', sa.Numeric(18, 8), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create product_types table
    op.create_table(
        'product_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
        sa.Column('validity_days', sa.Integer(), nullable=False, server_default='365'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_consumable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create deposits table
    op.create_table(
        'deposits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_type_id', sa.Integer(), nullable=False),
        sa.Column('payment_method_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
        sa.Column('status', sa.Enum('pending', 'validated', 'rejected', 'expired', name='depositstatus'), nullable=False, server_default='pending'),
        sa.Column('reference', sa.String(100), nullable=False, unique=True),
        sa.Column('tx_hash', sa.String(255), nullable=True),
        sa.Column('from_address', sa.String(255), nullable=True),
        sa.Column('payment_provider_id', sa.String(255), nullable=True),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_type_id'], ['product_types.id']),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id']),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'])
    )
    
    # Create indexes
    op.create_index('ix_deposits_user_id', 'deposits', ['user_id'])
    op.create_index('ix_deposits_status', 'deposits', ['status'])
    op.create_index('ix_deposits_product_type_id', 'deposits', ['product_type_id'])
    
    # Insert default payment methods
    op.execute("""
        INSERT INTO payment_methods (code, name, category, network, token_symbol, is_active) VALUES
        ('usdt_bsc', 'USDT (BNB Chain)', 'crypto', 'bsc', 'USDT', true),
        ('usdt_sol', 'USDT (Solana)', 'crypto', 'solana', 'USDT', true),
        ('btc', 'Bitcoin', 'crypto', 'bitcoin', 'BTC', true),
        ('sol', 'Solana', 'crypto', 'solana', 'SOL', true),
        ('card', 'Carte bancaire', 'card', NULL, NULL, true),
        ('bank_transfer', 'Virement bancaire', 'bank', NULL, NULL, true)
    """)
    
    # Insert default product types
    op.execute("""
        INSERT INTO product_types (code, name, description, price, currency, validity_days, is_active, is_consumable) VALUES
        ('kyc', 'Vérification KYC', 'Vérification d''identité pour accéder aux fonctionnalités complètes', 1.00, 'USD', 365, true, true),
        ('subscription_club', 'Abonnement Club', 'Abonnement mensuel au club', 9.99, 'USD', 30, true, false),
        ('efm_membership', 'EFM Membership', 'Adhésion au programme EFM', 99.00, 'USD', 365, true, false)
    """)


def downgrade():
    op.drop_index('ix_deposits_product_type_id', 'deposits')
    op.drop_index('ix_deposits_status', 'deposits')
    op.drop_index('ix_deposits_user_id', 'deposits')
    op.drop_table('deposits')
    op.drop_table('product_types')
    op.drop_table('payment_methods')
    op.execute("DROP TYPE IF EXISTS depositstatus")
    op.execute("DROP TYPE IF EXISTS paymentmethodcategory")
