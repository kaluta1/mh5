"""
Vercel Cron Jobs for Background Tasks
These functions are called by Vercel Cron to handle scheduled tasks
"""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.payment_scheduler import PaymentScheduler
from app.services.contest_status import ContestStatusScheduler
from app.services.season_migration_scheduler import SeasonMigrationScheduler
import logging

logger = logging.getLogger(__name__)

def handler(request):
    """Vercel cron handler"""
    try:
        # Run payment checks
        payment_scheduler = PaymentScheduler()
        db = SessionLocal()
        try:
            # Check pending payments
            import asyncio
            asyncio.run(payment_scheduler._check_pending_payments())
        finally:
            db.close()
        
        return {
            "statusCode": 200,
            "body": "Cron job executed successfully"
        }
    except Exception as e:
        logger.error(f"Cron job error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }
