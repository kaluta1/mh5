-- Verify that crypto_amount column was fixed
-- Run this to check the column type

SELECT 
    column_name, 
    data_type, 
    character_maximum_length,
    numeric_precision,
    numeric_scale
FROM information_schema.columns 
WHERE table_name = 'deposits' 
  AND column_name = 'crypto_amount';

-- Expected result:
-- data_type should be 'character varying' or 'varchar'
-- character_maximum_length should be 255
-- numeric_precision and numeric_scale should be NULL
