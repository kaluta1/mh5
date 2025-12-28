-- Migration: Add position column to contestant_voting table
-- This column allows users to reorder their MyHigh5 votes
-- Position 1 = 5 points, Position 2 = 4 points, Position 3 = 3 points, Position 4 = 2 points, Position 5 = 1 point

-- Add the position column
ALTER TABLE contestant_voting 
ADD COLUMN IF NOT EXISTS position INTEGER DEFAULT NULL;

-- Create an index for faster queries when ordering by position
CREATE INDEX IF NOT EXISTS idx_contestant_voting_user_position 
ON contestant_voting (user_id, position);

-- Optional: Initialize positions based on vote_date for existing votes
-- This sets the position based on the chronological order of votes per user
-- UPDATE contestant_voting cv
-- SET position = subq.row_num
-- FROM (
--     SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY vote_date ASC) as row_num
--     FROM contestant_voting
-- ) subq
-- WHERE cv.id = subq.id AND subq.row_num <= 5;

-- Verify the column was added
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'contestant_voting' AND column_name = 'position';

