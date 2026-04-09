"""Add chart_of_accounts.balance if missing (legacy DBs).

Revision ID: c1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-04-09

"""
import warnings

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError


revision = "c1a2b3c4d5e6"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _is_privilege_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    orig = getattr(exc, "orig", None)
    if orig is not None:
        msg += " " + str(orig).lower()
    return (
        "must be owner" in msg
        or "insufficientprivilege" in msg.replace(" ", "")
        or "permission denied" in msg
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chart_of_accounts", "balance"):
        return
    # PG: a failed ALTER aborts the whole migration transaction unless we use a savepoint.
    if bind.dialect.name != "postgresql":
        op.add_column(
            "chart_of_accounts",
            sa.Column("balance", sa.Numeric(precision=15, scale=2), nullable=True),
        )
        return

    op.execute(text("SAVEPOINT sp_c1_balance"))
    try:
        op.add_column(
            "chart_of_accounts",
            sa.Column("balance", sa.Numeric(precision=15, scale=2), nullable=True),
        )
        op.execute(text("RELEASE SAVEPOINT sp_c1_balance"))
    except (ProgrammingError, OperationalError) as e:
        op.execute(text("ROLLBACK TO SAVEPOINT sp_c1_balance"))
        if _is_privilege_error(e):
            warnings.warn(
                "chart_of_accounts.balance was not added (DB user is not table owner). "
                "Run backend/scripts/sql/fix_accounting_schema_privileged.sql as PostgreSQL superuser.",
                stacklevel=1,
            )
            return
        raise


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "chart_of_accounts", "balance"):
        return
    if bind.dialect.name != "postgresql":
        try:
            op.drop_column("chart_of_accounts", "balance")
        except (ProgrammingError, OperationalError) as e:
            if _is_privilege_error(e):
                return
            raise
        return

    op.execute(text("SAVEPOINT sp_c1_balance_dn"))
    try:
        op.drop_column("chart_of_accounts", "balance")
        op.execute(text("RELEASE SAVEPOINT sp_c1_balance_dn"))
    except (ProgrammingError, OperationalError) as e:
        op.execute(text("ROLLBACK TO SAVEPOINT sp_c1_balance_dn"))
        if _is_privilege_error(e):
            return
        raise
