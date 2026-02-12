
import sys
import os

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.session import engine
from sqlalchemy import text

def check_data():
    with engine.connect() as conn:
        print("\n=== DATA CHECK ===")
        
        # Check Country Formatting
        countries = conn.execute(text("SELECT DISTINCT country FROM contestants WHERE country IS NOT NULL")).fetchall()
        print(f"Contestant Countries: {[c[0] for c in countries]}")
        
        user_countries = conn.execute(text("SELECT DISTINCT country FROM users WHERE country IS NOT NULL")).fetchall()
        print(f"User Countries: {[c[0] for c in user_countries]}")

        # Check a few random contestants
        rows = conn.execute(text("SELECT c.id, c.country, u.country FROM contestants c JOIN users u ON c.user_id = u.id LIMIT 5")).fetchall()
        for r in rows:
            print(f"C: {r[1]} | U: {r[2]}")

if __name__ == "__main__":
    check_data()
