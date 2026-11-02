"""Verified-only earnings: missed_earnings, KYC snapshot on ad impressions, retained-revenue account 4030.

Revision ID: d4f6a8c0e2b5
Revises: b0d2f4a6c8e1
Create Date: 2026-11-02

Owner rule (Shafi Abeid, 2026-11-02): only KYC-approved members earn commissions or advertising revenue
shares. Additive only:
  * new table missed_earnings (one row per member, category and source event; never payable);
  * two nullable columns on adv_impression_events (KYC of creative / sponsor at the earning event);
  * 'MISSED_KYC' added to the allowed adv_allocations statuses;
  * chart-of-accounts row 4030 (revenue retained: earnings not payable, earner's KYC not approved).
No existing row changes; nothing is backfilled (historical commissions stay as they are).
"""
import sqlalchemy as sa
from alembic import op

revision = "d4f6a8c0e2b5"
down_revision = "b0d2f4a6c8e1"
branch_labels = None
depends_on = None

ACCOUNT = ("4030", "Revenue retained - earnings not payable (earner's KYC not approved)", "4000")
OLD_STATUSES = "'ESTIMATED', 'HELD_UNCLAIMED', 'HELD_SPONSOR', 'HELD_REVIEW', 'RELEASED', 'REVERSED', 'SUPERSEDED'"


def upgrade() -> None:
    op.create_table(
        "missed_earnings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_product", sa.String(50), nullable=True),
        sa.Column("source_user_id", sa.Integer(), nullable=True),
        sa.Column("contestant_id", sa.Integer(), nullable=True),
        sa.Column("origin_kind", sa.String(20), nullable=True),
        sa.Column("rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("base_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("kyc_status", sa.String(30), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("rule_version", sa.String(40), nullable=False),
        sa.Column("revenue_account", sa.String(10), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="RECORDED"),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("reversal_reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "category", "source_type", "source_id", name="uq_missed_earning_event"),
        sa.CheckConstraint("category IN ('REFERRAL_COMMISSION', 'AD_CREATIVE_SHARE', 'AD_SPONSOR_SHARE')",
                           name="ck_missed_earning_category"),
        sa.CheckConstraint("status IN ('RECORDED', 'REVERSED')", name="ck_missed_earning_status"),
        sa.CheckConstraint("amount > 0", name="ck_missed_earning_amount"),
    )
    op.create_index("ix_missed_earnings_id", "missed_earnings", ["id"])
    op.create_index("ix_missed_earnings_user_event", "missed_earnings", ["user_id", "event_at"])

    op.execute("ALTER TABLE adv_impression_events ADD COLUMN IF NOT EXISTS creative_kyc_approved BOOLEAN NULL")
    op.execute("ALTER TABLE adv_impression_events ADD COLUMN IF NOT EXISTS sponsor_kyc_approved BOOLEAN NULL")

    op.execute("ALTER TABLE adv_allocations DROP CONSTRAINT IF EXISTS ck_adv_alloc_status")
    op.execute(f"ALTER TABLE adv_allocations ADD CONSTRAINT ck_adv_alloc_status "
               f"CHECK (status IN ({OLD_STATUSES}, 'MISSED_KYC'))")

    code, name, parent = ACCOUNT
    op.execute(sa.text("""
        INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_id, balance,
                                       description, is_active, created_at, updated_at)
        SELECT :code, :name, p.account_type, p.id, 0, :name, true, now(), now()
        FROM chart_of_accounts p
        WHERE p.account_code = :parent
          AND NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = :code)
    """).bindparams(code=code, name=name, parent=parent))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM missed_earnings) OR EXISTS (SELECT 1 FROM adv_allocations WHERE status = 'MISSED_KYC') THEN
                RAISE EXCEPTION 'Missed earnings exist: export them before downgrading d4f6a8c0e2b5';
            END IF;
        END $$;
    """)
    op.execute(sa.text("""DELETE FROM chart_of_accounts c WHERE c.account_code = :code
                          AND NOT EXISTS (SELECT 1 FROM journal_lines l WHERE l.account_id = c.id)""")
               .bindparams(code=ACCOUNT[0]))
    op.execute("ALTER TABLE adv_allocations DROP CONSTRAINT IF EXISTS ck_adv_alloc_status")
    op.execute(f"ALTER TABLE adv_allocations ADD CONSTRAINT ck_adv_alloc_status CHECK (status IN ({OLD_STATUSES}))")
    op.execute("ALTER TABLE adv_impression_events DROP COLUMN IF EXISTS sponsor_kyc_approved")
    op.execute("ALTER TABLE adv_impression_events DROP COLUMN IF EXISTS creative_kyc_approved")
    op.drop_index("ix_missed_earnings_user_event", table_name="missed_earnings")
    op.drop_index("ix_missed_earnings_id", table_name="missed_earnings")
    op.drop_table("missed_earnings")
