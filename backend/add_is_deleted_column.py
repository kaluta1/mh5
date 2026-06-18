#!/usr/bin/env python
"""Add is_deleted column to comment table"""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@localhost/myhigh5":
    print("DATABASE_URL not set in backend/.env")
    sys.exit(1)

print(f"Connecting to database: {DATABASE_URL}")

try:
    # Create engine
    engine = create_engine(DATABASE_URL)
    
    # Execute the ALTER TABLE command
    with engine.begin() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='comment' AND column_name='is_deleted'
        """))
        
        if result.fetchone():
            print("Column 'is_deleted' already exists in 'comment' table")
        else:
            # Add the column
            conn.execute(text("""
                ALTER TABLE comment ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false
            """))
            print("Successfully added 'is_deleted' column to 'comment' table")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Done!")
