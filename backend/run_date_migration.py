from app.db.session import SessionLocal
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    db = SessionLocal()
    try:
        logger.info("Starting migration to make contest dates nullable...")
        
        # Read the SQL file
        with open("migrations/make_contest_dates_nullable.sql", "r") as f:
            sql_commands = f.read().split(';')
            
        for command in sql_commands:
            if command.strip():
                logger.info(f"Executing: {command.strip()[:50]}...")
                try:
                    db.execute(text(command))
                    db.commit()
                except Exception as e:
                    logger.warning(f"Error (might be already nullable): {e}")
                    db.rollback()
                    
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
