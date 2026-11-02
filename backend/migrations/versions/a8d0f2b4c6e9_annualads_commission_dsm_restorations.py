"""Annual Ads sponsor commission and refund evidence, provider event log, DSM sponsor restoration log (Prompt 6).

Revision ID: a8d0f2b4c6e9
Revises: f6b8d0a2c4e7
Create Date: 2026-11-03

Additive only:
  * adv_annualads_payments: nullable columns recording the direct-sponsor commission decision (sponsor, rate,
    rule version and qualification evidence, commission id/amount) and the refund state of the payment;
  * adv_annualads_events: one row per signed Annual Ads webhook delivery processed (idempotency + outcome);
  * dsm_sponsor_restorations: one row per administrator-approved restoration of a DSM sponsor link.
No existing row changes; nothing is backfilled; no sponsor relationship is modified.
"""
import sqlalchemy as sa
from alembic import op

revision = "a8d0f2b4c6e9"
down_revision = "f6b8d0a2c4e7"
branch_labels = None
depends_on = None

PAYMENT_COLUMNS = (
    ("sponsor_user_id", "INTEGER"), ("sponsor_rate", "NUMERIC(6,4)"), ("sponsor_rule_version", "VARCHAR(60)"),
    ("sponsor_commission_id", "INTEGER"), ("sponsor_commission_amount", "NUMERIC(15,2)"),
    ("sponsor_decided_at", "TIMESTAMP"), ("sponsor_evidence", "JSON"),
    ("refund_status", "VARCHAR(20)"), ("refund_event", "VARCHAR(100)"), ("refund_amount", "NUMERIC(15,2)"),
    ("refunded_at", "TIMESTAMP"), ("refund_payload_sha256", "VARCHAR(64)"),
)


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    for column, kind in PAYMENT_COLUMNS:
        op.execute(f"ALTER TABLE adv_annualads_payments ADD COLUMN IF NOT EXISTS {column} {kind} NULL")
    op.create_table(
        "adv_annualads_events", *_base(),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("tx_hash", sa.String(255), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("adv_annualads_payments.id"), nullable=True),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.UniqueConstraint("event", "tx_hash", "payload_sha256", name="uq_adv_annualads_event"),
    )
    op.create_index("ix_adv_annualads_events_id", "adv_annualads_events", ["id"])
    op.create_index("ix_adv_annualads_events_tx", "adv_annualads_events", ["tx_hash"])
    op.create_table(
        "dsm_sponsor_restorations", *_base(),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dsm_id", sa.Integer(), nullable=False),
        sa.Column("previous_sponsor_id", sa.Integer(), nullable=True),
        sa.Column("restored_sponsor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_dsm_sponsor_restoration_user"),
        sa.CheckConstraint("status IN ('APPLIED', 'REFUSED')", name="ck_dsm_restoration_status"),
        sa.CheckConstraint("user_id <> restored_sponsor_id", name="ck_dsm_restoration_not_self"),
    )
    op.create_index("ix_dsm_sponsor_restorations_id", "dsm_sponsor_restorations", ["id"])


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM dsm_sponsor_restorations) OR EXISTS (SELECT 1 FROM adv_annualads_events)
               OR EXISTS (SELECT 1 FROM adv_annualads_payments WHERE sponsor_decided_at IS NOT NULL OR refund_status IS NOT NULL) THEN
                RAISE EXCEPTION 'Annual Ads decisions or DSM restorations exist: they cannot be dropped by downgrading a8d0f2b4c6e9';
            END IF;
        END $$;
    """)
    op.drop_index("ix_dsm_sponsor_restorations_id", table_name="dsm_sponsor_restorations")
    op.drop_table("dsm_sponsor_restorations")
    op.drop_index("ix_adv_annualads_events_tx", table_name="adv_annualads_events")
    op.drop_index("ix_adv_annualads_events_id", table_name="adv_annualads_events")
    op.drop_table("adv_annualads_events")
    for column, _kind in reversed(PAYMENT_COLUMNS):
        op.execute(f"ALTER TABLE adv_annualads_payments DROP COLUMN IF EXISTS {column}")
