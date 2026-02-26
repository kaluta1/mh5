import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()

try:
    print("Truncating contestants table and cascading to all dependent records...")
    db.execute(text("TRUNCATE TABLE contestants CASCADE"))
    db.commit()
    print("Success: Truncated contestants table. All participations deleted.")
except Exception as e:
    db.rollback()
    print(f"Error truncating table: {e}")
finally:
    db.close()
