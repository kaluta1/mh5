"""Fix base_amount column in affiliate_commissions

Revision ID: fix_base_amount_column
Revises: aff_comm_product_type
Create Date: 2024-12-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_base_amount_column'
down_revision = 'aff_comm_product_type'
branch_labels = None
depends_on = None


def upgrade():
    # Vérifier et ajouter base_amount si elle n'existe pas
    conn = op.get_bind()
    
    # Vérifier si la colonne base_amount existe
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'affiliate_commissions' AND column_name = 'base_amount'
    """))
    base_amount_exists = result.fetchone() is not None
    
    # Vérifier si la colonne min_amount existe
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'affiliate_commissions' AND column_name = 'min_amount'
    """))
    min_amount_exists = result.fetchone() is not None
    
    if min_amount_exists and not base_amount_exists:
        # Renommer min_amount en base_amount
        op.alter_column('affiliate_commissions', 'min_amount', new_column_name='base_amount')
    elif not base_amount_exists:
        # Ajouter base_amount si elle n'existe pas
        op.add_column('affiliate_commissions',
            sa.Column('base_amount', sa.Numeric(10, 2), nullable=True)
        )


def downgrade():
    pass  # Ne rien faire au downgrade
