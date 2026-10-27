"""Member short links: optional personal invitation, one active link per choice, fixed records.

Revision ID: e3a5c7e9b1d3
Revises: d2f4b6c8e0a1
Create Date: 2026-10-27

Additive on referral_share_links; no row is rewritten.

  * invitation_enabled   NOT NULL DEFAULT true: every existing link keeps its current behaviour (it was
                         created by a referral share button and always carried the creator's invitation).
  * uq_referral_share_user_url (user_id, normalized_url) is replaced by a PARTIAL unique index over
    ACTIVE links (user_id, normalized_url, invitation_enabled) WHERE disabled_at IS NULL, so a member
    can have a neutral and an invitation link to the same page, and can create a new link after
    disabling one.
  * trigger: short_code, user_id, destination_url, normalized_url and invitation_enabled can never be
    changed once written; a link can only be disabled (disabled_at, last_used_at stay writable).

Downgrade restores the old constraint; it refuses while a member holds two links to one destination.
"""
from alembic import op


revision = "e3a5c7e9b1d3"
down_revision = "d2f4b6c8e0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE referral_share_links ADD COLUMN IF NOT EXISTS invitation_enabled BOOLEAN NOT NULL "
               "DEFAULT true")
    op.execute("ALTER TABLE referral_share_links DROP CONSTRAINT IF EXISTS uq_referral_share_user_url")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_share_active_user_url ON referral_share_links "
               "(user_id, normalized_url, invitation_enabled) WHERE disabled_at IS NULL")
    op.execute("""
        CREATE OR REPLACE FUNCTION referral_share_links_fixed() RETURNS trigger AS $$
        BEGIN
            IF NEW.short_code IS DISTINCT FROM OLD.short_code
               OR NEW.user_id IS DISTINCT FROM OLD.user_id
               OR NEW.destination_url IS DISTINCT FROM OLD.destination_url
               OR NEW.normalized_url IS DISTINCT FROM OLD.normalized_url
               OR NEW.invitation_enabled IS DISTINCT FROM OLD.invitation_enabled THEN
                RAISE EXCEPTION 'referral_share_links: destination, owner and invitation are fixed at creation';
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_referral_share_links_fixed ON referral_share_links")
    op.execute("CREATE TRIGGER trg_referral_share_links_fixed BEFORE UPDATE ON referral_share_links "
               "FOR EACH ROW EXECUTE FUNCTION referral_share_links_fixed()")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM referral_share_links GROUP BY user_id, normalized_url HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'referral_share_links holds several links per member and destination; downgrade refused';
            END IF;
        END $$""")
    op.execute("DROP TRIGGER IF EXISTS trg_referral_share_links_fixed ON referral_share_links")
    op.execute("DROP FUNCTION IF EXISTS referral_share_links_fixed()")
    op.execute("DROP INDEX IF EXISTS uq_referral_share_active_user_url")
    op.execute("ALTER TABLE referral_share_links ADD CONSTRAINT uq_referral_share_user_url UNIQUE (user_id, normalized_url)")
    op.execute("ALTER TABLE referral_share_links DROP COLUMN IF EXISTS invitation_enabled")
