# Fix for crypto_amount Numeric Overflow Error

## Problem
The `crypto_amount` column in the `deposits` table was defined as `NUMERIC(18, 8)`, which can only store values up to 10^10. However, we're storing wei amounts (smallest unit of cryptocurrency), which can be very large. For example:
- 10 USDT = `10000000000000000000` wei (10 * 10^18)
- This exceeds the NUMERIC(18, 8) limit

## Solution
Changed `crypto_amount` column type from `NUMERIC(18, 8)` to `VARCHAR(255)` to store wei amounts as strings.

## Changes Made

### 1. Database Migration
- Created migration: `fix_crypto_amount_for_wei.py`
- Changes column type from `NUMERIC(18, 8)` to `VARCHAR(255)`
- Converts existing values to strings

### 2. Model Update
- Updated `app/models/payment.py`:
  - Changed `crypto_amount` type from `Optional[float]` with `Numeric(18, 8)` to `Optional[str]` with `String(255)`

### 3. Code Updates
- `app/api/api_v1/endpoints/payments.py`: Already stores as string (`str(amount_wei)`)
- `app/api/api_v1/endpoints/admin.py`: Updated to return string instead of float

## How to Apply

### Option 1: Run Migration (Recommended)
```bash
cd backend
alembic upgrade head
```

### Option 2: Manual SQL (If migration fails)
Run the SQL script:
```bash
psql -d your_database -f fix_crypto_amount_manual.sql
```

Or manually:
```sql
-- Convert existing values
UPDATE deposits 
SET crypto_amount = crypto_amount::text 
WHERE crypto_amount IS NOT NULL;

-- Change column type
ALTER TABLE deposits 
ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
USING CASE 
    WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
    ELSE NULL
END;
```

## Usage

### Storing Wei Amounts
```python
# Store wei amount as string
deposit.crypto_amount = "10000000000000000000"  # 10 USDT in wei
```

### Reading Wei Amounts
```python
# Convert string to int for calculations
wei_amount = int(deposit.crypto_amount) if deposit.crypto_amount else 0

# Convert to human-readable format
usdt_amount = int(deposit.crypto_amount) / 1e18 if deposit.crypto_amount else 0
```

## Verification

After applying the fix, verify:
```sql
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'deposits' AND column_name = 'crypto_amount';
```

Should show:
- `data_type`: `character varying` or `varchar`
- `character_maximum_length`: `255`

## Notes

- Wei amounts are always integers (no decimals)
- Storing as string prevents precision loss
- Can handle any size wei amount
- Backend code already handles string conversion correctly
