
from app.db.session import engine
from sqlalchemy import text
import sys
import os

# Ensure backend is in path if running from root
sys.path.append(os.path.join(os.getcwd(), 'backend'))

def debug_countries():
    print("Connecting...")
    with engine.connect() as conn:
        try:
            print("--- Distinct Contestant Countries ---")
            countries = conn.execute(text("SELECT DISTINCT country FROM contestants")).fetchall()
            print([c[0] for c in countries])
            
            print("\n--- Contestants with User Data (Sample) ---")
            # Join with users to see if there's a mismatch
            query = text("""
                SELECT c.id, c.country as c_country, u.country as u_country, u.id 
                FROM contestants c 
                JOIN users u ON c.user_id = u.id 
                WHERE c.country IS NOT NULL 
                LIMIT 5
            """)
            data = conn.execute(query).fetchall()
            for row in data:
                print(f"Contestant {row[0]}: Ctag='{row[1]}', User='{row[2]}'")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_countries()
