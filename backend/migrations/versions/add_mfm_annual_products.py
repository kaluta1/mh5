"""Add MFM and Annual Membership product types

Revision ID: add_mfm_annual_products
Revises: fix_base_amount_column
Create Date: 2024-12-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_mfm_annual_prods'
down_revision = 'fix_base_amount_column'
branch_labels = None
depends_on = None


def upgrade():
    """Add MFM and Annual Membership product types"""
    conn = op.get_bind()
    
    # Check if product_types table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'product_types'
        )
    """))
    table_exists = result.fetchone()[0]
    
    if not table_exists:
        return
    
    # Check if MFM product exists
    result = conn.execute(sa.text(
        "SELECT id FROM product_types WHERE code = 'mfm_membership'"
    ))
    mfm_exists = result.fetchone() is not None
    
    if not mfm_exists:
        conn.execute(sa.text("""
            INSERT INTO product_types (code, name, description, base_price, currency, validity_days, is_active, has_affiliate_commission, affiliate_direct_amount, affiliate_indirect_amount)
            VALUES (
                'mfm_membership', 
                'MFM (Founding Member)', 
                'Become a MyHigh5 Founding Member. Access to monthly revenue pool (10%) and annual profit pool (20%). Receive random referrals.',
                100.00, 
                'USD', 
                3650, 
                true,
                true,
                20.00,
                2.00
            )
        """))
    
    # Check if annual membership product exists
    result = conn.execute(sa.text(
        "SELECT id FROM product_types WHERE code = 'annual_membership'"
    ))
    annual_exists = result.fetchone() is not None
    
    if not annual_exists:
        conn.execute(sa.text("""
            INSERT INTO product_types (code, name, description, base_price, currency, validity_days, is_active, has_affiliate_commission, affiliate_direct_amount, affiliate_indirect_amount)
            VALUES (
                'annual_membership', 
                'Annual Membership', 
                'Annual membership fee to maintain Founding Member status. Required to keep access to FM benefits.',
                50.00, 
                'USD', 
                365, 
                true,
                true,
                10.00,
                1.00
            )
        """))
    
    # Update KYC product with affiliate commission info
    conn.execute(sa.text("""
        UPDATE product_types 
        SET has_affiliate_commission = true,
            affiliate_direct_amount = 2.00,
            affiliate_indirect_amount = 0.20
        WHERE code = 'kyc' AND has_affiliate_commission IS NOT TRUE
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM product_types WHERE code = 'mfm_membership'"))
    conn.execute(sa.text("DELETE FROM product_types WHERE code = 'annual_membership'"))
