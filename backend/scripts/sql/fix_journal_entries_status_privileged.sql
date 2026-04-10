-- Run as table owner / superuser ONLY if journal_entries exists and you need status as VARCHAR.
-- Skip entirely if you have not created journal_entries yet.

ALTER TABLE journal_entries ALTER COLUMN status DROP DEFAULT;
ALTER TABLE journal_entries
  ALTER COLUMN status TYPE VARCHAR(20)
  USING (lower(status::text));
ALTER TABLE journal_entries ALTER COLUMN status SET DEFAULT 'posted';
