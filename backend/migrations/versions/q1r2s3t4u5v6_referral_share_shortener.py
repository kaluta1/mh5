"""Referral-aware share link shortener tables.

Revision ID: q1r2s3t4u5v6
Revises: p8q9r0s1t2u3
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "q1r2s3t4u5v6"
down_revision = "p8q9r0s1t2u3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_share_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("short_code", sa.String(length=16), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_code"),
        sa.UniqueConstraint("user_id", "normalized_url", name="uq_referral_share_user_url"),
    )
    op.create_index("ix_referral_share_links_user_id", "referral_share_links", ["user_id"])
    op.create_index("ix_referral_share_links_short_code", "referral_share_links", ["short_code"])

    op.create_table(
        "referral_share_clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("share_link_id", sa.Integer(), nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=1000), nullable=True),
        sa.Column("referer", sa.String(length=2048), nullable=True),
        sa.Column("landing_url", sa.Text(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["share_link_id"], ["referral_share_links.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_share_clicks_share_link_id",
        "referral_share_clicks",
        ["share_link_id"],
    )

    op.create_table(
        "referral_share_conversions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("converted_user_id", sa.Integer(), nullable=True),
        sa.Column("conversion_type", sa.String(length=50), nullable=False),
        sa.Column("conversion_reference", sa.String(length=255), nullable=True),
        sa.Column("share_link_id", sa.Integer(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["converted_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["share_link_id"], ["referral_share_links.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_share_conversions_referrer_user_id",
        "referral_share_conversions",
        ["referrer_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_share_conversions_referrer_user_id", table_name="referral_share_conversions")
    op.drop_table("referral_share_conversions")
    op.drop_index("ix_referral_share_clicks_share_link_id", table_name="referral_share_clicks")
    op.drop_table("referral_share_clicks")
    op.drop_index("ix_referral_share_links_short_code", table_name="referral_share_links")
    op.drop_index("ix_referral_share_links_user_id", table_name="referral_share_links")
    op.drop_table("referral_share_links")
