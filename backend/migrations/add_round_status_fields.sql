-- SQL Migration: Add new fields to rounds table
-- Run this migration to add is_submission_open, is_voting_open, current_season_level to rounds

-- Step 1: Add new columns to rounds table
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS is_submission_open BOOLEAN DEFAULT TRUE NOT NULL;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS is_voting_open BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS current_season_level VARCHAR(20);

-- Step 2: Copy existing data from contest table to rounds (if rounds exist)
-- This updates rounds with the state from their parent contest
UPDATE rounds r
SET 
    is_submission_open = COALESCE(c.is_submission_open, TRUE),
    is_voting_open = COALESCE(c.is_voting_open, FALSE),
    current_season_level = c.level
FROM contest c
WHERE r.contest_id = c.id;

-- Verification query: Check the migration worked
SELECT r.id, r.name, r.is_submission_open, r.is_voting_open, r.current_season_level, c.name as contest_name
FROM rounds r
JOIN contest c ON r.contest_id = c.id
LIMIT 10;
