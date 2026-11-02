"""Advertising completion (Prompt 4): approved CPM price, review states, creative image metadata.

Revision ID: e5a7c9e1f3b4
Revises: d4f6a8c0e2b5
Create Date: 2026-11-03

Owner-approved advertising policy (Prompt 4, 2026-11-03): CPM 0.50 USD per 1,000 valid impressions,
minimum campaign budget 10.00 USD. Additive only:
  * adv_settings: the two prices are written ONLY where they are still unset (NULL). An administrator's
    existing value is never overwritten. Every switch (campaigns, funding, sharing) stays as it is (off).
    The change is written to audit_trails.
  * adv_campaigns: two more allowed statuses, CHANGES_REQUESTED (an administrator asked for changes; the
    budget stays reserved) and CANCELLED (stopped by the advertiser before serving; the budget returns).
  * adv_creatives: nullable metadata of an uploaded image (MIME type, bytes, width, height).
No campaign, impression, allocation, credit or ledger row changes.
"""
import sqlalchemy as sa
from alembic import op

revision = "e5a7c9e1f3b4"
down_revision = "d4f6a8c0e2b5"
branch_labels = None
depends_on = None

OLD_STATUSES = "'DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'PAUSED', 'COMPLETED', 'REJECTED'"
CPM, MIN_BUDGET = "0.5000", "10.00"


def upgrade() -> None:
    op.execute("ALTER TABLE adv_campaigns DROP CONSTRAINT IF EXISTS ck_adv_campaign_status")
    op.execute(f"ALTER TABLE adv_campaigns ADD CONSTRAINT ck_adv_campaign_status "
               f"CHECK (status IN ({OLD_STATUSES}, 'CHANGES_REQUESTED', 'CANCELLED'))")
    for column, kind in (("image_mime", "VARCHAR(40)"), ("image_bytes", "INTEGER"),
                         ("image_width", "INTEGER"), ("image_height", "INTEGER")):
        op.execute(f"ALTER TABLE adv_creatives ADD COLUMN IF NOT EXISTS {column} {kind} NULL")

    op.execute(sa.text("""
        INSERT INTO audit_trails (table_name, record_id, action, old_values, new_values, timestamp,
                                  created_at, updated_at)
        SELECT 'adv_settings', s.id, 'APPROVED_PRICING',
               json_build_object('cpm_rate_usd', s.cpm_rate_usd::text,
                                 'min_campaign_budget_usd', s.min_campaign_budget_usd::text),
               json_build_object('cpm_rate_usd', COALESCE(s.cpm_rate_usd::text, :cpm),
                                 'min_campaign_budget_usd', COALESCE(s.min_campaign_budget_usd::text, :minb),
                                 'source', 'Owner-approved advertising policy (Prompt 4, 2026-11-03)'),
               now(), now(), now()
        FROM adv_settings s
        WHERE s.cpm_rate_usd IS NULL OR s.min_campaign_budget_usd IS NULL
    """).bindparams(cpm=CPM, minb=MIN_BUDGET))
    op.execute(sa.text("UPDATE adv_settings SET cpm_rate_usd = CAST(:cpm AS NUMERIC), updated_at = now() "
                       "WHERE cpm_rate_usd IS NULL").bindparams(cpm=CPM))
    op.execute(sa.text("UPDATE adv_settings SET min_campaign_budget_usd = CAST(:minb AS NUMERIC), updated_at = now() "
                       "WHERE min_campaign_budget_usd IS NULL").bindparams(minb=MIN_BUDGET))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM adv_campaigns WHERE status IN ('CHANGES_REQUESTED', 'CANCELLED')) THEN
                RAISE EXCEPTION 'Campaigns use the new statuses: resolve them before downgrading e5a7c9e1f3b4';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE adv_campaigns DROP CONSTRAINT IF EXISTS ck_adv_campaign_status")
    op.execute(f"ALTER TABLE adv_campaigns ADD CONSTRAINT ck_adv_campaign_status CHECK (status IN ({OLD_STATUSES}))")
    for column in ("image_height", "image_width", "image_bytes", "image_mime"):
        op.execute(f"ALTER TABLE adv_creatives DROP COLUMN IF EXISTS {column}")
    # The approved prices stay: they are configuration with an audit record, not schema.
