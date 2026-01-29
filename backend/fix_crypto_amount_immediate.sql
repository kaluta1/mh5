-- Immediate fix for crypto_amount column type
-- Run this SQL directly on your database to fix the numeric overflow error

-- Step 1: Check current column type
SELECT column_name, data_type, numeric_precision, numeric_scale, character_maximum_length
FROM information_schema.columns 
WHERE table_name = 'deposits' AND column_name = 'crypto_amount';

-- Step 2: If column is still NUMERIC, convert existing values to text first
-- (This prevents data loss during type conversion)
UPDATE deposits 
SET crypto_amount = crypto_amount::text 
WHERE crypto_amount IS NOT NULL AND crypto_amount::text != crypto_amount::text;

-- Step 3: Change column type from NUMERIC(18, 8) to VARCHAR(255)
ALTER TABLE deposits 
ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
USING CASE 
    WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
    ELSE NULL
END;

-- Step 4: Verify the change
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'deposits' AND column_name = 'crypto_amount';

-- Expected result:
-- data_type should be 'character varying' or 'varchar'
-- character_maximum_length should be 255
