
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
            print("\n=== DEBUGGING CONTESTANT FILTER ===")
            
            # 1. Get all unique countries in users and contestants
            print("\n[1] Distinct Countries in DB:")
            user_countries = conn.execute(text("SELECT DISTINCT country FROM users WHERE country IS NOT NULL")).fetchall()
            contestant_countries = conn.execute(text("SELECT DISTINCT country FROM contestants WHERE country IS NOT NULL")).fetchall()
            print(f"Users: {[r[0] for r in user_countries]}")
            print(f"Contestants: {[r[0] for r in contestant_countries]}")

            # 2. detailed dump of first 20 contestants
            print("\n[2] Detailed Contestant Dump (Limit 20):")
            query = text("""
                SELECT 
                    c.id, 
                    c.title,
                    c.country as c_country, 
                    u.country as u_country, 
                    c.season_id, 
                    c.is_qualified,
                    c.is_deleted,
                    c.user_id
                FROM contestants c 
                LEFT JOIN users u ON c.user_id = u.id 
                LIMIT 20
            """)
            rows = conn.execute(query).fetchall()
            for r in rows:
                print(f"ID={r[0]} | Title='{r[1]}' | C.Country='{r[2]}' | U.Country='{r[3]}' | Season={r[4]} | Qual={r[5]} | Del={r[6]}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_countries()
