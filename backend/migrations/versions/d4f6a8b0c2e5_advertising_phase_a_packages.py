"""Advertising Phase A: eight-package foundation, package-aware events, daily bookings, lead foundation.

Revision ID: d4f6a8b0c2e5
Revises: c2e4a6b8d0f1
Create Date: 2026-11-04

Additive only. Nothing is backfilled, priced, activated or recalculated; every new package stays OFF.
  * adv_settings.enabled_packages (JSON, NULL = none switched on besides Standard CPM).
  * adv_settings.daily_city_min_impressions (NULL = not determined: Daily City cannot be switched on).
  * adv_campaigns: pricing_model check widened to the 8 models; nullable unit_rate_usd NUMERIC(18,6).
  * adv_creatives: nullable creative_format and video_* columns (no upload path is exposed).
  * adv_serve_decisions: nullable package, viewer_user_id, viewer_city_id.
  * adv_impression_events: event_type check widened (VIDEO_2S, VIDEO_VIEW, CLICK); nullable played_ms,
    action, package.
  * adv_bookings: Daily City / Daily Local booked days (settled once).
  * adv_bookings.min_impressions: the delivery threshold in force when the day was booked.
  * adv_leads: lead lifecycle WITHOUT personal data (keyed contact hash only); unanswered leads EXPIRE unbilled.
Downgrade refuses while any Phase A data exists (a non-CPM campaign, a new event type, a booking or a lead),
so nothing recorded under Phase A can be lost by downgrading.
"""
import sqlalchemy as sa
from alembic import op

revision = "d4f6a8b0c2e5"
down_revision = "c2e4a6b8d0f1"
branch_labels = None
depends_on = None

MODELS = "('CPM', 'CPM_VIDEO', 'CPC', 'CPV', 'ENGAGEMENT', 'LEAD', 'DAILY_LOCAL', 'DAILY_CITY')"
EVENTS = "('SERVED', 'VIEWABLE', 'VIDEO_2S', 'VIDEO_VIEW', 'CLICK')"


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.add_column("adv_settings", sa.Column("enabled_packages", sa.JSON(), nullable=True))
    op.add_column("adv_settings", sa.Column("daily_city_min_impressions", sa.Integer(), nullable=True))

    op.execute("ALTER TABLE adv_campaigns DROP CONSTRAINT IF EXISTS ck_adv_campaign_pricing")
    op.execute(f"ALTER TABLE adv_campaigns ADD CONSTRAINT ck_adv_campaign_pricing CHECK (pricing_model IN {MODELS})")
    op.add_column("adv_campaigns", sa.Column("unit_rate_usd", sa.Numeric(18, 6), nullable=True))

    for name, kind in (("creative_format", sa.String(10)), ("video_url", sa.String(500)), ("video_mime", sa.String(40)),
                       ("video_bytes", sa.Integer()), ("video_duration_ms", sa.Integer())):
        op.add_column("adv_creatives", sa.Column(name, kind, nullable=True))

    for name, kind in (("package", sa.String(20)), ("viewer_user_id", sa.Integer()), ("viewer_city_id", sa.Integer())):
        op.add_column("adv_serve_decisions", sa.Column(name, kind, nullable=True))

    op.execute("ALTER TABLE adv_impression_events DROP CONSTRAINT IF EXISTS ck_adv_event_type")
    op.execute(f"ALTER TABLE adv_impression_events ADD CONSTRAINT ck_adv_event_type CHECK (event_type IN {EVENTS})")
    for name, kind in (("played_ms", sa.Integer()), ("action", sa.String(20)), ("package", sa.String(20))):
        op.add_column("adv_impression_events", sa.Column(name, kind, nullable=True))

    op.create_table(
        "adv_bookings", *_base(),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("adv_campaigns.id"), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="BOOKED"),
        sa.Column("min_impressions", sa.Integer(), nullable=False),
        sa.Column("valid_impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entry_impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("charged_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("campaign_id", "scope", "area_id", "day", name="uq_adv_booking"),
        sa.CheckConstraint("scope IN ('CITY', 'LOCAL')", name="ck_adv_booking_scope"),
        sa.CheckConstraint("status IN ('BOOKED', 'EARNED', 'RETURNED', 'CANCELLED')", name="ck_adv_booking_status"),
        sa.CheckConstraint("price > 0", name="ck_adv_booking_price"),
        sa.CheckConstraint("min_impressions >= 1", name="ck_adv_booking_min_impressions"),
    )
    op.create_index("ix_adv_booking_settle", "adv_bookings", ["status", "day"])
    op.create_index("ix_adv_bookings_id", "adv_bookings", ["id"])

    op.create_table(
        "adv_leads", *_base(),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("adv_campaigns.id"), nullable=False),
        sa.Column("decision_id", sa.String(36), sa.ForeignKey("adv_serve_decisions.id"), nullable=True),
        sa.Column("contact_hash", sa.String(64), nullable=False),
        sa.Column("consent_version", sa.String(40), nullable=False),
        sa.Column("consented_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="SUBMITTED"),
        sa.Column("decision_deadline", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.String(40), nullable=True),
        sa.Column("charged_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("charge_day", sa.Date(), nullable=True),
        sa.UniqueConstraint("campaign_id", "contact_hash", name="uq_adv_lead_contact"),
        sa.CheckConstraint("status IN ('SUBMITTED', 'ACCEPTED', 'REJECTED', 'EXPIRED')", name="ck_adv_lead_status"),
    )
    op.create_index("ix_adv_lead_campaign", "adv_leads", ["campaign_id", "status"])
    op.create_index("ix_adv_leads_id", "adv_leads", ["id"])


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_bookings) OR EXISTS (SELECT 1 FROM adv_leads)
               OR EXISTS (SELECT 1 FROM adv_campaigns WHERE pricing_model <> 'CPM' OR unit_rate_usd IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_impression_events WHERE event_type NOT IN ('SERVED', 'VIEWABLE'))
               OR EXISTS (SELECT 1 FROM adv_creatives WHERE creative_format IS NOT NULL OR video_url IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_settings WHERE daily_city_min_impressions IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_settings WHERE enabled_packages IS NOT NULL
                          AND enabled_packages::text NOT IN ('null', '[]')) THEN
                RAISE EXCEPTION 'Advertising Phase A data exists: it cannot be dropped by downgrading d4f6a8b0c2e5';
            END IF;
        END $$;
    """)
    op.drop_index("ix_adv_leads_id", table_name="adv_leads")
    op.drop_index("ix_adv_lead_campaign", table_name="adv_leads")
    op.drop_table("adv_leads")
    op.drop_index("ix_adv_bookings_id", table_name="adv_bookings")
    op.drop_index("ix_adv_booking_settle", table_name="adv_bookings")
    op.drop_table("adv_bookings")
    for name in ("package", "action", "played_ms"):
        op.drop_column("adv_impression_events", name)
    op.execute("ALTER TABLE adv_impression_events DROP CONSTRAINT IF EXISTS ck_adv_event_type")
    op.execute("ALTER TABLE adv_impression_events ADD CONSTRAINT ck_adv_event_type "
               "CHECK (event_type IN ('SERVED', 'VIEWABLE'))")
    for name in ("viewer_city_id", "viewer_user_id", "package"):
        op.drop_column("adv_serve_decisions", name)
    for name in ("video_duration_ms", "video_bytes", "video_mime", "video_url", "creative_format"):
        op.drop_column("adv_creatives", name)
    op.drop_column("adv_campaigns", "unit_rate_usd")
    op.execute("ALTER TABLE adv_campaigns DROP CONSTRAINT IF EXISTS ck_adv_campaign_pricing")
    op.execute("ALTER TABLE adv_campaigns ADD CONSTRAINT ck_adv_campaign_pricing CHECK (pricing_model = 'CPM')")
    op.drop_column("adv_settings", "daily_city_min_impressions")
    op.drop_column("adv_settings", "enabled_packages")
