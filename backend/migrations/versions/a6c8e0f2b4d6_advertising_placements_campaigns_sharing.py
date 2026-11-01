"""Advertising: controlled placements, CPM campaigns, advertiser credit, contest-entry ad revenue sharing,
AdSense reconciliation and Annual Ads audit records.

Revision ID: a6c8e0f2b4d6
Revises: f3b5d7e9a1c2
Create Date: 2026-11-01

Additive only: new adv_* tables, six chart-of-accounts rows (1240, 2320, 2322, 4020, 4021, 5006), the
advertising_credit product (face value 1.00 USD per unit), one adv_settings row with every money
switch OFF and NO price (pricing pending approval), and the unassigned permission manage_advertising.
The legacy ad_* tables are not touched. Downgrade refuses while any advertising money record exists.
"""
import sqlalchemy as sa
from alembic import op


revision = "a6c8e0f2b4d6"
down_revision = "f3b5d7e9a1c2"
branch_labels = None
depends_on = None

ACCOUNTS = (
    ("1240", "AdSense publisher earnings receivable (finalized, not yet paid by Google)", "1000"),
    ("2320", "Advertiser credit - prepaid, not yet delivered (liability)", "2000"),
    ("2322", "Contest-page ad shares held (nominee not linked / sponsor unresolved)", "2000"),
    ("4020", "Ordinary MyHigh5 advertising revenue (validated delivery)", "4000"),
    ("4021", "Google AdSense revenue (finalized publisher earnings)", "4000"),
    ("5006", "Contest-page advertising revenue share expense (creatives and direct sponsors)", "5000"),
)


def _base(pk=True):
    cols = [sa.Column("id", sa.Integer, primary_key=True)] if pk else []
    return cols + [sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
                   sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now())]


def _user(name, nullable=True):
    return sa.Column(name, sa.Integer, sa.ForeignKey("users.id"), nullable=nullable)


def _journal(name):
    return sa.Column(name, sa.Integer, sa.ForeignKey("journal_entries.id"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "adv_settings", *_base(),
        sa.Column("cpm_rate_usd", sa.Numeric(12, 4)), sa.Column("min_campaign_budget_usd", sa.Numeric(12, 2)),
        sa.Column("min_daily_cap_usd", sa.Numeric(12, 2)),
        sa.Column("campaigns_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("funding_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("adsense_fallback_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("adsense_sharing_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("contest_sharing_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reservation_ttl_seconds", sa.Integer, nullable=False, server_default="900"),
        sa.Column("frequency_cap_per_day", sa.Integer, nullable=False, server_default="20"),
        sa.Column("max_viewable_per_viewer_hour", sa.Integer, nullable=False, server_default="120"),
        _user("updated_by_user_id"),
    )
    op.create_table(
        "adv_campaigns", *_base(),
        _user("advertiser_user_id", nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("pricing_model", sa.String(10), nullable=False, server_default="CPM"),
        sa.Column("cpm_rate_usd", sa.Numeric(12, 4)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("budget_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("spent", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("daily_cap", sa.Numeric(15, 2)),
        sa.Column("start_at", sa.DateTime), sa.Column("end_at", sa.DateTime),
        sa.Column("targeting", sa.JSON), sa.Column("placements", sa.JSON),
        sa.Column("review_note", sa.String(500)), _user("reviewed_by_user_id"),
        sa.Column("completed_at", sa.DateTime), sa.Column("completion_reason", sa.String(40)),
        sa.Column("settled_at", sa.DateTime),
        sa.CheckConstraint("status IN ('DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'PAUSED', 'COMPLETED', 'REJECTED')",
                           name="ck_adv_campaign_status"),
        sa.CheckConstraint("pricing_model = 'CPM'", name="ck_adv_campaign_pricing"),
        sa.CheckConstraint("spent >= 0 AND reserved >= 0 AND spent + reserved <= budget_total",
                           name="ck_adv_campaign_budget"),
    )
    op.create_index("ix_adv_campaign_status", "adv_campaigns", ["status"])
    op.create_table(
        "adv_credit_movements", *_base(),
        _user("advertiser_user_id", nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("adv_campaigns.id")),
        sa.Column("deposit_id", sa.Integer, sa.ForeignKey("deposits.id")),
        _journal("journal_entry_id"),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("note", sa.String(300)), _user("actor_user_id"),
        sa.CheckConstraint("movement_type IN ('DEPOSIT', 'ALLOCATE', 'RELEASE', 'REFUND', 'DEPOSIT_REVERSAL')",
                           name="ck_adv_credit_type"),
        sa.UniqueConstraint("idempotency_key", name="uq_adv_credit_idem"),
    )
    op.create_index("ix_adv_credit_advertiser", "adv_credit_movements", ["advertiser_user_id"])
    op.create_table(
        "adv_campaign_days", *_base(),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("adv_campaigns.id"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("spent", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Numeric(18, 6), nullable=False, server_default="0"),
        _journal("recognized_journal_id"), sa.Column("recognized_at", sa.DateTime),
        sa.UniqueConstraint("campaign_id", "day", name="uq_adv_campaign_day"),
        sa.CheckConstraint("spent >= 0 AND reserved >= 0", name="ck_adv_campaign_day_amounts"),
    )
    op.create_table(
        "adv_creatives", *_base(),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("adv_campaigns.id"), nullable=False),
        sa.Column("headline", sa.String(90), nullable=False), sa.Column("body", sa.String(240)),
        sa.Column("image_url", sa.String(500)), sa.Column("destination_url", sa.String(500), nullable=False),
        sa.Column("review_status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("review_note", sa.String(500)), _user("reviewed_by_user_id"), sa.Column("reviewed_at", sa.DateTime),
        sa.CheckConstraint("review_status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_adv_creative_review"),
    )
    op.create_table(
        "adv_entry_origins", *_base(),
        sa.Column("contestant_id", sa.Integer, sa.ForeignKey("contestants.id"), nullable=False),
        sa.Column("origin_kind", sa.String(20)), sa.Column("status", sa.String(10), nullable=False),
        sa.Column("evidence", sa.JSON), _user("resolved_by_user_id"), sa.Column("resolved_at", sa.DateTime),
        sa.UniqueConstraint("contestant_id", name="uq_adv_entry_origin"),
        sa.CheckConstraint("status IN ('RESOLVED', 'REVIEW')", name="ck_adv_origin_status"),
        sa.CheckConstraint("origin_kind IS NULL OR origin_kind IN ('PERSONAL_SUBMISSION', 'NOMINATION')",
                           name="ck_adv_origin_kind"),
    )
    # A RESOLVED origin is immutable (the original submission type never changes with the contest level).
    op.execute("""
        CREATE OR REPLACE FUNCTION adv_entry_origin_immutable() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'RESOLVED' AND (NEW.origin_kind IS DISTINCT FROM OLD.origin_kind
                                            OR NEW.status IS DISTINCT FROM OLD.status
                                            OR NEW.contestant_id IS DISTINCT FROM OLD.contestant_id) THEN
                RAISE EXCEPTION 'adv_entry_origins: a resolved original submission type cannot change';
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER trg_adv_entry_origin_immutable BEFORE UPDATE ON adv_entry_origins
                  FOR EACH ROW EXECUTE FUNCTION adv_entry_origin_immutable()""")
    op.execute("""CREATE TRIGGER trg_adv_entry_origin_no_delete BEFORE DELETE ON adv_entry_origins
                  FOR EACH ROW WHEN (OLD.status = 'RESOLVED') EXECUTE FUNCTION adv_entry_origin_immutable()""")
    op.create_table(
        "adv_serve_decisions",
        sa.Column("id", sa.String(36), primary_key=True), *_base(pk=False),
        sa.Column("slot_kind", sa.String(12), nullable=False), sa.Column("page_type", sa.String(24), nullable=False),
        sa.Column("slot_key", sa.String(80), nullable=False),
        sa.Column("contestant_id", sa.Integer, sa.ForeignKey("contestants.id")),
        sa.Column("source", sa.String(10), nullable=False), sa.Column("product", sa.String(10), nullable=False),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("adv_campaigns.id")),
        sa.Column("creative_id", sa.Integer, sa.ForeignKey("adv_creatives.id")),
        sa.Column("adsense_slot", sa.String(32)),
        sa.Column("reserved_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("reserved_day", sa.Date), sa.Column("state", sa.String(10), nullable=False),
        sa.Column("viewer_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("source IN ('MYHIGH5', 'ADSENSE')", name="ck_adv_decision_source"),
        sa.CheckConstraint("product IN ('ORDINARY', 'ADSENSE')", name="ck_adv_decision_product"),
        sa.CheckConstraint("state IN ('RESERVED', 'CHARGED', 'RELEASED', 'UNPAID')", name="ck_adv_decision_state"),
    )
    op.create_index("ix_adv_decision_expiry", "adv_serve_decisions", ["state", "expires_at"])
    op.create_index("ix_adv_decision_created", "adv_serve_decisions", ["created_at"])
    op.create_index("ix_adv_decision_frequency", "adv_serve_decisions", ["campaign_id", "viewer_hash", "created_at"])
    op.create_table(
        "adv_impression_events", *_base(),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("decision_id", sa.String(36), sa.ForeignKey("adv_serve_decisions.id"), nullable=False),
        sa.Column("event_type", sa.String(10), nullable=False), sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("visible_ms", sa.Integer), sa.Column("visible_ratio", sa.Numeric(4, 3)),
        sa.Column("page_visible", sa.Boolean), sa.Column("ua_hash", sa.String(64)), sa.Column("viewer_hash", sa.String(64)),
        sa.Column("is_bot_ua", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("validation_status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("invalid_reason", sa.String(40)), sa.Column("validated_at", sa.DateTime),
        sa.Column("earning_day", sa.Date), sa.Column("source", sa.String(10)), sa.Column("product", sa.String(10)),
        sa.Column("adsense_slot", sa.String(32)), sa.Column("campaign_id", sa.Integer),
        sa.Column("charged_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("contestant_id", sa.Integer), sa.Column("origin_kind", sa.String(20)),
        sa.Column("creative_user_id", sa.Integer), sa.Column("sponsor_user_id", sa.Integer),
        sa.Column("sponsor_status", sa.String(12)), sa.Column("contest_level", sa.String(20)),
        sa.Column("season_id", sa.Integer), sa.Column("rule_version", sa.String(40)),
        sa.Column("reversed_at", sa.DateTime), sa.Column("reversal_reason", sa.String(40)),
        sa.UniqueConstraint("event_id", name="uq_adv_event_id"),
        sa.UniqueConstraint("decision_id", "event_type", name="uq_adv_event_decision_type"),
        sa.CheckConstraint("event_type IN ('SERVED', 'VIEWABLE')", name="ck_adv_event_type"),
        sa.CheckConstraint("validation_status IN ('PENDING', 'VALID', 'INVALID')", name="ck_adv_event_validation"),
        sa.CheckConstraint("product IS NULL OR product IN ('ORDINARY', 'ADSENSE')", name="ck_adv_event_product"),
    )
    op.create_index("ix_adv_event_pending", "adv_impression_events", ["validation_status", "received_at"])
    op.create_index("ix_adv_event_day", "adv_impression_events", ["earning_day", "source"])
    op.create_index("ix_adv_event_contestant", "adv_impression_events", ["contestant_id", "earning_day"])
    op.create_index("ix_adv_event_viewer", "adv_impression_events", ["viewer_hash", "validated_at"])
    op.create_index("ix_adv_event_creative", "adv_impression_events", ["creative_user_id"])
    op.create_index("ix_adv_event_sponsor", "adv_impression_events", ["sponsor_user_id"])
    op.create_table(
        "adv_adsense_imports", *_base(),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date), sa.Column("rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("detail", sa.String(500)), _user("actor_user_id"),
    )
    op.create_table(
        "adv_adsense_buckets", *_base(),
        sa.Column("day", sa.Date, nullable=False), sa.Column("ad_unit", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("estimated_earnings", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("finalized_earnings", sa.Numeric(18, 6)), sa.Column("google_impressions", sa.Integer),
        sa.Column("status", sa.String(10), nullable=False, server_default="ESTIMATED"),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("adv_adsense_imports.id")),
        sa.Column("finalized_at", sa.DateTime),
        sa.UniqueConstraint("day", "ad_unit", "currency", name="uq_adv_adsense_bucket"),
        sa.CheckConstraint("status IN ('ESTIMATED', 'FINALIZED')", name="ck_adv_adsense_status"),
    )
    op.create_table(
        "adv_adsense_months", *_base(),
        sa.Column("period", sa.String(7), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("finalized_total", sa.Numeric(15, 2), nullable=False),
        sa.Column("estimated_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        _journal("journal_entry_id"), _user("recorded_by_user_id"), sa.Column("evidence_note", sa.String(500)),
        sa.UniqueConstraint("period", "currency", name="uq_adv_adsense_month"),
    )
    op.create_table(
        "adv_allocations", *_base(),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("contestant_id", sa.Integer, sa.ForeignKey("contestants.id"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False), sa.Column("source", sa.String(10), nullable=False),
        sa.Column("product", sa.String(10), nullable=False), sa.Column("origin_kind", sa.String(20)),
        sa.Column("contest_level", sa.String(20)), sa.Column("season_key", sa.Integer, nullable=False, server_default="0"),
        _user("beneficiary_user_id"), sa.Column("beneficiary_key", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rate", sa.Numeric(6, 4), nullable=False), sa.Column("base_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("valid_impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rule_version", sa.String(40), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("commission_id", sa.Integer, sa.ForeignKey("affiliate_commissions.id")),
        _journal("hold_journal_id"), sa.Column("released_at", sa.DateTime), sa.Column("reversed_at", sa.DateTime),
        sa.Column("note", sa.String(300)),
        sa.UniqueConstraint("period", "contestant_id", "role", "source", "season_key", "beneficiary_key", "version",
                            name="uq_adv_allocation_line"),
        sa.CheckConstraint("role IN ('CREATIVE', 'SPONSOR')", name="ck_adv_alloc_role"),
        sa.CheckConstraint("product IN ('ORDINARY', 'ADSENSE')", name="ck_adv_alloc_product"),
        sa.CheckConstraint("status IN ('ESTIMATED', 'HELD_UNCLAIMED', 'HELD_SPONSOR', 'HELD_REVIEW', 'RELEASED', "
                           "'REVERSED', 'SUPERSEDED')", name="ck_adv_alloc_status"),
        sa.CheckConstraint("amount >= 0 AND amount <= base_amount", name="ck_adv_alloc_amount"),
        sa.CheckConstraint("rate >= 0 AND rate <= 0.20", name="ck_adv_alloc_rate"),
    )
    op.create_index("ix_adv_alloc_beneficiary", "adv_allocations", ["beneficiary_user_id", "status"])
    op.create_index("ix_adv_alloc_period", "adv_allocations", ["period", "status"])
    op.create_table(
        "adv_annualads_payments", *_base(),
        sa.Column("tx_hash", sa.String(255), nullable=False), sa.Column("event", sa.String(100), nullable=False),
        sa.Column("buyer_reference", sa.String(64)), _user("buyer_user_id"),
        sa.Column("buyer_match", sa.String(10), nullable=False),
        sa.Column("gross_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("platform_fee", sa.Numeric(15, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("entitlement_snapshot", sa.JSON), _journal("journal_entry_id"),
        sa.Column("sponsor_commission_status", sa.String(20), nullable=False, server_default="PENDING_POLICY"),
        sa.Column("raw_payload_sha256", sa.String(64)), sa.Column("note", sa.Text),
        sa.UniqueConstraint("tx_hash", name="uq_adv_annualads_tx"),
        sa.CheckConstraint("buyer_match IN ('MATCHED', 'UNMATCHED', 'ABSENT')", name="ck_adv_annualads_buyer"),
    )

    # One settings row: no price (pending approval), every money switch off; AdSense fallback on in the
    # new placements (AdSense is already live on the site; no revenue sharing).
    op.execute("INSERT INTO adv_settings (created_at, updated_at) VALUES (now(), now())")

    for code, name, parent in ACCOUNTS:
        op.execute(sa.text("""
            INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_id, balance,
                                           description, is_active, created_at, updated_at)
            SELECT :code, :name, p.account_type, p.id, 0, :name, true, now(), now()
            FROM chart_of_accounts p
            WHERE p.account_code = :parent
              AND NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = :code)
        """).bindparams(code=code, name=name, parent=parent))

    op.execute("""
        INSERT INTO product_types (code, name, description, price, currency, validity_days, is_active,
                                   is_consumable, has_affiliate_commission, created_at, updated_at)
        SELECT 'advertising_credit', 'MyHigh5 advertiser credit',
               'Prepaid advertiser credit (USD, face value). Spent only on validated, viewable impressions.',
               1.00, 'USD', 0, true, false, false, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM product_types WHERE code = 'advertising_credit')""")

    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL THEN
                INSERT INTO permissions (name, description, category, created_at, updated_at)
                SELECT 'manage_advertising',
                       'Manage advertising prices, campaign review, AdSense reconciliation and ad revenue sharing',
                       'admin', now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'manage_advertising');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_credit_movements) OR EXISTS (SELECT 1 FROM adv_allocations)
               OR EXISTS (SELECT 1 FROM adv_adsense_months) OR EXISTS (SELECT 1 FROM adv_annualads_payments)
               OR EXISTS (SELECT 1 FROM adv_impression_events WHERE charged_amount > 0) THEN
                RAISE EXCEPTION 'Advertising money records exist: export them before downgrading a6c8e0f2b4d6';
            END IF;
        END $$;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_adv_entry_origin_no_delete ON adv_entry_origins")
    op.execute("DROP TRIGGER IF EXISTS trg_adv_entry_origin_immutable ON adv_entry_origins")
    op.execute("DROP FUNCTION IF EXISTS adv_entry_origin_immutable()")
    for table in ("adv_annualads_payments", "adv_allocations", "adv_adsense_months", "adv_adsense_buckets",
                  "adv_adsense_imports", "adv_impression_events", "adv_serve_decisions", "adv_entry_origins",
                  "adv_creatives", "adv_campaign_days", "adv_credit_movements", "adv_campaigns", "adv_settings"):
        op.drop_table(table)
    op.execute("""DELETE FROM product_types p WHERE p.code = 'advertising_credit'
                  AND NOT EXISTS (SELECT 1 FROM deposits d WHERE d.product_type_id = p.id)""")
    for code, _name, _parent in ACCOUNTS:
        op.execute(sa.text("""DELETE FROM chart_of_accounts c WHERE c.account_code = :code
                              AND NOT EXISTS (SELECT 1 FROM journal_lines l WHERE l.account_id = c.id)""")
                   .bindparams(code=code))
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL AND to_regclass('public.role_permissions') IS NOT NULL THEN
                DELETE FROM permissions p WHERE p.name = 'manage_advertising'
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
            END IF;
        END $$""")
