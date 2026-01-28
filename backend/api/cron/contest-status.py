"""
Vercel Cron Job: Contest Status Updater
Runs every 5 minutes to update contest statuses
"""
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.services.contest_status import ContestStatusScheduler
import asyncio
import logging

logger = logging.getLogger(__name__)

def handler(request):
    """Vercel cron handler for contest status updates"""
    try:
        contest_scheduler = ContestStatusScheduler()
        db = SessionLocal()
        try:
            # Run contest status checks asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(contest_scheduler._check_contests())
        except Exception as e:
            logger.error(f"Error in contest status cron job: {e}", exc_info=True)
            return {
                "statusCode": 500,
                "body": f"Error: {str(e)}"
            }
        finally:
            db.close()
            if 'loop' in locals():
                loop.close()
        
        return {
            "statusCode": 200,
            "body": "Contest status cron job executed successfully"
        }
    except Exception as e:
        logger.error(f"Cron job error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }
