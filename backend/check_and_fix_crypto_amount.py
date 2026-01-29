#!/usr/bin/env python3
"""
Check and fix crypto_amount column type
Run this script to verify and fix the crypto_amount column if needed
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from sqlalchemy import create_engine, text

def check_and_fix_crypto_amount():
    """Check the crypto_amount column type and fix it if needed"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # Check current column type
            result = conn.execute(text("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale
                FROM information_schema.columns 
                WHERE table_name = 'deposits' 
                  AND column_name = 'crypto_amount'
            """))
            
            row = result.fetchone()
            
            if not row:
                print("ERROR: crypto_amount column not found in deposits table")
                return False
            
            column_name, data_type, char_max_length, num_precision, num_scale = row
            
            print(f"Current column type: {data_type}")
            print(f"Character max length: {char_max_length}")
            print(f"Numeric precision: {num_precision}")
            print(f"Numeric scale: {num_scale}")
            
            # Check if it's still NUMERIC
            if data_type in ['numeric', 'decimal']:
                print("\nWARNING: Column is still NUMERIC! Fixing now...")
                
                # Change column type directly (PostgreSQL will handle conversion via USING clause)
                print("Changing column type from NUMERIC to VARCHAR(255)...")
                conn.execute(text("""
                    ALTER TABLE deposits 
                    ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
                    USING CASE 
                        WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
                        ELSE NULL
                    END
                """))
                conn.commit()
                print("SUCCESS: Column type changed to VARCHAR(255)")
                
                # Verify the change
                result = conn.execute(text("""
                    SELECT 
                        column_name, 
                        data_type, 
                        character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_name = 'deposits' 
                      AND column_name = 'crypto_amount'
                """))
                
                row = result.fetchone()
                if row:
                    print(f"\nSUCCESS: Verified - Column type is now {row[1]} with max length {row[2]}")
                    return True
                else:
                    print("ERROR: Could not verify column change")
                    return False
            else:
                print("\nSUCCESS: Column is already VARCHAR/TEXT - no fix needed")
                return True
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    print("Checking crypto_amount column type...")
    success = check_and_fix_crypto_amount()
    sys.exit(0 if success else 1)
