
import sys
import os
import logging
from datetime import datetime, date
from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.round import Round, RoundStatus
from app.schemas.round import RoundCreate
from app.crud.crud_round import round as crud_round

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_migration():
    db = SessionLocal()
    try:
        # 1. Read SQL file
        sql_path = r"C:\Users\godso\.gemini\antigravity\brain\0f7ecbac-30ea-4808-a8a7-1cbf8627653f\migration_round.sql"
        if not os.path.exists(sql_path):
            logger.error(f"SQL file not found at {sql_path}")
            return

        with open(sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        # Split SQL into parts (simple splitting by sections based on comments)
        # Or just execute blocks.
        # We need to execute creation commands first.
        
        # Part 1: Create Round Table
        logger.info("Executing Part 1: Create Round Table")
        db.execute(text("""
        CREATE TABLE IF NOT EXISTS rounds (
            id SERIAL PRIMARY KEY,
            contest_id INTEGER NOT NULL REFERENCES contest(id),
            name VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'upcoming',
            submission_start_date DATE,
            submission_end_date DATE,
            voting_start_date DATE,
            voting_end_date DATE,
            city_season_start_date DATE,
            city_season_end_date DATE,
            country_season_start_date DATE,
            country_season_end_date DATE,
            regional_start_date DATE,
            regional_end_date DATE,
            continental_start_date DATE,
            continental_end_date DATE,
            global_start_date DATE,
            global_end_date DATE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_rounds_contest_id ON rounds(contest_id);
        """))
        db.commit()

        # Part 2-4: Add Columns
        logger.info("Executing Parts 2-4: Add columns to other tables")
        db.execute(text("ALTER TABLE contestants ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_contestants_round_id ON contestants(round_id);"))
        
        db.execute(text("ALTER TABLE contest_seasons ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_contest_seasons_round_id ON contest_seasons(round_id);"))
        
        db.execute(text("ALTER TABLE contest_votes ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES rounds(id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_contest_votes_round_id ON contest_votes(round_id);"))
        db.commit()

        # Data Migration
        logger.info("Starting Data Migration: Moving dates from Contest to Round")
        
        # Query old dates using raw SQL
        result = db.execute(text("""
            SELECT id, name, 
                   submission_start_date, submission_end_date, 
                   voting_start_date, voting_end_date,
                   city_season_start_date, city_season_end_date,
                   country_season_start_date, country_season_end_date,
                   regional_start_date, regional_end_date,
                   continental_start_date, continental_end_date,
                   global_start_date, global_end_date
            FROM contest
            WHERE is_deleted = false
        """))
        
        contests = result.fetchall()
        logger.info(f"Found {len(contests)} contests to migrate")
        
        for c in contests:
            contest_id = c[0]
            contest_name = c[1]
            
            # Check if round already exists
            existing_round = db.execute(text("SELECT id FROM rounds WHERE contest_id = :cid"), {"cid": contest_id}).fetchone()
            if existing_round:
                logger.info(f"Contest {contest_id} already has a round. Skipping.")
                continue

            # Check if any dates exist
            has_dates = any([c[2], c[3], c[4], c[5]])
            if not has_dates:
                logger.info(f"Contest {contest_id} has no dates. Creating empty Round.")
            
            # Create Round
            # Determine name
            voting_start = c[4] # voting_start_date
            round_name = f"Round {voting_start.strftime('%B %Y')}" if voting_start else "Initial Round"
            
            # Build insert dict
            insert_query = text("""
                INSERT INTO rounds (
                    contest_id, name, status,
                    submission_start_date, submission_end_date,
                    voting_start_date, voting_end_date,
                    city_season_start_date, city_season_end_date,
                    country_season_start_date, country_season_end_date,
                    regional_start_date, regional_end_date,
                    continental_start_date, continental_end_date,
                    global_start_date, global_end_date
                ) VALUES (
                    :contest_id, :name, :status,
                    :submission_start, :submission_end,
                    :voting_start, :voting_end,
                    :city_start, :city_end,
                    :country_start, :country_end,
                    :regional_start, :regional_end,
                    :continental_start, :continental_end,
                    :global_start, :global_end
                ) RETURNING id
            """)
            
            params = {
                "contest_id": contest_id,
                "name": round_name,
                "status": "active", # Assume active or use logic
                "submission_start": c[2],
                "submission_end": c[3],
                "voting_start": c[4],
                "voting_end": c[5],
                "city_start": c[6],
                "city_end": c[7],
                "country_start": c[8],
                "country_end": c[9],
                "regional_start": c[10],
                "regional_end": c[11],
                "continental_start": c[12],
                "continental_end": c[13],
                "global_start": c[14],
                "global_end": c[15]
            }
            
            round_id_row = db.execute(insert_query, params).fetchone()
            round_id = round_id_row[0] if round_id_row else None
            
            # Update contestants to link to this round?
            # Existing contestants should probably belong to this round.
            if round_id:
                db.execute(text("UPDATE contestants SET round_id = :rid WHERE season_id = :cid"), {"rid": round_id, "cid": contest_id})
                db.execute(text("UPDATE contest_votes SET round_id = :rid WHERE contest_id = :cid"), {"rid": round_id, "cid": contest_id})
                logger.info(f"Migrated Contest {contest_id} -> Round {round_id}")
        
        db.commit()
        
        # Part 5: Cleanup
        logger.info("Executing Part 5: Cleanup - Dropping old columns")
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS submission_start_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS submission_end_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS voting_start_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS voting_end_date;"))
        
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS city_season_start_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS city_season_end_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS country_season_start_date;"))
        db.execute(text("ALTER TABLE contest DROP COLUMN IF EXISTS country_season_end_date;"))
        # (Add others if strictly following SQL file, but these are the main ones)
        
        # Drop others from SQL file
        columns_to_drop = [
            "regional_start_date", "regional_end_date",
            "continental_start_date", "continental_end_date",
            "global_start_date", "global_end_date"
        ]
        for col in columns_to_drop:
            db.execute(text(f"ALTER TABLE contest DROP COLUMN IF EXISTS {col};"))

        db.commit()
        logger.info("Migration completed successfully!")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    apply_migration()
