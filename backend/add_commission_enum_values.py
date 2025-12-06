"""
Script to add new CommissionType enum values to PostgreSQL database
Run this script directly: python add_commission_enum_values.py
"""
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.core.config import settings

def add_enum_values():
    """Add KYC_PAYMENT and EFM_MEMBERSHIP to commissiontype enum"""
    
    database_url = settings.SQLALCHEMY_DATABASE_URI
    if not database_url:
        print("ERROR: DATABASE_URL not found")
        return False
    
    print(f"Connecting to database...")
    engine = create_engine(str(database_url))
    
    try:
        with engine.connect() as conn:
            # Check if the enum type exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'commissiontype'
                )
            """))
            enum_exists = result.scalar()
            
            if not enum_exists:
                print("commissiontype enum does not exist yet. It will be created when the table is first used.")
                return True
            
            # Check existing values
            result = conn.execute(text("""
                SELECT enumlabel FROM pg_enum 
                WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'commissiontype')
            """))
            existing_values = [row[0] for row in result.fetchall()]
            print(f"Existing enum values: {existing_values}")
            
            # Add KYC_PAYMENT if not exists (uppercase to match existing pattern)
            if 'KYC_PAYMENT' not in existing_values:
                conn.execute(text("ALTER TYPE commissiontype ADD VALUE 'KYC_PAYMENT'"))
                print("Added 'KYC_PAYMENT' to commissiontype enum")
            else:
                print("'KYC_PAYMENT' already exists in commissiontype enum")
            
            # Add EFM_MEMBERSHIP if not exists (uppercase to match existing pattern)
            if 'EFM_MEMBERSHIP' not in existing_values:
                conn.execute(text("ALTER TYPE commissiontype ADD VALUE 'EFM_MEMBERSHIP'"))
                print("Added 'EFM_MEMBERSHIP' to commissiontype enum")
            else:
                print("'EFM_MEMBERSHIP' already exists in commissiontype enum")
            
            conn.commit()
            print("Successfully updated commissiontype enum!")
            
            # Also check CommissionStatus enum
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'commissionstatus'
                )
            """))
            status_enum_exists = result.scalar()
            
            if status_enum_exists:
                result = conn.execute(text("""
                    SELECT enumlabel FROM pg_enum 
                    WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'commissionstatus')
                """))
                status_values = [row[0] for row in result.fetchall()]
                print(f"Existing commissionstatus enum values: {status_values}")
                
                # Check if we need to add uppercase versions
                for status in ['PENDING', 'APPROVED', 'PAID', 'CANCELLED']:
                    if status not in status_values:
                        conn.execute(text(f"ALTER TYPE commissionstatus ADD VALUE '{status}'"))
                        print(f"Added '{status}' to commissionstatus enum")
                
                conn.commit()
            
            return True
            
    except Exception as e:
        print(f"Error updating enum: {e}")
        return False

if __name__ == "__main__":
    success = add_enum_values()
    sys.exit(0 if success else 1)
