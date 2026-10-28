"""Marketplace: member listings (physical, service, digital) with warranty/insurance disclosures,
the listing snapshot on an order and the digital delivery time.

Revision ID: a7c9e1b3d5f7
Revises: f4b6d8a0c2e4
Create Date: 2026-10-29

Additive (production holds no marketplace order or listing): one new table and two nullable columns
on market_orders; no row rewritten.

  * market_listings                     seller listings; price_usd is the seller base
  * market_orders.listing_snapshot      what the buyer was shown when ordering (kept as it was)
  * market_orders.digital_delivered_at  the buyer's first complete download of a digital listing

Downgrade refuses while a listing or a listing order exists.
"""
from alembic import op


revision = "a7c9e1b3d5f7"
down_revision = "f4b6d8a0c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_listings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            seller_user_id INTEGER NOT NULL REFERENCES users(id),
            kind VARCHAR(20) NOT NULL,
            title VARCHAR(160) NOT NULL,
            description TEXT NOT NULL,
            price_usd NUMERIC(15, 2) NOT NULL,
            quantity_available INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            handover_details TEXT,
            warranty_available BOOLEAN NOT NULL DEFAULT false,
            warranty_terms TEXT,
            insurance_available BOOLEAN NOT NULL DEFAULT false,
            insurance_terms TEXT,
            file_storage_key VARCHAR(80) UNIQUE,
            file_name VARCHAR(200),
            file_content_type VARCHAR(100),
            file_size BIGINT,
            file_sha256 VARCHAR(64),
            published_at TIMESTAMP,
            CONSTRAINT ck_market_listings_kind CHECK (kind IN ('PHYSICAL', 'SERVICE', 'DIGITAL')),
            CONSTRAINT ck_market_listings_status CHECK (status IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED')),
            CONSTRAINT ck_market_listings_price CHECK (price_usd > 0),
            CONSTRAINT ck_market_listings_quantity CHECK (quantity_available IS NULL OR quantity_available >= 0)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_listings_id ON market_listings (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_listings_seller_user_id ON market_listings (seller_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_listings_status_published ON market_listings (status, published_at)")
    op.execute("ALTER TABLE market_orders ADD COLUMN IF NOT EXISTS listing_snapshot JSON")
    op.execute("ALTER TABLE market_orders ADD COLUMN IF NOT EXISTS digital_delivered_at TIMESTAMP")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM market_listings) OR EXISTS (SELECT 1 FROM market_orders WHERE item_type = 'listing') THEN
                RAISE EXCEPTION 'marketplace listings or listing orders exist; downgrade refused';
            END IF;
        END $$""")
    op.execute("ALTER TABLE market_orders DROP COLUMN IF EXISTS digital_delivered_at")
    op.execute("ALTER TABLE market_orders DROP COLUMN IF EXISTS listing_snapshot")
    op.execute("DROP TABLE IF EXISTS market_listings")
