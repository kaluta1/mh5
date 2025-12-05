"""
Simple script to add is_deleted column to comment table
"""
import sys
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from sqlalchemy import text

def main():
    db = SessionLocal()
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='comment' AND column_name='is_deleted'
        """))
        
        if result.fetchone():
            print("✓ Column 'is_deleted' already exists")
            return True
        
        # Add the column
        db.execute(text("""
            ALTER TABLE comment ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false
        """))
        db.commit()
        print("✓ Successfully added 'is_deleted' column to comment table")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
