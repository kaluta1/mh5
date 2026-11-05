"""Advertising campaign & creative workflow (owner-approved requirements, 2026-11-05).

Revision ID: f1a3c5e7b9d2
Revises: e7b9d1f3a5c8
Create Date: 2026-11-05

Additive only. Nothing is backfilled; existing campaigns, creatives, balances and earnings are unchanged.
  * adv_creatives: display_name, cta_code, video_poster_url, video_width, video_height, review_issues,
    supersedes_creative_id (a revision of an approved creative; the approved one keeps serving until the
    revision is approved), headline nullable (incomplete drafts), review_status DRAFT and ARCHIVED.
  * adv_campaigns: timezone (the advertiser's IANA zone, display only: times are stored in UTC),
    review_issues.
  * adv_campaign_days: the advertiser's direct-sponsor commission decision on the day's recognized charge
    (status, commission id, amount, rate).
  * adv_settings: advertiser_sponsor_commission_enabled (OFF).
Downgrade refuses while any new data exists.
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a3c5e7b9d2"
down_revision = "e7b9d1f3a5c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adv_creatives", sa.Column("display_name", sa.String(60), nullable=True))
    op.add_column("adv_creatives", sa.Column("cta_code", sa.String(20), nullable=True))
    op.add_column("adv_creatives", sa.Column("video_poster_url", sa.String(500), nullable=True))
    op.add_column("adv_creatives", sa.Column("video_width", sa.Integer(), nullable=True))
    op.add_column("adv_creatives", sa.Column("video_height", sa.Integer(), nullable=True))
    op.add_column("adv_creatives", sa.Column("review_issues", sa.JSON(), nullable=True))
    op.add_column("adv_creatives", sa.Column("supersedes_creative_id", sa.Integer(),
                                             sa.ForeignKey("adv_creatives.id"), nullable=True))
    op.alter_column("adv_creatives", "headline", existing_type=sa.String(90), nullable=True)
    op.execute("ALTER TABLE adv_creatives DROP CONSTRAINT IF EXISTS ck_adv_creative_review")
    op.execute("ALTER TABLE adv_creatives ADD CONSTRAINT ck_adv_creative_review "
               "CHECK (review_status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'ARCHIVED'))")
    op.create_index("ix_adv_creative_supersedes", "adv_creatives", ["supersedes_creative_id"])

    op.add_column("adv_campaigns", sa.Column("timezone", sa.String(64), nullable=True))
    op.add_column("adv_campaigns", sa.Column("review_issues", sa.JSON(), nullable=True))

    op.add_column("adv_campaign_days", sa.Column("sponsor_commission_status", sa.String(20), nullable=True))
    op.add_column("adv_campaign_days", sa.Column("sponsor_commission_id", sa.Integer(), nullable=True))
    op.add_column("adv_campaign_days", sa.Column("sponsor_commission_amount", sa.Numeric(15, 2), nullable=True))
    op.add_column("adv_campaign_days", sa.Column("sponsor_rate", sa.Numeric(6, 4), nullable=True))

    op.add_column("adv_settings", sa.Column("advertiser_sponsor_commission_enabled", sa.Boolean(), nullable=False,
                                            server_default=sa.false()))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_creatives WHERE review_status IN ('DRAFT', 'ARCHIVED') OR headline IS NULL
                         OR supersedes_creative_id IS NOT NULL OR display_name IS NOT NULL OR cta_code IS NOT NULL
                         OR video_poster_url IS NOT NULL OR review_issues IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_campaigns WHERE timezone IS NOT NULL OR review_issues IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_campaign_days WHERE sponsor_commission_status IS NOT NULL)
               OR EXISTS (SELECT 1 FROM adv_settings WHERE advertiser_sponsor_commission_enabled) THEN
                RAISE EXCEPTION 'Advertising workflow data exists: it cannot be dropped by downgrading f1a3c5e7b9d2';
            END IF;
        END $$;
    """)
    op.drop_column("adv_settings", "advertiser_sponsor_commission_enabled")
    for name in ("sponsor_rate", "sponsor_commission_amount", "sponsor_commission_id", "sponsor_commission_status"):
        op.drop_column("adv_campaign_days", name)
    for name in ("review_issues", "timezone"):
        op.drop_column("adv_campaigns", name)
    op.drop_index("ix_adv_creative_supersedes", table_name="adv_creatives")
    op.execute("ALTER TABLE adv_creatives DROP CONSTRAINT IF EXISTS ck_adv_creative_review")
    op.execute("ALTER TABLE adv_creatives ADD CONSTRAINT ck_adv_creative_review "
               "CHECK (review_status IN ('PENDING', 'APPROVED', 'REJECTED'))")
    op.alter_column("adv_creatives", "headline", existing_type=sa.String(90), nullable=False)
    for name in ("supersedes_creative_id", "review_issues", "video_height", "video_width", "video_poster_url",
                 "cta_code", "display_name"):
        op.drop_column("adv_creatives", name)
