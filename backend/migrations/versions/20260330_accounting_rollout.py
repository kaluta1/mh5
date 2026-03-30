"""Create accounting ledger tables and trace columns.

Revision ID: 20260330_accounting_rollout
Revises: f2a1c9d4e7b8
Create Date: 2026-03-30 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260330_accounting_rollout"
down_revision = "f2a1c9d4e7b8"
branch_labels = None
depends_on = None


account_type_enum = sa.Enum("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE", name="accounttype")
entry_status_enum = sa.Enum("DRAFT", "POSTED", "REVERSED", name="entrystatus")
report_type_enum = sa.Enum(
    "BALANCE_SHEET",
    "INCOME_STATEMENT",
    "CASH_FLOW",
    "TRIAL_BALANCE",
    "GENERAL_LEDGER",
    name="reporttype",
)


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "chart_of_accounts"):
        op.create_table(
            "chart_of_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("account_code", sa.String(length=20), nullable=False),
            sa.Column("account_name", sa.String(length=200), nullable=False),
            sa.Column("account_type", account_type_enum, nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("chart_of_accounts.id"), nullable=True),
            sa.Column("total_liabilities", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("credit_balance", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("normal_balance", sa.String(length=10), nullable=False, server_default="debit"),
            sa.Column("statement_section", sa.String(length=50), nullable=True),
            sa.Column("report_group", sa.String(length=100), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_contra_account", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("account_code"),
        )
        op.create_index(op.f("ix_chart_of_accounts_id"), "chart_of_accounts", ["id"], unique=False)
    else:
        for column_name, column in (
            ("normal_balance", sa.Column("normal_balance", sa.String(length=10), nullable=False, server_default="debit")),
            ("statement_section", sa.Column("statement_section", sa.String(length=50), nullable=True)),
            ("report_group", sa.Column("report_group", sa.String(length=100), nullable=True)),
            ("sort_order", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0")),
            ("is_contra_account", sa.Column("is_contra_account", sa.Boolean(), nullable=False, server_default=sa.false())),
        ):
            if not _has_column(inspector, "chart_of_accounts", column_name):
                op.add_column("chart_of_accounts", column)

    if not _has_table(inspector, "journal_entries"):
        op.create_table(
            "journal_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("entry_number", sa.String(length=50), nullable=False),
            sa.Column("entry_date", sa.DateTime(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("reference_number", sa.String(length=100), nullable=True),
            sa.Column("source_document", sa.String(length=100), nullable=True),
            sa.Column("event_type", sa.String(length=50), nullable=True),
            sa.Column("source_type", sa.String(length=50), nullable=True),
            sa.Column("source_id", sa.String(length=100), nullable=True),
            sa.Column("source_ref", sa.String(length=255), nullable=True),
            sa.Column("source_metadata", sa.JSON(), nullable=True),
            sa.Column("threshold", sa.Numeric(15, 2), nullable=True),
            sa.Column("total_debit", sa.Numeric(15, 2), nullable=False),
            sa.Column("total_credit", sa.Numeric(15, 2), nullable=False),
            sa.Column("status", entry_status_enum, nullable=False, server_default="DRAFT"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("posted_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("entry_number"),
        )
        op.create_index(op.f("ix_journal_entries_id"), "journal_entries", ["id"], unique=False)
        op.create_index("ix_journal_entries_entry_date", "journal_entries", ["entry_date"], unique=False)
        op.create_index("ix_journal_entries_source", "journal_entries", ["source_type", "source_id"], unique=False)
        op.create_index(
            "uq_journal_entries_event_source_idx",
            "journal_entries",
            ["event_type", "source_type", "source_id"],
            unique=True,
        )
    else:
        for column_name, column in (
            ("reference_number", sa.Column("reference_number", sa.String(length=100), nullable=True)),
            ("source_document", sa.Column("source_document", sa.String(length=100), nullable=True)),
            ("event_type", sa.Column("event_type", sa.String(length=50), nullable=True)),
            ("source_type", sa.Column("source_type", sa.String(length=50), nullable=True)),
            ("source_id", sa.Column("source_id", sa.String(length=100), nullable=True)),
            ("source_ref", sa.Column("source_ref", sa.String(length=255), nullable=True)),
            ("source_metadata", sa.Column("source_metadata", sa.JSON(), nullable=True)),
        ):
            if not _has_column(inspector, "journal_entries", column_name):
                op.add_column("journal_entries", column)

        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_journal_entries_entry_date ON journal_entries (entry_date)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_journal_entries_source ON journal_entries (source_type, source_id)"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entries_event_source_idx "
            "ON journal_entries (event_type, source_type, source_id)"
        )

    if not _has_table(inspector, "journal_lines"):
        op.create_table(
            "journal_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("chart_of_accounts.id"), nullable=False),
            sa.Column("debit_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("credit_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("reference_id", sa.String(length=100), nullable=True),
            sa.Column("reference_type", sa.String(length=50), nullable=True),
        )
        op.create_index(op.f("ix_journal_lines_id"), "journal_lines", ["id"], unique=False)
    else:
        if not _has_column(inspector, "journal_lines", "reference_id"):
            op.add_column("journal_lines", sa.Column("reference_id", sa.String(length=100), nullable=True))
        if not _has_column(inspector, "journal_lines", "reference_type"):
            op.add_column("journal_lines", sa.Column("reference_type", sa.String(length=50), nullable=True))

    if not _has_table(inspector, "financial_reports"):
        op.create_table(
            "financial_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("report_type", report_type_enum, nullable=False),
            sa.Column("period_start", sa.DateTime(), nullable=False),
            sa.Column("period_end", sa.DateTime(), nullable=False),
            sa.Column("report_data", sa.JSON(), nullable=False),
            sa.Column("generated_date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("generated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index(op.f("ix_financial_reports_id"), "financial_reports", ["id"], unique=False)

    if not _has_table(inspector, "revenue_transactions"):
        op.create_table(
            "revenue_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("source_type", sa.String(length=50), nullable=False),
            sa.Column("source_id", sa.String(length=100), nullable=True),
            sa.Column("gross_amount", sa.Numeric(15, 2), nullable=False),
            sa.Column("platform_fee", sa.Numeric(15, 2), nullable=False),
            sa.Column("net_amount", sa.Numeric(15, 2), nullable=False),
            sa.Column("participant_share", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("affiliate_commissions", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("founding_member_share", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("transaction_date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id"), nullable=True),
        )
        op.create_index(op.f("ix_revenue_transactions_id"), "revenue_transactions", ["id"], unique=False)

    if not _has_table(inspector, "tax_configurations"):
        op.create_table(
            "tax_configurations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("tax_name", sa.String(length=100), nullable=False),
            sa.Column("tax_type", sa.String(length=50), nullable=False),
            sa.Column("rate", sa.Numeric(5, 4), nullable=False),
            sa.Column("tax_payable_account_id", sa.Integer(), sa.ForeignKey("chart_of_accounts.id"), nullable=False),
            sa.Column("tax_expense_account_id", sa.Integer(), sa.ForeignKey("chart_of_accounts.id"), nullable=True),
            sa.Column("country_code", sa.String(length=3), nullable=True),
            sa.Column("province_code", sa.String(length=3), nullable=True),
            sa.Column("effective_date", sa.DateTime(), nullable=False),
            sa.Column("expiry_date", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index(op.f("ix_tax_configurations_id"), "tax_configurations", ["id"], unique=False)

    if not _has_table(inspector, "audit_trails"):
        op.create_table(
            "audit_trails",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("table_name", sa.String(length=100), nullable=False),
            sa.Column("record_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("old_values", sa.JSON(), nullable=True),
            sa.Column("new_values", sa.JSON(), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(op.f("ix_audit_trails_id"), "audit_trails", ["id"], unique=False)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_journal_entries_event_source_idx")
    op.execute("DROP INDEX IF EXISTS ix_journal_entries_source")
    op.execute("DROP INDEX IF EXISTS ix_journal_entries_entry_date")

    for table_name in (
        "audit_trails",
        "tax_configurations",
        "revenue_transactions",
        "financial_reports",
        "journal_lines",
        "journal_entries",
        "chart_of_accounts",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table_name}")
