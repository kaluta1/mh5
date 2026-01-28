-- Manual SQL script to fix crypto_amount column type
-- Run this if migration doesn't work

-- Step 1: Convert existing numeric values to strings (if any)
UPDATE deposits 
SET crypto_amount = crypto_amount::text 
WHERE crypto_amount IS NOT NULL;

-- Step 2: Change column type from NUMERIC(18, 8) to VARCHAR(255)
ALTER TABLE deposits 
ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
USING CASE 
    WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
    ELSE NULL
END;

-- Verify the change
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'deposits' AND column_name = 'crypto_amount';
