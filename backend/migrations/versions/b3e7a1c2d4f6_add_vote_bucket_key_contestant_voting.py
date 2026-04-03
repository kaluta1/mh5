"""add vote_bucket_key to contestant_voting for per-category MyHigh5 buckets

Revision ID: b3e7a1c2d4f6
Revises: c8d1e2f3a4b5
Create Date: 2026-04-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b3e7a1c2d4f6"
down_revision = "c8d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("contestant_voting")] if insp.has_table("contestant_voting") else []

    if "vote_bucket_key" not in cols:
        op.add_column(
            "contestant_voting",
            sa.Column("vote_bucket_key", sa.String(length=128), nullable=True),
        )

    # Backfill from contest row linked by contest_id
    op.execute(
        sa.text(
            """
            UPDATE contestant_voting AS cv
            SET vote_bucket_key = CASE
                WHEN c.category_id IS NOT NULL THEN 'cat:' || c.category_id::text
                ELSE 'ty:' || COALESCE(c.contest_type, '') || ':' || COALESCE(c.contest_mode, '')
            END
            FROM contest AS c
            WHERE cv.contest_id = c.id
              AND (cv.vote_bucket_key IS NULL OR cv.vote_bucket_key = '')
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE contestant_voting
            SET vote_bucket_key = 'ty:unknown:participation'
            WHERE vote_bucket_key IS NULL OR vote_bucket_key = ''
            """
        )
    )

    op.alter_column(
        "contestant_voting",
        "vote_bucket_key",
        existing_type=sa.String(length=128),
        nullable=False,
    )

    insp2 = sa.inspect(bind)
    existing_ix = [ix["name"] for ix in insp2.get_indexes("contestant_voting")] if insp2.has_table("contestant_voting") else []
    if "ix_contestant_voting_user_season_bucket" not in existing_ix:
        op.create_index(
            "ix_contestant_voting_user_season_bucket",
            "contestant_voting",
            ["user_id", "season_id", "vote_bucket_key"],
            unique=False,
        )


def downgrade():
    op.drop_index("ix_contestant_voting_user_season_bucket", table_name="contestant_voting")
    op.drop_column("contestant_voting", "vote_bucket_key")
