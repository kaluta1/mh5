-- Run once as PostgreSQL superuser or table owner (e.g. psql -U postgres -d yourdb -f this.sql)
-- Fixes schema when the app/migration user cannot ALTER tables (must be owner).

-- 1) chart_of_accounts columns the app may try to ADD (ORM / init_coa)
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS balance NUMERIC(15, 2);
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE chart_of_accounts SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL;

-- 2) journal_entries.status: replace PG enum with VARCHAR so 'posted' inserts work
ALTER TABLE journal_entries ALTER COLUMN status DROP DEFAULT;
ALTER TABLE journal_entries
  ALTER COLUMN status TYPE VARCHAR(20)
  USING (lower(status::text));
ALTER TABLE journal_entries ALTER COLUMN status SET DEFAULT 'posted';

-- Optional: drop orphaned enum type if nothing else uses it (verify first):
-- DROP TYPE IF EXISTS entrystatus;
