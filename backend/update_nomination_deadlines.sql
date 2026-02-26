-- Update nomination rounds to have +32 days deadline
-- This adds 32 days to the submission_end_date for all rounds linked to nomination contests

UPDATE rounds r
SET submission_end_date = r.submission_end_date + INTERVAL '32 days'
FROM contest c
WHERE r.contest_id = c.id
  AND c.voting_type_id IS NOT NULL
  AND r.submission_end_date IS NOT NULL;

-- Show updated rounds
SELECT 
    r.id,
    r.name,
    r.contest_id,
    c.name as contest_name,
    r.submission_end_date as new_deadline
FROM rounds r
JOIN contest c ON r.contest_id = c.id
WHERE c.voting_type_id IS NOT NULL
ORDER BY r.id;
