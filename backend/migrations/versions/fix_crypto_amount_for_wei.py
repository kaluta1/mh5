"""Fix crypto_amount column to store wei amounts as string

Revision ID: fix_crypto_amount_wei
Revises: bb2015d76c4b
Create Date: 2025-01-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'fix_crypto_amount_wei'
down_revision = 'bb2015d76c4b'  # Depends on merge migration
branch_labels = None
depends_on = None


def upgrade():
    # Change crypto_amount from Numeric(18, 8) to String/Text to store wei amounts
    # Wei amounts can be very large (e.g., 10000000000000000000 for 10 USDT)
    # and need to be stored as strings to avoid precision loss
    
    # Change column type to String using USING clause for type conversion
    op.execute("""
        ALTER TABLE deposits 
        ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
        USING CASE 
            WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
            ELSE NULL
        END
    """)


def downgrade():
    # Convert back to Numeric (may lose precision for large wei amounts)
    # Note: This will fail for wei amounts larger than NUMERIC(18,8) can handle
    op.execute("""
        ALTER TABLE deposits 
        ALTER COLUMN crypto_amount TYPE NUMERIC(18, 8) 
        USING CASE 
            WHEN crypto_amount IS NOT NULL AND crypto_amount ~ '^[0-9]+\\\\.?[0-9]*$' 
            THEN crypto_amount::numeric
            ELSE NULL
        END
    """)
