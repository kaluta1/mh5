"""Frozen historical Top High5 results table.

Revision ID: v5w6x7y8z9a0
Revises: u4v5w6x7y8z9
Create Date: 2026-09-14

Additive only, no existing data touched. See season_migration.py's freeze
hook (SeasonMigrationService._freeze_top_high5_results) for the writer and
the /top-high5 endpoint for the reader. reuses the existing `seasonlevel`
Postgres enum type created by simplify_contest_seasons_table.py.
"""
from alembic import op


revision = "v5w6x7y8z9a0"
down_revision = "u4v5w6x7y8z9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent DDL — VPS app role may not own tables until fix_postgres_ownership.sh runs.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS top_high5_results (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            contestant_id INTEGER NOT NULL REFERENCES contestants(id),
            contest_id INTEGER NOT NULL REFERENCES contest(id),
            category_id INTEGER REFERENCES categories(id),
            level seasonlevel NOT NULL,
            jurisdiction VARCHAR(150) NOT NULL,
            round_id INTEGER NOT NULL REFERENCES rounds(id),
            from_season_id INTEGER NOT NULL REFERENCES contest_seasons(id),
            to_season_id INTEGER REFERENCES contest_seasons(id),
            "rank" INTEGER NOT NULL,
            total_points INTEGER NOT NULL DEFAULT 0,
            total_votes INTEGER NOT NULL DEFAULT 0,
            shares INTEGER NOT NULL DEFAULT 0,
            likes INTEGER NOT NULL DEFAULT 0,
            comments INTEGER NOT NULL DEFAULT 0,
            views INTEGER NOT NULL DEFAULT 0,
            migrated BOOLEAN NOT NULL DEFAULT false
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_top_high5_results_group_rank "
        'ON top_high5_results (contest_id, level, jurisdiction, round_id, "rank")'
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_top_high5_results_round_level_contest "
        "ON top_high5_results (round_id, level, contest_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_top_high5_results_contestant_id "
        "ON top_high5_results (contestant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_top_high5_results_contestant_id")
    op.execute("DROP INDEX IF EXISTS ix_top_high5_results_round_level_contest")
    op.execute("DROP INDEX IF EXISTS uq_top_high5_results_group_rank")
    op.execute("DROP TABLE IF EXISTS top_high5_results")
