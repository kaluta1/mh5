"""Email foundation (EMAIL-1): settings, event overrides, outbox, webhook events.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-05

Additive only. Four new tables and one new permission row; no existing table,
column or row is changed.

  email_settings         one configuration row (id = 1), created with the
                         defaults that match today's behaviour: email on, no
                         emergency stop, Resend enabled, no Admin override.
  email_event_settings   Admin overrides of an event switch. Empty: every event
                         uses its default from the source-controlled registry.
  email_deliveries       the outbox and the delivery log. Unique
                         idempotency_key. No email body is ever stored; the
                         encrypted payload is cleared at a terminal state.
  email_webhook_events   empty until EMAIL-5 implements provider webhooks.

No secret is written by this migration. The permission manage_email_settings
is created but assigned to NO role: granting it is a deliberate Admin action.

Downgrade drops the four tables and the unassigned permission row.
"""
from alembic import op


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_settings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            emergency_stop BOOLEAN NOT NULL DEFAULT FALSE,
            resend_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            from_name VARCHAR(120),
            from_address VARCHAR(320),
            reply_to VARCHAR(320),
            support_address VARCHAR(320),
            admin_alert_recipients JSONB,
            resend_api_key_ciphertext TEXT,
            resend_api_key_last4 VARCHAR(4),
            resend_api_key_updated_at TIMESTAMP,
            resend_api_key_updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            webhook_secret_ciphertext TEXT,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_settings_id ON email_settings (id)")
    op.execute("INSERT INTO email_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    op.execute("SELECT setval(pg_get_serial_sequence('email_settings', 'id'), "
               "GREATEST((SELECT MAX(id) FROM email_settings), 1))")

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_event_settings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            event_key VARCHAR(80) NOT NULL CONSTRAINT uq_email_event_settings_event_key UNIQUE,
            enabled BOOLEAN NOT NULL,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_event_settings_id ON email_event_settings (id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_deliveries (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            event_key VARCHAR(80) NOT NULL,
            category VARCHAR(20) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            recipient_masked VARCHAR(320) NOT NULL,
            recipient_hash VARCHAR(64),
            lang VARCHAR(5) NOT NULL DEFAULT 'en',
            payload_ciphertext TEXT,
            provider VARCHAR(30),
            provider_message_id VARCHAR(120),
            status VARCHAR(20) NOT NULL DEFAULT 'QUEUED'
                CONSTRAINT ck_email_deliveries_status CHECK (status IN
                ('QUEUED', 'PROCESSING', 'SENT', 'DELIVERED', 'DELAYED', 'FAILED', 'BOUNCED', 'COMPLAINED',
                 'SUPPRESSED')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMP,
            locked_at TIMESTAMP,
            idempotency_key VARCHAR(200) NOT NULL CONSTRAINT uq_email_deliveries_idempotency_key UNIQUE,
            failure_category VARCHAR(40),
            failure_code VARCHAR(40),
            queued_at TIMESTAMP,
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            failed_at TIMESTAMP)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_id ON email_deliveries (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_status_next "
               "ON email_deliveries (status, next_attempt_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_event_key ON email_deliveries (event_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_recipient_hash "
               "ON email_deliveries (recipient_hash, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_created_at ON email_deliveries (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_deliveries_provider_message_id "
               "ON email_deliveries (provider_message_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_webhook_events (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            provider VARCHAR(30) NOT NULL,
            provider_event_id VARCHAR(160) NOT NULL CONSTRAINT uq_email_webhook_events_provider_event_id UNIQUE,
            event_type VARCHAR(60) NOT NULL,
            email_delivery_id INTEGER REFERENCES email_deliveries(id) ON DELETE SET NULL,
            received_at TIMESTAMP NOT NULL DEFAULT now(),
            meta JSONB)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_webhook_events_id ON email_webhook_events (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_webhook_events_email_delivery_id "
               "ON email_webhook_events (email_delivery_id)")

    # The permission exists but is held by nobody until an Admin grants it.
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL THEN
                INSERT INTO permissions (name, description, category, created_at, updated_at)
                SELECT 'manage_email_settings',
                       'Manage email settings: provider, API key, switches, emergency stop, test email',
                       'admin', now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'manage_email_settings');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_webhook_events")
    op.execute("DROP TABLE IF EXISTS email_deliveries")
    op.execute("DROP TABLE IF EXISTS email_event_settings")
    op.execute("DROP TABLE IF EXISTS email_settings")
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL
               AND to_regclass('public.role_permissions') IS NOT NULL THEN
                DELETE FROM permissions p
                WHERE p.name = 'manage_email_settings'
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
            END IF;
        END $$""")
