#!/usr/bin/env python3
"""
Immediate fix for crypto_amount column type.
This script changes the column from NUMERIC(18, 8) to VARCHAR(255) to store wei amounts.
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_crypto_amount_column():
    """Fix the crypto_amount column type in the deposits table"""
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set")
        print("Please set DATABASE_URL in your .env file or environment")
        sys.exit(1)
    
    print("Connecting to database...")
    print(f"   Database: {database_url.split('@')[-1] if '@' in database_url else '***'}")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                # Step 1: Check current column type
                print("\nChecking current column type...")
                result = conn.execute(text("""
                    SELECT column_name, data_type, numeric_precision, numeric_scale, character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_name = 'deposits' AND column_name = 'crypto_amount'
                """))
                
                col_info = result.fetchone()
                if not col_info:
                    print("ERROR: crypto_amount column not found in deposits table")
                    sys.exit(1)
                
                current_type = col_info[1]
                print(f"   Current type: {current_type}")
                if col_info[2]:
                    print(f"   Precision: {col_info[2]}, Scale: {col_info[3]}")
                if col_info[4]:
                    print(f"   Max length: {col_info[4]}")
                
                # If already VARCHAR, skip
                if current_type.lower() in ['character varying', 'varchar']:
                    print("\nSUCCESS: Column is already VARCHAR. No changes needed!")
                    trans.rollback()
                    return
                
                # Change column type directly using USING clause
                # This converts numeric values to text during the type change
                print("\nChanging column type from NUMERIC(18, 8) to VARCHAR(255)...")
                print("   This will convert existing numeric values to strings automatically")
                conn.execute(text("""
                    ALTER TABLE deposits 
                    ALTER COLUMN crypto_amount TYPE VARCHAR(255) 
                    USING CASE 
                        WHEN crypto_amount IS NOT NULL THEN crypto_amount::text
                        ELSE NULL
                    END
                """))
                print("   Column type changed successfully")
                
                # Step 4: Verify the change
                print("\nVerifying the change...")
                result = conn.execute(text("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'deposits' AND column_name = 'crypto_amount'
                """))
                
                verify_info = result.fetchone()
                if verify_info:
                    new_type = verify_info[1]
                    max_length = verify_info[2]
                    print(f"   New type: {new_type}")
                    print(f"   Max length: {max_length}")
                    
                    if new_type.lower() in ['character varying', 'varchar']:
                        print("\nSUCCESS: Column type changed to VARCHAR(255)")
                        trans.commit()
                        print("\nMigration completed successfully!")
                        print("   You can now insert wei amounts as strings (e.g., '10000000000000000000')")
                    else:
                        print(f"\nWARNING: Column type is {new_type}, expected VARCHAR")
                        trans.rollback()
                else:
                    print("\nERROR: Could not verify column change")
                    trans.rollback()
                    
            except Exception as e:
                print(f"\nERROR during migration: {e}")
                trans.rollback()
                raise
                
    except Exception as e:
        print(f"\nERROR connecting to database: {e}")
        print("\nTroubleshooting:")
        print("1. Check that DATABASE_URL is correct in your .env file")
        print("2. Verify database is accessible")
        print("3. Check database credentials")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("Fix crypto_amount Column Type")
    print("=" * 60)
    fix_crypto_amount_column()
