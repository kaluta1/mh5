"""Advertising final integration (owner-approved decisions, 2026-11-05).

Revision ID: a2c4e6f8b0d3
Revises: f1a3c5e7b9d2
Create Date: 2026-11-05

Additive only. Nothing is backfilled; existing campaigns, commissions, balances and earnings are unchanged.
  * adv_campaign_days: sponsor_base_amount, sponsor_reversed_amount, sponsor_offset_amount (recovery inputs).
  * adv_sponsor_adjustments / adv_sponsor_receivables / adv_sponsor_offsets: automated advertiser-sponsor
    commission recovery (immutable adjustments, receivables offset against the same sponsor's later
    advertiser-sponsor commissions, one offset per receivable and day).
  * adv_fixed_allocations: fixed-price (Daily Local / Daily City) earned revenue per delivering placement;
    adv_impression_events.allocated_amount: each event's share of it (feeds contest-entry sharing).
  * adv_leads: encrypted contact details, advertiser identity, privacy notice, deletion / purge timestamps;
    adv_lead_access_log.
  * adv_geo_attestations: country, local area (NULL until verified areas exist), evidence source, status
    (ATTESTED / VERIFIED / REJECTED) and administrator review.
Downgrade refuses while any new data exists.
"""
import sqlalchemy as sa
from alembic import op

revision = "a2c4e6f8b0d3"
down_revision = "f1a3c5e7b9d2"
branch_labels = None
depends_on = None


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.add_column("adv_campaign_days", sa.Column("sponsor_base_amount", sa.Numeric(15, 2), nullable=True))
    op.add_column("adv_campaign_days", sa.Column("sponsor_reversed_amount", sa.Numeric(15, 2), nullable=False,
                                                 server_default="0"))
    op.add_column("adv_campaign_days", sa.Column("sponsor_offset_amount", sa.Numeric(15, 2), nullable=False,
                                                 server_default="0"))

    op.create_table(
        "adv_sponsor_adjustments", *_base(),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("campaign_day_id", sa.Integer(), sa.ForeignKey("adv_campaign_days.id"), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("sponsor_user_id", sa.Integer(), nullable=True),
        sa.Column("original_commission_id", sa.Integer(), nullable=True),
        sa.Column("replacement_commission_id", sa.Integer(), nullable=True),
        sa.Column("reversed_revenue", sa.Numeric(15, 2), nullable=False),
        sa.Column("base_before", sa.Numeric(15, 2), nullable=False),
        sa.Column("base_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("entitlement_before", sa.Numeric(15, 2), nullable=False),
        sa.Column("entitlement_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("reduction", sa.Numeric(15, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_adv_sponsor_adjustment_key"),
        sa.CheckConstraint("method IN ('NONE', 'CANCELLED', 'REISSUED', 'RECEIVABLE', 'MISSED_ADJUSTED', "
                           "'FINANCE_REVIEW')", name="ck_adv_sponsor_adjustment_method"),
        sa.CheckConstraint("reduction >= 0 AND reversed_revenue >= 0", name="ck_adv_sponsor_adjustment_amounts"),
    )
    op.create_index("ix_adv_sponsor_adjustment_day", "adv_sponsor_adjustments", ["campaign_day_id"])

    op.create_table(
        "adv_sponsor_receivables", *_base(),
        sa.Column("sponsor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("adjustment_id", sa.Integer(), sa.ForeignKey("adv_sponsor_adjustments.id"), nullable=False),
        sa.Column("campaign_day_id", sa.Integer(), nullable=False),
        sa.Column("original_commission_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("recovered", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.UniqueConstraint("adjustment_id", name="uq_adv_sponsor_receivable_adjustment"),
        sa.CheckConstraint("amount > 0 AND recovered >= 0 AND recovered <= amount",
                           name="ck_adv_sponsor_receivable_amounts"),
        sa.CheckConstraint("status IN ('OPEN', 'RECOVERED', 'FINANCE_REVIEW', 'WRITTEN_OFF')",
                           name="ck_adv_sponsor_receivable_status"),
    )
    op.create_index("ix_adv_sponsor_receivable_open", "adv_sponsor_receivables", ["sponsor_user_id", "status"])

    op.create_table(
        "adv_sponsor_offsets", *_base(),
        sa.Column("receivable_id", sa.Integer(), sa.ForeignKey("adv_sponsor_receivables.id"), nullable=False),
        sa.Column("campaign_day_id", sa.Integer(), sa.ForeignKey("adv_campaign_days.id"), nullable=False),
        sa.Column("sponsor_user_id", sa.Integer(), nullable=False),
        sa.Column("gross_commission_id", sa.Integer(), nullable=True),
        sa.Column("net_commission_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("journal_entry_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("receivable_id", "campaign_day_id", name="uq_adv_sponsor_offset"),
        sa.CheckConstraint("amount > 0", name="ck_adv_sponsor_offset_amount"),
    )

    op.create_table(
        "adv_fixed_allocations", *_base(),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("adv_bookings.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot_kind", sa.String(12), nullable=False),
        sa.Column("page_type", sa.String(24), nullable=False),
        sa.Column("contestant_key", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("booking_id", "version", "slot_kind", "page_type", "contestant_key",
                            name="uq_adv_fixed_allocation"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_adv_fixed_allocation_status"),
        sa.CheckConstraint("weight > 0 AND amount >= 0", name="ck_adv_fixed_allocation_amounts"),
    )
    op.create_index("ix_adv_fixed_allocation_day", "adv_fixed_allocations", ["campaign_id", "day"])
    op.add_column("adv_impression_events", sa.Column("allocated_amount", sa.Numeric(18, 6), nullable=False,
                                                     server_default="0"))

    for col in (sa.Column("pii_ciphertext", sa.Text(), nullable=True),
                sa.Column("advertiser_identity", sa.String(120), nullable=True),
                sa.Column("privacy_notice_version", sa.String(40), nullable=True),
                sa.Column("deletion_requested_at", sa.DateTime(), nullable=True),
                sa.Column("pii_purged_at", sa.DateTime(), nullable=True)):
        op.add_column("adv_leads", col)
    op.create_table(
        "adv_lead_access_log", *_base(),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("adv_leads.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
    )
    op.create_index("ix_adv_lead_access_lead", "adv_lead_access_log", ["lead_id"])

    for col in (sa.Column("country_id", sa.Integer(), nullable=True),
                sa.Column("local_area_id", sa.Integer(), nullable=True),
                sa.Column("evidence_source", sa.String(40), nullable=False,
                          server_default="KYC_ADDRESS_DECLARED_CITY"),
                sa.Column("status", sa.String(16), nullable=False, server_default="ATTESTED"),
                sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
                sa.Column("reviewed_at", sa.DateTime(), nullable=True),
                sa.Column("review_note", sa.String(300), nullable=True)):
        op.add_column("adv_geo_attestations", col)
    op.create_check_constraint("ck_adv_geo_attestation_status", "adv_geo_attestations",
                               "status IN ('ATTESTED', 'VERIFIED', 'REJECTED')")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_sponsor_adjustments) OR EXISTS (SELECT 1 FROM adv_fixed_allocations)
               OR EXISTS (SELECT 1 FROM adv_lead_access_log)
               OR EXISTS (SELECT 1 FROM adv_impression_events WHERE allocated_amount <> 0)
               OR EXISTS (SELECT 1 FROM adv_leads WHERE pii_ciphertext IS NOT NULL OR pii_purged_at IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_geo_attestations WHERE status <> 'ATTESTED' OR reviewed_at IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_campaign_days WHERE sponsor_base_amount IS NOT NULL
                            OR sponsor_reversed_amount <> 0 OR sponsor_offset_amount <> 0) THEN
                RAISE EXCEPTION 'Advertising final-integration data exists: it cannot be dropped by downgrading a2c4e6f8b0d3';
            END IF;
        END $$;
    """)
    op.drop_constraint("ck_adv_geo_attestation_status", "adv_geo_attestations", type_="check")
    for name in ("review_note", "reviewed_at", "reviewed_by_user_id", "status", "evidence_source", "local_area_id",
                 "country_id"):
        op.drop_column("adv_geo_attestations", name)
    op.drop_index("ix_adv_lead_access_lead", table_name="adv_lead_access_log")
    op.drop_table("adv_lead_access_log")
    for name in ("pii_purged_at", "deletion_requested_at", "privacy_notice_version", "advertiser_identity",
                 "pii_ciphertext"):
        op.drop_column("adv_leads", name)
    op.drop_column("adv_impression_events", "allocated_amount")
    op.drop_index("ix_adv_fixed_allocation_day", table_name="adv_fixed_allocations")
    op.drop_table("adv_fixed_allocations")
    op.drop_table("adv_sponsor_offsets")
    op.drop_index("ix_adv_sponsor_receivable_open", table_name="adv_sponsor_receivables")
    op.drop_table("adv_sponsor_receivables")
    op.drop_index("ix_adv_sponsor_adjustment_day", table_name="adv_sponsor_adjustments")
    op.drop_table("adv_sponsor_adjustments")
    for name in ("sponsor_offset_amount", "sponsor_reversed_amount", "sponsor_base_amount"):
        op.drop_column("adv_campaign_days", name)
