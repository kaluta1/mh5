"""Placeholder: accounting rollout revision referenced by deployed databases.

Some environments stamped `20260330_accounting_rollout` without this file in the repo.
Linear continuation after f1a2b3c4d5e6 (journal_entries.status VARCHAR).

Revision ID: 20260330_accounting_rollout
Revises: f1a2b3c4d5e6
Create Date: 2026-03-30

"""
from alembic import op


revision = "20260330_accounting_rollout"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
