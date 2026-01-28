"""
Vercel Cron Job: Payment Status Checker
Runs every 2 minutes to check pending payments
"""
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.services.payment_scheduler import PaymentScheduler
import asyncio
import logging

logger = logging.getLogger(__name__)

def handler(request):
    """Vercel cron handler for payment checks"""
    try:
        payment_scheduler = PaymentScheduler()
        db = SessionLocal()
        try:
            # Run payment checks asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(payment_scheduler._check_pending_payments())
        except Exception as e:
            logger.error(f"Error in payment cron job: {e}", exc_info=True)
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
            "body": "Payment cron job executed successfully"
        }
    except Exception as e:
        logger.error(f"Cron job error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }
