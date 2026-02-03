import logging
import sys
from sqlalchemy import text

# Add parent directory to path to allow importing app modules
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_schema():
    logger.info("Starting schema fix for 'contest' table...")
    
    conn = engine.connect()
    try:
        # List of columns to check and add if missing
        # Format: (column_name, data_type, default_value)
        columns_to_add = [
            # Dates
            ("submission_start_date", "DATE", None),
            ("submission_end_date", "DATE", None),
            ("voting_start_date", "DATE", None),
            ("voting_end_date", "DATE", None),
            
            # Season dates
            ("city_season_start_date", "DATE", None),
            ("city_season_end_date", "DATE", None),
            ("country_season_start_date", "DATE", None),
            ("country_season_end_date", "DATE", None),
            ("regional_start_date", "DATE", None),
            ("regional_end_date", "DATE", None),
            ("continental_start_date", "DATE", None),
            ("continental_end_date", "DATE", None),
            ("global_start_date", "DATE", None),
            ("global_end_date", "DATE", None),
            
            # Verification flags
            ("requires_visual_verification", "BOOLEAN", "FALSE"),
            ("requires_voice_verification", "BOOLEAN", "FALSE"),
            ("requires_brand_verification", "BOOLEAN", "FALSE"),
            ("requires_content_verification", "BOOLEAN", "FALSE"),
            ("requires_video", "BOOLEAN", "FALSE"),
            
            # Age restrictions
            ("min_age", "INTEGER", None),
            ("max_age", "INTEGER", None),
            
            # Media configuration
            ("max_videos", "INTEGER", "1"),
            ("video_max_duration", "INTEGER", "3000"),
            ("video_max_size_mb", "INTEGER", "500"),
            ("min_images", "INTEGER", "0"),
            ("max_images", "INTEGER", "10"),
            ("verification_video_max_duration", "INTEGER", "30"),
            ("verification_max_size_mb", "INTEGER", "50"),
            
            # Other
            ("participant_count", "INTEGER", "0"),
            ("is_deleted", "BOOLEAN", "FALSE"),
            
            # Text/Enum fields (using text/varchar to be safe)
            ("participant_type", "VARCHAR(50)", "'individual'"),
            ("verification_type", "VARCHAR(50)", "'none'"),
        ]
        
        # Begin transaction
        trans = conn.begin()
        
        for col_name, col_type, default_val in columns_to_add:
            try:
                # Check if column exists
                check_query = text(f"SELECT column_name FROM information_schema.columns WHERE table_name='contest' AND column_name='{col_name}'")
                result = conn.execute(check_query)
                if not result.fetchone():
                    logger.info(f"Adding missing column: {col_name}")
                    
                    # Construct ALTER TABLE query
                    alter_query = f"ALTER TABLE contest ADD COLUMN {col_name} {col_type}"
                    if default_val is not None:
                        alter_query += f" DEFAULT {default_val}"
                    
                    conn.execute(text(alter_query))
                else:
                    logger.info(f"Column already exists: {col_name}")
            except Exception as col_err:
                logger.error(f"Error checking/adding column {col_name}: {col_err}")
                # Don't fail the whole script for one column
        
        trans.commit()
        logger.info("Schema fix completed successfully.")
        
    except Exception as e:
        logger.error(f"Critical error during schema fix: {e}")
        try:
            trans.rollback()
        except:
            pass
    finally:
        conn.close()

if __name__ == "__main__":
    fix_schema()
