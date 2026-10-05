"""EMAIL-5: provider webhook events can be matched and reconciled.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-06

email_webhook_events was created empty by EMAIL-1 (b9c0d1e2f3a4) as the store
for provider events, with a UNIQUE provider_event_id (the replay guard) and a
nullable link to the delivery. Processing them needs four more facts per
event, none of which the table could hold:

  provider_message_id  the provider's id of the message the event is about.
                       An event can arrive before our own row has recorded
                       that id (or for a message we do not know). Keeping the
                       id on the event, indexed, is what lets it be matched
                       later instead of being dropped.
  occurred_at          when the provider says it happened (events arrive out
                       of order; received_at is only when we got it).
  processed_at         when it was applied to a delivery (NULL = not matched yet).
  outcome              applied / recorded / unmatched / unknown_type.

Additive only: four nullable columns and one index on a table that has never
been written to. No existing row of any table changes; email_deliveries and
every EMAIL-1/2/3 table are untouched. Downgrade drops exactly these columns
and the index (provider event history kept in them is lost; deliveries and
their statuses are not affected).
"""
from alembic import op


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE email_webhook_events ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(120)")
    op.execute("ALTER TABLE email_webhook_events ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMP")
    op.execute("ALTER TABLE email_webhook_events ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP")
    op.execute("ALTER TABLE email_webhook_events ADD COLUMN IF NOT EXISTS outcome VARCHAR(30)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_webhook_events_provider_message_id "
               "ON email_webhook_events (provider_message_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_webhook_events_provider_message_id")
    op.execute("ALTER TABLE email_webhook_events DROP COLUMN IF EXISTS outcome")
    op.execute("ALTER TABLE email_webhook_events DROP COLUMN IF EXISTS processed_at")
    op.execute("ALTER TABLE email_webhook_events DROP COLUMN IF EXISTS occurred_at")
    op.execute("ALTER TABLE email_webhook_events DROP COLUMN IF EXISTS provider_message_id")
