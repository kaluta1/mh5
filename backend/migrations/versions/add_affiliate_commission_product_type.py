"""Add product_type_id and related fields to affiliate_commissions

Revision ID: add_affiliate_commission_product_type
Revises: 
Create Date: 2024-12-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aff_comm_product_type'
down_revision = 'add_user_verifications'
branch_labels = None
depends_on = None


def upgrade():
    # Ajouter les nouvelles colonnes à affiliate_commissions
    op.add_column('affiliate_commissions', 
        sa.Column('product_type_id', sa.Integer(), sa.ForeignKey('product_types.id'), nullable=True)
    )
    op.add_column('affiliate_commissions', 
        sa.Column('deposit_id', sa.Integer(), sa.ForeignKey('deposits.id'), nullable=True)
    )
    
    # Renommer min_amount en base_amount si la colonne existe
    try:
        op.alter_column('affiliate_commissions', 'min_amount', new_column_name='base_amount')
    except Exception:
        # Si min_amount n'existe pas, ajouter base_amount
        op.add_column('affiliate_commissions',
            sa.Column('base_amount', sa.Numeric(10, 2), nullable=True)
        )
    
    # Rendre commission_rate nullable
    op.alter_column('affiliate_commissions', 'commission_rate',
        existing_type=sa.Numeric(5, 4),
        nullable=True
    )
    
    # Ajouter les colonnes de commission d'affiliation à product_types
    op.add_column('product_types',
        sa.Column('has_affiliate_commission', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column('product_types',
        sa.Column('affiliate_direct_amount', sa.Numeric(10, 2), nullable=True)
    )
    op.add_column('product_types',
        sa.Column('affiliate_direct_rate', sa.Numeric(5, 4), nullable=True)
    )
    op.add_column('product_types',
        sa.Column('affiliate_indirect_amount', sa.Numeric(10, 2), nullable=True)
    )
    op.add_column('product_types',
        sa.Column('affiliate_indirect_rate', sa.Numeric(5, 4), nullable=True)
    )


def downgrade():
    # Supprimer les colonnes de product_types
    op.drop_column('product_types', 'affiliate_indirect_rate')
    op.drop_column('product_types', 'affiliate_indirect_amount')
    op.drop_column('product_types', 'affiliate_direct_rate')
    op.drop_column('product_types', 'affiliate_direct_amount')
    op.drop_column('product_types', 'has_affiliate_commission')
    
    # Remettre commission_rate non nullable
    op.alter_column('affiliate_commissions', 'commission_rate',
        existing_type=sa.Numeric(5, 4),
        nullable=False
    )
    
    # Renommer base_amount en min_amount
    try:
        op.alter_column('affiliate_commissions', 'base_amount', new_column_name='min_amount')
    except Exception:
        pass
    
    # Supprimer les colonnes de affiliate_commissions
    op.drop_column('affiliate_commissions', 'deposit_id')
    op.drop_column('affiliate_commissions', 'product_type_id')
