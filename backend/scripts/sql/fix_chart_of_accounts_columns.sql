-- Run ONCE as PostgreSQL table owner or superuser (Neon: SQL Editor with role that owns the table).
-- Fixes: app user gets "must be owner of table chart_of_accounts" when seeding tries ADD COLUMN.
--
-- 1) See owner:
--    SELECT tablename, tableowner FROM pg_tables
--    WHERE schemaname = 'public' AND tablename = 'chart_of_accounts';
--
-- 2) Optional: give ownership to your app role (replace neondb_owner with user from DATABASE_URL):
--    ALTER TABLE chart_of_accounts OWNER TO neondb_owner;

ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS balance NUMERIC(15, 2);
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS description TEXT;
UPDATE chart_of_accounts SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL;
