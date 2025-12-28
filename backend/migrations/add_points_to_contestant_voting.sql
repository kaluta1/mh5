-- Migration: Add points column to contestant_voting table
-- Points are calculated based on position: 1st = 5 points, 2nd = 4 points, 3rd = 3 points, 4th = 2 points, 5th = 1 point

-- Add the points column
ALTER TABLE contestant_voting 
ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT NULL;

-- Create an index for faster queries when ordering by points
CREATE INDEX IF NOT EXISTS idx_contestant_voting_user_points 
ON contestant_voting (user_id, points);

-- Optional: Initialize points based on position for existing votes
-- UPDATE contestant_voting
-- SET points = CASE 
--     WHEN position = 1 THEN 5
--     WHEN position = 2 THEN 4
--     WHEN position = 3 THEN 3
--     WHEN position = 4 THEN 2
--     WHEN position = 5 THEN 1
--     ELSE NULL
-- END
-- WHERE position IS NOT NULL AND points IS NULL;

-- Verify the column was added
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'contestant_voting' AND column_name = 'points';

