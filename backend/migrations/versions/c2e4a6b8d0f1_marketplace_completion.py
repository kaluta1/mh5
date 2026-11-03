"""Marketplace completion (Prompt 7): listing category/condition, moderation states and history, listing
images, checkout idempotency reference, buyer support requests.

Revision ID: c2e4a6b8d0f1
Revises: a8d0f2b4c6e9
Create Date: 2026-11-03

Additive only:
  * market_listings: nullable category, item_condition, moderation_note; the status check also allows
    SUSPENDED (administrator) and ARCHIVED (seller). No existing listing changes status.
  * market_listing_events: append-only listing status / moderation history.
  * market_listing_images: listing photos (private storage key, re-encoded on upload).
  * market_orders: nullable client_reference, unique per buyer (a repeated checkout returns the same order).
  * market_order_requests: buyer cancellation / refund requests for support review (no money moves).
Nothing is backfilled, published, approved or recalculated.
"""
import sqlalchemy as sa
from alembic import op

revision = "c2e4a6b8d0f1"
down_revision = "a8d0f2b4c6e9"
branch_labels = None
depends_on = None


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.execute("ALTER TABLE market_listings ADD COLUMN IF NOT EXISTS category VARCHAR(40) NULL")
    op.execute("ALTER TABLE market_listings ADD COLUMN IF NOT EXISTS item_condition VARCHAR(20) NULL")
    op.execute("ALTER TABLE market_listings ADD COLUMN IF NOT EXISTS moderation_note VARCHAR(500) NULL")
    op.execute("ALTER TABLE market_listings DROP CONSTRAINT IF EXISTS ck_market_listings_status")
    op.execute("ALTER TABLE market_listings ADD CONSTRAINT ck_market_listings_status "
               "CHECK (status IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED', 'SUSPENDED', 'ARCHIVED'))")
    op.execute("ALTER TABLE market_listings ADD CONSTRAINT ck_market_listings_condition "
               "CHECK (item_condition IS NULL OR item_condition IN ('NEW', 'USED', 'REFURBISHED'))")
    op.execute("ALTER TABLE market_orders ADD COLUMN IF NOT EXISTS client_reference VARCHAR(64) NULL")
    op.create_unique_constraint("uq_market_orders_buyer_client_ref", "market_orders",
                                ["buyer_user_id", "client_reference"])

    op.create_table(
        "market_listing_events", *_base(),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("market_listings.id"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
    )
    op.create_index("ix_market_listing_events_id", "market_listing_events", ["id"])
    op.create_index("ix_market_listing_events_listing", "market_listing_events", ["listing_id"])

    op.create_table(
        "market_listing_images", *_base(),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("market_listings.id"), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_market_listing_images_id", "market_listing_images", ["id"])
    op.create_index("ix_market_listing_images_listing", "market_listing_images", ["listing_id"])

    op.create_table(
        "market_order_requests", *_base(),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("market_orders.id"), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="OPEN"),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_note", sa.String(2000), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("kind IN ('CANCELLATION', 'REFUND')", name="ck_market_order_request_kind"),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_market_order_request_status"),
        sa.CheckConstraint("resolution IS NULL OR resolution IN ('REFUNDED', 'DECLINED', 'WITHDRAWN')",
                           name="ck_market_order_request_resolution"),
    )
    op.create_index("ix_market_order_requests_id", "market_order_requests", ["id"])
    op.create_index("ix_market_order_requests_order", "market_order_requests", ["order_id"])
    # At most one open request per order (PostgreSQL partial unique index).
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_market_order_requests_open ON market_order_requests (order_id) "
               "WHERE status = 'OPEN'")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM market_listing_events) OR EXISTS (SELECT 1 FROM market_listing_images)
               OR EXISTS (SELECT 1 FROM market_order_requests)
               OR EXISTS (SELECT 1 FROM market_listings WHERE status IN ('SUSPENDED', 'ARCHIVED')
                          OR category IS NOT NULL OR item_condition IS NOT NULL OR moderation_note IS NOT NULL)
               OR EXISTS (SELECT 1 FROM market_orders WHERE client_reference IS NOT NULL) THEN
                RAISE EXCEPTION 'Marketplace completion data exists: it cannot be dropped by downgrading c2e4a6b8d0f1';
            END IF;
        END $$;
    """)
    op.execute("DROP INDEX IF EXISTS uq_market_order_requests_open")
    op.drop_index("ix_market_order_requests_order", table_name="market_order_requests")
    op.drop_index("ix_market_order_requests_id", table_name="market_order_requests")
    op.drop_table("market_order_requests")
    op.drop_index("ix_market_listing_images_listing", table_name="market_listing_images")
    op.drop_index("ix_market_listing_images_id", table_name="market_listing_images")
    op.drop_table("market_listing_images")
    op.drop_index("ix_market_listing_events_listing", table_name="market_listing_events")
    op.drop_index("ix_market_listing_events_id", table_name="market_listing_events")
    op.drop_table("market_listing_events")
    op.drop_constraint("uq_market_orders_buyer_client_ref", "market_orders", type_="unique")
    op.execute("ALTER TABLE market_orders DROP COLUMN IF EXISTS client_reference")
    op.execute("ALTER TABLE market_listings DROP CONSTRAINT IF EXISTS ck_market_listings_condition")
    op.execute("ALTER TABLE market_listings DROP CONSTRAINT IF EXISTS ck_market_listings_status")
    op.execute("ALTER TABLE market_listings ADD CONSTRAINT ck_market_listings_status "
               "CHECK (status IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED'))")
    for column in ("moderation_note", "item_condition", "category"):
        op.execute(f"ALTER TABLE market_listings DROP COLUMN IF EXISTS {column}")
