-- Run once as PostgreSQL superuser or table owner.
-- Neon: SQL Editor → paste the chart_of_accounts block first; only run journal block if that table exists.
--
-- For CoA-only (recommended when seed fails with "must be owner"), use instead:
--   scripts/sql/fix_chart_of_accounts_columns.sql

-- === chart_of_accounts (required for init_chart_of_accounts / ORM) ===
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS balance NUMERIC(15, 2);
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE chart_of_accounts SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL;

-- === journal_entries (optional — skip if table does not exist yet) ===
ALTER TABLE journal_entries ALTER COLUMN status DROP DEFAULT;
ALTER TABLE journal_entries
  ALTER COLUMN status TYPE VARCHAR(20)
  USING (lower(status::text));
ALTER TABLE journal_entries ALTER COLUMN status SET DEFAULT 'posted';
