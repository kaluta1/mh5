"""Internal wallet payments (Prompt 5): payment records, the commission rows each one used, clearing account.

Revision ID: f6b8d0a2c4e7
Revises: e5a7c9e1f3b4
Create Date: 2026-11-03

Additive only:
  * internal_wallet_payments and internal_wallet_payment_lines (empty);
  * chart-of-accounts row 1050 (internal wallet settlement clearing; nets to zero, never cash).
No existing row changes. The feature switch is the server setting INTERNAL_WALLET_PAYMENTS_ENABLED
(default false); this migration never switches anything on.
"""
import sqlalchemy as sa
from alembic import op

revision = "f6b8d0a2c4e7"
down_revision = "e5a7c9e1f3b4"
branch_labels = None
depends_on = None

ACCOUNT = ("1050", "Internal wallet settlement clearing (purchases paid with commission earnings; not cash)", "1000")


def _base():
    return [sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table(
        "internal_wallet_payments", *_base(),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("product_code", sa.String(50), nullable=False),
        sa.Column("product_type_id", sa.Integer(), sa.ForeignKey("product_types.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("deposit_id", sa.Integer(), sa.ForeignKey("deposits.id"), nullable=True),
        sa.Column("settlement_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("balance_before", sa.Numeric(15, 2), nullable=True),
        sa.Column("failure_code", sa.String(40), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("refunded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("refund_reason", sa.String(300), nullable=True),
        sa.Column("refund_journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.UniqueConstraint("reference", name="uq_iwp_reference"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_iwp_user_idempotency"),
        sa.UniqueConstraint("deposit_id", name="uq_iwp_deposit"),
        sa.CheckConstraint("status IN ('COMPLETED', 'FAILED', 'REFUNDED')", name="ck_iwp_status"),
        sa.CheckConstraint("amount > 0", name="ck_iwp_amount"),
        sa.CheckConstraint("quantity > 0", name="ck_iwp_quantity"),
    )
    op.create_index("ix_internal_wallet_payments_id", "internal_wallet_payments", ["id"])
    op.create_index("ix_iwp_user_created", "internal_wallet_payments", ["user_id", "created_at"])
    op.create_table(
        "internal_wallet_payment_lines", *_base(),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("internal_wallet_payments.id"), nullable=False),
        sa.Column("commission_id", sa.Integer(), sa.ForeignKey("affiliate_commissions.id"), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint("payment_id", "commission_id", name="uq_iwp_line"),
        sa.CheckConstraint("amount > 0", name="ck_iwp_line_amount"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_iwp_line_status"),
    )
    op.create_index("ix_internal_wallet_payment_lines_id", "internal_wallet_payment_lines", ["id"])
    op.create_index("ix_iwp_line_commission", "internal_wallet_payment_lines", ["commission_id", "status"])

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
            IF EXISTS (SELECT 1 FROM internal_wallet_payments) THEN
                RAISE EXCEPTION 'Internal wallet payments exist: they cannot be dropped by downgrading f6b8d0a2c4e7';
            END IF;
        END $$;
    """)
    op.execute(sa.text("""DELETE FROM chart_of_accounts c WHERE c.account_code = :code
                          AND NOT EXISTS (SELECT 1 FROM journal_lines l WHERE l.account_id = c.id)""")
               .bindparams(code=ACCOUNT[0]))
    op.drop_index("ix_iwp_line_commission", table_name="internal_wallet_payment_lines")
    op.drop_index("ix_internal_wallet_payment_lines_id", table_name="internal_wallet_payment_lines")
    op.drop_table("internal_wallet_payment_lines")
    op.drop_index("ix_iwp_user_created", table_name="internal_wallet_payments")
    op.drop_index("ix_internal_wallet_payments_id", table_name="internal_wallet_payments")
    op.drop_table("internal_wallet_payments")
